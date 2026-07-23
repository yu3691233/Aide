"""Regression tests for exact wireless-ADB connection validation."""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes import device_routes


class _FakeAdbResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class AdbConnectionValidationTests(unittest.TestCase):
    def test_explicit_port_does_not_reuse_another_port_on_same_ip(self):
        with patch.object(
            device_routes,
            "_adb_devices",
            return_value={
                "192.168.3.52:39371": "device",
                "192.168.3.31:5555": "device",
            },
        ):
            self.assertIsNone(
                device_routes._connected_adb_device_for("192.168.3.52", 34977)
            )
            self.assertEqual(
                "192.168.3.52:39371",
                device_routes._connected_adb_device_for("192.168.3.52"),
            )

    def test_connect_output_is_not_success_without_device_state(self):
        results = [_FakeAdbResult(0, "connected to 192.168.3.52:34977", "")]
        with (
            patch.object(device_routes, "_run_adb", side_effect=results),
            patch.object(device_routes, "_connected_adb_device_for", return_value=None),
            patch.object(device_routes._time, "sleep"),
        ):
            connected, output = device_routes._connect_adb("192.168.3.52", 34977)

        self.assertIsNone(connected)
        self.assertIn("connected to", output)

    def test_connect_succeeds_only_after_exact_device_is_visible(self):
        results = [
            _FakeAdbResult(0, "connected to 192.168.3.52:39371", ""),
            _FakeAdbResult(0, "", ""),
        ]
        with (
            patch.object(device_routes, "_run_adb", side_effect=results),
            patch.object(
                device_routes,
                "_connected_adb_device_for",
                side_effect=[None, "192.168.3.52:39371"],
            ),
            patch.object(device_routes._time, "sleep"),
        ):
            connected, _ = device_routes._connect_adb("192.168.3.52", 39371)

        self.assertEqual("192.168.3.52:39371", connected)

    def test_tcp_probe_distinguishes_reachable_adb_listener(self):
        fake_socket = MagicMock()
        with patch.object(
            device_routes.socket,
            "create_connection",
            return_value=fake_socket,
        ) as connect:
            self.assertTrue(device_routes._tcp_port_open("192.168.3.52", 40117))

        connect.assert_called_once_with(("192.168.3.52", 40117), timeout=0.8)

    def test_reachable_port_explains_pairing_requirement(self):
        with patch.object(device_routes, "_tcp_port_open", return_value=True):
            error = device_routes._adb_connection_error("192.168.3.52", 43959)

        self.assertIn("尚未", error)
        self.assertIn("配对码", error)
        self.assertIn("Android 不允许 App 自动读取", error)

    def test_wireless_result_never_crosses_to_another_device(self):
        started_at = time.time()
        phone_result = {
            "ok": True,
            "ip": "192.168.3.31",
            "port": 5555,
            "method": "root",
            "request_id": "phone-request",
            "time": started_at + 0.1,
        }
        with (
            patch.object(
                device_routes,
                "_wireless_result_by_request",
                {"tablet-request": phone_result},
            ),
            patch.object(
                device_routes,
                "_wireless_result_pending",
                {"192.168.3.31": phone_result},
            ),
        ):
            result = device_routes._find_wireless_result(
                "tablet-request",
                started_at,
                ["192.168.3.52"],
            )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
