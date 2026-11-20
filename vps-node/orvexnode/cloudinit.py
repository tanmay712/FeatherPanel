"""cloud-init user-data and network-config generation.

Both documents are emitted as JSON, which is valid YAML, so no YAML library
is needed. Incus passes them to the guest through its NoCloud seed for
containers and VMs alike.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .network import ROUTED_GATEWAY, NicPlan

SSHD_DROPIN = "/etc/ssh/sshd_config.d/01-orvex.conf"

# Re-applies routed (/32 + on-link gateway) addressing on every boot. cloud-init
# renders the same config, but some renderers ignore "on-link"; this unit makes
# routed networking work on every systemd distribution.
ROUTED_FIX_SCRIPT = """#!/bin/sh
# Managed by OrveX VPS Node: keep routed IPv4 addressing in place.
set -u
CONF=/etc/orvex/routed.conf
[ -r "$CONF" ] || exit 0
while read -r mac ip gw; do
    [ -n "$mac" ] || continue
    dev=$(for d in /sys/class/net/*; do [ "$(cat "$d/address" 2>/dev/null)" = "$mac" ] && basename "$d"; done | head -n1)
    [ -n "$dev" ] || continue
    ip link set "$dev" up 2>/dev/null || true
    ip -4 addr show dev "$dev" | grep -q " $ip/" || ip -4 addr add "$ip/32" dev "$dev" 2>/dev/null || true
    ip -4 route replace "$gw" dev "$dev" scope link 2>/dev/null || true
    ip -4 route replace default via "$gw" dev "$dev" onlink 2>/dev/null || true
done < "$CONF"
"""

ROUTED_FIX_UNIT = """[Unit]
Description=OrveX routed IPv4 networking
After=network.target systemd-networkd.service NetworkManager.service networking.service
Wants=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/orvex-routed-net
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""


def network_config(plans: List[NicPlan], nameservers: List[str], searchdomain: Optional[str] = None) -> str:
    ethernets: Dict[str, Any] = {}
    for position, plan in enumerate(plans):
        entry: Dict[str, Any] = {"match": {"macaddress": plan.mac}, "set-name": plan.name}
        if plan.dhcp or not plan.ip:
            entry["dhcp4"] = bool(plan.dhcp)
        else:
            entry["dhcp4"] = False
            entry["addresses"] = ["%s/%d" % (plan.ip, plan.prefix)]
            if plan.gateway and position == 0:
                route: Dict[str, Any] = {"to": "0.0.0.0/0", "via": plan.gateway}
                if plan.mode == "routed":
                    route["on-link"] = True
                entry["routes"] = [route]
        if position == 0 and nameservers:
            entry["nameservers"] = {"addresses": list(nameservers)}
            if searchdomain:
                entry["nameservers"]["search"] = [searchdomain]
        ethernets[plan.name] = entry
    return json.dumps({"version": 2, "ethernets": ethernets}, indent=2)


def user_data(
    *,
    hostname: str,
    vm_type: str,
    login_user: str,
    password_hash: Optional[str],
    ssh_keys: List[str],
    plans: List[NicPlan],
) -> str:
    """Build #cloud-config user data.

    login_user gets the password and keys. For "root" (containers, or a KVM
    guest whose ciuser is root) root login over SSH is enabled; otherwise the
    user gets passwordless sudo and root stays locked, like Proxmox does.
    """
    short = hostname.split(".")[0]
    data: Dict[str, Any] = {
        "hostname": short,
        "manage_etc_hosts": True,
        "preserve_hostname": False,
        "ssh_pwauth": True,
        "disable_root": False,
        # Keep host keys when cloud-init re-runs (e.g. after a password change),
        # so users do not get host key warnings.
        "ssh_deletekeys": False,
    }
    if "." in hostname:
        data["fqdn"] = hostname
    write_files: List[Dict[str, Any]] = []
    runcmd: List[Any] = []
    root_login = login_user == "root"
    # Only keywords every supported OpenSSH knows: an unknown keyword stops sshd.
    sshd_lines = ["PasswordAuthentication yes"]
    if root_login:
        sshd_lines.insert(0, "PermitRootLogin yes")
        if password_hash:
            data["chpasswd"] = {"expire": False, "users": [{"name": "root", "password": password_hash, "type": "hash"}]}
        if ssh_keys:
            write_files.append({
                "path": "/root/.ssh/authorized_keys", "permissions": "0600", "owner": "root:root",
                "content": "\n".join(ssh_keys) + "\n",
            })
    else:
        user: Dict[str, Any] = {
            "name": login_user,
            "shell": "/bin/bash",
            "sudo": "ALL=(ALL) NOPASSWD:ALL",
            "lock_passwd": False,
        }
        if password_hash:
            user["passwd"] = password_hash
        if ssh_keys:
            user["ssh_authorized_keys"] = list(ssh_keys)
        data["users"] = [user]
    write_files.append({
        "path": SSHD_DROPIN, "permissions": "0644", "owner": "root:root",
        "content": "# Managed by OrveX VPS Node\n" + "\n".join(sshd_lines) + "\n",
    })
    routed = [p for p in plans if p.mode == "routed" and p.ip]
    if routed:
        write_files.extend([
            {"path": "/etc/orvex/routed.conf", "permissions": "0644", "owner": "root:root",
             "content": "".join("%s %s %s\n" % (p.mac, p.ip, ROUTED_GATEWAY) for p in routed)},
            {"path": "/usr/local/sbin/orvex-routed-net", "permissions": "0755", "owner": "root:root",
             "content": ROUTED_FIX_SCRIPT},
            {"path": "/etc/systemd/system/orvex-routed-net.service", "permissions": "0644", "owner": "root:root",
             "content": ROUTED_FIX_UNIT},
        ])
        runcmd.append(["sh", "-c", "command -v systemctl >/dev/null 2>&1 && systemctl daemon-reload && systemctl enable --now orvex-routed-net.service || /usr/local/sbin/orvex-routed-net || true"])
    if vm_type == "lxc":
        # Container images are minimal: make sure an SSH server is installed.
        data["package_update"] = True
        data["packages"] = ["openssh-server"]
        runcmd.append(["sh", "-c", "command -v rc-update >/dev/null 2>&1 && rc-update add sshd default || true"])
    runcmd.append(["sh", "-c", "systemctl restart ssh 2>/dev/null || systemctl restart sshd 2>/dev/null || rc-service sshd restart 2>/dev/null || true"])
    data["write_files"] = write_files
    data["runcmd"] = runcmd
    return "#cloud-config\n" + json.dumps(data, indent=2)
