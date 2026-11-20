"""vzdump-compatible backups backed by Incus instance exports.

Archives are written to <backup_dir>/dump/vzdump-<type>-<vmid>-<date>.tar.<ext>
and exposed as the Proxmox storage "backups" (volid "backups:backup/<file>"),
so the panel and the async runner can list, verify, delete and restore them.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from typing import Any, Dict, List, Optional

from .incus import IncusClient, IncusError
from .instances import InstanceService, pve_type
from .tasks import Task, TaskManager
from .util import PveError, now, parse_bool, parse_int

STORAGE = "backups"
ARCHIVE_RE = re.compile(r"^vzdump-(qemu|lxc)-(\d+)-(\d{4}_\d{2}_\d{2}-\d{2}_\d{2}_\d{2})\.tar(?:\.(zst|gz|xz))?$")
COMPRESSION = {"zstd": ("zstd", ".zst"), "1": ("zstd", ".zst"), "gzip": ("gzip", ".gz"), "lzo": ("zstd", ".zst"), "0": ("none", ""), "": ("zstd", ".zst")}


def _human(num: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if num < 1024 or unit == "TiB":
            return "%.2f %s" % (num, unit)
        num /= 1024.0
    return "%d B" % num


class BackupService:
    def __init__(self, cfg: Any, incus: IncusClient, tasks: TaskManager, instances: InstanceService):
        self.cfg = cfg
        self.incus = incus
        self.tasks = tasks
        self.instances = instances
        self.dump_dir = os.path.join(str(cfg["backup_dir"]), "dump")
        os.makedirs(self.dump_dir, exist_ok=True)

    # ----------------------------------------------------------- storage
    def storage_entry(self) -> Dict[str, Any]:
        try:
            vfs = os.statvfs(self.dump_dir)
            total = vfs.f_blocks * vfs.f_frsize
            avail = vfs.f_bavail * vfs.f_frsize
        except OSError:
            total = avail = 0
        used = sum(item["size"] for item in self.list())
        return {
            "storage": STORAGE, "type": "dir", "content": "backup", "active": 1, "enabled": 1, "shared": 0,
            "total": total, "used": used, "avail": avail, "used_fraction": (used / total) if total else 0,
            "path": self.dump_dir,
        }

    def volid(self, filename: str) -> str:
        return "%s:backup/%s" % (STORAGE, filename)

    def path_for_volid(self, volid: str) -> str:
        text = str(volid or "")
        if ":" in text:
            storage, _, rest = text.partition(":")
            if storage != STORAGE:
                raise PveError(500, "storage '%s' does not exist" % storage)
        else:
            rest = text
        filename = rest.split("/")[-1]
        if not ARCHIVE_RE.match(filename):
            raise PveError(500, "unable to parse volume ID '%s'" % volid)
        return os.path.join(self.dump_dir, filename)

    def list(self, vmid: Optional[int] = None) -> List[Dict[str, Any]]:
        items = []
        try:
            names = os.listdir(self.dump_dir)
        except OSError:
            return []
        for filename in names:
            match = ARCHIVE_RE.match(filename)
            if not match:
                continue
            item_vmid = int(match.group(2))
            if vmid is not None and item_vmid != vmid:
                continue
            path = os.path.join(self.dump_dir, filename)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            ctime = int(datetime.datetime.strptime(match.group(3), "%Y_%m_%d-%H_%M_%S")
                        .replace(tzinfo=datetime.timezone.utc).timestamp())
            ext = match.group(4)
            items.append({
                "volid": self.volid(filename), "content": "backup", "vmid": item_vmid,
                "format": "tar.%s" % ext if ext else "tar", "size": stat.st_size, "ctime": ctime,
                "subtype": match.group(1), "notes": "OrveX backup of VM %d" % item_vmid,
            })
        return sorted(items, key=lambda i: i["ctime"], reverse=True)

    def delete_volume(self, volid: str) -> None:
        path = self.path_for_volid(volid)
        try:
            os.unlink(path)
        except FileNotFoundError:
            raise PveError(500, "volume '%s' does not exist" % volid)

    # ------------------------------------------------------------ backup
    def vzdump(self, params: Dict[str, Any], user: str) -> str:
        raw_ids = str(params.get("vmid") or "").replace(";", ",")
        vmids = [parse_int(v) for v in raw_ids.split(",") if v.strip()]
        vmids = [v for v in vmids if v]
        if not vmids:
            raise PveError(400, "Parameter verification failed.", {"vmid": "property is missing"})
        for vmid in vmids:
            self.instances.get(vmid)
        algorithm, ext = COMPRESSION.get(str(params.get("compress", "zstd")).lower(), COMPRESSION["zstd"])

        def work(task: Task) -> None:
            for vmid in vmids:
                self._backup_one(task, vmid, algorithm, ext)

        return self.tasks.start("vzdump", vmids[0] if len(vmids) == 1 else "", user, work)

    def _backup_one(self, task: Task, vmid: int, algorithm: str, ext: str) -> None:
        inst = self.instances.get(vmid)
        vm_type = pve_type(inst)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y_%m_%d-%H_%M_%S")
        filename = "vzdump-%s-%d-%s.tar%s" % (vm_type, vmid, stamp, ext)
        path = os.path.join(self.dump_dir, filename)
        backup_name = "orvex-%d" % now()
        task.log("INFO: Starting Backup of VM %d (%s)" % (vmid, vm_type))
        task.log("INFO: creating vzdump archive '%s'" % path)
        try:
            self.incus.create_backup(inst["name"], backup_name, algorithm)
            tmp = path + ".tmp"
            with open(tmp, "wb") as handle:
                size = self.incus.export_backup(inst["name"], backup_name, handle)
            os.replace(tmp, path)
        except IncusError as exc:
            raise PveError(500, "backup of VM %d failed: %s" % (vmid, exc.message))
        finally:
            try:
                self.incus.delete_backup(inst["name"], backup_name)
            except IncusError:
                pass
            if os.path.exists(path + ".tmp"):
                try:
                    os.unlink(path + ".tmp")
                except OSError:
                    pass
        task.log("INFO: archive file size: %s" % _human(size))
        task.log("INFO: Finished Backup of VM %d" % vmid)

    # ----------------------------------------------------------- restore
    def restore(self, vm_type: str, params: Dict[str, Any], user: str) -> str:
        vmid = parse_int(params.get("vmid"))
        archive = params.get("archive") if vm_type == "qemu" else params.get("ostemplate")
        if not vmid or not archive:
            raise PveError(400, "Parameter verification failed.", {"vmid" if not vmid else "archive": "property is missing"})
        path = self.path_for_volid(str(archive))
        match = ARCHIVE_RE.match(os.path.basename(path))
        if not match or match.group(1) != vm_type:
            raise PveError(500, "archive '%s' is not a %s backup" % (archive, "KVM" if vm_type == "qemu" else "container"))
        if not os.path.exists(path):
            raise PveError(500, "volume '%s' does not exist" % archive)
        force = parse_bool(params.get("force"))
        pool = self.instances.pool_for(params.get("storage"))
        name = self.instances.name_for(vmid)

        def work(task: Task) -> None:
            with self.instances.vm_lock(vmid):
                if self.instances.exists(vmid):
                    if not force:
                        raise PveError(500, "unable to restore VM %d - VM already exists" % vmid)
                    inst = self.incus.instance(name)
                    if inst.get("status") in ("Running", "Frozen"):
                        self.incus.set_state(name, "stop", timeout=30, force=True)
                    task.log("removing existing VM %d" % vmid)
                    self.incus.delete_instance(name)
                task.log("restoring '%s' to VM %d" % (archive, vmid))
                try:
                    with open(path, "rb") as handle:
                        self.incus.import_backup(name, pool, handle, os.path.getsize(path))
                except IncusError as exc:
                    raise PveError(500, "restore failed: %s" % exc.message)
                inst = self.incus.instance(name)
                config = dict(inst.get("config") or {})
                config["user.orvex.vmid"] = str(vmid)
                display = parse_int(config.get("user.orvex.vnc_display"))
                if display is not None:
                    clash = [i for i in self.instances.managed()
                             if i["_vmid"] != vmid and parse_int((i.get("config") or {}).get("user.orvex.vnc_display")) == display]
                    if clash:
                        new_display = self.instances.allocate_vnc_display()
                        config["raw.qemu"] = "-vnc 127.0.0.1:%d" % new_display
                        config["user.orvex.vnc_display"] = str(new_display)
                pve = json.loads(config.get("user.orvex.pve") or "{}")
                config["user.orvex.pve"] = json.dumps(pve, sort_keys=True)
                inst["config"] = config
                self.incus.put_instance(name, inst)
                task.log("restore finished")
            self.instances.sync_forwards()

        return self.tasks.start("qmrestore" if vm_type == "qemu" else "vzrestore", vmid, user, work)
