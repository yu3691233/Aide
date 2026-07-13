import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from dispatch_utils import get_ide_running_statuses


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
        with patch.dict(sys.modules, {"psutil": fake_psutil}):
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


if __name__ == "__main__":
    unittest.main()
