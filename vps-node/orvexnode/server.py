"""HTTP(S) server exposing the Proxmox-compatible API."""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import ssl
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple

from .api import RAW, Api, Ctx
from .backups import BackupService
from .config import Config, load_templates
from .incus import IncusClient, IncusError
from .instances import InstanceService
from .metrics import MetricsCollector
from .network import NetworkManager
from .store import Store
from .tasks import TaskManager
from .util import LOG, PveError
from .vnc import VncService, pump, websocket_accept

MAX_BODY = 4 * 1024 * 1024


def cert_fingerprint(pem_path: str) -> str:
    try:
        with open(pem_path, "r", encoding="ascii") as handle:
            der = ssl.PEM_cert_to_DER_cert(handle.read())
    except (OSError, ValueError):
        return ""
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return "unknown"


class App:
    """Service container shared by all request threads."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        state_dir = str(cfg["state_dir"])
        os.makedirs(state_dir, exist_ok=True)
        self.incus = IncusClient(str(cfg["incus_socket"]))
        self.store = Store(state_dir)
        self.tasks = TaskManager(cfg.node_name, state_dir)
        self.net = NetworkManager(cfg, self.incus)
        self.templates = load_templates(cfg.get("templates_file"))
        self.instances = InstanceService(cfg, self.incus, self.tasks, self.store, self.net, self.templates)
        self.metrics = MetricsCollector(cfg, self.incus, state_dir, uplink=self.net.uplink())
        self.instances.metrics = self.metrics
        self.backups = BackupService(cfg, self.incus, self.tasks, self.instances)
        cert_path = str(cfg.get("tls_cert") or "")
        cert_pem = ""
        if cert_path and os.path.exists(cert_path):
            with open(cert_path, "r", encoding="ascii") as handle:
                cert_pem = handle.read()
        self.cert_fingerprint = cert_fingerprint(cert_path) if cert_pem else ""
        self.cpu_model = cpu_model()
        self.vnc = VncService(cfg, self.instances, cert_pem)
        self.api = Api(self)

    def start_background(self) -> None:
        self.metrics.start()

    def stop_background(self) -> None:
        self.metrics.stop()


class Handler(BaseHTTPRequestHandler):
    server_version = "pve-api-daemon/3.0"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    @property
    def app(self) -> App:
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:  # silence default logging
        return

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    # ------------------------------------------------------------ parse
    def _params(self, method: str, query: str) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        for key, value in urllib.parse.parse_qsl(query, keep_blank_values=True):
            params[key] = value
        if method in ("POST", "PUT"):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise PveError(413, "request entity too large")
            body = self.rfile.read(length) if length > 0 else b""
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if body:
                if ctype == "application/json":
                    try:
                        data = json.loads(body.decode("utf-8"))
                    except ValueError:
                        raise PveError(400, "invalid JSON body")
                    if isinstance(data, dict):
                        params.update(data)
                elif ctype in ("application/x-www-form-urlencoded", ""):
                    for key, value in urllib.parse.parse_qsl(body.decode("utf-8"), keep_blank_values=True):
                        params[key] = value
                else:
                    raise PveError(415, "unsupported content type '%s'" % ctype)
        return params

    def _cookie_ticket(self) -> Optional[str]:
        raw = self.headers.get("Cookie") or ""
        match = re.search(r"(?:^|;\s*)PVEAuthCookie=([^;]+)", raw)
        return urllib.parse.unquote(match.group(1)) if match else None

    # --------------------------------------------------------- dispatch
    def _dispatch(self, method: str) -> None:
        started = time.time()
        status = 200
        split = urllib.parse.urlsplit(self.path)
        raw_parts = split.path.split("/")
        fmt = raw_parts[2] if len(raw_parts) > 2 else ""
        try:
            if len(raw_parts) < 3 or raw_parts[1] != "api2" or fmt not in ("json", "extjs"):
                raise PveError(404, "Not Found")
            segments = [urllib.parse.unquote(p) for p in raw_parts[3:] if p != ""]
            route, args = self.app.api.match(method, segments)
            if route is None:
                raise PveError(501, "Method '%s /%s' not implemented" % (method, "/".join(segments)))
            user = self.app.api.authenticate(self.headers.get("Authorization") or "", self._cookie_ticket())
            if route.auth and user is None:
                raise PveError(401, "authentication failure")
            params = self._params(method, split.query)
            result = route.handler(Ctx(self.app, method, args, params, user or "", self))
            if result is RAW:
                status = 101
                return
            payload: Dict[str, Any] = {"data": result}
            if fmt == "extjs":
                payload["success"] = 1
            self._send(200, "OK", payload)
        except PveError as exc:
            status = exc.status
            self._send_error(exc, fmt)
        except IncusError as exc:
            status = 500
            self._send_error(PveError(500, exc.message), fmt)
        except Exception as exc:  # noqa: BLE001
            status = 500
            LOG.error("unhandled error for %s %s: %s\n%s", method, split.path, exc, traceback.format_exc())
            self._send_error(PveError(500, "internal error: %s" % exc), fmt)
        finally:
            LOG.info('%s "%s %s" %d %.0fms', self.client_address[0], method, split.path, status, (time.time() - started) * 1000)

    def _send(self, code: int, reason: str, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code, reason)
        self.send_header("Content-Type", "application/json;charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, exc: PveError, fmt: str) -> None:
        reason = re.sub(r"[^\x20-\x7e]", " ", exc.message.splitlines()[0] if exc.message else "error")[:200]
        payload: Dict[str, Any] = {"data": None, "message": exc.message + "\n"}
        if exc.errors:
            payload["errors"] = exc.errors
        if fmt == "extjs":
            payload["success"] = 0
        try:
            self._send(exc.status, reason, payload)
        except OSError:
            pass

    # --------------------------------------------------------- websocket
    def upgrade_websocket(self, port: int) -> None:
        key = self.headers.get("Sec-WebSocket-Key") or ""
        if (self.headers.get("Upgrade") or "").lower() != "websocket" or not key:
            raise PveError(400, "websocket upgrade required")
        offered = [p.strip() for p in (self.headers.get("Sec-WebSocket-Protocol") or "").split(",") if p.strip()]
        chosen = "binary" if "binary" in offered else ("base64" if "base64" in offered else (offered[0] if offered else None))
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", websocket_accept(key))
        if chosen:
            self.send_header("Sec-WebSocket-Protocol", chosen)
        self.end_headers()
        self.wfile.flush()
        self.close_connection = True
        self.connection.settimeout(None)
        pump(self.connection, port, text_mode=(chosen == "base64"))


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: Tuple[str, int], app: App, ssl_context: Optional[ssl.SSLContext] = None):
        self.app = app
        self.ssl_context = ssl_context
        family = socket.AF_INET6 if ":" in address[0] else socket.AF_INET
        self.address_family = family
        super().__init__(address, Handler)

    def finish_request(self, request: Any, client_address: Any) -> None:
        # TLS handshake happens here, in the worker thread, so a slow client
        # can never block the accept loop.
        if self.ssl_context is not None:
            request.settimeout(30)
            try:
                request = self.ssl_context.wrap_socket(request, server_side=True)
            except (ssl.SSLError, OSError) as exc:
                LOG.debug("TLS handshake with %s failed: %s", client_address[0], exc)
                return
            request.settimeout(300)
            try:
                self.RequestHandlerClass(request, client_address, self)
            finally:
                try:
                    request.close()
                except OSError:
                    pass
            return
        request.settimeout(300)
        self.RequestHandlerClass(request, client_address, self)


def make_ssl_context(cert: str, key: str) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)
    return context


def serve(cfg: Config) -> None:
    app = App(cfg)
    if not cfg["api_token_secret"]:
        raise SystemExit("api_token_secret is empty: run `orvex-node rotate-token` first")
    context = None
    if cfg.get("tls_cert") and cfg.get("tls_key") and os.path.exists(cfg["tls_cert"]):
        context = make_ssl_context(cfg["tls_cert"], cfg["tls_key"])
    else:
        LOG.warning("TLS certificate missing: serving plain HTTP (not recommended)")
    if not app.incus.ping():
        LOG.warning("Incus is not reachable on %s yet; requests will fail until it is", cfg["incus_socket"])
    server = Server((str(cfg["listen"]), int(cfg["port"])), app, context)
    app.start_background()
    threading.Thread(target=app.instances.sync_forwards, name="initial-forward-sync", daemon=True).start()
    LOG.info("OrveX VPS Node listening on %s:%s (node %s)", cfg["listen"], cfg["port"], cfg.node_name)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        app.stop_background()
