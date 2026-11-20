"""Node configuration (/etc/orvex-node/config.json) and the template catalog."""

from __future__ import annotations

import copy
import ipaddress
import os
import re
import socket
from typing import Any, Dict, List, Optional

from .util import LOG, read_json, write_json_atomic

DEFAULT_CONFIG_PATH = "/etc/orvex-node/config.json"

IMAGE_SERVER = "https://images.linuxcontainers.org"

DEFAULTS: Dict[str, Any] = {
    # Name reported as the Proxmox node name ("pve_node" in the panel).
    "node_name": "",
    "listen": "0.0.0.0",
    "port": 8006,
    "tls_cert": "/etc/orvex-node/tls/cert.pem",
    "tls_key": "/etc/orvex-node/tls/key.pem",
    # API token. In the panel: User = api_user, Token ID = api_token_id,
    # Secret = api_token_secret. The "@orvex" realm marks the node as an OrveX
    # node for the panel (Proxmox has no such realm).
    "api_user": "orvex@orvex",
    "api_token_id": "panel",
    "api_token_secret": "",
    "incus_socket": "/var/lib/incus/unix.socket",
    "storage_pool": "default",
    "state_dir": "/var/lib/orvex-node",
    "backup_dir": "/var/lib/orvex-node/backups",
    "templates_file": "/etc/orvex-node/templates.json",
    # Public IPv4 of the node: listen address for shared-IPv4 (NAT) forwards
    # and the SSH host shown to users of NAT instances.
    "public_ipv4": "",
    # Host interface that carries dedicated IPv4 addresses (routed NICs).
    "uplink_interface": "",
    # Pseudo bridge names shown to the panel.
    "routed_bridge": "orvexpub0",
    "nat": {
        "network": "orvexnat0",
        "subnet": "10.77.0.0/24",
        "gateway": "10.77.0.1",
        "ssh_port_base": 22000,
        "port_range_base": 30000,
        "port_range_size": 20,
        # Address the forwards listen on. Empty: public_ipv4 when it is assigned
        # to this host, otherwise the default-route source address (1:1 NAT clouds).
        "listen_address": "",
    },
    "nameservers": ["1.1.1.1", "8.8.8.8"],
    # Graphical console for KVM guests (QEMU VNC on 127.0.0.1, proxied by the
    # node API). Display numbers start here (port = 5900 + display).
    "vnc_enabled": True,
    "vnc_display_base": 100,
    "metrics_interval": 10,
    "log_level": "INFO",
    # IDs used for templates are never handed out to instances.
    "vmid_min": 100,
}

DEFAULT_TEMPLATES: List[Dict[str, Any]] = [
    {"vmid": 9000, "name": "ubuntu-24.04-kvm", "type": "qemu", "image": "ubuntu/24.04/cloud", "description": "Ubuntu 24.04 LTS (KVM)", "default_user": "ubuntu", "disk_gb": 10},
    {"vmid": 9001, "name": "ubuntu-22.04-kvm", "type": "qemu", "image": "ubuntu/22.04/cloud", "description": "Ubuntu 22.04 LTS (KVM)", "default_user": "ubuntu", "disk_gb": 10},
    {"vmid": 9002, "name": "debian-12-kvm", "type": "qemu", "image": "debian/12/cloud", "description": "Debian 12 (KVM)", "default_user": "debian", "disk_gb": 10},
    {"vmid": 9003, "name": "debian-13-kvm", "type": "qemu", "image": "debian/13/cloud", "description": "Debian 13 (KVM)", "default_user": "debian", "disk_gb": 10},
    {"vmid": 9004, "name": "rockylinux-9-kvm", "type": "qemu", "image": "rockylinux/9/cloud", "description": "Rocky Linux 9 (KVM)", "default_user": "rocky", "disk_gb": 10},
    {"vmid": 9005, "name": "almalinux-9-kvm", "type": "qemu", "image": "almalinux/9/cloud", "description": "AlmaLinux 9 (KVM)", "default_user": "almalinux", "disk_gb": 10},
    {"vmid": 9100, "name": "ubuntu-24.04-lxc", "type": "lxc", "image": "ubuntu/24.04/cloud", "description": "Ubuntu 24.04 LTS (LXC)", "disk_gb": 8},
    {"vmid": 9101, "name": "ubuntu-22.04-lxc", "type": "lxc", "image": "ubuntu/22.04/cloud", "description": "Ubuntu 22.04 LTS (LXC)", "disk_gb": 8},
    {"vmid": 9102, "name": "debian-12-lxc", "type": "lxc", "image": "debian/12/cloud", "description": "Debian 12 (LXC)", "disk_gb": 8},
    {"vmid": 9103, "name": "debian-13-lxc", "type": "lxc", "image": "debian/13/cloud", "description": "Debian 13 (LXC)", "disk_gb": 8},
    {"vmid": 9104, "name": "rockylinux-9-lxc", "type": "lxc", "image": "rockylinux/9/cloud", "description": "Rocky Linux 9 (LXC)", "disk_gb": 8},
    {"vmid": 9105, "name": "almalinux-9-lxc", "type": "lxc", "image": "almalinux/9/cloud", "description": "AlmaLinux 9 (LXC)", "disk_gb": 8},
    {"vmid": 9106, "name": "alpine-3.20-lxc", "type": "lxc", "image": "alpine/3.20/cloud", "description": "Alpine Linux 3.20 (LXC)", "disk_gb": 4},
]

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    def __init__(self, data: Dict[str, Any], path: Optional[str] = None):
        self.path = path
        self.data = _deep_merge(DEFAULTS, data)
        if not self.data.get("node_name"):
            self.data["node_name"] = re.sub(r"[^a-z0-9-]", "-", socket.gethostname().split(".")[0].lower()) or "orvex"
        self.validate()

    # ------------------------------------------------------------------ io
    @classmethod
    def load(cls, path: Optional[str] = None) -> "Config":
        path = path or os.environ.get("ORVEX_NODE_CONFIG") or DEFAULT_CONFIG_PATH
        data = read_json(path, {})
        if not isinstance(data, dict):
            raise ValueError("%s must contain a JSON object" % path)
        return cls(data, path)

    def save(self) -> None:
        if not self.path:
            raise ValueError("config has no path")
        write_json_atomic(self.path, self.data)

    # ---------------------------------------------------------- validation
    def validate(self) -> None:
        nat = self.data["nat"]
        net = ipaddress.IPv4Network(str(nat["subnet"]), strict=False)
        gateway = ipaddress.IPv4Address(str(nat["gateway"]))
        if gateway not in net:
            raise ValueError("nat.gateway %s is not inside nat.subnet %s" % (gateway, net))
        nat["subnet"] = str(net)
        max_index = net.num_addresses - 1
        ssh_top = int(nat["ssh_port_base"]) + max_index
        range_top = int(nat["port_range_base"]) + max_index * int(nat["port_range_size"]) + int(nat["port_range_size"]) - 1
        if int(nat["port_range_size"]) < 0:
            raise ValueError("nat.port_range_size must be >= 0")
        if ssh_top > 65535 or range_top > 65535:
            raise ValueError("NAT port ranges exceed 65535: use a smaller nat.subnet or port_range_size")
        ssh_low, ssh_high = int(nat["ssh_port_base"]), ssh_top
        rng_low, rng_high = int(nat["port_range_base"]), range_top
        if int(nat["port_range_size"]) > 0 and not (ssh_high < rng_low or rng_high < ssh_low):
            raise ValueError("nat.ssh_port_base range overlaps the nat.port_range_base range")
        if not _NAME_RE.match(str(self.data["node_name"])):
            raise ValueError("node_name must be a lowercase hostname-like string")

    # --------------------------------------------------------- properties
    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    @property
    def node_name(self) -> str:
        return str(self.data["node_name"])

    @property
    def nat(self) -> Dict[str, Any]:
        return self.data["nat"]

    @property
    def nat_network(self) -> ipaddress.IPv4Network:
        return ipaddress.IPv4Network(self.data["nat"]["subnet"])

    @property
    def nat_bridge(self) -> str:
        return str(self.data["nat"]["network"])

    @property
    def routed_bridge(self) -> str:
        return str(self.data["routed_bridge"])

    @property
    def token_header_value(self) -> str:
        return "%s!%s=%s" % (self.data["api_user"], self.data["api_token_id"], self.data["api_token_secret"])


def load_templates(path: Optional[str]) -> List[Dict[str, Any]]:
    """Load and validate the template catalog. Falls back to the defaults."""
    raw = read_json(path, None) if path else None
    if raw is None:
        raw = DEFAULT_TEMPLATES
    if not isinstance(raw, list):
        LOG.warning("templates file %s is not a JSON list; using defaults", path)
        raw = DEFAULT_TEMPLATES
    templates: List[Dict[str, Any]] = []
    seen = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            vmid = int(entry["vmid"])
        except (KeyError, TypeError, ValueError):
            LOG.warning("skipping template without a numeric vmid: %r", entry)
            continue
        vm_type = "lxc" if str(entry.get("type", "qemu")).lower() in ("lxc", "container") else "qemu"
        name = str(entry.get("name") or ("template-%d" % vmid))
        image = str(entry.get("image") or "").strip()
        if not image or vmid in seen:
            LOG.warning("skipping invalid or duplicate template %r", entry)
            continue
        seen.add(vmid)
        templates.append({
            "vmid": vmid,
            "name": name,
            "type": vm_type,
            "image": image,
            "server": str(entry.get("server") or IMAGE_SERVER),
            "protocol": str(entry.get("protocol") or "simplestreams"),
            "description": str(entry.get("description") or name),
            "default_user": str(entry.get("default_user") or ("root" if vm_type == "lxc" else "admin")),
            "disk_gb": int(entry.get("disk_gb") or (8 if vm_type == "lxc" else 10)),
            # Local alias used when the image was pre-downloaded by the installer.
            "local_alias": str(entry.get("local_alias") or ("orvex-" + name)),
        })
    return sorted(templates, key=lambda t: t["vmid"])
