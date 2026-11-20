"""Instance networking: dedicated IPv4 (routed or bridged) and shared IPv4 (NAT).

Network modes (chosen per NIC):

* ``nat``      shared IPv4. The guest gets a private address on the NAT bridge
               (default orvexnat0, 10.77.0.0/24) and the node forwards an SSH
               port plus a port range on its public IPv4 to the guest.
* ``routed``   dedicated IPv4 through an Incus "routed" NIC. Works for IPs the
               provider routes to the server, without touching host networking.
               Guest config: <ip>/32, default gateway 169.254.0.1 (on-link).
* ``bridged``  dedicated IPv4 on an existing host bridge (e.g. vmbr0/br0) with
               the provider's gateway, exactly like a Proxmox bridge.

The bridge requested by the panel decides the mode. Unknown bridge names
(like the panel default "vmbr0" when that bridge does not exist) fall back to
the IP: addresses inside the NAT subnet use NAT, everything else is routed.
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from . import pveconfig
from .incus import IncusClient, IncusError
from .util import LOG, normalize_mac, parse_size, random_mac

ROUTED_GATEWAY = "169.254.0.1"


class NicPlan:
    __slots__ = ("index", "key", "name", "mode", "ip", "prefix", "gateway", "mac", "parent", "rate_mbps", "dhcp")

    def __init__(self, **kwargs: Any):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def as_dict(self) -> Dict[str, Any]:
        return {slot: getattr(self, slot) for slot in self.__slots__}


def detect_uplink() -> str:
    """Interface of the IPv4 default route (from /proc/net/route)."""
    try:
        with open("/proc/net/route", "r", encoding="utf-8") as handle:
            for line in handle.readlines()[1:]:
                fields = line.split()
                if len(fields) > 2 and fields[1] == "00000000":
                    return fields[0]
    except OSError:
        pass
    return ""


def is_local_ipv4(address: str) -> bool:
    """True when the address is assigned to this host (binding to it works)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((address, 0))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def detect_public_ipv4() -> str:
    """Source address the host uses to reach the internet (no packet is sent)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1", 53))
        return sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()


class NetworkManager:
    def __init__(self, cfg: Any, incus: IncusClient):
        self.cfg = cfg
        self.incus = incus
        self._bridges: List[str] = []
        self._bridges_at = 0.0
        self._lock = threading.Lock()
        self._forward_lock = threading.Lock()

    # ------------------------------------------------------------- facts
    def uplink(self) -> str:
        return str(self.cfg.get("uplink_interface") or detect_uplink())

    def public_ipv4(self) -> str:
        """Address shown to users (SSH host of shared-IPv4 guests)."""
        return str(self.cfg.get("public_ipv4") or detect_public_ipv4())

    def listen_ipv4(self) -> str:
        """Address the NAT forwards listen on.

        On clouds with 1:1 NAT (AWS, GCP, Oracle...) the public IPv4 is not
        assigned to the host, so packets arrive for the local address instead.
        """
        explicit = str(self.cfg.nat.get("listen_address") or "")
        if explicit:
            return explicit
        public = str(self.cfg.get("public_ipv4") or "")
        if public and is_local_ipv4(public):
            return public
        return detect_public_ipv4() or public

    def host_bridges(self) -> List[str]:
        """Real bridges on the host usable for bridged NICs (cached 30s)."""
        with self._lock:
            if time.time() - self._bridges_at < 30:
                return list(self._bridges)
        names: List[str] = []
        try:
            for net in self.incus.networks():
                if net.get("type") == "bridge" and net.get("name") != self.cfg.nat_bridge:
                    names.append(str(net.get("name")))
        except IncusError as exc:
            LOG.warning("could not list host networks: %s", exc)
        with self._lock:
            self._bridges = sorted(set(names))
            self._bridges_at = time.time()
            return list(self._bridges)

    def bridge_list(self) -> List[Dict[str, Any]]:
        """Entries for GET /nodes/{node}/network (what the panel shows as bridges)."""
        nat = self.cfg.nat
        entries = [
            {
                "iface": self.cfg.routed_bridge, "type": "bridge", "active": 1, "autostart": 1,
                "comments": "OrveX: dedicated IPv4 (routed via %s)\n" % (self.uplink() or "default route"),
                "families": ["inet"], "method": "manual", "priority": 1,
            },
            {
                "iface": self.cfg.nat_bridge, "type": "bridge", "active": 1, "autostart": 1,
                "cidr": "%s/%d" % (nat["gateway"], self.cfg.nat_network.prefixlen),
                "address": nat["gateway"], "netmask": str(self.cfg.nat_network.netmask),
                "comments": "OrveX: shared IPv4 (NAT on %s)\n" % (self.public_ipv4() or "node IP"),
                "families": ["inet"], "method": "static", "priority": 2,
            },
        ]
        for index, name in enumerate(self.host_bridges()):
            entries.append({
                "iface": name, "type": "bridge", "active": 1, "autostart": 1,
                "comments": "Host bridge (dedicated IPv4, provider gateway)\n",
                "families": ["inet"], "method": "manual", "priority": 10 + index,
            })
        return entries

    def in_nat_subnet(self, ip: Optional[str]) -> bool:
        try:
            return ip is not None and ipaddress.IPv4Address(ip) in self.cfg.nat_network
        except (ipaddress.AddressValueError, ValueError):
            return False

    # -------------------------------------------------------------- plan
    def resolve_mode(self, bridge: str, ip: Optional[str]) -> Tuple[str, str]:
        """Return (mode, parent) for a NIC. ip is None or "dhcp" for dynamic addressing."""
        bridge = (bridge or "").strip()
        dhcp = ip is None or ip == "dhcp"
        is_private = self.in_nat_subnet(ip)
        if bridge == self.cfg.nat_bridge:
            if ip and not dhcp and not is_private:
                LOG.warning("IP %s is outside the NAT subnet; using a routed NIC instead of %s", ip, bridge)
                return "routed", self.uplink()
            return "nat", self.cfg.nat_bridge
        if bridge == self.cfg.routed_bridge:
            if is_private or dhcp:
                return "nat", self.cfg.nat_bridge
            return "routed", self.uplink()
        if bridge and bridge in self.host_bridges():
            return "bridged", bridge
        if is_private or dhcp:
            return "nat", self.cfg.nat_bridge
        return "routed", self.uplink()

    def plan(self, vm_type: str, pve: Dict[str, Any]) -> Tuple[List[NicPlan], bool]:
        """Build NIC plans from a Proxmox config. Assigns missing MACs (mutates pve)."""
        changed = False
        plans: List[NicPlan] = []
        keys = sorted((k for k in pve if k.startswith("net") and k[3:].isdigit()), key=lambda k: int(k[3:]))
        for key in keys:
            index = int(key[3:])
            if vm_type == "qemu":
                net = pveconfig.parse_qemu_net(pve.get(key))
                ipcfg = pveconfig.parse_ipconfig(pve.get("ipconfig%d" % index))
                ip, prefix = pveconfig.split_cidr(ipcfg.get("ip"))
                gateway = ipcfg.get("gw") or None
                name = "eth%d" % index
            else:
                net = pveconfig.parse_lxc_net(pve.get(key))
                ip, prefix = pveconfig.split_cidr(net.get("ip"))
                gateway = net.get("gw") or None
                name = net.get("name") or ("eth%d" % index)
            mac = normalize_mac(net.get("mac"))
            if not mac:
                mac = random_mac()
                changed = True
                if vm_type == "qemu":
                    pve[key] = pveconfig.format_qemu_net(net["model"], mac, net["bridge"], net["extra"])
                else:
                    pve[key] = pveconfig.format_lxc_net(name, net["bridge"], mac, net.get("ip"), net.get("gw"), net["extra"])
            if ip in ("manual", "auto"):
                ip = None
            # No address yet: DHCP (on the NAT bridge unless a host bridge was chosen),
            # so the guest still has outbound connectivity.
            dhcp = ip is None or ip == "dhcp"
            mode, parent = self.resolve_mode(net.get("bridge", ""), None if dhcp else ip)
            if mode == "nat":
                prefix = self.cfg.nat_network.prefixlen
                gateway = str(self.cfg.nat["gateway"])
            elif mode == "routed":
                prefix = 32
                gateway = ROUTED_GATEWAY
            rate = None
            if net.get("rate"):
                try:
                    rate = float(net["rate"])
                except ValueError:
                    rate = None
            plans.append(NicPlan(
                index=index, key=key, name=name, mode=mode, ip=None if dhcp else ip, prefix=prefix,
                gateway=gateway, mac=mac, parent=parent, rate_mbps=rate, dhcp=dhcp,
            ))
        return plans, changed

    def nic_device(self, plan: NicPlan) -> Dict[str, str]:
        device = {"type": "nic", "name": plan.name, "hwaddr": plan.mac}
        if plan.mode == "routed":
            device["nictype"] = "routed"
            if plan.ip:
                device["ipv4.address"] = plan.ip
            if plan.parent:
                device["parent"] = plan.parent
        else:
            device["nictype"] = "bridged"
            device["parent"] = plan.parent
        if plan.rate_mbps:
            limit = "%dMbit" % max(1, int(plan.rate_mbps * 8))  # Proxmox rate is MB/s
            device["limits.ingress"] = limit
            device["limits.egress"] = limit
        return device

    # ----------------------------------------------------------- NAT ports
    def nat_ports(self, ip: Optional[str]) -> Optional[Dict[str, int]]:
        if not self.in_nat_subnet(ip):
            return None
        network = self.cfg.nat_network
        index = int(ipaddress.IPv4Address(ip)) - int(network.network_address)
        if index <= 0 or index >= network.num_addresses - 1 or str(ip) == str(self.cfg.nat["gateway"]):
            return None
        nat = self.cfg.nat
        result = {"index": index, "ssh_port": int(nat["ssh_port_base"]) + index}
        size = int(nat["port_range_size"])
        if size > 0:
            start = int(nat["port_range_base"]) + index * size
            result["range_start"] = start
            result["range_end"] = start + size - 1
        return result

    def access_info(self, vm_type: str, plans: List[NicPlan]) -> Dict[str, Any]:
        """Connection details shown to users (SSH host/port, forwards)."""
        info: Dict[str, Any] = {"network_mode": None, "ssh": None, "forwards": [], "public_ipv4": None, "private_ipv4": None}
        primary = plans[0] if plans else None
        if primary is None:
            return info
        info["network_mode"] = "nat" if primary.mode == "nat" else "dedicated"
        info["nic_mode"] = primary.mode
        if primary.mode == "nat":
            public = self.public_ipv4()
            ports = self.nat_ports(primary.ip)
            info["public_ipv4"] = public or None
            info["private_ipv4"] = primary.ip
            if ports and public:
                info["ssh"] = {"host": public, "port": ports["ssh_port"]}
                info["forwards"].append({"protocol": "tcp", "public_port": str(ports["ssh_port"]), "private_port": "22", "purpose": "ssh"})
                if "range_start" in ports:
                    span = "%d-%d" % (ports["range_start"], ports["range_end"])
                    info["forwards"].append({"protocol": "tcp+udp", "public_port": span, "private_port": span, "purpose": "services"})
        elif primary.ip:
            info["public_ipv4"] = primary.ip
            info["ssh"] = {"host": primary.ip, "port": 22}
        return info

    def sync_forwards(self, nat_ips: List[Tuple[int, str]]) -> None:
        """Make the NAT forward on the node's listen address match the given (vmid, ip) list."""
        listen = self.listen_ipv4()
        if not listen:
            LOG.warning("node IPv4 unknown; set public_ipv4 (or nat.listen_address) in the config to enable NAT forwards")
            return
        ports: List[Dict[str, str]] = []
        seen = set()
        for vmid, ip in sorted(nat_ips):
            if ip in seen:
                continue  # the same IP during a reinstall (old + new instance)
            seen.add(ip)
            mapping = self.nat_ports(ip)
            if not mapping:
                continue
            ports.append({
                "description": "vps%d ssh" % vmid, "protocol": "tcp",
                "listen_port": str(mapping["ssh_port"]), "target_address": ip, "target_port": "22",
            })
            if "range_start" in mapping:
                span = "%d-%d" % (mapping["range_start"], mapping["range_end"])
                for proto in ("tcp", "udp"):
                    ports.append({
                        "description": "vps%d services" % vmid, "protocol": proto,
                        "listen_port": span, "target_address": ip,
                    })
        with self._forward_lock:
            if ports:
                self.incus.put_forward(self.cfg.nat_bridge, listen, ports, "Managed by OrveX VPS Node")
            else:
                self.incus.delete_forward(self.cfg.nat_bridge, listen)


def root_size_bytes(devices: Dict[str, Any]) -> int:
    root = devices.get("root") or {}
    return parse_size(root.get("size"), "") or 0
