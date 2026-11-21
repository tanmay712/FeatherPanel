"""`orvex-node register` against a fake OrveX Panel."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from orvexnode import __version__, cli  # noqa: E402
from orvexnode.panel import PanelError, normalize_panel_url  # noqa: E402

TOKEN = "orvx_12_" + "aB3" * 16


class FakePanel:
    """Records registration requests and answers with a canned response."""

    def __init__(self):
        self.requests = []
        self.status = 200
        self.body = {"success": True, "message": "Node connected", "data": {
            "node": {"id": 12, "name": "Frankfurt 1"}, "templates_imported": 13, "templates_total": 13,
            "ips_added": 253, "reachable": True, "reach_error": None, "warnings": [],
        }}
        panel = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - http.server API
                length = int(self.headers.get("Content-Length") or 0)
                panel.requests.append({
                    "path": self.path, "headers": dict(self.headers.items()),
                    "json": json.loads(self.rfile.read(length).decode("utf-8")),
                })
                raw = json.dumps(panel.body).encode("utf-8")
                self.send_response(panel.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class TestRegister(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="orvex-register-")
        self.config_path = os.path.join(self.tmp, "config.json")
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump({
                "node_name": "node1", "public_ipv4": "203.0.113.10", "uplink_interface": "eth0",
                "api_token_secret": "b1946ac9-2d0e-4b4d-9a8c-2f5c1f0e7a61", "port": 8006,
                "incus_socket": os.path.join(self.tmp, "missing.sock"),
                "tls_cert": os.path.join(self.tmp, "missing-cert.pem"),
                "templates_file": os.path.join(self.tmp, "no-templates.json"),
            }, handle)
        self.panel = FakePanel()

    def tearDown(self):
        self.panel.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--config", self.config_path] + list(args))
        return code, out.getvalue(), err.getvalue()

    def test_successful_registration_sends_the_node_details(self):
        code, out, err = self.run_cli("register", "--panel", self.panel.url + "/", "--token", TOKEN)
        self.assertEqual(code, 0, err)
        self.assertIn('Connected to OrveX Panel', out)
        self.assertIn('"Frankfurt 1" (#12)', out)
        self.assertIn("253", out)

        self.assertEqual(len(self.panel.requests), 1)
        request = self.panel.requests[0]
        self.assertEqual(request["path"], "/api/remote/orvex/register")
        self.assertEqual(request["headers"]["Authorization"], "Bearer " + TOKEN)
        self.assertEqual(request["headers"]["User-Agent"], "OrveX-Node/" + __version__)
        payload = request["json"]
        self.assertEqual(payload["address"], "203.0.113.10")
        self.assertEqual(payload["port"], 8006)
        self.assertEqual(payload["api_user"], "orvex@orvex")
        self.assertEqual(payload["api_token_id"], "panel")
        self.assertEqual(payload["api_token_secret"], "b1946ac9-2d0e-4b4d-9a8c-2f5c1f0e7a61")
        self.assertEqual(payload["node_name"], "node1")
        self.assertEqual(payload["agent_version"], __version__)
        self.assertEqual(payload["storage_pool"], "default")
        self.assertEqual(payload["backup_storage"], "backups")
        self.assertEqual(payload["nat"]["subnet"], "10.77.0.0/24")
        self.assertEqual(payload["nat"]["gateway"], "10.77.0.1")
        self.assertIsInstance(payload["kvm"], bool)
        self.assertEqual(len(payload["templates"]), 13)
        self.assertEqual(payload["templates"][0], {
            "vmid": 9000, "name": "ubuntu-24.04-kvm", "type": "qemu", "description": "Ubuntu 24.04 LTS (KVM)",
            "default_user": "ubuntu", "disk_gb": 10,
        })
        self.assertIn("hostname", payload["host"])

        with open(os.path.join(self.tmp, "panel.json"), encoding="utf-8") as handle:
            state = json.load(handle)
        self.assertEqual(state["panel_url"], self.panel.url)
        self.assertEqual(state["node_id"], 12)
        self.assertEqual(oct(os.stat(os.path.join(self.tmp, "panel.json")).st_mode & 0o777), "0o600")

        code, out, _ = self.run_cli("info")
        self.assertEqual(code, 0)
        self.assertIn(self.panel.url, out)

    def test_address_override_and_unreachable_warning(self):
        self.panel.body["data"].update({"reachable": False, "reach_error": "Connection timed out", "warnings": ["nat was ignored"]})
        code, out, _ = self.run_cli("register", "--panel", self.panel.url, "--token", TOKEN, "--address", "node1.example.com")
        self.assertEqual(code, 0)
        self.assertEqual(self.panel.requests[0]["json"]["address"], "node1.example.com")
        self.assertIn("FAILED", out)
        self.assertIn("Connection timed out", out)
        self.assertIn("TCP port 8006", out)
        self.assertIn("nat was ignored", out)

    def test_panel_errors_are_shown(self):
        self.panel.status = 401
        self.panel.body = {"success": False, "message": "This install command is invalid, expired or already used.",
                           "error_code": "INVALID_REGISTRATION_TOKEN", "data": None}
        code, _, err = self.run_cli("register", "--panel", self.panel.url, "--token", TOKEN)
        self.assertEqual(code, 1)
        self.assertIn("already used", err)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "panel.json")))

        self.panel.status = 422
        self.panel.body = {"success": False, "message": "Invalid registration data", "data": {"errors": ["port must be between 1 and 65535"]}}
        code, _, err = self.run_cli("register", "--panel", self.panel.url, "--token", TOKEN)
        self.assertEqual(code, 1)
        self.assertIn("port must be between 1 and 65535", err)

    def test_bad_input_is_rejected_before_any_request(self):
        code, _, err = self.run_cli("register", "--panel", self.panel.url, "--token", "not-a-token")
        self.assertEqual(code, 1)
        self.assertIn("orvx_", err)
        code, _, err = self.run_cli("register", "--panel", "panel.example.com", "--token", TOKEN)
        self.assertEqual(code, 1)
        self.assertIn("https://", err)
        self.assertEqual(self.panel.requests, [])

    def test_unreachable_panel(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        code, _, err = self.run_cli("register", "--panel", "http://127.0.0.1:%d" % port, "--token", TOKEN)
        self.assertEqual(code, 1)
        self.assertIn("could not reach the panel", err)

    def test_non_json_answer(self):
        self.panel.status = 404
        self.panel.body = "not json"  # json.dumps gives a JSON string, not an object
        code, _, err = self.run_cli("register", "--panel", self.panel.url, "--token", TOKEN)
        self.assertEqual(code, 1)
        self.assertIn("without JSON", err)

    def test_normalize_panel_url(self):
        self.assertEqual(normalize_panel_url(" https://panel.example.com/ "), "https://panel.example.com")
        self.assertEqual(normalize_panel_url("http://10.0.0.5:4831"), "http://10.0.0.5:4831")
        for bad in ("panel.example.com", "ftp://x", "https://", "https://a b"):
            with self.assertRaises(PanelError):
                normalize_panel_url(bad)


if __name__ == "__main__":
    unittest.main()
