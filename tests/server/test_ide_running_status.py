import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from dispatch_utils import get_ide_running_statuses
from routes.ide_routes import get_active_ide_status


class _Process:
    def __init__(self, name, exe, cmdline):
        self.info = {"name": name, "exe": exe, "cmdline": cmdline}


class IdeRunningStatusTests(unittest.TestCase):
    def setUp(self):
        self.ides = [
            {
                "key": "oc",
                "name": "OpenCode",
                "path": r"C:\Apps\OpenCode\OpenCode.exe",
            },
            {
                "key": "codex",
                "name": "ChatGPT",
                "path": r"C:\Apps\Codex\ChatGPT.exe",
            },
        ]

    def test_processes_are_snapshotted_once_for_all_ides(self):
        process_iter_calls = 0

        def process_iter(_attrs):
            nonlocal process_iter_calls
            process_iter_calls += 1
            return [_Process("ChatGPT.exe", r"C:\Apps\Codex\ChatGPT.exe", [])]

        fake_psutil = types.SimpleNamespace(
            process_iter=process_iter,
            NoSuchProcess=RuntimeError,
            AccessDenied=PermissionError,
        )
        with patch("dispatch_utils._has_visible_window_for_pid", return_value=True), patch.dict(
            sys.modules, {"psutil": fake_psutil}
        ):
            statuses = get_ide_running_statuses(self.ides)

        self.assertEqual(1, process_iter_calls)
        self.assertEqual({"oc": False, "codex": True}, statuses)

    def test_opencode_web_server_is_not_reported_as_desktop(self):
        fake_psutil = types.SimpleNamespace(
            process_iter=lambda _attrs: [
                _Process(
                    "opencode.exe",
                    r"C:\Apps\OpenCode\OpenCode.exe",
                    ["opencode", "serve", "--port", "4096"],
                )
            ],
            NoSuchProcess=RuntimeError,
            AccessDenied=PermissionError,
        )
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            statuses = get_ide_running_statuses(self.ides)

        self.assertFalse(statuses["oc"])

    def test_minimax_mcp_helper_is_not_reported_as_minimax_code(self):
        minimax = {
            "key": "minimax",
            "name": "MiniMax Code",
            "path": r"C:\Apps\MiniMax Code\MiniMax Code.exe",
        }
        fake_psutil = types.SimpleNamespace(
            process_iter=lambda _attrs: [
                _Process("minimax-mcp.exe", r"C:\Tools\minimax-mcp.exe", ["minimax-mcp"])
            ],
            NoSuchProcess=RuntimeError,
            AccessDenied=PermissionError,
        )
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
            statuses = get_ide_running_statuses([minimax])

        self.assertFalse(statuses["minimax"])

    def test_exact_ide_process_requires_a_visible_window(self):
        trae = {
            "key": "trae_solo_cn",
            "name": "TRAE SOLO CN",
            "path": r"C:\Apps\TRAE SOLO CN\TRAE SOLO CN.exe",
        }
        fake_psutil = types.SimpleNamespace(
            process_iter=lambda _attrs: [
                _Process("TRAE SOLO CN.exe", r"C:\Apps\TRAE SOLO CN\TRAE SOLO CN.exe", [])
            ],
            NoSuchProcess=RuntimeError,
            AccessDenied=PermissionError,
        )
        with patch("dispatch_utils._has_visible_window_for_pid", return_value=False), patch.dict(
            sys.modules, {"psutil": fake_psutil}
        ):
            hidden = get_ide_running_statuses([trae])
        with patch("dispatch_utils._has_visible_window_for_pid", return_value=True), patch.dict(
            sys.modules, {"psutil": fake_psutil}
        ):
            visible = get_ide_running_statuses([trae])

        self.assertFalse(hidden["trae_solo_cn"])
        self.assertTrue(visible["trae_solo_cn"])

    def test_active_status_combines_presence_and_runtime_busy(self):
        from flask import Flask

        app = Flask(__name__)
        runtime = types.SimpleNamespace(
            get_ide_status=lambda key: {
                "status": "busy",
                "current_task_id": "task-1",
                "lease_expires_at": "2026-07-18T12:00:00",
                "error": None,
            }
        )
        with app.test_request_context("/api/ide/active_status"), \
             patch("ide_scanner.get_all_ides", return_value=[self.ides[1]]), \
             patch("dispatch_utils.get_ide_running_statuses", return_value={"codex": True}), \
             patch("shared_runtime.runtime", runtime):
            response = get_active_ide_status()

        data = response.get_json()
        self.assertEqual("codex", data["ides"][0]["key"])
        self.assertTrue(data["ides"][0]["running"])
        self.assertTrue(data["ides"][0]["busy"])
        self.assertFalse(data["ides"][0]["dispatchable"])
        self.assertEqual(["ide_busy"], data["ides"][0]["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
