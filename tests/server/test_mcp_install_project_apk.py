"""Tests for adb_install_project_apk MCP tool.

Covers the one-click APK install workflow:
    /api/devices → /api/debug/connected (fallback) → /api/settings → /api/adb/connect → /api/adb/project-install

Mock strategy: patch mcp_server.urllib.request.urlopen to capture requests and
return canned responses. Each test asserts on URL, payload, status flow, and
final MCP result shape.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import mcp_server


class _FakeResponse:
    def __init__(self, body):
        self._body = json.dumps(body, ensure_ascii=False).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Recorder:
    """Captures urlopen calls and returns scripted responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, request, timeout=None):  # mirrors urllib.request.urlopen signature
        self.calls.append((request.full_url, json.loads(request.data.decode("utf-8")) if request.data else None))
        return self._responses.pop(0)


def _suffix(url):
    return url.split("127.0.0.1:5000")[-1]


class AdbInstallProjectApkTests(unittest.TestCase):
    def test_tool_registered(self):
        names = {tool["name"] for tool in mcp_server.get_tool_definitions()}
        self.assertIn("adb_install_project_apk", names)

    def test_required_only_user_confirmed(self):
        """alias/ip 都不再是 required，只保留 user_confirmed。"""
        tool = next(t for t in mcp_server.get_tool_definitions() if t["name"] == "adb_install_project_apk")
        self.assertEqual(["user_confirmed"], tool["inputSchema"].get("required", []))
        prop_names = set(tool["inputSchema"]["properties"].keys())
        self.assertIn("alias", prop_names)
        self.assertIn("ip", prop_names)
        self.assertIn("port", prop_names)

    def test_user_confirmed_false_returns_error_and_no_http_calls(self):
        result = mcp_server.handle_adb_install_project_apk({
            "alias": "phone",
            "user_confirmed": False,
        })
        self.assertTrue(result["isError"])
        self.assertIn("user_confirmed", result["content"][0]["text"])

    def test_user_confirmed_missing_returns_error(self):
        result = mcp_server.handle_adb_install_project_apk({"alias": "phone"})
        self.assertTrue(result["isError"])
        self.assertIn("user_confirmed", result["content"][0]["text"])

    def test_alias_missing_and_no_active_ip_returns_error(self):
        """alias 缺失 + /api/debug/connected 空 → 报错（含 hint）。"""
        recorder = _Recorder([
            _FakeResponse({"ok": True, "aliases": {}, "devices": []}),
            _FakeResponse({}),  # /api/debug/connected 返回空
        ])
        with patch("mcp_server.urllib.request.urlopen", side_effect=recorder):
            result = mcp_server.handle_adb_install_project_apk({"user_confirmed": True})
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("/api/debug/connected", text)
        self.assertIn("无活跃 IP", text)
        urls = [_suffix(c[0]) for c in recorder.calls]
        self.assertEqual(["/api/devices", "/api/debug/connected"], urls)

    def test_alias_not_found_and_no_active_ip_returns_error(self):
        """alias 未找到 + /api/debug/connected 空 → 报错（含 hint）。"""
        recorder = _Recorder([
            _FakeResponse({"ok": True, "aliases": {}, "devices": []}),
            _FakeResponse({}),
        ])
        with patch("mcp_server.urllib.request.urlopen", side_effect=recorder):
            result = mcp_server.handle_adb_install_project_apk({
                "alias": "missing_phone",
                "user_confirmed": True,
                "project_path": "F:\\aide",
            })
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("missing_phone", text)
        self.assertIn("无活跃 IP", text)
        urls = [_suffix(c[0]) for c in recorder.calls]
        self.assertEqual(["/api/devices", "/api/debug/connected"], urls)

    def test_alias_missing_multiple_active_ips_returns_list(self):
        """alias 缺失 + 多台活跃 IP → 返回列表让用户选 ip。"""
        recorder = _Recorder([
            _FakeResponse({"ok": True, "aliases": {}, "devices": []}),
            _FakeResponse({"192.168.1.10": "5s ago", "192.168.1.20": "30s ago"}),
        ])
        with patch("mcp_server.urllib.request.urlopen", side_effect=recorder):
            result = mcp_server.handle_adb_install_project_apk({"user_confirmed": True})
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("192.168.1.10", text)
        self.assertIn("192.168.1.20", text)
        self.assertIn("2 台活跃设备", text)
        urls = [_suffix(c[0]) for c in recorder.calls]
        self.assertEqual(["/api/devices", "/api/debug/connected"], urls)

    def test_alias_missing_single_active_ip_falls_back(self):
        """alias 缺失 + 单台活跃 IP → 自动选用，走完整 install 流程。"""
        recorder = _Recorder([
            _FakeResponse({"ok": True, "aliases": {}, "devices": []}),
            _FakeResponse({"192.168.1.10": "5s ago"}),
            _FakeResponse({"ok": True, "settings": {
                "current_project": "F:\\aide",
                "projects": [{"path": "F:\\aide", "name": "aide"}],
            }}),
            _FakeResponse({"ok": True, "device": "192.168.1.10:5555",
                            "ip": "192.168.1.10", "port": 5555, "method": "wireless_enabled"}),
            _FakeResponse({
                "ok": True,
                "message": "目标项目 APK 安装完成",
                "apk_path": "F:\\aide\\AideLink-app\\app\\build\\outputs\\apk\\debug\\app-debug.apk",
                "application_id": "cc.aidelink.app",
                "output": "Success",
            }),
        ])
        with patch("mcp_server.urllib.request.urlopen", side_effect=recorder):
            result = mcp_server.handle_adb_install_project_apk({"user_confirmed": True})
        self.assertFalse(result.get("isError", False))
        payload = json.loads(result["content"][0]["text"])
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["alias"])
        self.assertEqual("192.168.1.10", payload["ip"])
        self.assertEqual(5555, payload["port"])
        # 5 calls: devices → connected → settings → connect → project-install
        self.assertEqual(5, len(recorder.calls))
        urls = [_suffix(c[0]) for c in recorder.calls]
        self.assertEqual(
            ["/api/devices", "/api/debug/connected", "/api/settings", "/api/adb/connect", "/api/adb/project-install"],
            urls,
        )
        # connect payload 用 ip+port（alias 未解析到）
        connect_payload = recorder.calls[3][1]
        self.assertNotIn("alias", connect_payload)
        self.assertEqual("192.168.1.10", connect_payload["ip"])
        self.assertEqual(5555, connect_payload["port"])

    def test_alias_not_found_falls_back_to_active_ip(self):
        """alias 提供但未找到 + /api/debug/connected 有活跃 IP → 自动选用活跃 IP。"""
        recorder = _Recorder([
            _FakeResponse({"ok": True, "aliases": {"other": {"ip": "192.168.1.99"}}, "devices": []}),
            _FakeResponse({"192.168.1.10": "5s ago"}),
            _FakeResponse({"ok": True, "settings": {
                "current_project": "F:\\aide",
                "projects": [{"path": "F:\\aide", "name": "aide"}],
            }}),
            _FakeResponse({"ok": True, "device": "192.168.1.10:5555",
                            "ip": "192.168.1.10", "port": 5555, "method": "wireless_enabled"}),
            _FakeResponse({"ok": True, "apk_path": "F:\\app.apk", "application_id": "cc.aidelink.app"}),
        ])
        with patch("mcp_server.urllib.request.urlopen", side_effect=recorder):
            result = mcp_server.handle_adb_install_project_apk({
                "alias": "missing_phone",
                "user_confirmed": True,
            })
        self.assertFalse(result.get("isError", False))
        payload = json.loads(result["content"][0]["text"])
        self.assertIsNone(payload["alias"])
        self.assertEqual("192.168.1.10", payload["ip"])

    def test_explicit_ip_falls_back_without_alias(self):
        """alias 缺失 + ip 提供 → 用 ip（跳过单/多台自动选择逻辑）。"""
        recorder = _Recorder([
            _FakeResponse({"ok": True, "aliases": {}, "devices": []}),
            _FakeResponse({"192.168.1.10": "5s ago", "192.168.1.20": "10s ago"}),
            _FakeResponse({"ok": True, "settings": {
                "current_project": "F:\\aide",
                "projects": [{"path": "F:\\aide", "name": "aide"}],
            }}),
            _FakeResponse({"ok": True, "device": "192.168.1.20:5555",
                            "ip": "192.168.1.20", "port": 5555, "method": "adb_connect"}),
            _FakeResponse({"ok": True, "apk_path": "F:\\app.apk", "application_id": "cc.aidelink.app"}),
        ])
        with patch("mcp_server.urllib.request.urlopen", side_effect=recorder):
            result = mcp_server.handle_adb_install_project_apk({
                "ip": "192.168.1.20",
                "user_confirmed": True,
            })
        self.assertFalse(result.get("isError", False))
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual("192.168.1.20", payload["ip"])
        # 即使有多台活跃设备，因为显式传了 ip，不会触发 list 返回
        connect_payload = recorder.calls[3][1]
        self.assertEqual("192.168.1.20", connect_payload["ip"])

    def test_project_not_in_whitelist_returns_resolve_apk_error(self):
        """alias 找到 → 跳过 connected → settings 校验失败。"""
        recorder = _Recorder([
            _FakeResponse({"ok": True, "aliases": {"phone": {"ip": "192.168.1.10", "port": 5555}}, "devices": []}),
            _FakeResponse({"ok": True, "settings": {
                "current_project": "F:\\aide",
                "projects": [{"path": "F:\\other", "name": "other"}],
            }}),
        ])
        with patch("mcp_server.urllib.request.urlopen", side_effect=recorder):
            result = mcp_server.handle_adb_install_project_apk({
                "alias": "phone",
                "user_confirmed": True,
                "project_path": "F:\\aide",
            })
        self.assertTrue(result["isError"])
        self.assertIn("settings.projects", result["content"][0]["text"])
        # alias 路径不调 /api/debug/connected
        urls = [_suffix(c[0]) for c in recorder.calls]
        self.assertEqual(["/api/devices", "/api/settings"], urls)

    def test_install_failure_returns_stage_install_error(self):
        recorder = _Recorder([
            _FakeResponse({"ok": True, "aliases": {"phone": {"ip": "192.168.1.10", "port": 5555}}, "devices": []}),
            _FakeResponse({"ok": True, "settings": {
                "current_project": "F:\\aide",
                "projects": [{"path": "F:\\aide", "name": "aide"}],
            }}),
            _FakeResponse({"ok": True, "device": "192.168.1.10:5555",
                            "ip": "192.168.1.10", "port": 5555, "method": "adb_connect"}),
            _FakeResponse({"ok": False, "error": "INSTALL_FAILED_VERSION_DOWNGRADE"}),
        ])
        with patch("mcp_server.urllib.request.urlopen", side_effect=recorder):
            result = mcp_server.handle_adb_install_project_apk({
                "alias": "phone",
                "user_confirmed": True,
                "timeout": 30,
            })
        self.assertTrue(result["isError"])
        self.assertIn("INSTALL_FAILED_VERSION_DOWNGRADE", result["content"][0]["text"])
        # Three writes happened: connect + install (devices + settings are reads).
        write_calls = [c for c in recorder.calls if c[1] is not None]
        self.assertEqual(2, len(write_calls))
        self.assertTrue(write_calls[0][0].endswith("/api/adb/connect"))
        self.assertEqual("phone", write_calls[0][1]["alias"])
        self.assertTrue(write_calls[1][0].endswith("/api/adb/project-install"))
        self.assertEqual("F:\\aide", write_calls[1][1]["project_path"])

    def test_happy_path_returns_full_payload(self):
        recorder = _Recorder([
            _FakeResponse({"ok": True, "aliases": {"phone": {"ip": "192.168.1.10", "port": 5555}}, "devices": []}),
            _FakeResponse({"ok": True, "settings": {
                "current_project": "F:\\aide",
                "projects": [{"path": "F:\\aide", "name": "aide"}],
            }}),
            _FakeResponse({"ok": True, "device": "192.168.1.10:5555",
                            "ip": "192.168.1.10", "port": 5555, "method": "wireless_enabled"}),
            _FakeResponse({
                "ok": True,
                "message": "目标项目 APK 安装完成",
                "device": "192.168.1.10:5555",
                "apk_path": "F:\\aide\\AideLink-app\\app\\build\\outputs\\apk\\debug\\app-debug.apk",
                "application_id": "cc.aidelink.app",
                "output": "Success",
            }),
        ])
        with patch("mcp_server.urllib.request.urlopen", side_effect=recorder):
            result = mcp_server.handle_adb_install_project_apk({
                "alias": "phone",
                "user_confirmed": True,
                "timeout": 60,
            })
        self.assertFalse(result.get("isError", False))
        payload = json.loads(result["content"][0]["text"])
        self.assertTrue(payload["ok"])
        self.assertEqual("phone", payload["alias"])
        self.assertEqual("192.168.1.10", payload["ip"])
        self.assertEqual(5555, payload["port"])
        self.assertEqual("F:\\aide", payload["project_path"])
        self.assertEqual("cc.aidelink.app", payload["application_id"])
        self.assertEqual("wireless_enabled", payload["method"])
        self.assertIn("app-debug.apk", payload["apk_path"])
        # alias 路径 4 calls: devices → settings → connect → project-install
        self.assertEqual(4, len(recorder.calls))
        urls = [_suffix(c[0]) for c in recorder.calls]
        self.assertEqual(
            ["/api/devices", "/api/settings", "/api/adb/connect", "/api/adb/project-install"],
            urls,
        )
        # connect payload uses alias path.
        connect_payload = recorder.calls[2][1]
        self.assertEqual("phone", connect_payload["alias"])
        self.assertEqual(60, connect_payload["timeout"])
        # project-install payload carries ip/port/project_path; no apk_path unless explicit.
        install_payload = recorder.calls[3][1]
        self.assertEqual("192.168.1.10", install_payload["ip"])
        self.assertEqual(5555, install_payload["port"])
        self.assertEqual("F:\\aide", install_payload["project_path"])
        self.assertNotIn("apk_path", install_payload)

    def test_explicit_apk_path_is_forwarded(self):
        explicit_apk = "F:\\aide\\AideLink-app\\app\\build\\outputs\\apk\\debug\\app-debug.apk"
        recorder = _Recorder([
            _FakeResponse({"ok": True, "aliases": {"phone": {"ip": "192.168.1.10", "port": 5555}}, "devices": []}),
            _FakeResponse({"ok": True, "settings": {
                "current_project": "F:\\aide",
                "projects": [{"path": "F:\\aide", "name": "aide"}],
            }}),
            _FakeResponse({"ok": True, "device": "192.168.1.10:5555",
                            "ip": "192.168.1.10", "port": 5555, "method": "already_connected"}),
            _FakeResponse({"ok": True, "apk_path": explicit_apk, "application_id": "cc.aidelink.app"}),
        ])
        with patch("mcp_server.urllib.request.urlopen", side_effect=recorder):
            result = mcp_server.handle_adb_install_project_apk({
                "alias": "phone",
                "user_confirmed": True,
                "apk_path": explicit_apk,
            })
        self.assertFalse(result.get("isError", False))
        install_payload = recorder.calls[3][1]
        self.assertEqual(explicit_apk, install_payload["apk_path"])

    def test_connect_failure_returns_ensure_device_error(self):
        recorder = _Recorder([
            _FakeResponse({"ok": True, "aliases": {"phone": {"ip": "192.168.1.10", "port": 5555}}, "devices": []}),
            _FakeResponse({"ok": True, "settings": {
                "current_project": "F:\\aide",
                "projects": [{"path": "F:\\aide", "name": "aide"}],
            }}),
            _FakeResponse({"ok": False, "error": "等待超时(30s)，App 未回报或连接失败"}),
        ])
        with patch("mcp_server.urllib.request.urlopen", side_effect=recorder):
            result = mcp_server.handle_adb_install_project_apk({
                "alias": "phone",
                "user_confirmed": True,
                "timeout": 30,
            })
        self.assertTrue(result["isError"])
        self.assertIn("ensure_device", result["content"][0]["text"])
        # install endpoint was NOT called.
        urls = [_suffix(c[0]) for c in recorder.calls]
        self.assertFalse(any("/api/adb/project-install" in u for u in urls))


if __name__ == "__main__":
    unittest.main()
