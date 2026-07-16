import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import mcp_server


class _Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.body, ensure_ascii=False).encode("utf-8")


class McpServerTests(unittest.TestCase):
    def test_tools_include_ask_aide(self):
        names = {tool["name"] for tool in mcp_server.get_tool_definitions()}
        self.assertIn("ask_aide", names)

    def test_ask_aide_calls_bridge_and_returns_model_metadata(self):
        response = _Response({
            "ok": True,
            "response": "建议先写回归测试。",
            "model_used": "minimax",
            "task_id": "task_1",
        })
        with patch("mcp_server.urllib.request.urlopen", return_value=response) as urlopen:
            result = mcp_server.handle_ask_aide({"message": "分析启动问题", "task_type": "analysis"})

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual("分析启动问题", payload["message"])
        self.assertEqual("analysis", payload["task_type"])
        self.assertFalse(result.get("isError", False))
        self.assertIn("建议先写回归测试。", result["content"][0]["text"])
        self.assertIn("minimax", result["content"][0]["text"])

    def test_ask_aide_rejects_empty_message(self):
        result = mcp_server.handle_ask_aide({"message": "  "})
        self.assertTrue(result["isError"])

    def test_tools_include_delegation_loop(self):
        names = {tool["name"] for tool in mcp_server.get_tool_definitions()}
        self.assertTrue({
            "prepare_aidelink_delegation",
            "delegate_aidelink_task",
            "get_delegated_aidelink_task",
            "report_delegated_aidelink_task",
            "verify_delegated_aidelink_task",
        }.issubset(names))

    def test_tools_include_project_inspiration(self):
        names = {tool["name"] for tool in mcp_server.get_tool_definitions()}
        self.assertIn("create_aidelink_inspiration", names)

    def test_get_tasks_reads_project_runtime_and_defaults_to_actionable(self):
        class Runtime:
            def read_tasks(self):
                return [
                    {"task_id": "idea-1", "title": "later", "status": "draft", "priority": "high",
                     "target_ide": None, "updated_at": "2026-01-02", "metadata": {"content_kind": "inspiration"}},
                    {"task_id": "done-1", "title": "done", "status": "done", "priority": "medium",
                     "updated_at": "2026-01-01", "metadata": {}},
                ]

        with patch("mcp_server.get_runtime", return_value=Runtime()):
            result = mcp_server.handle_get_tasks({})

        text = result["content"][0]["text"]
        self.assertIn("idea-1", text)
        self.assertIn("灵感", text)
        self.assertNotIn("done-1", text)

    def test_get_tasks_can_return_inspiration_details(self):
        class Runtime:
            def read_tasks(self):
                return [{"task_id": "idea-1", "title": "later", "text": "full context", "status": "draft",
                         "updated_at": "2026-01-02", "metadata": {"content_kind": "inspiration"}}]

        with patch("mcp_server.get_runtime", return_value=Runtime()):
            result = mcp_server.handle_get_tasks({"scope": "inspirations", "include_details": True})

        self.assertIn("full context", result["content"][0]["text"])

    def test_create_inspiration_has_no_ide_target(self):
        response = _Response({
            "ok": True,
            "task": {"task_id": "idea-1", "text": "later", "status": "draft", "target_ide": None},
        })
        with patch("mcp_server.urllib.request.urlopen", return_value=response) as urlopen:
            result = mcp_server.handle_create_inspiration({"text": "later", "title": "idea"})

        self.assertFalse(result.get("isError", False))
        self.assertIn("idea-1", result["content"][0]["text"])
        self.assertNotIn("full context", result["content"][0]["text"])
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/api/tasks/inspiration"))
        self.assertEqual("later", json.loads(request.data.decode("utf-8"))["text"])

    def test_delegate_task_marks_primary_ide_source(self):
        class Runtime:
            def create_task(self, text, **kwargs):
                self.created = (text, kwargs)
                return {"task_id": "task-1", "status": "draft"}

            def assign_task(self, task_id, ide):
                return {"task_id": task_id, "target_ide": ide, "source": "primary_ide"}

        runtime = Runtime()
        with patch("mcp_server.get_runtime", return_value=runtime):
            with patch("dispatch_utils.dispatch_task", return_value=(True, "ok")):
                result = mcp_server.handle_delegate_task({
                    "task": "写测试", "target_ide": "trae", "user_confirmed": True,
                    "task_type": "test", "owned_paths": ["tests/server"],
                })

        self.assertFalse(result.get("isError", False))
        self.assertIn("primary_ide", result["content"][0]["text"])
        self.assertEqual(["tests/server"], runtime.created[1]["owned_paths"])

    def test_prepare_delegation_is_read_only_and_recommends_open_idle_worker(self):
        class Runtime:
            def get_ide_status(self, ide):
                return {"status": "busy" if ide == "codex" else "idle"}

            def is_ide_available(self, ide):
                return ide != "codex"

        ides = [
            {"key": "codex", "name": "ChatGPT", "is_primary": False},
            {"key": "trae", "name": "Trae"},
            {"key": "mimo", "name": "Mimo"},
        ]
        with patch("mcp_server.get_runtime", return_value=Runtime()), patch(
            "ide_scanner.get_all_ides", return_value=ides
        ), patch(
            "dispatch_utils.get_ide_running_statuses",
            return_value={"codex": True, "trae": True, "mimo": False},
        ):
            result = mcp_server.handle_prepare_delegation({
                "objective": "只读检查任务状态",
                "main_ide": "codex",
                "task_type": "research",
                "main_owned_paths": ["server/mcp_server.py"],
                "validation_commands": ["python -m unittest tests.server.test_mcp_server"],
            })

        payload = json.loads(result["content"][0]["text"])
        self.assertEqual("trae", payload["recommended_ide"])
        self.assertTrue(next(item for item in payload["ide_candidates"] if item["key"] == "codex")["is_manager"])
        self.assertEqual("complete_here", payload["choices"][0]["id"])
        self.assertTrue(payload["task_package"]["contract"]["result_ref_preferred"])
        self.assertIn("new_codex_session", {choice["id"] for choice in payload["choices"]})

    def test_delegate_requires_explicit_user_confirmation_without_creating_task(self):
        runtime = Mock()
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_delegate_task({"task": "检查", "target_ide": "trae"})

        self.assertTrue(result["isError"])
        runtime.create_task.assert_not_called()

    def test_code_delegation_rejects_overlapping_main_owned_paths(self):
        runtime = Mock()
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_delegate_task({
                "task": "改 MCP", "target_ide": "trae", "user_confirmed": True,
                "task_type": "code", "main_owned_paths": ["server"],
                "owned_paths": ["server/mcp_server.py"],
            })

        self.assertTrue(result["isError"])
        self.assertIn("文件范围重叠", result["content"][0]["text"])
        runtime.create_task.assert_not_called()

    def test_code_delegation_requires_worker_owned_paths(self):
        runtime = Mock()
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_delegate_task({
                "task": "改代码", "target_ide": "trae", "user_confirmed": True,
                "task_type": "code", "main_owned_paths": ["server/mcp_server.py"],
            })

        self.assertTrue(result["isError"])
        self.assertIn("必须声明 owned_paths", result["content"][0]["text"])
        runtime.create_task.assert_not_called()


if __name__ == "__main__":
    unittest.main()
