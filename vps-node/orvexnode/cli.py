"""`orvex-node` command line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from . import __version__
from .config import Config, load_templates
from .incus import IncusClient, IncusError
from .network import NetworkManager
from .server import cert_fingerprint
from .util import setup_logging

BOLD = "\033[1m" if sys.stdout.isatty() else ""
DIM = "\033[2m" if sys.stdout.isatty() else ""
GREEN = "\033[32m" if sys.stdout.isatty() else ""
YELLOW = "\033[33m" if sys.stdout.isatty() else ""
RED = "\033[31m" if sys.stdout.isatty() else ""
RESET = "\033[0m" if sys.stdout.isatty() else ""


def _templates_with_cache(cfg: Config, incus: IncusClient) -> List[Dict[str, Any]]:
    out = []
    for tpl in load_templates(cfg.get("templates_file")):
        try:
            cached = incus.image_alias_exists(tpl["local_alias"])
        except IncusError:
            cached = False
        out.append(dict(tpl, cached=cached))
    return out


def cmd_info(cfg: Config, args: argparse.Namespace) -> int:
    incus = IncusClient(cfg["incus_socket"])
    net = NetworkManager(cfg, incus)
    public = net.public_ipv4()
    nat = cfg.nat
    network = cfg.nat_network
    first = network.network_address + 2
    last = network.broadcast_address - 1
    fingerprint = cert_fingerprint(cfg["tls_cert"])
    templates = _templates_with_cache(cfg, incus)
    data = {
        "node_name": cfg.node_name, "fqdn": public, "port": cfg["port"], "scheme": "https" if fingerprint else "http",
        "user": cfg["api_user"], "token_id": cfg["api_token_id"], "secret": cfg["api_token_secret"],
        "tls_fingerprint": fingerprint, "routed_bridge": cfg.routed_bridge, "nat_bridge": cfg.nat_bridge,
        "nat_range": "%s-%s" % (first, last), "nat_cidr": network.prefixlen, "nat_gateway": nat["gateway"],
        "uplink": net.uplink(), "templates": [{k: t[k] for k in ("vmid", "type", "description", "cached")} for t in templates],
    }
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    from .panel import load_state

    state = load_state(cfg)
    print("")
    print("%sOrveX VPS Node%s %s" % (BOLD, RESET, __version__))
    if state.get("panel_url"):
        print("  Panel            %s%s%s (node #%s, connected %s)" % (
            GREEN, state["panel_url"], RESET, state.get("node_id", "?"), state.get("registered_at", "?")))
    else:
        print("  Panel            %snot connected%s: Admin > VDS Nodes > Create > OrveX Node in the panel shows" % (YELLOW, RESET))
        print("                   the command to run; or: orvex-node register --panel URL --token TOKEN")
    print("")
    print("%sManual setup%s (only needed without the panel's install command)" % (DIM, RESET))
    rows = [
        ("Name", cfg.node_name), ("FQDN / IP", public or "(set public_ipv4 in the config)"),
        ("Port", str(cfg["port"])), ("Scheme", data["scheme"]), ("User", cfg["api_user"]),
        ("Token ID", cfg["api_token_id"]), ("Secret", cfg["api_token_secret"]),
        ("Skip TLS verify", "yes (self-signed certificate)" if fingerprint else "n/a"),
        ("TLS fingerprint", fingerprint or "-"),
    ]
    for label, value in rows:
        print("  %-16s %s%s%s" % (label, BOLD, value, RESET))
    print("")
    print("%sBridges%s (pick one when creating a VDS)" % (BOLD, RESET))
    print("  %-12s dedicated IPv4, routed via %s" % (cfg.routed_bridge, net.uplink() or "the default route"))
    print("  %-12s shared IPv4 (NAT %s, gateway %s)" % (cfg.nat_bridge, network, nat["gateway"]))
    print("")
    print("%sShared IPv4 pool%s  Admin > VDS Nodes > IPs > Add" % (BOLD, RESET))
    print("  IP %s   CIDR %d   Gateway %s   (a range like this adds every address)" % (data["nat_range"], network.prefixlen, nat["gateway"]))
    size = int(nat["port_range_size"])
    print("  Each NAT VPS gets SSH on %s:%d+N%s" % (
        public or "<node ip>", int(nat["ssh_port_base"]),
        " and ports %d+N*%d..+%d (TCP+UDP)" % (int(nat["port_range_base"]), size, size - 1) if size else ""))
    print("  (N = last octet offset of its private IP)")
    print("")
    print("%sTemplates%s  Admin > VDS Nodes > Templates: use the VMID as the template VMID" % (BOLD, RESET))
    for tpl in templates:
        state = "%scached%s" % (GREEN, RESET) if tpl["cached"] else "%sdownloads on first use%s" % (DIM, RESET)
        print("  %5d  %-4s %-28s %s" % (tpl["vmid"], "KVM" if tpl["type"] == "qemu" else "LXC", tpl["description"], state))
    print("")
    return 0


def cmd_status(cfg: Config, args: argparse.Namespace) -> int:
    from .server import App

    app = App(cfg)
    rows = []
    for inst in sorted(app.instances.managed(), key=lambda i: i["_vmid"]):
        vmid = inst["_vmid"]
        vm_type = "qemu" if inst.get("type") == "virtual-machine" else "lxc"
        pve = app.instances.load_pve(inst)
        plans, _ = app.net.plan(vm_type, dict(pve))
        access = app.net.access_info(vm_type, plans)
        ssh = access.get("ssh") or {}
        rows.append((vmid, "KVM" if vm_type == "qemu" else "LXC", inst.get("status", "?"),
                     pve.get("name") or pve.get("hostname") or "-",
                     (plans[0].ip if plans else "-") or "-", access.get("nic_mode") or "-",
                     "%s:%s" % (ssh.get("host"), ssh.get("port")) if ssh else "-"))
    if args.json:
        print(json.dumps([dict(zip(("vmid", "type", "status", "hostname", "ip", "mode", "ssh"), r)) for r in rows], indent=2))
        return 0
    if not rows:
        print("No guests yet. Create one from OrveX Panel (Admin > VDS Instances).")
        return 0
    print("%-6s %-4s %-8s %-24s %-16s %-8s %s" % ("VMID", "TYPE", "STATUS", "HOSTNAME", "IP", "MODE", "SSH"))
    for row in rows:
        print("%-6s %-4s %-8s %-24s %-16s %-8s %s" % row)
    return 0


def cmd_templates(cfg: Config, args: argparse.Namespace) -> int:
    incus = IncusClient(cfg["incus_socket"])
    templates = _templates_with_cache(cfg, incus)
    if args.json:
        print(json.dumps(templates, indent=2))
        return 0
    for tpl in templates:
        print("%5d  %-4s %-26s %-22s %s" % (tpl["vmid"], "KVM" if tpl["type"] == "qemu" else "LXC", tpl["name"], tpl["image"],
                                           "cached" if tpl["cached"] else "-"))
    return 0


def cmd_cache(cfg: Config, args: argparse.Namespace) -> int:
    incus = IncusClient(cfg["incus_socket"])
    wanted = set(args.templates or [])
    kvm = os.path.exists("/dev/kvm")
    failures = 0
    for tpl in load_templates(cfg.get("templates_file")):
        if wanted and tpl["name"] not in wanted and str(tpl["vmid"]) not in wanted:
            continue
        if tpl["type"] == "qemu" and not kvm and not wanted:
            print("skip  %-26s (no /dev/kvm on this host)" % tpl["name"])
            continue
        if incus.image_alias_exists(tpl["local_alias"]):
            print("ok    %-26s already cached" % tpl["name"])
            continue
        body = {
            "source": {
                "type": "image", "mode": "pull", "server": tpl["server"], "protocol": tpl["protocol"],
                "alias": tpl["image"], "image_type": "virtual-machine" if tpl["type"] == "qemu" else "container",
            },
            "aliases": [{"name": tpl["local_alias"], "description": "OrveX template %d" % tpl["vmid"]}],
            "auto_update": True,
        }
        print("pull  %-26s %s" % (tpl["name"], tpl["image"]))
        try:
            doc = incus.request("POST", "/1.0/images", body)
            op_path = doc.get("operation") or ""
            last = ""
            while True:
                op = incus.request("GET", op_path).get("metadata") or {}
                progress = ((op.get("metadata") or {}).get("download_progress") or "")
                if progress and progress != last and sys.stdout.isatty():
                    sys.stdout.write("\r      %s          " % progress)
                    sys.stdout.flush()
                    last = progress
                if op.get("status") == "Success":
                    break
                if op.get("status") in ("Failure", "Cancelled"):
                    raise IncusError(op.get("err") or "download failed")
                time.sleep(2)
            print("\r      %sdone%s                                  " % (GREEN, RESET))
        except IncusError as exc:
            failures += 1
            print("\r      %sfailed: %s%s" % (RED, exc.message, RESET))
    return 1 if failures else 0


def cmd_rotate(cfg: Config, args: argparse.Namespace) -> int:
    cfg.data["api_token_secret"] = str(uuid.uuid4())
    cfg.save()
    print(cfg.data["api_token_secret"])
    print("New secret saved. Restart the agent (systemctl restart orvex-node), then re-pair the node: in the panel open"
          " the node > Connect > New install command, and run `orvex-node register` with it.", file=sys.stderr)
    return 0


def cmd_register(cfg: Config, args: argparse.Namespace) -> int:
    from .panel import PanelError, register

    net = NetworkManager(cfg, IncusClient(cfg["incus_socket"]))
    try:
        data, payload = register(cfg, net, args.panel, args.token, address=args.address, insecure=args.insecure)
    except PanelError as exc:
        print("%serror:%s %s" % (RED, RESET, exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    node = data.get("node") or {}
    print("%s%sConnected to OrveX Panel%s as node \"%s\" (#%s)" % (GREEN, BOLD, RESET, node.get("name", "?"), node.get("id", "?")))
    print("  Panel reaches the node at   https://%s:%s" % (payload["address"], payload["port"]))
    print("  Templates added             %s of %s" % (data.get("templates_imported", 0), data.get("templates_total", 0)))
    print("  Shared IPv4 addresses added %s" % data.get("ips_added", 0))
    if data.get("reachable"):
        print("  Panel -> node connection    %sok%s" % (GREEN, RESET))
    else:
        print("  Panel -> node connection    %sFAILED%s: %s" % (YELLOW, RESET, data.get("reach_error") or "unknown error"))
        print("    The panel must reach TCP port %s on %s: open it in the firewall (and at your" % (payload["port"], payload["address"]))
        print("    provider), then press \"Test connection\" on the node page in the panel.")
    for warning in data.get("warnings") or []:
        print("  %swarning:%s %s" % (YELLOW, RESET, warning))
    return 0


def _check(label: str, ok: bool, detail: str = "", warn: bool = False) -> bool:
    mark = "%s ok %s" % (GREEN, RESET) if ok else ("%swarn%s" % (YELLOW, RESET) if warn else "%sFAIL%s" % (RED, RESET))
    print("[%s] %-28s %s" % (mark, label, detail))
    return ok or warn


def cmd_doctor(cfg: Config, args: argparse.Namespace) -> int:
    incus = IncusClient(cfg["incus_socket"])
    ok = True
    ok &= _check("Incus API", incus.ping(), cfg["incus_socket"])
    ok &= _check("KVM (/dev/kvm)", os.path.exists("/dev/kvm"), "needed for KVM guests; LXC works without", warn=True)
    try:
        forwarding = open("/proc/sys/net/ipv4/ip_forward", encoding="ascii").read().strip() == "1"
    except OSError:
        forwarding = False
    ok &= _check("IPv4 forwarding", forwarding, "net.ipv4.ip_forward=1")
    try:
        pools = {p.get("name") for p in incus.pools()}
        networks = {n.get("name") for n in incus.networks()}
    except IncusError:
        pools, networks = set(), set()
    ok &= _check("Storage pool", cfg["storage_pool"] in pools, cfg["storage_pool"])
    ok &= _check("NAT bridge", cfg.nat_bridge in networks, cfg.nat_bridge)
    net = NetworkManager(cfg, incus)
    ok &= _check("Public IPv4", bool(net.public_ipv4()), net.public_ipv4() or "set public_ipv4 in config")
    ok &= _check("Uplink interface", bool(net.uplink()), net.uplink() or "set uplink_interface in config")
    ok &= _check("TLS certificate", os.path.exists(cfg["tls_cert"]), cfg["tls_cert"])
    ok &= _check("API token", bool(cfg["api_token_secret"]), "%s!%s" % (cfg["api_user"], cfg["api_token_id"]))
    return 0 if ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="orvex-node", description="OrveX VPS Node agent: KVM + LXC hosting for OrveX Panel")
    parser.add_argument("--config", help="config file (default /etc/orvex-node/config.json)")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the API server (used by systemd)")
    for name, help_text in (("info", "show the values to enter in the panel"), ("status", "list guests"),
                            ("templates", "list templates")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--json", action="store_true")
    p = sub.add_parser("cache-templates", help="pre-download template images")
    p.add_argument("templates", nargs="*", help="template names or VMIDs (default: all)")
    p = sub.add_parser("register", help="connect this node to OrveX Panel with the token from the panel")
    p.add_argument("--panel", required=True, metavar="URL", help="panel URL, e.g. https://panel.example.com")
    p.add_argument("--token", required=True, help="one-time install token shown by the panel (orvx_...)")
    p.add_argument("--address", help="address the panel uses to reach this node (default: the public IPv4)")
    p.add_argument("--insecure", action="store_true", help="do not verify the panel's TLS certificate")
    p.add_argument("--json", action="store_true")
    sub.add_parser("rotate-token", help="generate a new API token secret")
    sub.add_parser("doctor", help="check the node setup")
    sub.add_parser("version", help="print the version")
    args = parser.parse_args(argv)
    if args.command == "version":
        print(__version__)
        return 0
    cfg = Config.load(args.config)
    setup_logging(cfg.get("log_level", "INFO"))
    if args.command in (None, "serve"):
        from .server import serve

        serve(cfg)
        return 0
    handlers = {"info": cmd_info, "status": cmd_status, "templates": cmd_templates, "cache-templates": cmd_cache,
                "register": cmd_register, "rotate-token": cmd_rotate, "doctor": cmd_doctor}
    try:
        return handlers[args.command](cfg, args)
    except IncusError as exc:
        print("error: %s" % exc.message, file=sys.stderr)
        return 1
