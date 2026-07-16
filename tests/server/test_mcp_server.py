import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


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
            "delegate_aidelink_task",
            "get_delegated_aidelink_task",
            "report_delegated_aidelink_task",
            "verify_delegated_aidelink_task",
        }.issubset(names))

    def test_tools_include_project_inspiration(self):
        names = {tool["name"] for tool in mcp_server.get_tool_definitions()}
        self.assertIn("create_aidelink_inspiration", names)

    def test_create_inspiration_has_no_ide_target(self):
        response = _Response({
            "ok": True,
            "task": {"task_id": "idea-1", "text": "later", "status": "draft", "target_ide": None},
        })
        with patch("mcp_server.urllib.request.urlopen", return_value=response) as urlopen:
            result = mcp_server.handle_create_inspiration({"text": "later", "title": "idea"})

        self.assertFalse(result.get("isError", False))
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

        with patch("mcp_server.get_runtime", return_value=Runtime()):
            with patch("dispatch_utils.dispatch_task", return_value=(True, "ok")):
                result = mcp_server.handle_delegate_task({"task": "写测试", "target_ide": "trae"})

        self.assertFalse(result.get("isError", False))
        self.assertIn("primary_ide", result["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
