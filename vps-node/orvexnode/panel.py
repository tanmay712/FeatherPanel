"""Connecting the node to OrveX Panel (`orvex-node register`).

The admin creates an OrveX node in the panel and gets a one-time token. With it the
node registers itself: it tells the panel how to reach it (address, port, API token)
and what it offers (templates, storage, shared-IPv4 network). The same node report is
served at /nodes/{node}/orvex/info for "Sync from node" in the panel.
"""

from __future__ import annotations

import json
import os
import platform
import re
import socket
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from . import __version__
from .config import load_templates
from .util import read_json, write_json_atomic

TOKEN_RE = re.compile(r"^orvx_[1-9][0-9]{0,9}_[A-Za-z0-9]{48}$")
REGISTER_PATH = "/api/remote/orvex/register"
BACKUP_STORAGE = "backups"


class PanelError(Exception):
    """Registration failed; the message is meant for the person running the command."""


def normalize_panel_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not re.match(r"^https?://[^\s/?#]+(?:/[^\s?#]*)?$", url):
        raise PanelError("the panel URL must look like https://panel.example.com")
    return url


def _os_name() -> str:
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.system()


def _memory_mb() -> int:
    try:
        with open("/proc/meminfo", "r", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


def host_facts() -> Dict[str, Any]:
    from .server import cpu_model

    return {
        "hostname": socket.getfqdn() or socket.gethostname(),
        "os": _os_name(),
        "kernel": platform.release(),
        "cpu": cpu_model(),
        "cpus": os.cpu_count() or 0,
        "memory_mb": _memory_mb(),
    }


def node_report(cfg: Any, net: Any) -> Dict[str, Any]:
    """What the node offers: templates, storage, networking and host facts."""
    from .server import cert_fingerprint

    nat = cfg.nat
    return {
        "node_name": cfg.node_name,
        "agent_version": __version__,
        "public_ipv4": net.public_ipv4() or None,
        "tls_fingerprint": cert_fingerprint(cfg["tls_cert"]) or None,
        "kvm": os.path.exists("/dev/kvm"),
        "storage_pool": str(cfg["storage_pool"]),
        "backup_storage": BACKUP_STORAGE,
        "routed_bridge": cfg.routed_bridge,
        "nat_bridge": cfg.nat_bridge,
        "nat": {
            "subnet": str(nat["subnet"]), "gateway": str(nat["gateway"]),
            "ssh_port_base": int(nat["ssh_port_base"]), "port_range_base": int(nat["port_range_base"]),
            "port_range_size": int(nat["port_range_size"]),
        },
        "templates": [
            {"vmid": t["vmid"], "name": t["name"], "type": t["type"], "description": t["description"],
             "default_user": t["default_user"], "disk_gb": t["disk_gb"]}
            for t in load_templates(cfg.get("templates_file"))
        ],
        "host": host_facts(),
    }


def registration_payload(cfg: Any, net: Any, address: Optional[str] = None) -> Dict[str, Any]:
    payload = node_report(cfg, net)
    payload.update({
        "address": (address or payload.get("public_ipv4") or "").strip(),
        "port": int(cfg["port"]),
        "scheme": "https",
        "api_user": cfg["api_user"],
        "api_token_id": cfg["api_token_id"],
        "api_token_secret": cfg["api_token_secret"],
    })
    return payload


def post_registration(panel_url: str, token: str, payload: Dict[str, Any], insecure: bool = False,
                      timeout: float = 90.0) -> Dict[str, Any]:
    """POST the registration; returns the panel's `data` object or raises PanelError."""
    url = normalize_panel_url(panel_url) + REGISTER_PATH
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": "Bearer " + token,
        "User-Agent": "OrveX-Node/" + __version__,
    })
    context = None
    if url.startswith("https://"):
        context = ssl.create_default_context()
        if insecure:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise PanelError("the panel's TLS certificate is not trusted (%s). Fix the certificate or add --insecure"
                             % (reason.verify_message or reason))
        raise PanelError("could not reach the panel at %s: %s" % (normalize_panel_url(panel_url), reason))
    except (socket.timeout, OSError) as exc:
        raise PanelError("could not reach the panel at %s: %s" % (normalize_panel_url(panel_url), exc))

    try:
        doc = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        doc = None
    if not isinstance(doc, dict):
        raise PanelError("the panel answered HTTP %d without JSON; is %s really OrveX Panel?" % (status, panel_url))
    if status != 200 or not doc.get("success"):
        message = str(doc.get("message") or doc.get("error_message") or "HTTP %d" % status)
        details = (doc.get("data") or {}).get("errors") if isinstance(doc.get("data"), dict) else None
        if details:
            message += " (" + "; ".join(str(d) for d in details) + ")"
        raise PanelError(message)
    data = doc.get("data")
    return data if isinstance(data, dict) else {}


def state_path(cfg: Any) -> str:
    base = os.path.dirname(cfg.path) if getattr(cfg, "path", None) else "/etc/orvex-node"
    return os.path.join(base, "panel.json")


def load_state(cfg: Any) -> Dict[str, Any]:
    data = read_json(state_path(cfg), {})
    return data if isinstance(data, dict) else {}


def save_state(cfg: Any, panel_url: str, data: Dict[str, Any]) -> None:
    import time

    node = data.get("node") if isinstance(data.get("node"), dict) else {}
    write_json_atomic(state_path(cfg), {
        "panel_url": normalize_panel_url(panel_url),
        "node_id": node.get("id"),
        "node_name": node.get("name"),
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


def register(cfg: Any, net: Any, panel_url: str, token: str, address: Optional[str] = None,
             insecure: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Register with the panel. Returns (panel response data, payload sent)."""
    token = (token or "").strip()
    if not TOKEN_RE.match(token):
        raise PanelError("this is not an OrveX install token (it starts with orvx_); copy it from the panel again")
    panel_url = normalize_panel_url(panel_url)
    payload = registration_payload(cfg, net, address)
    if not payload["address"]:
        raise PanelError("could not detect the public IPv4 of this server; pass --address")
    if not cfg["api_token_secret"]:
        raise PanelError("the node has no API token yet; run the installer or `orvex-node rotate-token` first")
    data = post_registration(panel_url, token, payload, insecure=insecure)
    save_state(cfg, panel_url, data)
    return data, payload
