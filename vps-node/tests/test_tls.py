"""TLS smoke test: the API served over HTTPS with a self-signed certificate."""

from __future__ import annotations

import http.client
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from fake_incus import FakeIncus  # noqa: E402
from orvexnode.config import Config  # noqa: E402
from orvexnode.server import App, Server, cert_fingerprint, make_ssl_context  # noqa: E402


@unittest.skipUnless(shutil.which("openssl"), "openssl not installed")
class TestTls(unittest.TestCase):
    def test_https_api_and_fingerprint(self):
        tmp = tempfile.mkdtemp(prefix="orvex-tls-")
        try:
            cert, key = os.path.join(tmp, "cert.pem"), os.path.join(tmp, "key.pem")
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", cert,
                            "-days", "1", "-subj", "/CN=orvex-test"], check=True, capture_output=True)
            fake = FakeIncus(os.path.join(tmp, "incus.sock")).start()
            cfg = Config({"node_name": "tls1", "incus_socket": fake.socket_path, "state_dir": os.path.join(tmp, "s"),
                          "backup_dir": os.path.join(tmp, "b"), "api_token_secret": "t0k", "tls_cert": cert, "tls_key": key,
                          "public_ipv4": "192.0.2.1", "uplink_interface": "eth0"})
            app = App(cfg)
            server = Server(("127.0.0.1", 0), app, make_ssl_context(cert, key))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE  # what "Skip TLS verification" does in the panel
            for _ in range(3):  # keep-alive + several handshakes
                conn = http.client.HTTPSConnection("127.0.0.1", server.server_address[1], context=ctx, timeout=10)
                conn.request("GET", "/api2/json/nodes", headers={"Authorization": "PVEAPIToken=orvex@orvex!panel=t0k"})
                resp = conn.getresponse()
                data = json.loads(resp.read())
                conn.close()
                self.assertEqual(resp.status, 200)
            self.assertEqual(data["data"][0]["ssl_fingerprint"], cert_fingerprint(cert))
            self.assertRegex(cert_fingerprint(cert), r"^([0-9A-F]{2}:){31}[0-9A-F]{2}$")
            # a client that never finishes the handshake must not block other clients
            import socket
            stalled = socket.create_connection(("127.0.0.1", server.server_address[1]))
            conn = http.client.HTTPSConnection("127.0.0.1", server.server_address[1], context=ctx, timeout=10)
            conn.request("GET", "/api2/json/version", headers={"Authorization": "PVEAPIToken=orvex@orvex!panel=t0k"})
            self.assertEqual(conn.getresponse().status, 200)
            conn.close()
            stalled.close()
            server.shutdown()
            server.server_close()
            fake.stop()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
