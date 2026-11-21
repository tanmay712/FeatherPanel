"""Minimal Incus REST client over the local unix socket (stdlib only)."""

from __future__ import annotations

import http.client
import json
import socket
import time
import urllib.parse
from typing import Any, BinaryIO, Dict, Iterable, List, Optional, Tuple

from .util import LOG


class IncusError(Exception):
    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status
        self.message = message

    @property
    def not_found(self) -> bool:
        return self.status == 404


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float):
        super().__init__("incus", timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:  # noqa: D401 - http.client API
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._socket_path)
        self.sock = sock


def quote(segment: str) -> str:
    return urllib.parse.quote(str(segment), safe="")


class IncusClient:
    """Thread-safe: every call opens its own connection."""

    def __init__(self, socket_path: str, timeout: float = 60.0):
        self.socket_path = socket_path
        self.timeout = timeout

    # ----------------------------------------------------------- transport
    def _connection(self, timeout: Optional[float] = None) -> _UnixHTTPConnection:
        return _UnixHTTPConnection(self.socket_path, timeout or self.timeout)

    def raw(
        self,
        method: str,
        path: str,
        body: Any = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
        stream: Optional[BinaryIO] = None,
        stream_length: Optional[int] = None,
    ) -> Tuple[int, Dict[str, str], bytes]:
        conn = self._connection(timeout)
        try:
            hdrs = dict(headers or {})
            payload: Any = None
            if stream is not None:
                payload = stream
                if stream_length is not None:
                    hdrs["Content-Length"] = str(stream_length)
                hdrs.setdefault("Content-Type", "application/octet-stream")
            elif body is not None:
                payload = json.dumps(body).encode("utf-8")
                hdrs.setdefault("Content-Type", "application/json")
            conn.request(method, path, body=payload, headers=hdrs)
            resp = conn.getresponse()
            data = resp.read()
            return resp.status, {k.lower(): v for k, v in resp.getheaders()}, data
        except (OSError, http.client.HTTPException) as exc:
            raise IncusError("Incus is unreachable on %s: %s" % (self.socket_path, exc), 503) from exc
        finally:
            conn.close()

    def request(self, method: str, path: str, body: Any = None, **kwargs: Any) -> Dict[str, Any]:
        status, _headers, data = self.raw(method, path, body, **kwargs)
        try:
            doc = json.loads(data.decode("utf-8") or "{}")
        except ValueError as exc:
            raise IncusError("invalid JSON from Incus for %s %s (HTTP %d)" % (method, path, status), status) from exc
        if doc.get("type") == "error" or status >= 400:
            message = doc.get("error") or ("HTTP %d" % status)
            code = int(doc.get("error_code") or status or 500)
            raise IncusError(str(message), code)
        return doc

    def query(self, method: str, path: str, body: Any = None, wait: bool = True, timeout: float = 600, **kwargs: Any) -> Any:
        """Perform a request; wait for async operations and return their metadata."""
        doc = self.request(method, path, body, **kwargs)
        if doc.get("type") == "async":
            op_path = doc.get("operation") or ""
            if not wait:
                return doc.get("metadata")
            return self.wait(op_path, timeout)
        return doc.get("metadata")

    def wait(self, op_path: str, timeout: float = 600) -> Any:
        if not op_path:
            raise IncusError("async response without operation", 500)
        deadline = time.time() + timeout
        while True:
            remaining = max(1, int(min(60, deadline - time.time())))
            doc = self.request("GET", "%s/wait?timeout=%d" % (op_path, remaining), timeout=remaining + 15)
            op = doc.get("metadata") or {}
            status = str(op.get("status", ""))
            if status == "Success":
                return op.get("metadata") or {}
            if status in ("Failure", "Cancelled"):
                raise IncusError(str(op.get("err") or "operation failed"), int(op.get("status_code") or 500))
            if time.time() >= deadline:
                raise IncusError("timed out waiting for Incus operation %s" % op_path, 504)

    # ----------------------------------------------------------- instances
    def instances(self, recursion: int = 1) -> List[Dict[str, Any]]:
        return self.query("GET", "/1.0/instances?recursion=%d" % recursion) or []

    def instance(self, name: str, recursion: int = 0) -> Dict[str, Any]:
        suffix = "?recursion=%d" % recursion if recursion else ""
        return self.query("GET", "/1.0/instances/%s%s" % (quote(name), suffix))

    def instance_state(self, name: str) -> Dict[str, Any]:
        return self.query("GET", "/1.0/instances/%s/state" % quote(name)) or {}

    def create_instance(self, payload: Dict[str, Any], timeout: float = 3600) -> Any:
        return self.query("POST", "/1.0/instances", payload, timeout=timeout)

    def put_instance(self, name: str, inst: Dict[str, Any], timeout: float = 600) -> Any:
        body = {
            "architecture": inst.get("architecture", ""),
            "config": inst.get("config", {}),
            "devices": inst.get("devices", {}),
            "ephemeral": bool(inst.get("ephemeral", False)),
            "profiles": inst.get("profiles", []),
            "stateful": bool(inst.get("stateful", False)),
            "description": inst.get("description", ""),
        }
        return self.query("PUT", "/1.0/instances/%s" % quote(name), body, timeout=timeout)

    def set_state(self, name: str, action: str, timeout: int = 30, force: bool = False) -> Any:
        body = {"action": action, "timeout": timeout, "force": force, "stateful": False}
        return self.query("PUT", "/1.0/instances/%s/state" % quote(name), body, timeout=max(120, timeout + 60))

    def delete_instance(self, name: str) -> Any:
        return self.query("DELETE", "/1.0/instances/%s" % quote(name), timeout=900)

    def exec(
        self,
        name: str,
        command: List[str],
        environment: Optional[Dict[str, str]] = None,
        timeout: float = 120,
    ) -> Tuple[int, str, str]:
        body = {
            "command": command,
            "environment": environment or {},
            "wait-for-websocket": False,
            "interactive": False,
            "record-output": True,
            "width": 80,
            "height": 25,
        }
        meta = self.query("POST", "/1.0/instances/%s/exec" % quote(name), body, timeout=timeout) or {}
        code = int(meta.get("return", -1))
        output = meta.get("output") or {}
        stdout = self._read_log(output.get("1"))
        stderr = self._read_log(output.get("2"))
        return code, stdout, stderr

    def _read_log(self, path: Optional[str]) -> str:
        if not path:
            return ""
        try:
            status, _h, data = self.raw("GET", path)
            if status >= 400:
                return ""
            text = data.decode("utf-8", "replace")
            try:  # remove the recorded log file again (best effort)
                self.raw("DELETE", path)
            except IncusError:
                pass
            return text
        except IncusError:
            return ""

    # ----------------------------------------------------------- snapshots
    def snapshots(self, name: str) -> List[Dict[str, Any]]:
        return self.query("GET", "/1.0/instances/%s/snapshots?recursion=1" % quote(name)) or []

    def create_snapshot(self, name: str, snap: str, stateful: bool = False) -> Any:
        return self.query("POST", "/1.0/instances/%s/snapshots" % quote(name), {"name": snap, "stateful": stateful})

    def delete_snapshot(self, name: str, snap: str) -> Any:
        return self.query("DELETE", "/1.0/instances/%s/snapshots/%s" % (quote(name), quote(snap)))

    def restore_snapshot(self, name: str, snap: str) -> Any:
        return self.query("PUT", "/1.0/instances/%s" % quote(name), {"restore": snap}, timeout=1800)

    # ------------------------------------------------------------- backups
    def create_backup(self, name: str, backup: str, compression: str = "zstd") -> Any:
        body = {
            "name": backup,
            "instance_only": True,
            "optimized_storage": False,
            "compression_algorithm": compression,
        }
        return self.query("POST", "/1.0/instances/%s/backups" % quote(name), body, timeout=6 * 3600)

    def export_backup(self, name: str, backup: str, dest: BinaryIO, chunk: int = 1024 * 1024) -> int:
        conn = self._connection(timeout=6 * 3600)
        written = 0
        try:
            conn.request("GET", "/1.0/instances/%s/backups/%s/export" % (quote(name), quote(backup)))
            resp = conn.getresponse()
            if resp.status >= 400:
                raise IncusError("backup export failed: HTTP %d %s" % (resp.status, resp.read()[:300]), resp.status)
            while True:
                block = resp.read(chunk)
                if not block:
                    break
                dest.write(block)
                written += len(block)
        except (OSError, http.client.HTTPException) as exc:
            raise IncusError("backup export failed: %s" % exc, 503) from exc
        finally:
            conn.close()
        return written

    def delete_backup(self, name: str, backup: str) -> Any:
        return self.query("DELETE", "/1.0/instances/%s/backups/%s" % (quote(name), quote(backup)))

    def import_backup(self, name: str, pool: str, stream: BinaryIO, length: int) -> Any:
        headers = {"X-Incus-name": name, "X-Incus-pool": pool}
        doc = self.request(
            "POST", "/1.0/instances", headers=headers, stream=stream, stream_length=length, timeout=6 * 3600
        )
        if doc.get("type") == "async":
            return self.wait(doc.get("operation") or "", timeout=6 * 3600)
        return doc.get("metadata")

    # ---------------------------------------------------------- host level
    def server(self) -> Dict[str, Any]:
        return self.query("GET", "/1.0") or {}

    def resources(self) -> Dict[str, Any]:
        return self.query("GET", "/1.0/resources") or {}

    def pools(self) -> List[Dict[str, Any]]:
        return self.query("GET", "/1.0/storage-pools?recursion=1") or []

    def pool_resources(self, pool: str) -> Dict[str, Any]:
        return self.query("GET", "/1.0/storage-pools/%s/resources" % quote(pool)) or {}

    def networks(self) -> List[Dict[str, Any]]:
        return self.query("GET", "/1.0/networks?recursion=1") or []

    def forwards(self, network: str) -> List[Dict[str, Any]]:
        return self.query("GET", "/1.0/networks/%s/forwards?recursion=1" % quote(network)) or []

    def put_forward(self, network: str, listen: str, ports: Iterable[Dict[str, Any]], description: str) -> None:
        body = {"description": description, "config": {}, "ports": list(ports)}
        try:
            self.query("PUT", "/1.0/networks/%s/forwards/%s" % (quote(network), quote(listen)), body)
        except IncusError as exc:
            if not exc.not_found:
                raise
            body["listen_address"] = listen
            self.query("POST", "/1.0/networks/%s/forwards" % quote(network), body)

    def delete_forward(self, network: str, listen: str) -> None:
        try:
            self.query("DELETE", "/1.0/networks/%s/forwards/%s" % (quote(network), quote(listen)))
        except IncusError as exc:
            if not exc.not_found:
                raise

    def image_alias_exists(self, alias: str) -> bool:
        try:
            self.query("GET", "/1.0/images/aliases/%s" % quote(alias))
            return True
        except IncusError as exc:
            if exc.not_found:
                return False
            raise

    def metrics_text(self) -> str:
        status, _headers, data = self.raw("GET", "/1.0/metrics", timeout=30)
        if status >= 400:
            raise IncusError("metrics unavailable (HTTP %d)" % status, status)
        return data.decode("utf-8", "replace")

    def ping(self) -> bool:
        try:
            self.server()
            return True
        except IncusError as exc:
            LOG.debug("incus ping failed: %s", exc)
            return False
