"""Instances (KVM VMs and LXC containers) exposed as Proxmox guests.

Every guest is an Incus instance named ``vps<vmid>``. Its Proxmox-style
configuration (what the panel reads and writes through /config) is stored in
the instance config key ``user.orvex.pve`` and translated into Incus limits,
NIC devices and cloud-init documents by :meth:`InstanceService.apply`.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import threading
import time
import urllib.parse
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import cloudinit, pveconfig
from .incus import IncusClient, IncusError
from .network import NetworkManager, root_size_bytes
from .store import Store
from .tasks import Task, TaskManager
from .util import (
    GIB, LOG, MIB, PveError, format_size, hash_password, is_relative_size, now, parse_bool, parse_int,
    parse_size, random_mac, sanitize_hostname,
)

NAME_PREFIX = "vps"
QEMU_DISK_KEYS = ("scsi0", "virtio0", "sata0", "ide0")
SNAPSHOT_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-]{1,39}$")
USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_.-]{0,31}$")
CONFIG_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
INT_KEYS = {"memory", "cores", "sockets", "swap", "onboot", "balloon", "cpuunits", "vmid", "template", "unprivileged", "cpulimit"}
RUNNING_STATES = ("Running", "Frozen")


def pve_type(inst: Dict[str, Any]) -> str:
    return "qemu" if inst.get("type") == "virtual-machine" else "lxc"


def parse_time(value: Any) -> int:
    """RFC3339 timestamp (with optional nanoseconds) to a unix timestamp."""
    if not value or not isinstance(value, str):
        return 0
    match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})?$", value.strip())
    if not match:
        return 0
    try:
        stamp = datetime.datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return 0
    offset = match.group(2) or "Z"
    delta = datetime.timedelta(0)
    if offset != "Z":
        sign = 1 if offset[0] == "+" else -1
        hours, minutes = offset[1:].split(":")
        delta = sign * datetime.timedelta(hours=int(hours), minutes=int(minutes))
    stamp = stamp.replace(tzinfo=datetime.timezone.utc) - delta
    if stamp.year < 2000:  # Incus uses year 1 for "never"
        return 0
    return int(stamp.timestamp())


def incus_size(num_bytes: int) -> str:
    if num_bytes % GIB == 0:
        return "%dGiB" % (num_bytes // GIB)
    return "%dMiB" % max(1, num_bytes // MIB)


class InstanceService:
    def __init__(
        self,
        cfg: Any,
        incus: IncusClient,
        tasks: TaskManager,
        store: Store,
        network: NetworkManager,
        templates: List[Dict[str, Any]],
    ):
        self.cfg = cfg
        self.incus = incus
        self.tasks = tasks
        self.store = store
        self.net = network
        self.templates: Dict[int, Dict[str, Any]] = {t["vmid"]: t for t in templates}
        self.metrics: Any = None  # set by the app (MetricsCollector)
        self._lock = threading.RLock()
        self._reserved: set = set()
        self._reserved_displays: set = set()
        self._vm_locks: Dict[int, threading.RLock] = {}

    # ------------------------------------------------------------ helpers
    @staticmethod
    def name_for(vmid: int) -> str:
        return "%s%d" % (NAME_PREFIX, int(vmid))

    def vm_lock(self, vmid: int) -> threading.RLock:
        with self._lock:
            lock = self._vm_locks.get(vmid)
            if lock is None:
                lock = self._vm_locks[vmid] = threading.RLock()
            return lock

    def _missing(self, vmid: int, vm_type: Optional[str]) -> PveError:
        folder = "lxc" if vm_type == "lxc" else "qemu-server"
        return PveError(500, "Configuration file 'nodes/%s/%s/%d.conf' does not exist" % (self.cfg.node_name, folder, vmid))

    @staticmethod
    def load_pve(inst: Dict[str, Any]) -> Dict[str, Any]:
        try:
            data = json.loads((inst.get("config") or {}).get("user.orvex.pve") or "{}")
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    def managed(self, recursion: int = 1) -> List[Dict[str, Any]]:
        result = []
        for inst in self.incus.instances(recursion=recursion):
            vmid = parse_int((inst.get("config") or {}).get("user.orvex.vmid"))
            if vmid:
                inst["_vmid"] = vmid
                result.append(inst)
        return result

    def exists(self, vmid: int) -> bool:
        try:
            self.incus.instance(self.name_for(vmid))
            return True
        except IncusError as exc:
            if exc.not_found:
                return False
            raise PveError(500, exc.message)

    def get(self, vmid: int, vm_type: Optional[str] = None, recursion: int = 0) -> Dict[str, Any]:
        try:
            inst = self.incus.instance(self.name_for(vmid), recursion)
        except IncusError as exc:
            if exc.not_found:
                raise self._missing(vmid, vm_type)
            raise PveError(500, exc.message)
        if vm_type and pve_type(inst) != vm_type:
            raise self._missing(vmid, vm_type)
        return inst

    def pool_for(self, storage: Any) -> str:
        """Map a Proxmox storage name to an Incus storage pool."""
        wanted = str(storage or "").strip()
        if wanted:
            try:
                names = {str(p.get("name")) for p in self.incus.pools()}
            except IncusError:
                names = set()
            if wanted in names:
                return wanted
        return str(self.cfg["storage_pool"])

    @staticmethod
    def disk_key(vm_type: str, pve: Dict[str, Any]) -> str:
        if vm_type == "lxc":
            return "rootfs"
        for key in QEMU_DISK_KEYS:
            if key in pve:
                return key
        return "scsi0"

    def credentials(self, vm_type: str, pve: Dict[str, Any], inst: Optional[Dict[str, Any]] = None) -> Tuple[str, Optional[str]]:
        if vm_type == "lxc":
            return "root", pve.get("orvex_password")
        user = str(pve.get("ciuser") or "").strip()
        if not user and inst is not None:
            tpl = self.templates.get(parse_int((inst.get("config") or {}).get("user.orvex.template"), 0) or 0)
            user = (tpl or {}).get("default_user") or "root"
        return user or "root", pve.get("cipassword")

    def sync_forwards(self) -> None:
        try:
            entries: List[Tuple[int, str]] = []
            for inst in self.managed():
                plans, _ = self.net.plan(pve_type(inst), self.load_pve(inst))
                entries.extend((inst["_vmid"], p.ip) for p in plans if p.mode == "nat" and p.ip)
            self.net.sync_forwards(entries)
        except (IncusError, PveError) as exc:
            LOG.error("NAT forward sync failed: %s", getattr(exc, "message", exc))

    # ----------------------------------------------------------- listing
    def template_resources(self) -> List[Dict[str, Any]]:
        out = []
        for tpl in self.templates.values():
            out.append({
                "id": "%s/%d" % (tpl["type"], tpl["vmid"]), "type": tpl["type"], "vmid": tpl["vmid"],
                "name": tpl["name"], "node": self.cfg.node_name, "status": "stopped", "template": 1,
                "maxcpu": 1, "cpu": 0, "maxmem": 512 * MIB, "mem": 0, "maxdisk": tpl["disk_gb"] * GIB, "disk": 0,
                "uptime": 0, "netin": 0, "netout": 0, "diskread": 0, "diskwrite": 0,
                "tags": "orvex-template", "description": tpl["description"],
            })
        return out

    def vm_resources(self) -> List[Dict[str, Any]]:
        out = []
        for inst in self.managed():
            vmid = inst["_vmid"]
            vm_type = pve_type(inst)
            pve = self.load_pve(inst)
            cur = self.metrics.current(vmid) if self.metrics else {}
            running = inst.get("status") in RUNNING_STATES
            out.append({
                "id": "%s/%d" % (vm_type, vmid), "type": vm_type, "vmid": vmid,
                "name": pve.get("name") or pve.get("hostname") or self.name_for(vmid),
                "node": self.cfg.node_name, "status": "running" if running else "stopped", "template": 0,
                "maxcpu": parse_int((inst.get("config") or {}).get("limits.cpu"), 1),
                "cpu": cur.get("cpu", 0.0) if running else 0,
                "maxmem": parse_size((inst.get("config") or {}).get("limits.memory"), "") or 0,
                "mem": cur.get("mem", 0) if running else 0,
                "maxdisk": root_size_bytes(inst.get("devices") or {}), "disk": cur.get("disk", 0),
                "uptime": cur.get("uptime", 0) if running else 0,
                "netin": cur.get("netin", 0), "netout": cur.get("netout", 0),
                "diskread": cur.get("diskread", 0), "diskwrite": cur.get("diskwrite", 0),
                "tags": pve.get("tags", ""),
            })
        return out

    def next_id(self, minimum: Optional[int]) -> int:
        used = {inst["_vmid"] for inst in self.managed()} | set(self.templates) | set(self._reserved)
        candidate = max(int(minimum or 0), int(self.cfg["vmid_min"]))
        while candidate in used:
            candidate += 1
        return candidate

    def list_guests(self, vm_type: str) -> List[Dict[str, Any]]:
        return [r for r in self.template_resources() + self.vm_resources() if r["type"] == vm_type]

    # ------------------------------------------------------------- clone
    def allocate_vnc_display(self) -> int:
        with self._lock:
            used = set(self._reserved_displays)
            for inst in self.managed():
                display = parse_int((inst.get("config") or {}).get("user.orvex.vnc_display"))
                if display is not None:
                    used.add(display)
            display = int(self.cfg["vnc_display_base"])
            while display in used:
                display += 1
            self._reserved_displays.add(display)
            return display

    def image_source(self, tpl: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if self.incus.image_alias_exists(tpl["local_alias"]):
                return {"type": "image", "alias": tpl["local_alias"]}
        except IncusError as exc:
            LOG.warning("could not check local image alias %s: %s", tpl["local_alias"], exc)
        return {
            "type": "image", "mode": "pull", "server": tpl["server"],
            "protocol": tpl["protocol"], "alias": tpl["image"],
        }

    def template_pve(self, tpl: Dict[str, Any], vmid: int, hostname: str, pool: str, pending: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        mac = random_mac()
        size = format_size(int(tpl["disk_gb"]) * GIB)
        if tpl["type"] == "qemu":
            pve: Dict[str, Any] = {
                "name": hostname, "memory": 512, "sockets": 1, "cores": 1, "cpu": "host", "ostype": "l26",
                "agent": "1", "scsihw": "virtio-scsi-single",
                "scsi0": "%s:vm-%d-disk-0,size=%s" % (pool, vmid, size),
                "ide2": "%s:vm-%d-cloudinit,media=cdrom" % (pool, vmid),
                "boot": "order=scsi0", "net0": pveconfig.format_qemu_net("virtio", mac, "auto"),
                "ciuser": tpl["default_user"], "onboot": 0,
                "smbios1": "uuid=%s" % uuid.uuid4(), "vmgenid": str(uuid.uuid4()),
            }
            if pending:
                pve["ciuser"] = pending.get("username") or pve["ciuser"]
                pve["cipassword"] = pending.get("password_hash")
        else:
            distro = tpl["image"].split("/")[0]
            pve = {
                "hostname": hostname, "memory": 512, "swap": 512, "cores": 1, "ostype": distro, "arch": "amd64",
                "rootfs": "%s:subvol-%d-disk-0,size=%s" % (pool, vmid, size),
                "net0": pveconfig.format_lxc_net("eth0", "auto", mac, None, None),
                "unprivileged": 1, "features": "nesting=1", "onboot": 0,
            }
            if pending and pending.get("password_hash"):
                pve["orvex_password"] = pending["password_hash"]
        return pve

    def clone(self, template_vmid: int, vm_type: str, params: Dict[str, Any], user: str) -> str:
        tpl = self.templates.get(int(template_vmid))
        if tpl is None or tpl["type"] != vm_type:
            raise self._missing(int(template_vmid), vm_type)
        newid = parse_int(params.get("newid"))
        if not newid or newid < 100:
            raise PveError(400, "Parameter verification failed.", {"newid": "value must be an integer >= 100"})
        hostname = sanitize_hostname(
            params.get("name") if vm_type == "qemu" else params.get("hostname"), self.name_for(newid)
        )
        with self._lock:
            if newid in self.templates or newid in self._reserved or self.exists(newid):
                raise PveError(500, "unable to create VM %d: config file already exists" % newid)
            self._reserved.add(newid)
        try:
            pool = self.pool_for(params.get("storage"))
            pending = self.store.pop_pending_credentials(newid)
            pve = self.template_pve(tpl, newid, hostname, pool, pending)
            display = self.allocate_vnc_display() if vm_type == "qemu" and parse_bool(self.cfg["vnc_enabled"], True) else None
        except BaseException:
            with self._lock:
                self._reserved.discard(newid)
            raise

        def work(task: Task) -> None:
            try:
                task.log("create full clone of template %d (%s) to VM %d" % (tpl["vmid"], tpl["description"], newid))
                source = self.image_source(tpl)
                task.log("image: %s %s" % (source.get("server", "local"), source["alias"]))
                config: Dict[str, str] = {
                    "limits.cpu": "1", "limits.memory": "512MiB", "boot.autostart": "false",
                    "user.orvex.vmid": str(newid), "user.orvex.template": str(tpl["vmid"]),
                    "user.orvex.pve": json.dumps(pve, sort_keys=True), "user.orvex.created": str(now()),
                }
                if vm_type == "qemu":
                    config["security.secureboot"] = "false"
                    if display is not None:
                        config["raw.qemu"] = "-vnc 127.0.0.1:%d" % display
                        config["user.orvex.vnc_display"] = str(display)
                else:
                    config["security.nesting"] = "true"
                payload = {
                    "name": self.name_for(newid),
                    "type": "virtual-machine" if vm_type == "qemu" else "container",
                    "source": source,
                    "config": config,
                    "devices": {"root": {"type": "disk", "path": "/", "pool": pool, "size": "%dGiB" % int(tpl["disk_gb"])}},
                    "profiles": [],
                    "description": "OrveX VPS %d (%s)" % (newid, hostname),
                }
                try:
                    self.incus.create_instance(payload, timeout=3 * 3600)
                except IncusError as exc:
                    if vm_type == "lxc" and ("quota" in exc.message.lower() or "not supported" in exc.message.lower()):
                        task.log("WARN: storage pool cannot enforce a container disk size; creating without a size limit")
                        del payload["devices"]["root"]["size"]
                        self.incus.create_instance(payload, timeout=3 * 3600)
                    else:
                        raise PveError(500, "clone failed: %s" % exc.message)
                task.log("clone finished: %s" % self.name_for(newid))
            finally:
                with self._lock:
                    self._reserved.discard(newid)
                    if display is not None:
                        self._reserved_displays.discard(display)

        return self.tasks.start("qmclone" if vm_type == "qemu" else "vzclone", tpl["vmid"], user, work)

    # ------------------------------------------------------------ config
    def get_config(self, vmid: int, vm_type: str) -> Dict[str, Any]:
        inst = self.get(vmid, vm_type)
        pve = self.load_pve(inst)
        out: Dict[str, Any] = {}
        for key, value in pve.items():
            if key.startswith("orvex_"):
                continue
            if key == "cipassword":
                out[key] = "**********"
                continue
            if key in INT_KEYS and isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
                value = int(value)
            out[key] = value
        disk_key = self.disk_key(vm_type, pve)
        actual = root_size_bytes(inst.get("devices") or {})
        if actual and disk_key in pve:
            out[disk_key] = pveconfig.with_disk_size(pve[disk_key], actual)
        out["digest"] = hashlib.sha1(json.dumps(pve, sort_keys=True).encode()).hexdigest()
        return out

    def update_config(self, vmid: int, vm_type: str, params: Dict[str, Any]) -> None:
        with self.vm_lock(vmid):
            inst = self.get(vmid, vm_type)
            pve = self.load_pve(inst)
            params = dict(params)
            delete = params.pop("delete", None)
            for ignored in ("digest", "skiplock", "background_delay", "revert", "node", "vmid", "force"):
                params.pop(ignored, None)
            for key in re.split(r"[,;\s]+", str(delete or "")):
                if key:
                    pve.pop(key.strip(), None)
            for key, value in params.items():
                if not CONFIG_KEY_RE.match(str(key)) or key.startswith("orvex_"):
                    continue
                if value is None:
                    continue
                if isinstance(value, bool):
                    value = 1 if value else 0
                if key == "cipassword":
                    text = str(value)
                    pve[key] = text if text.startswith("$") else hash_password(text)
                    continue
                if key == "password" and vm_type == "lxc":  # root password (Proxmox create-time key)
                    pve["orvex_password"] = hash_password(str(value))
                    continue
                if key.startswith("net") and key[3:].isdigit():
                    value = self._keep_mac(vm_type, pve.get(key), str(value))
                pve[key] = value if isinstance(value, (int, float)) else str(value)
            self.apply(inst, pve)
        self.sync_forwards()

    @staticmethod
    def _keep_mac(vm_type: str, old: Any, new: str) -> str:
        """Reuse the existing MAC when the panel rewrites netX without one."""
        if not old:
            return new
        if vm_type == "qemu":
            old_net, new_net = pveconfig.parse_qemu_net(old), pveconfig.parse_qemu_net(new)
            if old_net.get("mac") and not new_net.get("mac"):
                return pveconfig.format_qemu_net(new_net["model"], old_net["mac"], new_net["bridge"] or old_net["bridge"], new_net["extra"])
            return new
        old_net, new_net = pveconfig.parse_lxc_net(old), pveconfig.parse_lxc_net(new)
        if old_net.get("mac") and not new_net.get("mac"):
            return pveconfig.format_lxc_net(
                new_net["name"] or old_net["name"] or "eth0", new_net["bridge"], old_net["mac"],
                new_net.get("ip"), new_net.get("gw"), new_net["extra"],
            )
        return new

    def apply(self, inst: Dict[str, Any], pve: Dict[str, Any], start_phase: bool = False) -> None:
        """Translate the Proxmox config into Incus config/devices and save it."""
        vm_type = pve_type(inst)
        vmid = parse_int((inst.get("config") or {}).get("user.orvex.vmid"), 0) or 0
        name = inst.get("name") or self.name_for(vmid)
        plans, _changed = self.net.plan(vm_type, pve)
        config = dict(inst.get("config") or {})
        devices = {key: dict(value) for key, value in (inst.get("devices") or {}).items()}

        if vm_type == "qemu":
            cpus = max(1, (parse_int(pve.get("sockets"), 1) or 1) * (parse_int(pve.get("cores"), 1) or 1))
        else:
            cpus = max(1, parse_int(pve.get("cores"), 1) or 1)
        config["limits.cpu"] = str(cpus)
        config["limits.memory"] = "%dMiB" % max(64, parse_int(pve.get("memory"), 512) or 512)
        if vm_type == "lxc":
            config["limits.memory.swap"] = "true" if (parse_int(pve.get("swap"), 0) or 0) > 0 else "false"
        config["boot.autostart"] = "true" if parse_bool(pve.get("onboot")) else "false"

        for key in [k for k, d in devices.items() if d.get("type") == "nic"]:
            del devices[key]
        for plan in plans:
            devices[plan.name] = self.net.nic_device(plan)

        disk_key = self.disk_key(vm_type, pve)
        wanted = pveconfig.disk_size(pve.get(disk_key))
        root = devices.setdefault("root", {"type": "disk", "path": "/", "pool": self.cfg["storage_pool"]})
        current = parse_size(root.get("size"), "") or 0
        if wanted and wanted > current:
            root["size"] = incus_size(wanted)
        elif current and disk_key in pve:
            pve[disk_key] = pveconfig.with_disk_size(pve[disk_key], current)

        hostname = sanitize_hostname(pve.get("name") if vm_type == "qemu" else pve.get("hostname"), name)
        login_user, password_hash = self.credentials(vm_type, pve, inst)
        keys = [line.strip() for line in urllib.parse.unquote(str(pve.get("sshkeys") or "")).splitlines() if line.strip()]
        nameservers = str(pve.get("nameserver") or "").split() or list(self.cfg["nameservers"])
        config["cloud-init.user-data"] = cloudinit.user_data(
            hostname=hostname, vm_type=vm_type, login_user=login_user,
            password_hash=password_hash, ssh_keys=keys, plans=plans,
        )
        config["cloud-init.network-config"] = cloudinit.network_config(plans, nameservers, pve.get("searchdomain"))
        config["user.orvex.pve"] = json.dumps(pve, sort_keys=True)

        desired = dict(inst)
        desired["config"] = config
        desired["devices"] = devices
        try:
            self.incus.put_instance(name, desired)
        except IncusError as exc:
            running = inst.get("status") in RUNNING_STATES
            if start_phase:
                raise PveError(500, "unable to apply configuration to VM %d: %s" % (vmid, exc.message))
            # Running guests or conflicting devices (e.g. the old instance of a
            # reinstall still owns the IP): keep the panel's config and apply
            # everything right before the next start, like Proxmox pending changes.
            LOG.warning("VM %d: deferring configuration until next start (%s)", vmid, exc.message)
            fallback = dict(inst)
            fallback_config = dict(inst.get("config") or {})
            fallback_config["user.orvex.pve"] = config["user.orvex.pve"]
            fallback_config["user.orvex.pending"] = "1"
            if not running:
                for key in ("limits.cpu", "limits.memory", "boot.autostart", "cloud-init.user-data", "cloud-init.network-config"):
                    fallback_config[key] = config[key]
            fallback["config"] = fallback_config
            try:
                self.incus.put_instance(name, fallback)
            except IncusError as exc2:
                raise PveError(500, "unable to update VM %d: %s" % (vmid, exc2.message))
            return
        inst["config"] = config
        inst["devices"] = devices

    # ------------------------------------------------------------- state
    def status_current(self, vmid: int, vm_type: str) -> Dict[str, Any]:
        inst = self.get(vmid, vm_type, recursion=1)
        state = inst.get("state") or {}
        pve = self.load_pve(inst)
        plans, _ = self.net.plan(vm_type, dict(pve))
        cur = self.metrics.current(vmid) if self.metrics else {}
        status = inst.get("status") or state.get("status") or "Stopped"
        running = status in RUNNING_STATES
        config = inst.get("config") or {}
        net = state.get("network") or {}
        netin = sum(int((v.get("counters") or {}).get("bytes_received", 0)) for k, v in net.items() if k != "lo")
        netout = sum(int((v.get("counters") or {}).get("bytes_sent", 0)) for k, v in net.items() if k != "lo")
        memory = state.get("memory") or {}
        disk = ((state.get("disk") or {}).get("root") or {})
        uptime = max(0, now() - parse_time(inst.get("last_used_at"))) if running and parse_time(inst.get("last_used_at")) else 0
        login_user, _hash = self.credentials(vm_type, pve, inst)
        access = self.net.access_info(vm_type, plans)
        if access.get("ssh"):
            access["ssh"]["user"] = login_user
        data: Dict[str, Any] = {
            "vmid": vmid,
            "name": pve.get("name") or pve.get("hostname") or self.name_for(vmid),
            "status": "running" if running else "stopped",
            "cpu": float(cur.get("cpu", 0.0)) if running else 0,
            "cpus": parse_int(config.get("limits.cpu"), 1),
            "mem": int(memory.get("usage", 0)) if running else 0,
            "maxmem": parse_size(config.get("limits.memory"), "") or 0,
            "disk": int(disk.get("usage", 0)),
            "maxdisk": root_size_bytes(inst.get("devices") or {}),
            "netin": netin,
            "netout": netout,
            "diskread": int(cur.get("diskread", 0)),
            "diskwrite": int(cur.get("diskwrite", 0)),
            "uptime": uptime,
            "pid": state.get("pid") or None,
            "ha": {"managed": 0},
            "tags": pve.get("tags", ""),
            "orvex": dict(access, type="kvm" if vm_type == "qemu" else "lxc",
                          vnc=vm_type == "qemu" and "raw.qemu" in config,
                          pending_changes=config.get("user.orvex.pending") == "1"),
        }
        if vm_type == "qemu":
            data["qmpstatus"] = "paused" if status == "Frozen" else ("running" if running else "stopped")
            data["agent"] = 1
        else:
            data["swap"] = int(memory.get("swap_usage", 0))
            data["maxswap"] = (parse_int(pve.get("swap"), 0) or 0) * MIB
            data["type"] = "lxc"
        return data

    def _start(self, inst: Dict[str, Any], task: Optional[Task]) -> None:
        name = inst["name"]
        try:
            self.incus.set_state(name, "start", timeout=60)
        except IncusError as exc:
            config = dict(inst.get("config") or {})
            if pve_type(inst) == "qemu" and "raw.qemu" in config:
                LOG.warning("%s failed to start with the VNC option (%s); retrying without it", name, exc.message)
                if task:
                    task.log("WARN: QEMU rejected the VNC console option; starting without graphical console")
                config.pop("raw.qemu", None)
                config.pop("user.orvex.vnc_display", None)
                fresh = self.incus.instance(name)
                fresh["config"] = dict(fresh.get("config") or {})
                fresh["config"].pop("raw.qemu", None)
                fresh["config"].pop("user.orvex.vnc_display", None)
                self.incus.put_instance(name, fresh)
                try:
                    self.incus.set_state(name, "start", timeout=60)
                    return
                except IncusError as exc2:
                    raise PveError(500, "start failed: %s" % exc2.message)
            raise PveError(500, "start failed: %s" % exc.message)

    def _stop(self, name: str, graceful_timeout: int = 0) -> None:
        if graceful_timeout > 0:
            try:
                self.incus.set_state(name, "stop", timeout=graceful_timeout, force=False)
                return
            except IncusError as exc:
                LOG.info("%s did not shut down gracefully (%s); forcing", name, exc.message)
        self.incus.set_state(name, "stop", timeout=30, force=True)

    def _start_fresh(self, vmid: int, vm_type: str, task: Task) -> None:
        inst = self.get(vmid, vm_type)
        pve = self.load_pve(inst)
        self.apply(inst, pve, start_phase=True)
        inst = self.get(vmid, vm_type)
        if (inst.get("config") or {}).get("user.orvex.pending"):
            inst["config"] = dict(inst["config"])
            inst["config"].pop("user.orvex.pending", None)
            self.incus.put_instance(inst["name"], inst)
            inst = self.get(vmid, vm_type)
        self._start(inst, task)

    def power(self, vmid: int, vm_type: str, action: str, params: Dict[str, Any], user: str) -> str:
        prefix = "qm" if vm_type == "qemu" else "vz"
        valid = ("start", "stop", "shutdown", "reboot", "reset", "suspend", "resume")
        if action not in valid or (action == "reset" and vm_type != "qemu"):
            raise PveError(501, "Method 'POST /nodes/{node}/%s/{vmid}/status/%s' not implemented" % (vm_type, action))
        self.get(vmid, vm_type)
        timeout = parse_int(params.get("timeout"), 60) or 60

        def work(task: Task) -> None:
            with self.vm_lock(vmid):
                inst = self.get(vmid, vm_type)
                name = inst["name"]
                status = inst.get("status")
                running = status in RUNNING_STATES
                if action == "start":
                    if status == "Frozen":
                        self.incus.set_state(name, "unfreeze")
                    elif not running:
                        self._start_fresh(vmid, vm_type, task)
                    else:
                        task.log("VM %d already running" % vmid)
                elif action in ("stop", "shutdown"):
                    if not running:
                        task.log("VM %d not running" % vmid)
                    elif action == "stop" or parse_bool(params.get("forceStop")):
                        self._stop(name, 0 if action == "stop" else timeout)
                    else:
                        try:
                            self.incus.set_state(name, "stop", timeout=timeout, force=False)
                        except IncusError as exc:
                            raise PveError(500, "shutdown of VM %d timed out: %s" % (vmid, exc.message))
                elif action in ("reboot", "reset"):
                    if running:
                        self._stop(name, 0 if action == "reset" else timeout)
                    self._start_fresh(vmid, vm_type, task)
                elif action == "suspend":
                    if running:
                        self.incus.set_state(name, "freeze")
                elif action == "resume":
                    if status == "Frozen":
                        self.incus.set_state(name, "unfreeze")
            if action in ("start", "reboot", "reset"):
                self.sync_forwards()

        return self.tasks.start(prefix + action, vmid, user, work)

    def resize(self, vmid: int, vm_type: str, disk: str, size: str, user: str) -> str:
        inst = self.get(vmid, vm_type)
        pve = self.load_pve(inst)
        disk_key = self.disk_key(vm_type, pve)
        if disk != disk_key:
            raise PveError(500, "disk '%s' does not exist" % disk)
        delta = parse_size(size, "G")
        if delta is None:
            raise PveError(400, "Parameter verification failed.", {"size": "invalid size '%s'" % size})

        def work(task: Task) -> None:
            with self.vm_lock(vmid):
                fresh = self.get(vmid, vm_type)
                pve_now = self.load_pve(fresh)
                devices = {k: dict(v) for k, v in (fresh.get("devices") or {}).items()}
                root = devices.setdefault("root", {"type": "disk", "path": "/", "pool": self.cfg["storage_pool"]})
                current = parse_size(root.get("size"), "") or pveconfig.disk_size(pve_now.get(disk_key))
                target = current + delta if is_relative_size(size) else delta
                if target < current:
                    raise PveError(500, "shrinking disks is not supported")
                if target == current:
                    task.log("disk %s already has size %s" % (disk_key, format_size(current)))
                    return
                root["size"] = incus_size(target)
                pve_now[disk_key] = pveconfig.with_disk_size(pve_now.get(disk_key) or "%s:vm-%d-disk-0" % (root.get("pool"), vmid), target)
                fresh["devices"] = devices
                fresh["config"] = dict(fresh.get("config") or {})
                fresh["config"]["user.orvex.pve"] = json.dumps(pve_now, sort_keys=True)
                try:
                    self.incus.put_instance(fresh["name"], fresh)
                except IncusError as exc:
                    raise PveError(500, "resize failed: %s" % exc.message)
                task.log("resized %s from %s to %s" % (disk_key, format_size(current), format_size(target)))

        return self.tasks.start("resize", vmid, user, work)

    def delete(self, vmid: int, vm_type: str, user: str) -> str:
        self.get(vmid, vm_type)

        def work(task: Task) -> None:
            with self.vm_lock(vmid):
                try:
                    inst = self.get(vmid, vm_type)
                except PveError:
                    task.log("VM %d already removed" % vmid)
                    return
                if inst.get("status") in RUNNING_STATES:
                    self._stop(inst["name"], 0)
                try:
                    self.incus.delete_instance(inst["name"])
                except IncusError as exc:
                    raise PveError(500, "destroy failed: %s" % exc.message)
                self.store.drop_snapshot_note(vmid)
                if self.metrics:
                    self.metrics.forget(vmid)
                task.log("destroyed VM %d" % vmid)
            self.sync_forwards()

        return self.tasks.start("qmdestroy" if vm_type == "qemu" else "vzdestroy", vmid, user, work)

    # --------------------------------------------------------- passwords
    def set_password(self, vmid: int, vm_type: str, username: Optional[str], password: str) -> Dict[str, Any]:
        if not isinstance(password, str) or not (5 <= len(password) <= 1024) or "\n" in password or "\r" in password:
            raise PveError(400, "Parameter verification failed.", {"password": "must be 5-1024 characters without line breaks"})
        username = (username or "").strip()
        if username and not USERNAME_RE.match(username):
            raise PveError(400, "Parameter verification failed.", {"username": "invalid user name"})
        hashed = hash_password(password)
        with self.vm_lock(vmid):
            inst = self.get(vmid, vm_type)
            pve = self.load_pve(inst)
            login_user, _old = self.credentials(vm_type, pve, inst)
            username = username or login_user
            if vm_type == "qemu" and username == login_user:
                pve["cipassword"] = hashed
            elif vm_type == "lxc" and username == "root":
                pve["orvex_password"] = hashed
            self.apply(inst, pve)
            applied = "next_boot"
            message = "The new password is applied when the server starts next time."
            if inst.get("status") == "Running":
                try:
                    code, _out, err = self.incus.exec(
                        inst["name"],
                        ["sh", "-c", 'printf "%s:%s\\n" "$ORVEX_USER" "$ORVEX_HASH" | chpasswd -e'],
                        {"ORVEX_USER": username, "ORVEX_HASH": hashed},
                    )
                    if code == 0:
                        applied = "immediate"
                        message = "Password changed."
                    else:
                        message = "Could not change the password inside the guest (%s); it is applied on next start." % (err.strip() or "exit code %d" % code)
                except IncusError as exc:
                    message = "Guest agent unavailable (%s); the password is applied on next start." % exc.message
        return {"result": {}, "applied": applied, "username": username, "message": message}

    # --------------------------------------------------------- snapshots
    def list_snapshots(self, vmid: int, vm_type: str) -> List[Dict[str, Any]]:
        inst = self.get(vmid, vm_type)
        try:
            snaps = self.incus.snapshots(inst["name"])
        except IncusError as exc:
            raise PveError(500, exc.message)
        out: List[Dict[str, Any]] = []
        parent = None
        for snap in sorted(snaps, key=lambda s: parse_time(s.get("created_at"))):
            name = str(snap.get("name", "")).split("/")[-1]
            note = self.store.snapshot_note(vmid, name)
            entry: Dict[str, Any] = {
                "name": name, "description": note.get("description", ""),
                "snaptime": parse_time(snap.get("created_at")), "vmstate": int(note.get("vmstate", 0)),
            }
            if parent:
                entry["parent"] = parent
            out.append(entry)
            parent = name
        current: Dict[str, Any] = {"name": "current", "description": "You are here!", "running": 1 if inst.get("status") in RUNNING_STATES else 0}
        if parent:
            current["parent"] = parent
        out.append(current)
        return out

    def create_snapshot(self, vmid: int, vm_type: str, params: Dict[str, Any], user: str) -> str:
        snap = str(params.get("snapname") or "").strip()
        if not SNAPSHOT_NAME_RE.match(snap):
            raise PveError(400, "Parameter verification failed.", {"snapname": "invalid format"})
        if snap in {s["name"] for s in self.list_snapshots(vmid, vm_type)}:
            raise PveError(500, "snapshot name '%s' already used" % snap)
        description = str(params.get("description") or "")[:8192]

        def work(task: Task) -> None:
            with self.vm_lock(vmid):
                inst = self.get(vmid, vm_type)
                try:
                    self.incus.create_snapshot(inst["name"], snap)
                except IncusError as exc:
                    raise PveError(500, "snapshot failed: %s" % exc.message)
                self.store.set_snapshot_note(vmid, snap, description, False)
                task.log("created snapshot '%s'" % snap)

        return self.tasks.start("qmsnapshot" if vm_type == "qemu" else "vzsnapshot", vmid, user, work)

    def snapshot_action(self, vmid: int, vm_type: str, snap: str, action: str, user: str) -> str:
        if snap not in {s["name"] for s in self.list_snapshots(vmid, vm_type) if s["name"] != "current"}:
            raise PveError(500, "snapshot '%s' does not exist" % snap)

        def work(task: Task) -> None:
            with self.vm_lock(vmid):
                inst = self.get(vmid, vm_type)
                try:
                    if action == "delete":
                        self.incus.delete_snapshot(inst["name"], snap)
                        self.store.drop_snapshot_note(vmid, snap)
                    else:
                        self.incus.restore_snapshot(inst["name"], snap)
                except IncusError as exc:
                    raise PveError(500, "snapshot %s failed: %s" % (action, exc.message))
                task.log("%s snapshot '%s'" % ("deleted" if action == "delete" else "rolled back to", snap))
            if action == "rollback":
                self.sync_forwards()

        dtype = ("qm" if vm_type == "qemu" else "vz") + ("delsnapshot" if action == "delete" else "rollback")
        return self.tasks.start(dtype, vmid, user, work)

    def snapshot_config(self, vmid: int, vm_type: str, snap: str) -> Dict[str, Any]:
        inst = self.get(vmid, vm_type)
        for item in self.incus.snapshots(inst["name"]):
            if str(item.get("name", "")).split("/")[-1] == snap:
                pve = self.load_pve(item)
                pve.pop("cipassword", None)
                return {k: v for k, v in pve.items() if not k.startswith("orvex_")}
        raise PveError(500, "snapshot '%s' does not exist" % snap)

    # ------------------------------------------------------------- misc
    def guest_interfaces(self, vmid: int, vm_type: str) -> Dict[str, Any]:
        inst = self.get(vmid, vm_type, recursion=1)
        result = []
        for name, data in ((inst.get("state") or {}).get("network") or {}).items():
            addresses = []
            for addr in data.get("addresses") or []:
                addresses.append({
                    "ip-address": addr.get("address"), "prefix": parse_int(addr.get("netmask"), 0),
                    "ip-address-type": "ipv6" if addr.get("family") == "inet6" else "ipv4",
                })
            result.append({"name": name, "hardware-address": data.get("hwaddr"), "ip-addresses": addresses})
        return {"result": result}

    def run_quick(self, dtype: str, item: Any, user: str, fn: Callable[[], None]) -> str:
        def work(task: Task) -> None:
            fn()

        return self.tasks.start(dtype, item, user, work)


def wait_until(predicate: Callable[[], bool], timeout: float, interval: float = 0.2) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()
