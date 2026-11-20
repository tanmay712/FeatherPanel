"""Proxmox VE API routes implemented on top of the OrveX services."""

from __future__ import annotations

import hmac
import os
import platform
import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import PVE_COMPAT_VERSION, __version__
from .backups import STORAGE as BACKUP_STORAGE
from .incus import IncusError
from .util import GIB, PveError, hash_password, parse_bool, parse_int

RAW = object()  # handler already wrote the response (websocket)
TYPES = ("qemu", "lxc")


class Ctx:
    def __init__(self, app: Any, method: str, args: Dict[str, Any], params: Dict[str, Any], user: str, request: Any):
        self.app = app
        self.method = method
        self.args = args
        self.params = params
        self.user = user
        self.request = request

    def int_arg(self, name: str) -> int:
        return int(self.args[name])


class Route:
    def __init__(self, method: str, pattern: str, handler: Callable[[Ctx], Any], auth: bool = True):
        self.method = method
        self.parts = [p for p in pattern.strip("/").split("/") if p]
        self.handler = handler
        self.auth = auth

    def match(self, method: str, segments: List[str]) -> Optional[Dict[str, Any]]:
        if method != self.method or len(segments) != len(self.parts):
            return None
        args: Dict[str, Any] = {}
        for part, seg in zip(self.parts, segments):
            if part.startswith("{") and part.endswith("}"):
                name, _, kind = part[1:-1].partition(":")
                if kind == "int":
                    if not seg.isdigit():
                        return None
                    args[name] = int(seg)
                elif kind == "type":
                    if seg not in TYPES:
                        return None
                    args[name] = seg
                else:
                    args[name] = seg
            elif part != seg:
                return None
        return args


class Api:
    def __init__(self, app: Any):
        self.app = app
        self._tickets: Dict[str, Tuple[str, float]] = {}
        self._ticket_lock = threading.Lock()
        guest = "nodes/{node}/{vtype:type}/{vmid:int}"
        r = Route
        self.routes: List[Route] = [
            r("GET", "version", self.version),
            r("GET", "cluster/resources", self.cluster_resources),
            r("GET", "cluster/nextid", self.next_id),
            r("GET", "cluster/status", self.cluster_status),
            r("GET", "cluster/firewall/options", self.firewall_options),
            r("GET", "cluster/firewall/rules", self.empty_list),
            r("GET", "cluster/firewall/groups", self.empty_list),
            r("POST", "access/ticket", self.access_ticket, auth=False),
            r("GET", "access/users", self.access_users),
            r("POST", "access/users", self.access_user_create),
            r("DELETE", "access/users/{userid}", self.access_user_delete),
            r("PUT", "access/acl", self.null),
            r("GET", "access/permissions", self.access_permissions),
            r("GET", "nodes", self.nodes),
            r("GET", "nodes/{node}", self.node_index),
            r("GET", "nodes/{node}/status", self.node_status),
            r("GET", "nodes/{node}/version", self.version),
            r("GET", "nodes/{node}/rrddata", self.node_rrd),
            r("GET", "nodes/{node}/network", self.node_network),
            r("GET", "nodes/{node}/storage", self.node_storage),
            r("GET", "nodes/{node}/storage/{storage}", self.storage_index),
            r("GET", "nodes/{node}/storage/{storage}/status", self.storage_status),
            r("GET", "nodes/{node}/storage/{storage}/content", self.storage_content),
            r("DELETE", "nodes/{node}/storage/{storage}/content/{volume}", self.storage_delete),
            r("POST", "nodes/{node}/storage/{storage}/upload", self.no_iso),
            r("POST", "nodes/{node}/storage/{storage}/download-url", self.no_iso),
            r("GET", "nodes/{node}/query-url-metadata", self.no_iso),
            r("GET", "nodes/{node}/tasks", self.tasks_list),
            r("GET", "nodes/{node}/tasks/{upid}", self.task_index),
            r("GET", "nodes/{node}/tasks/{upid}/status", self.task_status),
            r("GET", "nodes/{node}/tasks/{upid}/log", self.task_log),
            r("DELETE", "nodes/{node}/tasks/{upid}", self.null),
            r("POST", "nodes/{node}/vzdump", self.vzdump),
            r("GET", "nodes/{node}/firewall", self.firewall_index),
            r("GET", "nodes/{node}/firewall/options", self.firewall_options),
            r("GET", "nodes/{node}/firewall/rules", self.empty_list),
            r("GET", "nodes/{node}/firewall/log", self.empty_list),
            r("PUT", "nodes/{node}/firewall/options", self.no_firewall),
            r("POST", "nodes/{node}/firewall/rules", self.no_firewall),
            r("DELETE", "nodes/{node}/firewall/rules/{pos}", self.no_firewall),
            r("POST", "nodes/{node}/orvex/credentials", self.orvex_credentials),
            r("GET", "nodes/{node}/orvex/info", self.orvex_info),
            r("GET", "nodes/{node}/{vtype:type}", self.guest_list),
            r("POST", "nodes/{node}/{vtype:type}", self.guest_create),
            r("GET", guest, self.guest_index),
            r("DELETE", guest, self.guest_delete),
            r("GET", guest + "/config", self.config_get),
            r("PUT", guest + "/config", self.config_put),
            r("POST", guest + "/config", self.config_post),
            r("GET", guest + "/pending", self.config_pending),
            r("GET", guest + "/status", self.status_index),
            r("GET", guest + "/status/current", self.status_current),
            r("POST", guest + "/status/{action}", self.status_action),
            r("POST", guest + "/clone", self.clone),
            r("PUT", guest + "/resize", self.resize),
            r("PUT", guest + "/unlink", self.null),
            r("GET", guest + "/rrddata", self.guest_rrd),
            r("GET", guest + "/snapshot", self.snapshot_list),
            r("POST", guest + "/snapshot", self.snapshot_create),
            r("GET", guest + "/snapshot/{snap}", self.snapshot_index),
            r("GET", guest + "/snapshot/{snap}/config", self.snapshot_config),
            r("DELETE", guest + "/snapshot/{snap}", self.snapshot_delete),
            r("POST", guest + "/snapshot/{snap}/rollback", self.snapshot_rollback),
            r("POST", guest + "/vncproxy", self.vncproxy),
            r("GET", guest + "/vncwebsocket", self.vncwebsocket, auth=False),
            r("POST", guest + "/termproxy", self.no_termproxy),
            r("POST", guest + "/agent/set-user-password", self.agent_password),
            r("POST", guest + "/agent/ping", self.agent_ping),
            r("GET", guest + "/agent/network-get-interfaces", self.agent_interfaces),
            r("GET", guest + "/feature", self.feature),
            r("GET", guest + "/firewall", self.firewall_index),
            r("GET", guest + "/firewall/options", self.firewall_options),
            r("GET", guest + "/firewall/rules", self.empty_list),
            r("GET", guest + "/firewall/ipset", self.empty_list),
            r("GET", guest + "/firewall/aliases", self.empty_list),
            r("GET", guest + "/firewall/refs", self.empty_list),
            r("PUT", guest + "/firewall/options", self.no_firewall),
            r("POST", guest + "/firewall/rules", self.no_firewall),
            r("PUT", guest + "/firewall/rules/{pos}", self.no_firewall),
            r("DELETE", guest + "/firewall/rules/{pos}", self.no_firewall),
            r("POST", guest + "/migrate", self.no_migrate),
        ]

    # ------------------------------------------------------------ routing
    def match(self, method: str, segments: List[str]) -> Tuple[Optional[Route], Dict[str, Any]]:
        for route in self.routes:
            args = route.match(method, segments)
            if args is not None:
                return route, args
        return None, {}

    def authenticate(self, authorization: str, cookie_ticket: Optional[str]) -> Optional[str]:
        cfg = self.app.cfg
        header = (authorization or "").strip()
        for prefix in ("PVEAPIToken=", "PVEAPIToken "):
            if header.startswith(prefix):
                given = header[len(prefix):].strip()
                expected = cfg.token_header_value
                if cfg["api_token_secret"] and hmac.compare_digest(given.encode(), expected.encode()):
                    return "%s!%s" % (cfg["api_user"], cfg["api_token_id"])
                return None
        if cookie_ticket:
            with self._ticket_lock:
                entry = self._tickets.get(cookie_ticket)
            if entry and entry[1] > time.time():
                return entry[0]
        return None

    # ------------------------------------------------------ common bits
    def null(self, ctx: Ctx) -> Any:
        return None

    def empty_list(self, ctx: Ctx) -> Any:
        return []

    def no_iso(self, ctx: Ctx) -> Any:
        raise PveError(501, "ISO storage is not available on OrveX nodes")

    def no_firewall(self, ctx: Ctx) -> Any:
        raise PveError(501, "The Proxmox firewall is not available on OrveX nodes")

    def no_migrate(self, ctx: Ctx) -> Any:
        raise PveError(501, "Live migration is not available on OrveX nodes")

    def no_termproxy(self, ctx: Ctx) -> Any:
        raise PveError(501, "Use SSH to access OrveX guests (terminal proxy is not available)")

    def firewall_index(self, ctx: Ctx) -> Any:
        return [{"name": "rules"}, {"name": "options"}, {"name": "log"}]

    def firewall_options(self, ctx: Ctx) -> Any:
        return {"enable": 0, "policy_in": "ACCEPT", "policy_out": "ACCEPT"}

    # ------------------------------------------------------------- info
    def version(self, ctx: Ctx) -> Any:
        major_minor = ".".join(PVE_COMPAT_VERSION.split(".")[:2])
        return {
            "version": PVE_COMPAT_VERSION, "release": major_minor, "repoid": "orvex",
            "orvex": {"version": __version__, "node": self.app.cfg.node_name, "backend": "incus"},
        }

    def _node_entry(self) -> Dict[str, Any]:
        cur = self.app.metrics.node_current()
        try:
            with open("/proc/uptime", encoding="utf-8") as handle:
                uptime = int(float(handle.read().split()[0]))
        except (OSError, ValueError, IndexError):
            uptime = 0
        return {
            "node": self.app.cfg.node_name, "status": "online", "type": "node", "id": "node/%s" % self.app.cfg.node_name,
            "cpu": cur.get("cpu", 0.0), "maxcpu": cur.get("maxcpu", os.cpu_count() or 1),
            "mem": cur.get("mem", 0), "maxmem": cur.get("maxmem", 0),
            "disk": cur.get("disk", 0), "maxdisk": cur.get("maxdisk", 0),
            "uptime": uptime, "level": "", "ssl_fingerprint": self.app.cert_fingerprint,
        }

    def nodes(self, ctx: Ctx) -> Any:
        return [self._node_entry()]

    def node_index(self, ctx: Ctx) -> Any:
        return [{"name": n} for n in ("status", "network", "storage", "tasks", "qemu", "lxc", "rrddata", "version")]

    def node_status(self, ctx: Ctx) -> Any:
        cur = self.app.metrics.node_current()
        entry = self._node_entry()
        try:
            load = ["%.2f" % v for v in os.getloadavg()]
        except OSError:
            load = ["0.00", "0.00", "0.00"]
        total_mem = cur.get("maxmem", 0)
        used_mem = cur.get("mem", 0)
        return {
            "uptime": entry["uptime"], "loadavg": load, "cpu": entry["cpu"], "wait": cur.get("iowait", 0.0),
            "cpuinfo": {
                "cpus": os.cpu_count() or 1, "cores": os.cpu_count() or 1, "sockets": 1,
                "model": self.app.cpu_model, "hvm": "1" if os.path.exists("/dev/kvm") else "0", "mhz": "0",
            },
            "memory": {"total": total_mem, "used": used_mem, "free": max(0, total_mem - used_mem)},
            "swap": {"total": cur.get("swaptotal", 0), "used": cur.get("swapused", 0),
                     "free": max(0, cur.get("swaptotal", 0) - cur.get("swapused", 0))},
            "rootfs": {"total": cur.get("maxdisk", 0), "used": cur.get("disk", 0),
                       "avail": max(0, cur.get("maxdisk", 0) - cur.get("disk", 0)),
                       "free": max(0, cur.get("maxdisk", 0) - cur.get("disk", 0))},
            "kversion": "%s %s" % (platform.system(), platform.release()),
            "pveversion": "pve-manager/%s/orvex-%s" % (PVE_COMPAT_VERSION, __version__),
            "ksm": {"shared": 0}, "boot-info": {"mode": "efi"},
        }

    def node_rrd(self, ctx: Ctx) -> Any:
        return self.app.metrics.node_points(str(ctx.params.get("timeframe") or "hour"))

    def node_network(self, ctx: Ctx) -> Any:
        wanted = str(ctx.params.get("type") or "")
        entries = self.app.net.bridge_list()
        if wanted and wanted not in ("bridge", "any_bridge", "any_local_bridge"):
            return []
        return entries

    def cluster_status(self, ctx: Ctx) -> Any:
        return [{
            "type": "node", "name": self.app.cfg.node_name, "id": "node/%s" % self.app.cfg.node_name,
            "online": 1, "local": 1, "nodeid": 1, "ip": self.app.net.public_ipv4(), "level": "",
        }]

    # ---------------------------------------------------------- storage
    def _storages(self) -> List[Dict[str, Any]]:
        out = []
        try:
            pools = self.app.incus.pools()
        except IncusError as exc:
            raise PveError(500, exc.message)
        for pool in pools:
            name = str(pool.get("name"))
            try:
                space = (self.app.incus.pool_resources(name).get("space") or {})
            except IncusError:
                space = {}
            total = int(space.get("total", 0))
            used = int(space.get("used", 0))
            out.append({
                "storage": name, "type": str(pool.get("driver", "dir")), "content": "images,rootdir",
                "active": 1, "enabled": 1, "shared": 0, "total": total, "used": used,
                "avail": max(0, total - used), "used_fraction": (used / total) if total else 0,
            })
        out.append(self.app.backups.storage_entry())
        return out

    def node_storage(self, ctx: Ctx) -> Any:
        storages = self._storages()
        content = str(ctx.params.get("content") or "")
        if content:
            wanted = set(content.split(","))
            storages = [s for s in storages if wanted & set(s["content"].split(","))]
        return storages

    def storage_index(self, ctx: Ctx) -> Any:
        return [{"subdir": "status"}, {"subdir": "content"}]

    def storage_status(self, ctx: Ctx) -> Any:
        for storage in self._storages():
            if storage["storage"] == ctx.args["storage"]:
                return storage
        raise PveError(500, "storage '%s' does not exist" % ctx.args["storage"])

    def storage_content(self, ctx: Ctx) -> Any:
        if ctx.args["storage"] != BACKUP_STORAGE:
            return []
        content = str(ctx.params.get("content") or "backup")
        if "backup" not in content.split(","):
            return []
        return self.app.backups.list(parse_int(ctx.params.get("vmid")))

    def storage_delete(self, ctx: Ctx) -> Any:
        volume = ctx.args["volume"]
        if ":" not in volume:
            volume = "%s:backup/%s" % (ctx.args["storage"], volume.split("/")[-1])
        self.app.backups.delete_volume(volume)
        return None

    def cluster_resources(self, ctx: Ctx) -> Any:
        wanted = str(ctx.params.get("type") or "")
        out: List[Dict[str, Any]] = []
        if wanted in ("", "node"):
            out.append(self._node_entry())
        if wanted in ("", "vm"):
            out.extend(self.app.instances.template_resources())
            out.extend(self.app.instances.vm_resources())
        if wanted in ("", "storage"):
            for storage in self._storages():
                out.append({
                    "id": "storage/%s/%s" % (self.app.cfg.node_name, storage["storage"]), "type": "storage",
                    "storage": storage["storage"], "node": self.app.cfg.node_name, "status": "available",
                    "disk": storage["used"], "maxdisk": storage["total"], "content": storage["content"],
                    "plugintype": storage["type"], "shared": 0,
                })
        return out

    def next_id(self, ctx: Ctx) -> Any:
        return self.app.instances.next_id(parse_int(ctx.params.get("vmid"), 100))

    # ------------------------------------------------------------ tasks
    def tasks_list(self, ctx: Ctx) -> Any:
        return self.app.tasks.list(parse_int(ctx.params.get("limit"), 50) or 50)

    def task_index(self, ctx: Ctx) -> Any:
        self.app.tasks.get(ctx.args["upid"])
        return [{"name": "log"}, {"name": "status"}]

    def task_status(self, ctx: Ctx) -> Any:
        return self.app.tasks.get(ctx.args["upid"]).as_status()

    def task_log(self, ctx: Ctx) -> Any:
        task = self.app.tasks.get(ctx.args["upid"])
        start = parse_int(ctx.params.get("start"), 0) or 0
        limit = parse_int(ctx.params.get("limit"), 50) or 50
        lines = list(task.lines)
        return [{"n": start + i + 1, "t": line} for i, line in enumerate(lines[start:start + limit])]

    def vzdump(self, ctx: Ctx) -> Any:
        return self.app.backups.vzdump(ctx.params, ctx.user)

    # ----------------------------------------------------------- guests
    def guest_list(self, ctx: Ctx) -> Any:
        return self.app.instances.list_guests(ctx.args["vtype"])

    def guest_create(self, ctx: Ctx) -> Any:
        vm_type = ctx.args["vtype"]
        is_restore = ctx.params.get("archive") if vm_type == "qemu" else (
            parse_bool(ctx.params.get("restore")) and ctx.params.get("ostemplate"))
        if is_restore:
            return self.app.backups.restore(vm_type, ctx.params, ctx.user)
        raise PveError(501, "Creating guests from scratch is not supported; clone one of the node templates instead")

    def guest_index(self, ctx: Ctx) -> Any:
        self.app.instances.get(ctx.int_arg("vmid"), ctx.args["vtype"])
        return [{"subdir": s} for s in ("config", "pending", "status", "snapshot", "rrddata", "vncproxy")]

    def guest_delete(self, ctx: Ctx) -> Any:
        return self.app.instances.delete(ctx.int_arg("vmid"), ctx.args["vtype"], ctx.user)

    def config_get(self, ctx: Ctx) -> Any:
        return self.app.instances.get_config(ctx.int_arg("vmid"), ctx.args["vtype"])

    def config_put(self, ctx: Ctx) -> Any:
        self.app.instances.update_config(ctx.int_arg("vmid"), ctx.args["vtype"], ctx.params)
        return None

    def config_post(self, ctx: Ctx) -> Any:
        vmid, vm_type, params = ctx.int_arg("vmid"), ctx.args["vtype"], dict(ctx.params)
        self.app.instances.get(vmid, vm_type)
        return self.app.instances.run_quick(
            "qmconfig" if vm_type == "qemu" else "vzconfig", vmid, ctx.user,
            lambda: self.app.instances.update_config(vmid, vm_type, params),
        )

    def config_pending(self, ctx: Ctx) -> Any:
        config = self.app.instances.get_config(ctx.int_arg("vmid"), ctx.args["vtype"])
        return [{"key": k, "value": v} for k, v in config.items() if k != "digest"]

    def status_index(self, ctx: Ctx) -> Any:
        return [{"subdir": s} for s in ("current", "start", "stop", "shutdown", "reboot", "suspend", "resume")]

    def status_current(self, ctx: Ctx) -> Any:
        return self.app.instances.status_current(ctx.int_arg("vmid"), ctx.args["vtype"])

    def status_action(self, ctx: Ctx) -> Any:
        return self.app.instances.power(ctx.int_arg("vmid"), ctx.args["vtype"], ctx.args["action"], ctx.params, ctx.user)

    def clone(self, ctx: Ctx) -> Any:
        return self.app.instances.clone(ctx.int_arg("vmid"), ctx.args["vtype"], ctx.params, ctx.user)

    def resize(self, ctx: Ctx) -> Any:
        disk = str(ctx.params.get("disk") or "")
        size = str(ctx.params.get("size") or "")
        if not disk or not size:
            raise PveError(400, "Parameter verification failed.", {"disk" if not disk else "size": "property is missing"})
        return self.app.instances.resize(ctx.int_arg("vmid"), ctx.args["vtype"], disk, size, ctx.user)

    def guest_rrd(self, ctx: Ctx) -> Any:
        vmid = ctx.int_arg("vmid")
        self.app.instances.get(vmid, ctx.args["vtype"])
        return self.app.metrics.points(vmid, str(ctx.params.get("timeframe") or "hour"))

    def feature(self, ctx: Ctx) -> Any:
        feature = str(ctx.params.get("feature") or "")
        return {"hasFeature": 1 if feature in ("snapshot", "clone", "copy", "") else 0, "nodes": [self.app.cfg.node_name]}

    # -------------------------------------------------------- snapshots
    def snapshot_list(self, ctx: Ctx) -> Any:
        return self.app.instances.list_snapshots(ctx.int_arg("vmid"), ctx.args["vtype"])

    def snapshot_create(self, ctx: Ctx) -> Any:
        return self.app.instances.create_snapshot(ctx.int_arg("vmid"), ctx.args["vtype"], ctx.params, ctx.user)

    def snapshot_index(self, ctx: Ctx) -> Any:
        return [{"subdir": "config"}, {"subdir": "rollback"}]

    def snapshot_config(self, ctx: Ctx) -> Any:
        return self.app.instances.snapshot_config(ctx.int_arg("vmid"), ctx.args["vtype"], ctx.args["snap"])

    def snapshot_delete(self, ctx: Ctx) -> Any:
        return self.app.instances.snapshot_action(ctx.int_arg("vmid"), ctx.args["vtype"], ctx.args["snap"], "delete", ctx.user)

    def snapshot_rollback(self, ctx: Ctx) -> Any:
        return self.app.instances.snapshot_action(ctx.int_arg("vmid"), ctx.args["vtype"], ctx.args["snap"], "rollback", ctx.user)

    # ---------------------------------------------------------- console
    def vncproxy(self, ctx: Ctx) -> Any:
        vmid = ctx.int_arg("vmid")
        data = self.app.vnc.create_ticket(vmid, ctx.args["vtype"])
        data["upid"] = self.app.tasks.run_sync("vncproxy", vmid, ctx.user, lambda task: None)
        return data

    def vncwebsocket(self, ctx: Ctx) -> Any:
        vmid = ctx.int_arg("vmid")
        port = parse_int(ctx.params.get("port"))
        ticket = str(ctx.params.get("vncticket") or "")
        target = self.app.vnc.check_ticket(vmid, port, ticket)
        if target is None:
            raise PveError(401, "invalid or expired vncticket")
        ctx.request.upgrade_websocket(target)
        return RAW

    # ------------------------------------------------------------ agent
    def agent_password(self, ctx: Ctx) -> Any:
        return self.app.instances.set_password(
            ctx.int_arg("vmid"), ctx.args["vtype"], ctx.params.get("username"), str(ctx.params.get("password") or "")
        )

    def agent_ping(self, ctx: Ctx) -> Any:
        inst = self.app.instances.get(ctx.int_arg("vmid"), ctx.args["vtype"])
        if inst.get("status") != "Running":
            raise PveError(500, "VM %d is not running" % ctx.int_arg("vmid"))
        return {}

    def agent_interfaces(self, ctx: Ctx) -> Any:
        return self.app.instances.guest_interfaces(ctx.int_arg("vmid"), ctx.args["vtype"])

    # ----------------------------------------------------------- access
    def access_ticket(self, ctx: Ctx) -> Any:
        username = str(ctx.params.get("username") or "")
        password = str(ctx.params.get("password") or "")
        user = self.app.store.users().get(username)
        ok = False
        if user and password and (not user.get("expire") or int(user["expire"]) > time.time()):
            ok = hmac.compare_digest(str(user.get("password_hash", "")), self._digest(username, password))
        if not ok:
            raise PveError(401, "authentication failure")
        ticket = "PVE:%s:%s" % (username, secrets.token_hex(24))
        with self._ticket_lock:
            self._tickets[ticket] = (username, time.time() + 7200)
        return {"ticket": ticket, "CSRFPreventionToken": secrets.token_hex(16), "username": username, "cap": {}}

    @staticmethod
    def _digest(username: str, password: str) -> str:
        import hashlib

        return hashlib.sha256(("%s\0%s" % (username, password)).encode()).hexdigest()

    def access_users(self, ctx: Ctx) -> Any:
        out = [{"userid": self.app.cfg["api_user"], "enable": 1, "expire": 0, "comment": "OrveX panel token owner"}]
        for userid, data in self.app.store.users().items():
            out.append({"userid": userid, "enable": 1, "expire": int(data.get("expire") or 0), "comment": data.get("comment", "")})
        return out

    def access_user_create(self, ctx: Ctx) -> Any:
        userid = str(ctx.params.get("userid") or "").strip()
        if not userid or "@" not in userid:
            raise PveError(400, "Parameter verification failed.", {"userid": "invalid format"})
        password = str(ctx.params.get("password") or "")
        self.app.store.put_user(userid, {
            "password_hash": self._digest(userid, password) if password else "",
            "expire": parse_int(ctx.params.get("expire"), 0) or 0,
            "comment": str(ctx.params.get("comment") or ""),
        })
        return None

    def access_user_delete(self, ctx: Ctx) -> Any:
        if not self.app.store.delete_user(ctx.args["userid"]):
            raise PveError(500, "user '%s' does not exist" % ctx.args["userid"])
        return None

    def access_permissions(self, ctx: Ctx) -> Any:
        perms = {p: 1 for p in ("Sys.Audit", "Sys.Modify", "VM.Allocate", "VM.Audit", "VM.Config.Options",
                                "VM.Console", "VM.PowerMgmt", "VM.Snapshot", "VM.Backup", "Datastore.Allocate",
                                "Datastore.AllocateSpace", "Datastore.Audit")}
        return {"/": perms}

    # ------------------------------------------------------ extensions
    def orvex_credentials(self, ctx: Ctx) -> Any:
        """Register credentials for a guest that the panel is about to clone."""
        vmid = parse_int(ctx.params.get("vmid"))
        password = str(ctx.params.get("password") or "")
        username = str(ctx.params.get("username") or "root").strip() or "root"
        if not vmid or len(password) < 5:
            raise PveError(400, "Parameter verification failed.", {"vmid" if not vmid else "password": "invalid"})
        self.app.store.put_pending_credentials(vmid, username, hash_password(password))
        return {"vmid": vmid, "username": username}

    def orvex_info(self, ctx: Ctx) -> Any:
        cfg = self.app.cfg
        return {
            "version": __version__, "node": cfg.node_name, "public_ipv4": self.app.net.public_ipv4(),
            "uplink": self.app.net.uplink(), "routed_bridge": cfg.routed_bridge,
            "nat": dict(cfg.nat), "kvm": os.path.exists("/dev/kvm"),
            "templates": [{k: t[k] for k in ("vmid", "name", "type", "description", "default_user", "disk_gb")}
                          for t in self.app.instances.templates.values()],
        }


def total_gib(num: int) -> float:
    return round(num / GIB, 2)
