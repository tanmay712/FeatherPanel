"""End-to-end tests: Proxmox API calls (as the panel and runner make them) -> agent -> fake Incus."""

from __future__ import annotations

import base64
import http.client
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from fake_incus import FakeIncus  # noqa: E402
from orvexnode import cloudinit, pveconfig  # noqa: E402
from orvexnode.config import Config  # noqa: E402
from orvexnode.network import NetworkManager  # noqa: E402
from orvexnode.server import App, Server  # noqa: E402
from orvexnode.util import format_size, parse_size, sanitize_hostname  # noqa: E402

TOKEN = "PVEAPIToken=orvex@orvex!panel=s3cret-token"
RUNNER_BACKUP_RE = r"vzdump-(?:qemu|lxc)-%d-[^\s'\"/]+"


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class TestPveConfig(unittest.TestCase):
    def test_props_roundtrip(self):
        net = pveconfig.parse_qemu_net("virtio=00:16:3E:AA:BB:CC,bridge=vmbr0,firewall=1")
        self.assertEqual(net["model"], "virtio")
        self.assertEqual(net["mac"], "00:16:3E:AA:BB:CC")
        self.assertEqual(net["bridge"], "vmbr0")
        self.assertEqual(net["extra"], {"firewall": "1"})
        self.assertEqual(pveconfig.parse_qemu_net("virtio,bridge=vmbr0")["mac"], None)
        lxc = pveconfig.parse_lxc_net("name=eth0,bridge=vmbr0,ip=10.0.0.5/24,gw=10.0.0.1")
        self.assertEqual((lxc["name"], lxc["ip"], lxc["gw"]), ("eth0", "10.0.0.5/24", "10.0.0.1"))
        self.assertEqual(pveconfig.split_cidr("203.0.113.9/27"), ("203.0.113.9", 27))
        self.assertEqual(pveconfig.split_cidr("dhcp")[0], "dhcp")

    def test_sizes(self):
        self.assertEqual(parse_size("10G"), 10 * 1024 ** 3)
        self.assertEqual(parse_size("+5G"), 5 * 1024 ** 3)
        self.assertEqual(parse_size("512M"), 512 * 1024 ** 2)
        self.assertEqual(parse_size("20GiB"), 20 * 1024 ** 3)
        self.assertEqual(format_size(20 * 1024 ** 3), "20G")
        disk = "default:vm-5000-disk-0,size=10G"
        self.assertEqual(pveconfig.disk_size(disk), 10 * 1024 ** 3)
        self.assertEqual(pveconfig.with_disk_size(disk, 25 * 1024 ** 3), "default:vm-5000-disk-0,size=25G")

    def test_hostname(self):
        self.assertEqual(sanitize_hostname("My Server_01", "x"), "my-server-01")
        self.assertEqual(sanitize_hostname("---", "fallback"), "fallback")


class _StubIncus:
    def networks(self):
        return [{"name": "br0", "type": "bridge"}, {"name": "orvexnat0", "type": "bridge"}, {"name": "eth0", "type": "physical"}]


class TestNetwork(unittest.TestCase):
    def setUp(self):
        self.cfg = Config({"public_ipv4": "198.51.100.7", "uplink_interface": "eth0", "node_name": "n1"})
        self.net = NetworkManager(self.cfg, _StubIncus())

    def test_modes(self):
        self.assertEqual(self.net.resolve_mode("vmbr0", "203.0.113.10"), ("routed", "eth0"))
        self.assertEqual(self.net.resolve_mode("vmbr0", "10.77.0.20"), ("nat", "orvexnat0"))
        self.assertEqual(self.net.resolve_mode("orvexnat0", "10.77.0.20"), ("nat", "orvexnat0"))
        self.assertEqual(self.net.resolve_mode("orvexpub0", "203.0.113.10"), ("routed", "eth0"))
        self.assertEqual(self.net.resolve_mode("br0", "203.0.113.10"), ("bridged", "br0"))
        # IP wins when the bridge does not fit the address
        self.assertEqual(self.net.resolve_mode("orvexnat0", "203.0.113.10")[0], "routed")
        self.assertEqual(self.net.resolve_mode("orvexpub0", "10.77.0.20")[0], "nat")

    def test_nat_ports(self):
        self.assertEqual(self.net.nat_ports("10.77.0.10"), {"index": 10, "ssh_port": 22010, "range_start": 30200, "range_end": 30219})
        self.assertIsNone(self.net.nat_ports("10.77.0.1"))  # gateway
        self.assertIsNone(self.net.nat_ports("10.77.0.255"))  # broadcast
        self.assertIsNone(self.net.nat_ports("203.0.113.10"))
        top = self.net.nat_ports("10.77.0.254")
        self.assertLessEqual(top["range_end"], 65535)

    def test_nic_without_ip_uses_nat_dhcp(self):
        plans, _ = self.net.plan("qemu", {"net0": "virtio=00:16:3e:00:00:09,bridge=auto"})
        self.assertEqual((plans[0].mode, plans[0].dhcp, plans[0].ip), ("nat", True, None))
        self.assertNotIn("ipv4.address", self.net.nic_device(plans[0]))
        plans, _ = self.net.plan("lxc", {"net0": "name=eth0,bridge=br0,hwaddr=00:16:3e:00:00:0a"})
        self.assertEqual((plans[0].mode, plans[0].dhcp), ("bridged", True))

    def test_listen_address(self):
        cloud = NetworkManager(Config({"node_name": "n1", "public_ipv4": "198.51.100.7"}), _StubIncus())
        self.assertNotEqual(cloud.listen_ipv4(), "198.51.100.7")  # not on this host -> local address
        self.assertEqual(cloud.public_ipv4(), "198.51.100.7")     # still what users see
        local = NetworkManager(Config({"node_name": "n1", "public_ipv4": "127.0.0.1"}), _StubIncus())
        self.assertEqual(local.listen_ipv4(), "127.0.0.1")
        explicit = NetworkManager(Config({"node_name": "n1", "nat": {"listen_address": "10.0.0.4"}}), _StubIncus())
        self.assertEqual(explicit.listen_ipv4(), "10.0.0.4")

    def test_config_rejects_overlapping_ranges(self):
        with self.assertRaises(ValueError):
            Config({"nat": {"ssh_port_base": 30000, "port_range_base": 30100}, "node_name": "n1"})
        with self.assertRaises(ValueError):
            Config({"nat": {"subnet": "10.0.0.0/16"}, "node_name": "n1"})

    def test_plan_assigns_mac_and_modes(self):
        pve = {"net0": "virtio,bridge=vmbr0", "ipconfig0": "ip=203.0.113.10/24,gw=203.0.113.1"}
        plans, changed = self.net.plan("qemu", pve)
        self.assertTrue(changed)
        self.assertRegex(pve["net0"], r"^virtio=00:16:3e:")
        self.assertEqual((plans[0].mode, plans[0].prefix, plans[0].gateway), ("routed", 32, "169.254.0.1"))
        device = self.net.nic_device(plans[0])
        self.assertEqual(device["nictype"], "routed")
        self.assertEqual(device["ipv4.address"], "203.0.113.10")


class TestCloudInit(unittest.TestCase):
    def test_documents_are_valid_json_yaml(self):
        net = NetworkManager(Config({"node_name": "n1", "uplink_interface": "eth0"}), _StubIncus())
        plans, _ = net.plan("qemu", {"net0": "virtio=00:16:3e:00:00:01,bridge=orvexpub0", "ipconfig0": "ip=203.0.113.10/32"})
        ud = cloudinit.user_data(hostname="web.example.com", vm_type="qemu", login_user="admin",
                                 password_hash="$6$abc$def", ssh_keys=["ssh-ed25519 AAAA test"], plans=plans)
        self.assertTrue(ud.startswith("#cloud-config\n"))
        data = json.loads(ud.split("\n", 1)[1])
        self.assertEqual(data["users"][0]["name"], "admin")
        self.assertEqual(data["fqdn"], "web.example.com")
        self.assertFalse(data["ssh_deletekeys"])
        self.assertTrue(any(f["path"] == "/etc/orvex/routed.conf" for f in data["write_files"]))
        sshd = [f for f in data["write_files"] if f["path"] == cloudinit.SSHD_DROPIN][0]["content"]
        self.assertNotIn("KbdInteractive", sshd)
        nc = json.loads(cloudinit.network_config(plans, ["1.1.1.1"]))
        eth0 = nc["ethernets"]["eth0"]
        self.assertEqual(eth0["addresses"], ["203.0.113.10/32"])
        self.assertEqual(eth0["routes"][0], {"to": "0.0.0.0/0", "via": "169.254.0.1", "on-link": True})


class TestAgentFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="orvex-test-")
        cls.fake = FakeIncus(os.path.join(cls.tmp, "incus.sock")).start()
        cls.vnc_port = free_port()
        cfg = Config({
            "node_name": "orvex1",
            "incus_socket": cls.fake.socket_path,
            "state_dir": os.path.join(cls.tmp, "state"),
            "backup_dir": os.path.join(cls.tmp, "backups"),
            "templates_file": os.path.join(cls.tmp, "missing-templates.json"),
            "public_ipv4": "203.0.113.5",
            "nat": {"listen_address": "203.0.113.5"},
            "uplink_interface": "eth0",
            "api_token_secret": "s3cret-token",
            "tls_cert": "",
            "vnc_display_base": cls.vnc_port - 5900,
        }, path=os.path.join(cls.tmp, "config.json"))
        cls.app = App(cfg)
        cls.server = Server(("127.0.0.1", 0), cls.app, None)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.fake.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---------------------------------------------------------- helpers
    def call(self, method, path, form=None, body=None, auth=TOKEN, query=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = auth
        payload = None
        if body is not None:
            payload = json.dumps(body)
            headers["Content-Type"] = "application/json"
        elif form is not None:
            payload = urllib.parse.urlencode(form)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if query:
            path += "?" + urllib.parse.urlencode(query)
        conn.request(method, path, body=payload, headers=headers)
        resp = conn.getresponse()
        raw = resp.read().decode()
        conn.close()
        return resp.status, (json.loads(raw) if raw else None), resp.reason

    def wait_task(self, upid, timeout=20):
        enc = urllib.parse.quote(upid, safe="")
        deadline = time.time() + timeout
        while time.time() < deadline:
            status, doc, _ = self.call("GET", "/api2/json/nodes/orvex1/tasks/%s/status" % enc)
            self.assertEqual(status, 200, doc)
            if doc["data"]["status"] == "stopped":
                return doc["data"]
            time.sleep(0.05)
        self.fail("task %s did not finish" % upid)

    def task_ok(self, upid):
        data = self.wait_task(upid)
        if data["exitstatus"] != "OK":
            _s, log, _r = self.call("GET", "/api2/json/nodes/orvex1/tasks/%s/log" % urllib.parse.quote(upid, safe=""), query={"limit": 100})
            self.fail("task failed: %s\n%s" % (data["exitstatus"], "\n".join(line["t"] for line in log["data"])))
        return data

    def inst(self, vmid):
        return self.fake.state.instances["vps%d" % vmid]

    def forward_ports(self):
        fwd = self.fake.state.forwards.get("orvexnat0", {}).get("203.0.113.5")
        return fwd["ports"] if fwd else []

    # ------------------------------------------------------------ tests
    def test_01_auth_and_version(self):
        self.assertEqual(self.call("GET", "/api2/json/nodes", auth=None)[0], 401)
        self.assertEqual(self.call("GET", "/api2/json/nodes", auth="PVEAPIToken=orvex@orvex!panel=wrong")[0], 401)
        status, doc, _ = self.call("GET", "/api2/json/version")
        self.assertEqual(status, 200)
        self.assertEqual(doc["data"]["orvex"]["backend"], "incus")
        status, doc, reason = self.call("GET", "/api2/json/nodes/orvex1/nonexistent")
        self.assertEqual(status, 501)

    def test_02_discovery(self):
        status, doc, _ = self.call("GET", "/api2/json/nodes")
        self.assertEqual(doc["data"][0]["node"], "orvex1")
        _s, doc, _ = self.call("GET", "/api2/json/nodes/orvex1/network", query={"type": "bridge"})
        names = [e["iface"] for e in doc["data"]]
        self.assertEqual(names[:2], ["orvexpub0", "orvexnat0"])
        self.assertIn("br0", names)
        _s, doc, _ = self.call("GET", "/api2/json/nodes/orvex1/storage")
        by_name = {s["storage"]: s for s in doc["data"]}
        self.assertIs(by_name["default"]["active"], 1)  # PHP checks `active !== 1`
        self.assertIn("images", by_name["default"]["content"])
        self.assertEqual(by_name["backups"]["content"], "backup")
        _s, doc, _ = self.call("GET", "/api2/json/cluster/resources", query={"type": "vm"})
        templates = {r["vmid"]: r for r in doc["data"] if r["template"] == 1}
        self.assertEqual(templates[9000]["type"], "qemu")
        self.assertEqual(templates[9102]["type"], "lxc")
        self.assertEqual(templates[9000]["node"], "orvex1")
        _s, doc, _ = self.call("GET", "/api2/json/cluster/nextid", query={"vmid": 5000})
        self.assertEqual(doc["data"], 5000)

    def test_03_kvm_dedicated_ip_runner_flow(self):
        status, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/qemu/9000/clone", body={"newid": 5000, "name": "web1", "full": 1})
        self.assertEqual(status, 200, doc)
        self.assertTrue(doc["data"].startswith("UPID:orvex1:"))
        self.task_ok(doc["data"])
        inst = self.inst(5000)
        self.assertEqual(inst["type"], "virtual-machine")
        self.assertEqual(inst["config"]["raw.qemu"], "-vnc 127.0.0.1:%d" % (self.vnc_port - 5900))
        create = self.fake.state.create_calls[-1]
        self.assertEqual(create["source"]["alias"], "ubuntu/24.04/cloud")
        self.assertEqual(create["source"]["mode"], "pull")
        _s, doc, _ = self.call("GET", "/api2/json/nodes/orvex1/qemu/5000/config")
        self.assertIn("size=10G", doc["data"]["scsi0"])
        self.assertIn("bridge=auto", doc["data"]["net0"])
        # runner: resize first
        _s, doc, _ = self.call("PUT", "/api2/json/nodes/orvex1/qemu/5000/resize", body={"disk": "scsi0", "size": "20G"})
        self.task_ok(doc["data"])
        self.assertEqual(self.inst(5000)["devices"]["root"]["size"], "20GiB")
        # runner: config (JSON numbers, no net0)
        status, doc, _ = self.call("PUT", "/api2/json/nodes/orvex1/qemu/5000/config", body={
            "memory": 2048, "sockets": 1, "cores": 2, "nameserver": "1.1.1.1 8.8.8.8",
            "ipconfig0": "ip=203.0.113.10/24,gw=203.0.113.1", "onboot": 1, "boot": "order=scsi0",
            "ciuser": "admin", "cipassword": "S3cretPass!", "tags": "FeatherPanel-Managed", "description": "test",
        })
        self.assertEqual(status, 200, doc)
        cfg = self.inst(5000)["config"]
        self.assertEqual((cfg["limits.cpu"], cfg["limits.memory"], cfg["boot.autostart"]), ("2", "2048MiB", "true"))
        ud = json.loads(cfg["cloud-init.user-data"].split("\n", 1)[1])
        self.assertEqual(ud["users"][0]["name"], "admin")
        self.assertTrue(ud["users"][0]["passwd"].startswith("$6$"))
        nc = json.loads(cfg["cloud-init.network-config"])["ethernets"]["eth0"]
        self.assertEqual(nc["addresses"], ["203.0.113.10/32"])
        self.assertTrue(nc["routes"][0]["on-link"])
        nic = self.inst(5000)["devices"]["eth0"]
        self.assertEqual((nic["nictype"], nic["ipv4.address"], nic["parent"]), ("routed", "203.0.113.10", "eth0"))
        _s, doc, _ = self.call("GET", "/api2/json/nodes/orvex1/qemu/5000/config")
        self.assertEqual(doc["data"]["cipassword"], "**********")
        self.assertEqual(doc["data"]["memory"], 2048)
        self.assertIn("size=20G", doc["data"]["scsi0"])
        _s, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/qemu/5000/status/start", body={})
        self.task_ok(doc["data"])
        self.assertEqual(self.inst(5000)["status"], "Running")
        _s, doc, _ = self.call("GET", "/api2/json/nodes/orvex1/qemu/5000/status/current")
        data = doc["data"]
        self.assertEqual((data["status"], data["cpus"], data["maxmem"]), ("running", 2, 2048 * 1024 ** 2))
        self.assertEqual(data["orvex"]["ssh"], {"host": "203.0.113.10", "port": 22, "user": "admin"})
        self.assertEqual(data["orvex"]["network_mode"], "dedicated")
        self.assertTrue(data["orvex"]["vnc"])

    def test_04_lxc_shared_ip_php_flow(self):
        status, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/orvex/credentials", form={"vmid": 5001, "username": "root", "password": "RootPass123"})
        self.assertEqual(status, 200, doc)
        status, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/lxc/9102/clone", form={"newid": 5001, "hostname": "ct1", "full": 1, "storage": "local"})
        self.task_ok(doc["data"])
        self.assertEqual(self.fake.state.create_calls[-1]["source"], {"type": "image", "alias": "orvex-debian-12-lxc"})
        status, doc, _ = self.call("PUT", "/api2/json/nodes/orvex1/lxc/5001/config", form={
            "memory": 1024, "cores": 2, "nameserver": "1.1.1.1 8.8.8.8",
            "net0": "name=eth0,bridge=vmbr0,ip=10.77.0.10/24,gw=10.77.0.1", "onboot": 1,
            "tags": "FeatherPanel-Managed", "description": "ct",
        })
        self.assertEqual(status, 200, doc)
        inst = self.inst(5001)
        self.assertEqual((inst["devices"]["eth0"]["nictype"], inst["devices"]["eth0"]["parent"]), ("bridged", "orvexnat0"))
        ud = json.loads(inst["config"]["cloud-init.user-data"].split("\n", 1)[1])
        self.assertEqual(ud["chpasswd"]["users"][0]["name"], "root")
        self.assertTrue(ud["chpasswd"]["users"][0]["password"].startswith("$6$"))
        self.assertIn("openssh-server", ud["packages"])
        _s, doc, _ = self.call("PUT", "/api2/json/nodes/orvex1/lxc/5001/resize", form={"disk": "rootfs", "size": "10G"})
        self.task_ok(doc["data"])
        _s, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/lxc/5001/status/start")
        self.task_ok(doc["data"])
        ports = {(p["protocol"], p["listen_port"]): p for p in self.forward_ports()}
        self.assertEqual(ports[("tcp", "22010")]["target_port"], "22")
        self.assertEqual(ports[("tcp", "22010")]["target_address"], "10.77.0.10")
        self.assertIn(("tcp", "30200-30219"), ports)
        self.assertIn(("udp", "30200-30219"), ports)
        _s, doc, _ = self.call("GET", "/api2/json/nodes/orvex1/lxc/5001/status/current")
        orvex = doc["data"]["orvex"]
        self.assertEqual(orvex["ssh"], {"host": "203.0.113.5", "port": 22010, "user": "root"})
        self.assertEqual(orvex["network_mode"], "nat")
        self.assertEqual(orvex["private_ipv4"], "10.77.0.10")
        self.assertEqual(orvex["forwards"][1]["public_port"], "30200-30219")

    def test_05_password_change(self):
        status, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/lxc/5001/agent/set-user-password", form={"password": "NewPass1234"})
        self.assertEqual(status, 200, doc)
        self.assertEqual(doc["data"]["applied"], "immediate")
        call = self.fake.state.exec_calls[-1]
        self.assertIn("chpasswd -e", call["command"][-1])
        self.assertEqual(call["environment"]["ORVEX_USER"], "root")
        self.assertTrue(call["environment"]["ORVEX_HASH"].startswith("$6$"))
        self.assertNotIn("NewPass1234", json.dumps(call))  # plaintext never leaves the agent
        status, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/lxc/5001/agent/set-user-password", form={"password": "abc"})
        self.assertEqual(status, 400)
        # stopped KVM guest: stored for next boot
        status, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/qemu/5000/agent/set-user-password", form={"username": "admin", "password": "Another1234"})
        self.assertEqual(doc["data"]["applied"], "immediate")

    def test_06_snapshots(self):
        base = "/api2/json/nodes/orvex1/lxc/5001/snapshot"
        _s, doc, _ = self.call("POST", base, form={"snapname": "before-upgrade", "description": "safe point"})
        self.task_ok(doc["data"])
        _s, doc, _ = self.call("GET", base)
        names = [s["name"] for s in doc["data"]]
        self.assertEqual(names, ["before-upgrade", "current"])
        self.assertEqual(doc["data"][0]["description"], "safe point")
        self.assertEqual(self.call("POST", base, form={"snapname": "before-upgrade"})[0], 500)
        _s, doc, _ = self.call("POST", base + "/before-upgrade/rollback")
        self.task_ok(doc["data"])
        self.assertEqual(self.fake.state.restores[-1], ("vps5001", "before-upgrade"))
        _s, doc, _ = self.call("DELETE", base + "/before-upgrade")
        self.task_ok(doc["data"])
        _s, doc, _ = self.call("GET", base)
        self.assertEqual([s["name"] for s in doc["data"]], ["current"])

    def test_07_backups_like_runner(self):
        _s, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/vzdump", form={"vmid": 5001, "storage": "backups", "compress": "zstd", "mode": "snapshot", "remove": 0})
        upid = doc["data"]
        self.task_ok(upid)
        _s, log, _ = self.call("GET", "/api2/json/nodes/orvex1/tasks/%s/log" % urllib.parse.quote(upid, safe=""), query={"limit": 10000})
        names = set()
        for line in log["data"]:
            names.update(re.findall(RUNNER_BACKUP_RE % 5001, line["t"]))
        self.assertEqual(len(names), 1, log)
        filename = names.pop()
        _s, doc, _ = self.call("GET", "/api2/json/nodes/orvex1/storage/backups/content", query={"content": "backup", "vmid": 5001})
        items = doc["data"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["volid"], "backups:backup/" + filename)
        self.assertEqual((items[0]["vmid"], items[0]["content"]), (5001, "backup"))
        volid = items[0]["volid"]
        _s, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/lxc", form={"vmid": 5002, "ostemplate": volid, "storage": "local", "restore": 1, "force": 1})
        self.task_ok(doc["data"])
        self.assertEqual(self.inst(5002)["config"]["user.orvex.vmid"], "5002")
        status, _doc, _ = self.call("DELETE", "/api2/json/nodes/orvex1/storage/backups/content/%s" % urllib.parse.quote(volid, safe=""))
        self.assertEqual(status, 200)
        _s, doc, _ = self.call("GET", "/api2/json/nodes/orvex1/storage/backups/content", query={"content": "backup", "vmid": 5001})
        self.assertEqual(doc["data"], [])

    def test_08_metrics_and_rrd(self):
        t0 = time.time()
        self.app.metrics.sample_instances(t0)
        self.app.metrics.sample_instances(t0 + 10)
        cur = self.app.metrics.current(5001)
        self.assertGreater(cur["cpu"], 0)
        self.assertEqual(cur["diskread"], 1000)
        _s, doc, _ = self.call("GET", "/api2/json/nodes/orvex1/lxc/5001/rrddata", query={"timeframe": "hour", "cf": "AVERAGE"})
        points = doc["data"]
        self.assertEqual(len(points), 70)
        filled = [p for p in points if "cpu" in p]
        self.assertTrue(filled)
        for key in ("cpu", "maxcpu", "mem", "maxmem", "netin", "netout", "diskread", "diskwrite"):
            self.assertIn(key, filled[-1])
        _s, doc, _ = self.call("GET", "/api2/json/cluster/resources", query={"type": "vm"})
        running = {r["vmid"]: r["status"] for r in doc["data"] if r["template"] == 0}
        self.assertEqual(running[5000], "running")
        self.app.metrics.sample_node(t0)
        _s, doc, _ = self.call("GET", "/api2/json/nodes/orvex1/status")
        self.assertIn("cpuinfo", doc["data"])

    def test_09_reinstall_keeps_nat_forwards(self):
        _s, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/lxc/9102/clone", body={"newid": 5003, "hostname": "ct1", "full": 1, "storage": "local"})
        self.task_ok(doc["data"])
        self.call("PUT", "/api2/json/nodes/orvex1/lxc/5003/config", body={"memory": 1024, "cores": 2, "net0": "name=eth0,bridge=vmbr0,ip=10.77.0.10/24,gw=10.77.0.1"})
        _s, doc, _ = self.call("DELETE", "/api2/json/nodes/orvex1/lxc/5001", query={"purge": 1})
        self.task_ok(doc["data"])
        self.assertNotIn("vps5001", self.fake.state.instances)
        self.assertIn("22010", [p["listen_port"] for p in self.forward_ports()])
        for vmid in (5003, 5002):
            _s, doc, _ = self.call("DELETE", "/api2/json/nodes/orvex1/lxc/%d" % vmid, query={"purge": 1})
            self.task_ok(doc["data"])
        self.assertEqual(self.forward_ports(), [])

    def test_10_vnc_console(self):
        status, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/lxc/9102/vncproxy", form={"websocket": 1})
        self.assertEqual(status, 501)
        echo = socket.socket()
        echo.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        echo.bind(("127.0.0.1", self.vnc_port))
        echo.listen(1)

        def serve_echo():
            conn, _ = echo.accept()
            data = conn.recv(100)
            conn.sendall(b"ECHO:" + data)
            time.sleep(0.5)
            conn.close()

        threading.Thread(target=serve_echo, daemon=True).start()
        status, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/qemu/5000/vncproxy", form={"websocket": 1})
        self.assertEqual(status, 200, doc)
        self.assertEqual(int(doc["data"]["port"]), self.vnc_port)
        ticket = doc["data"]["ticket"]
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        path = "/api2/json/nodes/orvex1/qemu/5000/vncwebsocket?" + urllib.parse.urlencode({"port": self.vnc_port, "vncticket": ticket})
        sock.sendall(("GET %s HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: binary\r\n\r\n" % (path, key)).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += sock.recv(1)
        self.assertIn(b"101", head.split(b"\r\n")[0])
        self.assertIn(b"Sec-WebSocket-Protocol: binary", head)
        payload = b"hello"
        mask = os.urandom(4)
        sock.sendall(bytes([0x82, 0x80 | len(payload)]) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        first = sock.recv(2)
        self.assertEqual(first[0], 0x82)
        data = b""
        while len(data) < first[1]:
            data += sock.recv(first[1] - len(data))
        self.assertEqual(data, b"ECHO:hello")
        sock.close()
        echo.close()
        bad = self.call("GET", "/api2/json/nodes/orvex1/qemu/5000/vncwebsocket", auth=None, query={"port": self.vnc_port, "vncticket": "nope"})
        self.assertEqual(bad[0], 401)

    def test_11_vnc_fallback_when_qemu_rejects_option(self):
        self.fake.state.reject_raw_qemu_start = True
        try:
            _s, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/qemu/9002/clone", body={"newid": 5004, "name": "deb"})
            self.task_ok(doc["data"])
            self.call("PUT", "/api2/json/nodes/orvex1/qemu/5004/config", body={"ipconfig0": "ip=203.0.113.11/24,gw=203.0.113.1", "ciuser": "debian", "cipassword": "x1234567"})
            _s, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/qemu/5004/status/start")
            self.task_ok(doc["data"])
            self.assertEqual(self.inst(5004)["status"], "Running")
            self.assertNotIn("raw.qemu", self.inst(5004)["config"])
        finally:
            self.fake.state.reject_raw_qemu_start = False

    def test_12_conflicting_ip_is_deferred_until_start(self):
        self.fake.state.routed_conflicts = True
        try:
            _s, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/qemu/9000/clone", body={"newid": 5005, "name": "web1"})
            self.task_ok(doc["data"])
            status, doc, _ = self.call("PUT", "/api2/json/nodes/orvex1/qemu/5005/config", body={"ipconfig0": "ip=203.0.113.10/24,gw=203.0.113.1", "ciuser": "admin", "cipassword": "x1234567"})
            self.assertEqual(status, 200, doc)
            self.assertEqual(self.inst(5005)["config"].get("user.orvex.pending"), "1")
            self.assertNotIn("eth0", self.inst(5005)["devices"])
            _s, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/qemu/5000/status/stop")
            self.task_ok(doc["data"])
            _s, doc, _ = self.call("DELETE", "/api2/json/nodes/orvex1/qemu/5000", query={"purge": 1})
            self.task_ok(doc["data"])
            _s, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/qemu/5005/status/start")
            self.task_ok(doc["data"])
            self.assertEqual(self.inst(5005)["devices"]["eth0"]["ipv4.address"], "203.0.113.10")
            self.assertNotIn("user.orvex.pending", self.inst(5005)["config"])
        finally:
            self.fake.state.routed_conflicts = False

    def test_13_errors(self):
        status, doc, reason = self.call("GET", "/api2/json/nodes/orvex1/qemu/4999/config")
        self.assertEqual(status, 500)
        self.assertIn("does not exist", doc["message"])
        self.assertIn("does not exist", reason)
        status, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/qemu/9000/clone", body={"newid": 5005})
        self.assertEqual(status, 500)
        status, doc, _ = self.call("PUT", "/api2/json/nodes/orvex1/qemu/5005/resize", body={"disk": "virtio9", "size": "5G"})
        self.assertEqual(status, 500)
        status, doc, _ = self.call("POST", "/api2/json/nodes/orvex1/qemu/5005/firewall/rules", form={"type": "in"})
        self.assertEqual(status, 501)
        status, doc, _ = self.call("GET", "/api2/json/nodes/orvex1/qemu/5005/firewall/options")
        self.assertEqual(doc["data"]["enable"], 0)
        _s, doc, _ = self.call("GET", "/api2/json/nodes/orvex1/tasks/%s/status" % urllib.parse.quote("UPID:x:1:2:3:t:i:u:", safe=""))
        self.assertIn("no such task", doc["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
