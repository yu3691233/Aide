"""Tests for /api/devices endpoint active-IP fallback.

Covers the bug: when device_aliases.json is empty (user never configured any alias)
but App is online (connected_devices has fresh heartbeat IPs), /api/devices used to
return devices=[] so the web 设备管理页 showed "暂无已连接设备".

Fix: /api/devices now appends a synthetic device entry per active IP that has no
matching alias, so the web UI can display them with a "设置别名" button.
"""
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import connected_devices as cd
from routes.device_routes import device_bp


class _FakeAdbResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_client(aliases, conn, adb_devices_stdout=""):
    """Build a Flask test client with /api/devices backed by mocked state."""
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(device_bp)

    # Patch all external dependencies the endpoint touches.
    patchers = [
        patch("routes.device_routes._load_device_aliases", return_value=aliases),
        patch("routes.device_routes._get_connected_devices", return_value=conn),
        patch("routes.device_routes._run_adb", return_value=_FakeAdbResult(0, adb_devices_stdout, "")),
        # add_alias_ip persists to disk; suppress during tests.
        patch("routes.device_routes.add_alias_ip", lambda *a, **kw: None),
    ]
    for p in patchers:
        p.start()

    def teardown():
        for p in patchers:
            p.stop()

    return app.test_client(), teardown


class ApiDevicesActiveIpFallbackTests(unittest.TestCase):
    def test_empty_aliases_with_active_ip_returns_synthetic_device(self):
        """aliases={} + 1 active IP → devices=[synthetic entry with alias=None]."""
        now = time.time()
        aliases = {}
        conn = {"192.168.3.31": now}
        client, teardown = _make_client(aliases, conn, adb_devices_stdout="")
        try:
            resp = client.get("/api/devices")
            self.assertEqual(200, resp.status_code)
            body = resp.get_json()
            self.assertTrue(body["ok"])
            self.assertEqual({}, body["aliases"])
            devices = body["devices"]
            self.assertEqual(1, len(devices))
            dev = devices[0]
            self.assertEqual("192.168.3.31", dev["ip"])
            self.assertEqual("192.168.3.31", dev["online_ip"])
            self.assertTrue(dev["is_online"])
            self.assertTrue(dev["is_active"])
            self.assertIsNone(dev["alias"])
            self.assertEqual([dev["ip"]], dev["ips"])
        finally:
            teardown()

    def test_empty_aliases_with_stale_ip_does_not_show(self):
        """aliases={} + only stale IP (>120s) → devices=[] (synthetic entry suppressed)."""
        now = time.time()
        aliases = {}
        conn = {"192.168.3.31": now - 300}  # 5 分钟前
        client, teardown = _make_client(aliases, conn)
        try:
            resp = client.get("/api/devices")
            body = resp.get_json()
            self.assertEqual(0, len(body["devices"]))
        finally:
            teardown()

    def test_active_ip_already_in_alias_ips_not_duplicated(self):
        """alias 已配 + alias.ips 含活跃 IP → 不再生成 synthetic entry 重复显示。"""
        now = time.time()
        aliases = {
            "phone": {"ip": "192.168.3.31", "port": 5555, "ips": ["192.168.3.31"]}
        }
        conn = {"192.168.3.31": now}
        client, teardown = _make_client(aliases, conn)
        try:
            resp = client.get("/api/devices")
            body = resp.get_json()
            devices = body["devices"]
            self.assertEqual(1, len(devices))
            self.assertEqual("phone", devices[0]["alias"])
        finally:
            teardown()

    def test_adb_connected_active_ip_carries_device_id(self):
        """活跃 IP 已 adb connect → synthetic entry 带 device_id + is_adb_connected=True。"""
        now = time.time()
        aliases = {}
        conn = {"192.168.3.31": now}
        adb_stdout = "List of devices attached\n192.168.3.31:5555\tdevice\n"
        client, teardown = _make_client(aliases, conn, adb_devices_stdout=adb_stdout)
        try:
            resp = client.get("/api/devices")
            body = resp.get_json()
            dev = body["devices"][0]
            self.assertEqual("192.168.3.31:5555", dev["device_id"])
            self.assertTrue(dev["is_adb_connected"])
            self.assertEqual(5555, dev["adb_port"])
        finally:
            teardown()

    def test_mixed_alias_and_unmatched_active_ip(self):
        """alias 已配 + 另有一台未配 alias 的活跃 IP → 两组设备都显示。"""
        now = time.time()
        aliases = {
            "phone": {"ip": "192.168.3.31", "port": 5555, "ips": ["192.168.3.31"]}
        }
        conn = {
            "192.168.3.31": now,
            "192.168.3.52": now - 30,  # 30s ago，仍在 120s 内
        }
        client, teardown = _make_client(aliases, conn)
        try:
            resp = client.get("/api/devices")
            body = resp.get_json()
            devices = body["devices"]
            self.assertEqual(2, len(devices))
            aliases_returned = {d["alias"] for d in devices}
            self.assertIn("phone", aliases_returned)
            self.assertIn(None, aliases_returned)
            unmatched = next(d for d in devices if d["alias"] is None)
            self.assertEqual("192.168.3.52", unmatched["ip"])
        finally:
            teardown()


if __name__ == "__main__":
    unittest.main()
