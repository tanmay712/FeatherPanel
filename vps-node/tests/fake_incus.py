"""In-memory fake of the Incus REST API served on a unix socket (tests only)."""

from __future__ import annotations

import json
import os
import socketserver
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + ".123456789Z"


class FakeIncusState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.instances: Dict[str, Dict[str, Any]] = {}
        self.snapshots: Dict[str, List[Dict[str, Any]]] = {}
        self.backups: Dict[str, Dict[str, Any]] = {}
        self.operations: Dict[str, Dict[str, Any]] = {}
        self.forwards: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.images = {"orvex-debian-12-lxc"}
        self.logs: Dict[str, str] = {}
        self.exec_calls: List[Dict[str, Any]] = []
        self.create_calls: List[Dict[str, Any]] = []
        self.restores: List[Any] = []
        self.networks = [
            {"name": "eth0", "type": "physical", "managed": False},
            {"name": "orvexnat0", "type": "bridge", "managed": True},
            {"name": "br0", "type": "bridge", "managed": False},
        ]
        self.pools = [{"name": "default", "driver": "btrfs"}]
        # Behaviour switches for tests
        self.reject_raw_qemu_start = False
        self.routed_conflicts = False
        self.cpu_ns = 0


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def address_string(self) -> str:  # unix sockets have no address
        return "unix"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    @property
    def st(self) -> FakeIncusState:
        return self.server.state  # type: ignore[attr-defined]

    # -------------------------------------------------------- responses
    def _write(self, code: int, doc: Any, raw: Optional[bytes] = None, ctype: str = "application/json") -> None:
        body = raw if raw is not None else json.dumps(doc).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        try:
            self.end_headers()
            if body:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the client already read the (empty) response and hung up

    def sync(self, metadata: Any = None) -> None:
        self._write(200, {"type": "sync", "status": "Success", "status_code": 200, "metadata": metadata})

    def error(self, code: int, message: str) -> None:
        self._write(code, {"type": "error", "error": message, "error_code": code})

    def async_op(self, metadata: Any = None, err: Optional[str] = None) -> None:
        op_id = str(uuid.uuid4())
        with self.st.lock:
            self.st.operations[op_id] = {
                "id": op_id, "status": "Failure" if err else "Success", "status_code": 400 if err else 200,
                "err": err or "", "metadata": metadata,
            }
        self._write(202, {"type": "async", "status": "Operation created", "status_code": 100,
                          "operation": "/1.0/operations/%s" % op_id, "metadata": {"id": op_id, "status": "Running"}})

    def body(self) -> Any:
        data = self._raw
        if (self.headers.get("Content-Type") or "").startswith("application/json"):
            return json.loads(data.decode() or "{}")
        return data

    # --------------------------------------------------------- routing
    def do_GET(self) -> None:
        self.route("GET")

    def do_POST(self) -> None:
        self.route("POST")

    def do_PUT(self) -> None:
        self.route("PUT")

    def do_DELETE(self) -> None:
        self.route("DELETE")

    def route(self, method: str) -> None:
        # Like Go's net/http (real Incus): consume the body even if the handler errors out early.
        length = int(self.headers.get("Content-Length") or 0)
        self._raw = self.rfile.read(length) if length else b""
        split = urllib.parse.urlsplit(self.path)
        parts = [urllib.parse.unquote(p) for p in split.path.split("/") if p]
        query = dict(urllib.parse.parse_qsl(split.query))
        try:
            self.dispatch(method, parts, query)
        except KeyError as exc:
            self.error(404, "not found: %s" % exc)

    def dispatch(self, method: str, p: List[str], q: Dict[str, str]) -> None:  # noqa: C901 - test fake
        st = self.st
        if p == ["1.0"]:
            return self.sync({"api_version": "1.0", "environment": {"server": "incus", "server_version": "6.0.0"}})
        if p[:2] == ["1.0", "operations"]:
            op = st.operations[p[2]]
            return self.sync(op)
        if p == ["1.0", "resources"]:
            return self.sync({"cpu": {"total": 8}, "memory": {"total": 32 * 1024 ** 3, "used": 4 * 1024 ** 3}})
        if p == ["1.0", "metrics"]:
            lines = []
            for name in st.instances:
                lines.append('incus_disk_read_bytes_total{device="sda",name="%s",project="default",type="container"} 1000' % name)
                lines.append('incus_disk_written_bytes_total{device="sda",name="%s",project="default",type="container"} 2000' % name)
            return self._write(200, None, ("\n".join(lines) + "\n").encode(), "text/plain")
        if p == ["1.0", "storage-pools"]:
            return self.sync(st.pools)
        if p[:2] == ["1.0", "storage-pools"] and p[-1] == "resources":
            return self.sync({"space": {"total": 100 * 1024 ** 3, "used": 10 * 1024 ** 3}})
        if p == ["1.0", "networks"]:
            return self.sync(st.networks)
        if p[:2] == ["1.0", "networks"] and len(p) >= 4 and p[3] == "forwards":
            net = st.forwards.setdefault(p[2], {})
            if len(p) == 4 and method == "GET":
                return self.sync([dict(v, listen_address=k) for k, v in net.items()])
            if len(p) == 4 and method == "POST":
                body = self.body()
                net[body["listen_address"]] = {"ports": body.get("ports", []), "description": body.get("description", "")}
                return self.sync({})
            listen = p[4]
            if method == "PUT":
                if listen not in net:
                    return self.error(404, "Network forward not found")
                body = self.body()
                net[listen] = {"ports": body.get("ports", []), "description": body.get("description", "")}
                return self.sync({})
            if method == "DELETE":
                if listen not in net:
                    return self.error(404, "Network forward not found")
                del net[listen]
                return self.sync({})
        if p[:3] == ["1.0", "images", "aliases"]:
            return self.sync({"name": p[3]}) if p[3] in st.images else self.error(404, "Image alias not found")
        if p == ["1.0", "images"] and method == "POST":
            body = self.body()
            for alias in body.get("aliases", []):
                st.images.add(alias["name"])
            return self.async_op({})
        if p[:2] == ["1.0", "instances"]:
            return self.instances(method, p[2:], q)
        return self.error(404, "unknown path /%s" % "/".join(p))

    # -------------------------------------------------------- instances
    def full(self, inst: Dict[str, Any], recursion: int) -> Dict[str, Any]:
        out = json.loads(json.dumps(inst))
        if recursion >= 1:
            out["state"] = self.state_of(inst)
            out["snapshots"] = self.st.snapshots.get(inst["name"], [])
        return out

    def state_of(self, inst: Dict[str, Any]) -> Dict[str, Any]:
        running = inst["status"] in ("Running", "Frozen")
        self.st.cpu_ns += 5 * 10 ** 9
        network = {}
        for name, dev in inst["devices"].items():
            if dev.get("type") == "nic":
                network[dev.get("name", name)] = {
                    "addresses": [{"family": "inet", "address": dev.get("ipv4.address", "10.77.0.10"), "netmask": "24"}],
                    "counters": {"bytes_received": 1000 if running else 0, "bytes_sent": 2000 if running else 0},
                    "hwaddr": dev.get("hwaddr"),
                }
        return {
            "status": inst["status"], "pid": 4242 if running else 0,
            "cpu": {"usage": self.st.cpu_ns if running else 0},
            "memory": {"usage": 256 * 1024 ** 2 if running else 0, "swap_usage": 0},
            "disk": {"root": {"usage": 1024 ** 3}},
            "network": network,
        }

    def instances(self, method: str, rest: List[str], q: Dict[str, str]) -> None:  # noqa: C901
        st = self.st
        recursion = int(q.get("recursion", "0"))
        if not rest:
            if method == "GET":
                with st.lock:
                    items = list(st.instances.values())
                if recursion:
                    return self.sync([self.full(i, recursion - 1 if recursion == 1 else recursion) for i in items])
                return self.sync(["/1.0/instances/%s" % i["name"] for i in items])
            if method == "POST":
                if (self.headers.get("Content-Type") or "").startswith("application/octet-stream"):
                    raw = self.body()
                    name = self.headers.get("X-Incus-name")
                    payload = json.loads(raw.decode().split(":", 2)[2])
                    payload["name"] = name
                    payload["status"] = "Stopped"
                    st.instances[name] = payload
                    return self.async_op({})
                body = self.body()
                st.create_calls.append(body)
                name = body["name"]
                if name in st.instances:
                    return self.async_op(None, "Instance %s already exists" % name)
                src = body.get("source") or {}
                if src.get("mode") != "pull" and src.get("alias") not in st.images:
                    return self.async_op(None, "Image not found")
                config = dict(body.get("config") or {})
                config["volatile.uuid"] = str(uuid.uuid4())
                config["image.os"] = "debian"
                st.instances[name] = {
                    "name": name, "type": body.get("type", "container"), "status": "Stopped",
                    "config": config, "devices": body.get("devices") or {}, "profiles": body.get("profiles", []),
                    "architecture": "x86_64", "ephemeral": False, "stateful": False,
                    "description": body.get("description", ""), "created_at": _now(), "last_used_at": "0001-01-01T00:00:00Z",
                }
                return self.async_op({})
        name = rest[0]
        if name not in st.instances:
            return self.error(404, "Instance not found")
        inst = st.instances[name]
        sub = rest[1:]
        if not sub:
            if method == "GET":
                return self.sync(self.full(inst, recursion))
            if method == "PUT":
                body = self.body()
                if "restore" in body:
                    st.restores.append((name, body["restore"]))
                    return self.async_op({})
                missing = [k for k in inst["config"] if k.startswith("volatile.") and k not in body.get("config", {})]
                if missing:
                    return self.error(400, "Volatile keys missing from update: %s" % missing)
                if st.routed_conflicts:
                    for other in st.instances.values():
                        if other["name"] == name:
                            continue
                        used = {d.get("ipv4.address") for d in other["devices"].values() if d.get("nictype") == "routed"}
                        for dev in body.get("devices", {}).values():
                            if dev.get("nictype") == "routed" and dev.get("ipv4.address") in used:
                                return self.error(400, "IP address %s already in use" % dev["ipv4.address"])
                inst["config"] = body["config"]
                inst["devices"] = body["devices"]
                inst["profiles"] = body.get("profiles", [])
                return self.async_op({})
            if method == "DELETE":
                if inst["status"] != "Stopped":
                    return self.async_op(None, "Instance is running")
                del st.instances[name]
                st.snapshots.pop(name, None)
                return self.async_op({})
        if sub == ["state"]:
            if method == "GET":
                return self.sync(self.state_of(inst))
            body = self.body()
            action = body["action"]
            if action == "start":
                if st.reject_raw_qemu_start and "raw.qemu" in inst["config"]:
                    return self.async_op(None, "QEMU failed to start: invalid -vnc option")
                inst["status"] = "Running"
                inst["last_used_at"] = _now()
            elif action == "stop":
                inst["status"] = "Stopped"
            elif action == "restart":
                inst["status"] = "Running"
            elif action == "freeze":
                inst["status"] = "Frozen"
            elif action == "unfreeze":
                inst["status"] = "Running"
            return self.async_op({})
        if sub == ["exec"]:
            body = self.body()
            st.exec_calls.append({"name": name, **body})
            out_id = uuid.uuid4().hex
            st.logs["/1.0/instances/%s/logs/exec_%s.stdout" % (name, out_id)] = "ok\n"
            st.logs["/1.0/instances/%s/logs/exec_%s.stderr" % (name, out_id)] = ""
            return self.async_op({"return": 0, "output": {
                "1": "/1.0/instances/%s/logs/exec_%s.stdout" % (name, out_id),
                "2": "/1.0/instances/%s/logs/exec_%s.stderr" % (name, out_id)}})
        if sub[:1] == ["logs"]:
            path = "/1.0/instances/%s/%s" % (name, "/".join(sub))
            if method == "DELETE":
                st.logs.pop(path, None)
                return self.sync({})
            return self._write(200, None, st.logs.get(path, "").encode(), "application/octet-stream")
        if sub[:1] == ["snapshots"]:
            snaps = st.snapshots.setdefault(name, [])
            if len(sub) == 1 and method == "GET":
                return self.sync(snaps)
            if len(sub) == 1 and method == "POST":
                body = self.body()
                snaps.append({"name": body["name"], "created_at": _now(), "config": dict(inst["config"])})
                return self.async_op({})
            if len(sub) == 2 and method == "DELETE":
                st.snapshots[name] = [s for s in snaps if s["name"] != sub[1]]
                return self.async_op({})
        if sub[:1] == ["backups"]:
            if len(sub) == 1 and method == "POST":
                body = self.body()
                st.backups["%s/%s" % (name, body["name"])] = json.loads(json.dumps(inst))
                return self.async_op({})
            key = "%s/%s" % (name, sub[1])
            if len(sub) == 3 and sub[2] == "export":
                snapshot = st.backups[key]
                payload = {k: snapshot[k] for k in ("type", "config", "devices", "profiles", "architecture")}
                return self._write(200, None, ("FAKEBACKUP:%s:%s" % (name, json.dumps(payload))).encode(), "application/octet-stream")
            if len(sub) == 2 and method == "DELETE":
                st.backups.pop(key, None)
                return self.async_op({})
        return self.error(404, "unknown instance path %s" % sub)


class _UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class FakeIncus:
    def __init__(self, socket_path: str):
        self.socket_path = socket_path
        if os.path.exists(socket_path):
            os.unlink(socket_path)
        self.server = _UnixServer(socket_path, Handler)
        self.state = FakeIncusState()
        self.server.state = self.state  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> "FakeIncus":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
