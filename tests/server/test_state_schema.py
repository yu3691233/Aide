"""
关键状态文件 schema 快照测试。

目的:在产品化各阶段中,如果改动破坏了状态文件的顶层结构,此测试会变红。
这是阶段 0b 的回归安全网(见 docs/productization/productization-plan.md)。

如果状态文件不存在(CI 环境),跳过对应测试——它们是运行时产物。
"""

import json
import os
import unittest
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parents[2] / "server" / "state"
BRIDGE_DIR = STATE_DIR.parent


def _load(path: Path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class ChatHistorySchemaTests(unittest.TestCase):
    """chat_history.json: list,每个元素是 dict 含 sender/text/time。"""

    def test_chat_history_structure(self):
        data = _load(STATE_DIR / "chat_history.json")
        if data is None:
            self.skipTest("chat_history.json not found (runtime artifact)")
        self.assertIsInstance(data, list, "chat_history must be a list")
        for i, msg in enumerate(data):
            with self.subTest(msg_index=i):
                self.assertIsInstance(msg, dict)
                self.assertIn("sender", msg)
                self.assertIn("text", msg)
                self.assertIn("time", msg)
                self.assertIsInstance(msg["sender"], str)
                self.assertIsInstance(msg["text"], str)
                self.assertIsInstance(msg["time"], str)


class TasksSchemaTests(unittest.TestCase):
    """tasks.json / tasks_*.json: list,每个元素是 dict 含 task_id/title/text/status。"""

    def _check_task_list(self, data, source=""):
        self.assertIsInstance(data, list, f"tasks{source} must be a list")
        for i, task in enumerate(data):
            with self.subTest(task_index=i, source=source):
                self.assertIsInstance(task, dict)
                for key in ("task_id", "title", "text", "status"):
                    self.assertIn(key, task, f"task {i} missing {key}")
                self.assertIsInstance(task["task_id"], str)
                self.assertIsInstance(task["status"], str)

    def test_tasks_json_structure(self):
        data = _load(STATE_DIR / "tasks.json")
        if data is None:
            self.skipTest("tasks.json not found (runtime artifact)")
        self._check_task_list(data, " (tasks.json)")


class SettingsSchemaTests(unittest.TestCase):
    """aidelink_settings.json: dict,关键 key 必须存在(对照 SETTINGS_SCHEMA)。"""

    REQUIRED_KEYS = [
        "server_url", "wol_mac", "app_language", "app_theme",
        "dynamic_color", "notifications_enabled", "haptic_feedback",
        "monitor_interval_ms", "monitor_height_dp", "xiaomengling_model",
        "desktop_ide", "desktop_ide_path", "opencode_web_urls",
        "opencode_web_mode", "opencode_web_connection",
        "opencode_web_password", "opencode_web_username",
        "opencode_web_port", "project_dir", "projects",
        "current_project", "app_project_name",
    ]

    def test_settings_structure(self):
        data = _load(BRIDGE_DIR / "aidelink_settings.json")
        if data is None:
            self.skipTest("aidelink_settings.json not found (runtime artifact)")
        self.assertIsInstance(data, dict, "settings must be a dict")
        for key in self.REQUIRED_KEYS:
            self.assertIn(key, data, f"settings missing required key: {key}")
        self.assertIsInstance(data["projects"], list, "projects must be a list")
        self.assertIsInstance(data["opencode_web_urls"], dict, "opencode_web_urls must be a dict")


class IdeStatusSchemaTests(unittest.TestCase):
    """ide_status.json: dict[ide_key -> dict],value 含 ide/status/current_task_id。"""

    def test_ide_status_structure(self):
        data = _load(STATE_DIR / "ide_status.json")
        if data is None:
            self.skipTest("ide_status.json not found (runtime artifact)")
        self.assertIsInstance(data, dict, "ide_status must be a dict")
        for ide_key, entry in data.items():
            with self.subTest(ide_key=ide_key):
                self.assertIsInstance(entry, dict)
                self.assertIn("ide", entry)
                self.assertIn("status", entry)
                self.assertIn("current_task_id", entry)
                self.assertIsInstance(entry["ide"], str)
                self.assertIsInstance(entry["status"], str)


class IdeWindowBindingsSchemaTests(unittest.TestCase):
    """ide_window_bindings.json: dict[ide_key -> dict],value 含 title/process_name/exe_name/window_class。

    保护 gap 8.4 修复:窗口绑定必须按模式匹配存储,不能回退到存 HWND。
    """

    REQUIRED_BINDING_KEYS = ("title", "process_name", "exe_name", "window_class")

    def test_window_bindings_structure(self):
        data = _load(STATE_DIR / "ide_window_bindings.json")
        if data is None:
            self.skipTest("ide_window_bindings.json not found (runtime artifact)")
        self.assertIsInstance(data, dict, "bindings must be a dict")
        for ide_key, binding in data.items():
            with self.subTest(ide_key=ide_key):
                self.assertIsInstance(binding, dict)
                for key in self.REQUIRED_BINDING_KEYS:
                    self.assertIn(key, binding, f"binding {ide_key} missing {key}")
                    self.assertIsInstance(binding[key], str)
                # 保护 gap 8.4:不能有 hwnd 字段(回退到旧方式)
                self.assertNotIn("hwnd", binding, f"binding {ide_key} has hwnd (gap 8.4 regression)")


if __name__ == "__main__":
    unittest.main()
