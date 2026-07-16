import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import mcp_server
from task_runtime import TaskRuntime


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
            "get_aidelink_workflow",
            "delegate_aidelink_task",
            "get_delegated_aidelink_task",
            "report_delegated_aidelink_task",
            "fail_delegated_aidelink_task",
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
                return {"task_id": task_id, "target_ide": ide, "source": "primary_ide", "status": "queued"}

            def update_task(self, task_id, **fields):
                self.updated = (task_id, fields)
                return {"task_id": task_id, "status": "draft", **fields}

        runtime = Runtime()
        with patch("mcp_server.get_runtime", return_value=runtime):
            with patch("dispatch_utils.dispatch_task", return_value=(True, "ok")):
                result = mcp_server.handle_delegate_task({
                    "task": "写测试", "target_ide": "trae", "user_confirmed": True,
                    "task_type": "test", "owned_paths": ["tests/server"],
                })

        self.assertFalse(result.get("isError", False))
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual("task-1", payload["task_id"])
        self.assertEqual(["tests/server"], runtime.created[1]["owned_paths"])
        self.assertIn("report_delegated_aidelink_task", runtime.updated[1]["text"])

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
        self.assertEqual(["trae"], [item["key"] for item in payload["ide_candidates"]])
        self.assertEqual("complete_here", payload["choices"][0]["id"])
        self.assertTrue(payload["task_package"]["contract"]["result_ref_required"])
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

    def test_worker_report_requires_result_ref_for_new_delegations(self):
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "task-1", "source": "primary_ide", "status": "running",
            "metadata": {"result_ref_required": True},
        }
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_report_delegated_task({"task_id": "task-1", "summary": "通过"})

        self.assertTrue(result["isError"])
        self.assertIn("result_ref", result["content"][0]["text"])
        runtime.mark_task_done.assert_not_called()

    def test_worker_report_moves_task_to_pending_test_with_evidence(self):
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "task-1", "source": "primary_ide", "status": "running",
            "metadata": {"result_ref_required": True},
        }
        runtime.mark_task_done.return_value = {"task_id": "task-1", "status": "pending_test"}
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_report_delegated_task({
                "task_id": "task-1", "summary": "测试通过", "result_ref": "test:python -m unittest",
            })

        payload = json.loads(result["content"][0]["text"])
        self.assertEqual("pending_test", payload["status"])
        runtime.mark_task_done.assert_called_once_with(
            "task-1", summary="测试通过", result_ref="test:python -m unittest"
        )

    def test_manager_verification_only_completes_pending_test_task(self):
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "task-1", "source": "primary_ide", "status": "pending_test",
            "metadata": {"result_ref_required": True}, "result_ref": "commit:abc123",
        }
        runtime.confirm_task_done.return_value = {"task_id": "task-1", "status": "done"}
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_verify_delegated_task({
                "task_id": "task-1", "verification_summary": "tests passed",
            })

        payload = json.loads(result["content"][0]["text"])
        self.assertEqual("done", payload["status"])
        runtime.confirm_task_done.assert_called_once_with("task-1")

    def test_manager_cannot_complete_new_delegation_without_result_ref(self):
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "task-1", "source": "primary_ide", "status": "pending_test",
            "metadata": {"result_ref_required": True}, "result_ref": None,
        }
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_verify_delegated_task({
                "task_id": "task-1", "verification_summary": "looks fine",
            })

        self.assertTrue(result["isError"])
        runtime.confirm_task_done.assert_not_called()

    def test_worker_can_report_failure_without_marking_done(self):
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "task-1", "source": "primary_ide", "status": "running",
        }
        runtime.mark_task_failed.return_value = {"task_id": "task-1", "status": "failed"}
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_fail_delegated_task({
                "task_id": "task-1", "error": "dependency missing",
            })

        payload = json.loads(result["content"][0]["text"])
        self.assertEqual("failed", payload["status"])
        runtime.confirm_task_done.assert_not_called()

    def test_real_runtime_delegation_report_and_manager_verification_loop(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            TaskRuntime, "_ensure_timeout_scanner"
        ), patch.object(TaskRuntime, "_try_dispatch_next_queued", return_value=None):
            runtime = TaskRuntime(temp_dir)
            with patch("mcp_server.get_runtime", return_value=runtime):
                delegated = mcp_server.handle_delegate_task({
                    "task": "验证闭环", "target_ide": "trae_solo_cn",
                    "user_confirmed": True, "dispatch": False,
                    "task_type": "test", "owned_paths": ["tests/server"],
                })
                task_id = json.loads(delegated["content"][0]["text"])["task_id"]
                runtime.mark_task_running(task_id, "trae_solo_cn")
                reported = mcp_server.handle_report_delegated_task({
                    "task_id": task_id, "summary": "定向测试通过",
                    "result_ref": "test:python -m unittest tests.server.test_mcp_server",
                })
                verified = mcp_server.handle_verify_delegated_task({
                    "task_id": task_id, "verification_summary": "主 IDE 复跑测试通过",
                })

            self.assertEqual("pending_test", json.loads(reported["content"][0]["text"])["status"])
            self.assertEqual("done", json.loads(verified["content"][0]["text"])["status"])
            final_task = runtime.get_task(task_id)
            self.assertEqual("done", final_task["status"])
            self.assertEqual("主 IDE 复跑测试通过", final_task["metadata"]["manager_verification"])

    def test_worker_report_supplements_missing_result_ref_for_pending_test(self):
        """补报路径：pending_test + result_ref=null 时 worker 可补传 result_ref，状态不变。"""
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "task-stuck", "source": "primary_ide", "status": "pending_test",
            "metadata": {"result_ref_required": True}, "result_ref": None,
        }
        runtime.update_task.return_value = {"task_id": "task-stuck", "status": "pending_test"}
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_report_delegated_task({
                "task_id": "task-stuck",
                "summary": "补报：实际完成证据",
                "result_ref": "commit:abc123",
            })

        self.assertFalse(result.get("isError", False))
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual("pending_test", payload["status"])
        self.assertEqual("commit:abc123", payload["result_ref"])
        # 关键：不调 mark_task_done（避免重置状态机），只 update_task 补写 result_ref
        runtime.mark_task_done.assert_not_called()
        runtime.update_task.assert_called_once_with(
            "task-stuck", summary="补报：实际完成证据", result_ref="commit:abc123"
        )

    def test_worker_report_still_rejects_missing_result_ref_for_pending_test(self):
        """补报路径仍要求 result_ref：result_ref_required 任务缺 result_ref 一律拒绝。"""
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "task-stuck", "source": "primary_ide", "status": "pending_test",
            "metadata": {"result_ref_required": True}, "result_ref": None,
        }
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_report_delegated_task({
                "task_id": "task-stuck", "summary": "缺证据",
            })

        self.assertTrue(result["isError"])
        self.assertIn("result_ref", result["content"][0]["text"])
        runtime.update_task.assert_not_called()
        runtime.mark_task_done.assert_not_called()

    def test_worker_report_rejects_supplement_when_result_ref_already_present(self):
        """补报路径禁止覆盖：pending_test + 已有 result_ref 拒绝补报。"""
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "task-stuck", "source": "primary_ide", "status": "pending_test",
            "metadata": {"result_ref_required": True}, "result_ref": "commit:orig",
        }
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_report_delegated_task({
                "task_id": "task-stuck",
                "summary": "试图覆盖原证据",
                "result_ref": "commit:new",
            })

        self.assertTrue(result["isError"])
        self.assertIn("已有 result_ref", result["content"][0]["text"])
        runtime.update_task.assert_not_called()
        runtime.mark_task_done.assert_not_called()

    def test_worker_fail_recovers_pending_test_deadlock(self):
        """pending_test 死锁任务可经 fail 路径释放为 failed，交主 IDE 决策。"""
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "task-stuck", "source": "primary_ide", "status": "pending_test",
            "metadata": {"result_ref_required": True}, "result_ref": None,
        }
        runtime.mark_task_failed.return_value = {"task_id": "task-stuck", "status": "failed"}
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_fail_delegated_task({
                "task_id": "task-stuck",
                "error": "被自动推进死锁，转 failed 释放",
                "result_ref": "inline:部分证据",
            })

        payload = json.loads(result["content"][0]["text"])
        self.assertEqual("failed", payload["status"])
        self.assertEqual("inline:部分证据", payload["result_ref"])
        runtime.mark_task_failed.assert_called_once_with("task-stuck", error="被自动推进死锁，转 failed 释放")
        runtime.update_task.assert_called_once_with("task-stuck", result_ref="inline:部分证据")

    def test_worker_fail_rejected_when_result_ref_already_present(self):
        """fail 路径禁止降级：pending_test + 已有 result_ref 拒绝降为 failed。"""
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "task-stuck", "source": "primary_ide", "status": "pending_test",
            "metadata": {"result_ref_required": True}, "result_ref": "commit:orig",
        }
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_fail_delegated_task({
                "task_id": "task-stuck", "error": "试图降级",
            })

        self.assertTrue(result["isError"])
        self.assertIn("已有 result_ref", result["content"][0]["text"])
        runtime.mark_task_failed.assert_not_called()

    def test_verify_keeps_result_ref_hard_gate_after_supplement_path(self):
        """补报路径不放宽 verify：pending_test + result_ref=null 仍被 verify 拒绝。"""
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "task-stuck", "source": "primary_ide", "status": "pending_test",
            "metadata": {"result_ref_required": True}, "result_ref": None,
        }
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_verify_delegated_task({
                "task_id": "task-stuck", "verification_summary": "试图绕过 result_ref",
            })

        self.assertTrue(result["isError"])
        self.assertIn("result_ref", result["content"][0]["text"])
        runtime.confirm_task_done.assert_not_called()

    def test_real_runtime_supplement_then_verify_loop(self):
        """端到端：pending_test+result_ref=null → 补报 → verify 通过。"""
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            TaskRuntime, "_ensure_timeout_scanner"
        ), patch.object(TaskRuntime, "_try_dispatch_next_queued", return_value=None):
            runtime = TaskRuntime(temp_dir)
            with patch("mcp_server.get_runtime", return_value=runtime):
                delegated = mcp_server.handle_delegate_task({
                    "task": "验证补报闭环", "target_ide": "trae_solo_cn",
                    "user_confirmed": True, "dispatch": False,
                    "task_type": "test", "owned_paths": ["tests/server"],
                })
                task_id = json.loads(delegated["content"][0]["text"])["task_id"]
                runtime.mark_task_running(task_id, "trae_solo_cn")
                # 模拟 TaskMonitor 抢跑：直接调 mark_task_done 不带 result_ref
                runtime.mark_task_done(task_id, summary="抢跑：无 result_ref")
                self.assertEqual("pending_test", runtime.get_task(task_id)["status"])
                self.assertIsNone(runtime.get_task(task_id)["result_ref"])
                # 此时 report/fail 原本被状态守卫拒绝；现在 report 可补报
                supplemented = mcp_server.handle_report_delegated_task({
                    "task_id": task_id,
                    "summary": "补报：测试通过证据",
                    "result_ref": "test:python -m unittest tests.server.test_mcp_server",
                })
                self.assertEqual(
                    "pending_test",
                    json.loads(supplemented["content"][0]["text"])["status"],
                )
                self.assertEqual(
                    "test:python -m unittest tests.server.test_mcp_server",
                    runtime.get_task(task_id)["result_ref"],
                )
                # verify 现在可通过
                verified = mcp_server.handle_verify_delegated_task({
                    "task_id": task_id, "verification_summary": "主 IDE 确认补报证据",
                })
                self.assertEqual("done", json.loads(verified["content"][0]["text"])["status"])
                self.assertEqual("done", runtime.get_task(task_id)["status"])


class GetDelegatedTaskFieldsTests(unittest.TestCase):
    """T5-C：get_delegated_task 返回结构化字段，员工不必解析 prompt 文本。"""

    def _delegate_and_get(self, runtime, delegate_args):
        """辅助：派发任务后用 get_delegated_task 读取并返回 payload。"""
        with patch("mcp_server.get_runtime", return_value=runtime):
            delegated = mcp_server.handle_delegate_task(delegate_args)
            task_id = json.loads(delegated["content"][0]["text"])["task_id"]
            result = mcp_server.handle_get_delegated_task({"task_id": task_id})
        return task_id, json.loads(result["content"][0]["text"])

    def test_get_delegated_task_returns_main_owned_paths(self):
        """1. get_delegated_task 返回 main_owned_paths。"""
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            TaskRuntime, "_ensure_timeout_scanner"
        ), patch.object(TaskRuntime, "_try_dispatch_next_queued", return_value=None):
            runtime = TaskRuntime(temp_dir)
            task_id, payload = self._delegate_and_get(runtime, {
                "task": "验证字段", "target_ide": "trae_solo_cn",
                "user_confirmed": True, "dispatch": False,
                "task_type": "code", "owned_paths": ["tests/server"],
                "main_owned_paths": ["server/mcp_server.py", "server/task_runtime.py"],
            })
        self.assertEqual(
            ["server/mcp_server.py", "server/task_runtime.py"],
            payload["main_owned_paths"],
        )

    def test_get_delegated_task_returns_validation(self):
        """2. get_delegated_task 返回 validation。"""
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            TaskRuntime, "_ensure_timeout_scanner"
        ), patch.object(TaskRuntime, "_try_dispatch_next_queued", return_value=None):
            runtime = TaskRuntime(temp_dir)
            task_id, payload = self._delegate_and_get(runtime, {
                "task": "验证字段", "target_ide": "trae_solo_cn",
                "user_confirmed": True, "dispatch": False,
                "task_type": "test", "owned_paths": ["tests/server"],
                "validation_commands": [
                    "python -m unittest tests.server.test_mcp_server",
                    "git diff --check",
                ],
            })
        self.assertEqual(
            [
                "python -m unittest tests.server.test_mcp_server",
                "git diff --check",
            ],
            payload["validation"],
        )

    def test_get_delegated_task_returns_task_type(self):
        """3. get_delegated_task 返回 task_type。"""
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            TaskRuntime, "_ensure_timeout_scanner"
        ), patch.object(TaskRuntime, "_try_dispatch_next_queued", return_value=None):
            runtime = TaskRuntime(temp_dir)
            task_id, payload = self._delegate_and_get(runtime, {
                "task": "验证字段", "target_ide": "trae_solo_cn",
                "user_confirmed": True, "dispatch": False,
                "task_type": "code", "owned_paths": ["tests/server"],
            })
        self.assertEqual("code", payload["task_type"])

    def test_get_delegated_task_returns_defaults_when_metadata_missing(self):
        """4. 老任务数据缺少字段时保持兼容（回退默认值）。"""
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "legacy-1",
            "source": "primary_ide",
            "status": "running",
            "title": "legacy task",
            "text": "old task without structured fields",
            "target_ide": "codex",
            "owned_paths": [],
            "summary": None,
            "result_ref": None,
            "error": None,
            "updated_at": "2026-01-01",
            "metadata": {},  # 老任务 metadata 为空，无 main_owned_paths/validation/task_type
        }
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_get_delegated_task({"task_id": "legacy-1"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual([], payload["main_owned_paths"])
        self.assertEqual([], payload["validation"])
        self.assertEqual("research", payload["task_type"])

    def test_get_delegated_task_returns_empty_validation_when_not_provided(self):
        """5. 新任务未传 validation_commands 时返回空数组（不报错）。"""
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            TaskRuntime, "_ensure_timeout_scanner"
        ), patch.object(TaskRuntime, "_try_dispatch_next_queued", return_value=None):
            runtime = TaskRuntime(temp_dir)
            task_id, payload = self._delegate_and_get(runtime, {
                "task": "无 validation 的任务", "target_ide": "trae_solo_cn",
                "user_confirmed": True, "dispatch": False,
                "task_type": "research", "owned_paths": [],
            })
        self.assertEqual([], payload["validation"])
        self.assertEqual("research", payload["task_type"])
        self.assertEqual([], payload["main_owned_paths"])

    def test_get_delegated_task_metadata_still_returned_for_compat(self):
        """6. metadata 仍整体返回，保持现有消费者兼容（contract 字段可在 metadata 中读取）。"""
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            TaskRuntime, "_ensure_timeout_scanner"
        ), patch.object(TaskRuntime, "_try_dispatch_next_queued", return_value=None):
            runtime = TaskRuntime(temp_dir)
            task_id, payload = self._delegate_and_get(runtime, {
                "task": "验证 metadata 兼容", "target_ide": "trae_solo_cn",
                "user_confirmed": True, "dispatch": False,
                "task_type": "test", "owned_paths": ["tests/server"],
                "main_owned_paths": ["server/mcp_server.py"],
                "validation_commands": ["python -m pytest"],
            })
        metadata = payload["metadata"]
        # 顶层字段与 metadata 内字段一致（无双写不一致）
        self.assertEqual(payload["main_owned_paths"], metadata["main_owned_paths"])
        self.assertEqual(payload["validation"], metadata["validation"])
        self.assertEqual(payload["task_type"], metadata["task_type"])
        # contract 相关字段仍在 metadata（result_ref_required 等）
        self.assertTrue(metadata["result_ref_required"])


if __name__ == "__main__":
    unittest.main()
