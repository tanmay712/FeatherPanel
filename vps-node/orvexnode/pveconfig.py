"""Parsing and formatting of Proxmox VE property strings.

Examples::

    net0 (qemu)   virtio=00:16:3e:aa:bb:cc,bridge=vmbr0,rate=12.5
    net0 (lxc)    name=eth0,bridge=vmbr0,hwaddr=00:16:3e:aa:bb:cc,ip=10.0.0.5/24,gw=10.0.0.1
    ipconfig0     ip=203.0.113.10/24,gw=203.0.113.1
    scsi0         default:vm-5001-disk-0,size=20G
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple

from .util import format_size, parse_size

QEMU_NET_MODELS = (
    "virtio", "e1000", "e1000e", "rtl8139", "vmxnet3", "i82551", "i82557b", "i82559er",
    "ne2k_isa", "ne2k_pci", "pcnet",
)


def parse_props(value: Any, default_key: Optional[str] = None) -> "OrderedDict[str, str]":
    """Parse "a=1,b=2" into an ordered dict. A bare first item goes to default_key."""
    result: "OrderedDict[str, str]" = OrderedDict()
    if value is None:
        return result
    for index, part in enumerate(str(value).split(",")):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, _, val = part.partition("=")
            result[key.strip()] = val.strip()
        elif index == 0 and default_key:
            result[default_key] = part
        else:
            result[part] = ""
    return result


def format_props(props: Dict[str, Any], default_key: Optional[str] = None) -> str:
    parts = []
    for key, val in props.items():
        if val is None:
            continue
        if default_key and key == default_key:
            parts.insert(0, str(val))
        elif val == "":
            parts.append(key)
        else:
            parts.append("%s=%s" % (key, val))
    return ",".join(parts)


def parse_qemu_net(value: Any) -> Dict[str, Any]:
    props = parse_props(value)
    model = "virtio"
    mac = None
    for candidate in QEMU_NET_MODELS:
        if candidate in props:
            model = candidate
            mac = props.pop(candidate) or None
            break
    if "macaddr" in props:
        mac = props.pop("macaddr") or mac
    return {"model": model, "mac": mac, "bridge": props.pop("bridge", ""), "rate": props.pop("rate", None), "extra": props}


def format_qemu_net(model: str, mac: str, bridge: str, extra: Optional[Dict[str, str]] = None) -> str:
    props: "OrderedDict[str, Any]" = OrderedDict()
    props[model or "virtio"] = mac
    props["bridge"] = bridge or "auto"
    for key, val in (extra or {}).items():
        props[key] = val
    return format_props(props)


def parse_lxc_net(value: Any) -> Dict[str, Any]:
    props = parse_props(value)
    return {
        "name": props.pop("name", ""),
        "bridge": props.pop("bridge", ""),
        "mac": props.pop("hwaddr", None),
        "ip": props.pop("ip", None),
        "gw": props.pop("gw", None),
        "rate": props.pop("rate", None),
        "extra": props,
    }


def format_lxc_net(name: str, bridge: str, mac: str, ip: Optional[str], gw: Optional[str], extra: Optional[Dict[str, str]] = None) -> str:
    props: "OrderedDict[str, Any]" = OrderedDict()
    props["name"] = name
    props["bridge"] = bridge or "auto"
    props["hwaddr"] = mac
    if ip:
        props["ip"] = ip
    if gw:
        props["gw"] = gw
    for key, val in (extra or {}).items():
        if key not in props:
            props[key] = val
    props.setdefault("type", "veth")
    return format_props(props)


def parse_ipconfig(value: Any) -> Dict[str, str]:
    return dict(parse_props(value))


def split_cidr(value: Optional[str], default_prefix: int = 24) -> Tuple[Optional[str], int]:
    if not value:
        return None, default_prefix
    text = str(value).strip()
    if text.lower() in ("dhcp", "manual", "auto"):
        return text.lower(), default_prefix
    if "/" in text:
        ip, _, prefix = text.partition("/")
        try:
            return ip.strip(), max(0, min(32, int(prefix)))
        except ValueError:
            return ip.strip(), default_prefix
    return text, default_prefix


def disk_size(value: Any) -> int:
    """Size in bytes from a disk property string ("pool:vol,size=10G")."""
    props = parse_props(value, default_key="file")
    return parse_size(props.get("size"), "G") or 0


def with_disk_size(value: Any, num_bytes: int) -> str:
    props = parse_props(value, default_key="file")
    props["size"] = format_size(num_bytes)
    return format_props(props, default_key="file")
