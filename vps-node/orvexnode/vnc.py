"""Graphical console for KVM guests.

QEMU serves VNC on 127.0.0.1:<5900 + display> (configured through raw.qemu at
creation). /vncproxy hands out a short-lived ticket and /vncwebsocket bridges
an RFC 6455 websocket (noVNC in the panel) to that VNC server, exactly like
Proxmox' vncproxy/vncwebsocket pair.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import select
import socket
import struct
import threading
import time
from typing import Any, Dict, Optional, Tuple

from .util import LOG, PveError, parse_int

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TICKET_TTL = 300


class VncService:
    def __init__(self, cfg: Any, instances: Any, cert_pem: str = ""):
        self.cfg = cfg
        self.instances = instances
        self.cert_pem = cert_pem
        self._tickets: Dict[str, Tuple[int, int, float]] = {}
        self._lock = threading.Lock()

    def create_ticket(self, vmid: int, vm_type: str) -> Dict[str, Any]:
        if vm_type != "qemu":
            raise PveError(501, "The graphical console is available for KVM guests only; connect to containers over SSH.")
        inst = self.instances.get(vmid, "qemu")
        config = inst.get("config") or {}
        display = parse_int(config.get("user.orvex.vnc_display"))
        if display is None or "raw.qemu" not in config:
            raise PveError(501, "The graphical console is not enabled for VM %d." % vmid)
        if inst.get("status") != "Running":
            raise PveError(500, "VM %d not running" % vmid)
        port = 5900 + display
        ticket = "PVEVNC:%s" % secrets.token_hex(24)
        with self._lock:
            cutoff = time.time()
            for key in [k for k, v in self._tickets.items() if v[2] < cutoff]:
                del self._tickets[key]
            self._tickets[ticket] = (vmid, port, time.time() + TICKET_TTL)
        return {"port": str(port), "ticket": ticket, "user": self.cfg["api_user"], "cert": self.cert_pem}

    def check_ticket(self, vmid: int, port: Optional[int], ticket: str) -> Optional[int]:
        with self._lock:
            entry = self._tickets.get(ticket or "")
        if not entry:
            return None
        t_vmid, t_port, expires = entry
        if t_vmid != vmid or expires < time.time() or (port is not None and port != t_port):
            return None
        return t_port


def websocket_accept(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + WS_GUID).encode("ascii")).digest()).decode("ascii")


def encode_frame(payload: bytes, opcode: int = 0x2) -> bytes:
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header += struct.pack("!H", length)
    else:
        header.append(127)
        header += struct.pack("!Q", length)
    return bytes(header) + payload


class _Reader:
    def __init__(self, sock: Any):
        self.sock = sock

    def exact(self, count: int) -> bytes:
        data = b""
        while len(data) < count:
            chunk = self.sock.recv(count - len(data))
            if not chunk:
                raise ConnectionError("websocket closed")
            data += chunk
        return data

    def frame(self) -> Tuple[int, bytes, bool]:
        first, second = self.exact(2)
        fin = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self.exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self.exact(8))[0]
        if length > 16 * 1024 * 1024:
            raise ConnectionError("websocket frame too large")
        mask = self.exact(4) if masked else b""
        payload = self.exact(length) if length else b""
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload, fin


def pump(client: Any, port: int, text_mode: bool = False) -> None:
    """Bridge websocket <-> TCP in one thread (TLS sockets are not shared across threads)."""
    upstream = socket.create_connection(("127.0.0.1", port), timeout=10)
    upstream.settimeout(None)
    reader = _Reader(client)
    try:
        while True:
            pending = client.pending() if hasattr(client, "pending") else 0
            readable = [client] if pending else select.select([client, upstream], [], [], 30)[0]
            if not readable:
                client.sendall(encode_frame(b"", 0x9))  # ping keeps proxies from timing out
                continue
            if client in readable:
                opcode, payload, _fin = reader.frame()
                if opcode == 0x8:
                    try:
                        client.sendall(encode_frame(payload[:2], 0x8))
                    except OSError:
                        pass
                    return
                if opcode == 0x9:
                    client.sendall(encode_frame(payload, 0xA))
                elif opcode in (0x0, 0x1, 0x2) and payload:
                    if opcode == 0x1 and text_mode:
                        payload = base64.b64decode(payload)
                    upstream.sendall(payload)
            if upstream in readable:
                data = upstream.recv(65536)
                if not data:
                    client.sendall(encode_frame(struct.pack("!H", 1000), 0x8))
                    return
                if text_mode:
                    client.sendall(encode_frame(base64.b64encode(data), 0x1))
                else:
                    client.sendall(encode_frame(data, 0x2))
    except (ConnectionError, OSError, ValueError) as exc:
        LOG.debug("vnc bridge closed: %s", exc)
    finally:
        try:
            upstream.close()
        except OSError:
            pass
