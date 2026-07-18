import socket
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import floating_window_app as fwa


class FloatingWindowAppModelTests(unittest.TestCase):
    def test_empty_bootstrap_renders_safe_empty_states(self):
        model = fwa.build_home_model({})
        self.assertEqual("暂无项目", model["title"])
        self.assertEqual([], model["ides"])
        self.assertEqual([], model["tasks"])
        self.assertEqual("未选择 IDE", model["selected_target"])

    def test_bootstrap_model_uses_project_ide_summary_and_tasks(self):
        model = fwa.build_home_model({
            "project": {"name": "AideLink", "capabilities": ["web", "android"]},
            "ides": [
                {"key": "trae", "name": "Trae", "running": True, "dispatchable": True, "busy": False},
                {"key": "codex", "name": "Codex", "running": True, "dispatchable": False, "busy": True},
                {"key": "oc", "name": "OpenCode", "running": False, "dispatchable": False},
            ],
            "selected_target": {"key": "trae", "name": "Trae"},
            "task_summary": {
                "needs_user": 2,
                "by_status": {"pending_test": 1, "running": 1, "queued": 1},
            },
            "tasks": [
                {"title": "桌面浮窗服务端适配", "status": "running", "target_ide": "trae"},
            ],
        })

        self.assertEqual("AideLink 📱🌐", model["title"])
        self.assertEqual(["web", "android"], model["capabilities"])
        self.assertEqual(["●", "🟡", "○"], [item["dot"] for item in model["ides"]])
        self.assertEqual({"待处理": 2, "待测试": 1, "进行中": 2}, model["summary"])
        self.assertEqual("执行中", model["tasks"][0]["status"])
        self.assertEqual("general", model["tasks"][0]["surface"])

    def test_task_surface_groups_android_and_web_tasks(self):
        model = fwa.build_home_model({
            "project": {"name": "AideLink", "capabilities": ["web", "android"]},
            "tasks": [
                {"title": "APK 安装异常", "metadata": {"platform": "Android"}},
                {"title": "登录页面调整", "metadata": {"platform": "Web"}},
            ],
        })

        self.assertEqual(["android", "web"], [task["surface"] for task in model["tasks"]])

    def test_generated_think_title_falls_back_to_task_text(self):
        model = fwa.build_home_model({
            "tasks": [{"title": "<think>The user wants...", "text": "修复登录页提示词"}],
        })

        self.assertEqual("修复登录页提示词", model["tasks"][0]["title"])

    def test_single_running_ide_is_selected_and_closed_target_is_replaced(self):
        ides = [
            {"key": "codex", "running": False, "dispatchable": False},
            {"key": "trae", "running": True, "dispatchable": True},
        ]
        self.assertEqual("trae", fwa.choose_selected_ide("codex", ides))

    def test_busy_running_ide_remains_selectable(self):
        self.assertEqual("codex", fwa.choose_selected_ide(
            None,
            [{"key": "codex", "running": True, "dispatchable": False, "busy": True}],
        ))

    def test_stopped_ide_clears_selection(self):
        self.assertIsNone(fwa.choose_selected_ide(
            "codex",
            [{"key": "codex", "running": False, "dispatchable": False}],
        ))

    def test_visible_task_actions_are_uniform_for_every_status(self):
        for status in ("待处理", "待测试", "执行中", "超时", "失败", "未派发"):
            with self.subTest(status=status):
                self.assertEqual(("copy", "view", "more"), fwa.VISIBLE_TASK_ACTIONS)

    def test_copy_uses_full_body_and_removes_reasoning_fragments(self):
        copied = fwa.task_copy_text({
            "title": "修复登录问题",
            "text": "<think>private reasoning</think>\n完整任务正文\nThe user wants internal details",
        })
        self.assertIn("完整任务正文", copied)
        self.assertNotIn("think", copied.lower())
        self.assertNotIn("The user wants", copied)

    def test_select_ide_only_changes_ui_state(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.selected_ide_key = "codex"
        app.current_model = {}
        app._render = Mock()

        app.select_ide("trae")

        self.assertEqual("trae", app.selected_ide_key)
        app._render.assert_called_once_with({})

    def test_send_uses_selected_ide_and_send_route(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.selected_ide_key = "trae"
        app._input_text = Mock(return_value="修复问题")
        app._run_api = Mock()

        app._send_input()

        self.assertEqual("/send", app._run_api.call_args.args[0])
        self.assertEqual(
            {"text": "修复问题", "target": "trae"},
            app._run_api.call_args.kwargs["payload"],
        )

    def test_create_task_and_inspiration_use_existing_server_routes(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.selected_ide_key = "codex"
        app._input_text = Mock(return_value="任务正文")
        app._run_api = Mock()

        app.create_task()
        self.assertEqual("/api/tasks/create", app._run_api.call_args.args[0])
        self.assertFalse(app._run_api.call_args.kwargs["payload"]["auto_dispatch"])

        app.save_inspiration()
        self.assertEqual("/api/tasks/inspiration", app._run_api.call_args.args[0])

    def test_task_confirm_uses_allowed_server_action_route(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app._run_api = Mock()

        app.execute_task_action("confirm_done", {"task_id": "task-1"})

        self.assertEqual("/api/tasks/task-1/confirm", app._run_api.call_args.args[0])

    def test_window_signal_sends_requested_command(self):
        received = []
        ready = threading.Event()
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        test_port = probe.getsockname()[1]
        probe.close()

        def server():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", test_port))
            sock.listen(1)
            ready.set()
            conn, _addr = sock.accept()
            with conn:
                received.append(conn.recv(32))
            sock.close()

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        ready.wait(timeout=1)
        with patch("floating_window_app.SHOW_SIGNAL_PORT", test_port):
            self.assertTrue(fwa.send_window_signal("close", timeout=1))
        thread.join(timeout=1)
        self.assertEqual([b"close"], received)

    def test_duplicate_instance_main_exits_after_signal(self):
        instance = Mock()
        instance.acquire.return_value = False
        with patch("floating_window_app.SingleInstance", return_value=instance), \
             patch("floating_window_app.send_window_signal", return_value=True) as send_signal:
            self.assertEqual(0, fwa.main())
        send_signal.assert_called_once_with("activate")

    def test_close_destroys_window(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.root = Mock()

        app.close()

        app.root.destroy.assert_called_once_with()
        app.root.withdraw.assert_not_called()


if __name__ == "__main__":
    unittest.main()
