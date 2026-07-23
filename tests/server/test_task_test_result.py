import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.task_routes import map_task_for_client
from routes.task_routes_flow import (
    _create_and_dispatch_test_task,
    _deliver_test_result_to_development_ide,
    _record_test_result,
)


class FakeRuntime:
    def __init__(self):
        self.tasks = {
            "task-parent": {
                "task_id": "task-parent",
                "status": "pending_test",
                "text": "修复任务",
                "metadata": {},
            },
            "test-task-parent-1": {
                "task_id": "test-task-parent-1",
                "parent_task_id": "task-parent",
                "status": "running",
                "target_ide": "trae",
                "metadata": {"is_test": True, "source_task_id": "task-parent"},
            },
        }

    def get_task(self, task_id):
        task = self.tasks.get(task_id)
        return dict(task) if task else None

    def update_task(self, task_id, **fields):
        self.tasks[task_id].update(fields)
        return dict(self.tasks[task_id])

    def read_tasks(self):
        return list(self.tasks.values())

    def write_tasks(self, tasks):
        self.tasks = {task["task_id"]: dict(task) for task in tasks}

    def mark_task_running(self, task_id, ide):
        return self.update_task(task_id, status="running", target_ide=ide)

    def set_ide_status(self, *_args, **_kwargs):
        return None


class TaskTestResultTests(unittest.TestCase):
    def test_failed_result_is_written_to_parent_without_completing_it(self):
        runtime = FakeRuntime()

        parent_id, report = _record_test_result(
            runtime,
            "test-task-parent-1",
            "failed",
            "Windows 抬头仍不正确",
            "test:manual dispatch",
        )

        parent = runtime.tasks[parent_id]
        self.assertEqual("pending_test", parent["status"])
        self.assertEqual("failed", parent["metadata"]["test_result"])
        self.assertEqual("Windows 抬头仍不正确", parent["metadata"]["test_summary"])
        self.assertEqual("trae", parent["metadata"]["test_ide"])
        self.assertEqual("failed", report["result"])

    def test_passed_result_is_exposed_to_task_clients(self):
        runtime = FakeRuntime()
        _record_test_result(
            runtime,
            "test-task-parent-1",
            "passed",
            "相关测试全部通过",
            "test:14 passed",
        )

        mapped = map_task_for_client(runtime.tasks["task-parent"])

        self.assertEqual("passed", mapped["test_result"])
        self.assertEqual("相关测试全部通过", mapped["test_summary"])
        self.assertEqual("test:14 passed", mapped["test_evidence"])

    def test_result_is_delivered_to_original_development_ide(self):
        runtime = FakeRuntime()
        runtime.tasks["task-parent"]["target_ide"] = "codex"
        report = {
            "result": "failed",
            "summary": "仍可复现标题错误",
            "evidence": "test:1 failed",
        }

        with patch(
            "routes.task_routes_flow._inject_to_ide", return_value=(True, "ok")
        ) as inject:
            delivered, detail = _deliver_test_result_to_development_ide(
                runtime, "task-parent", report,
            )

        self.assertTrue(delivered)
        self.assertEqual("ok", detail)
        self.assertEqual("codex", inject.call_args.args[0])
        self.assertIn("结论：未通过", inject.call_args.args[1])
        self.assertIn("请据此判断继续修复", inject.call_args.args[1])

    def test_rejects_non_test_task_and_unknown_result(self):
        runtime = FakeRuntime()
        runtime.tasks["test-task-parent-1"]["metadata"]["is_test"] = False
        with self.assertRaisesRegex(ValueError, "不是测试任务"):
            _record_test_result(runtime, "test-task-parent-1", "passed", "ok")

        runtime.tasks["test-task-parent-1"]["metadata"]["is_test"] = True
        with self.assertRaisesRegex(ValueError, "passed 或 failed"):
            _record_test_result(runtime, "test-task-parent-1", "unknown", "ok")

    def test_dedicated_test_dispatch_contains_read_only_instruction(self):
        runtime = FakeRuntime()
        runtime.tasks["task-parent"]["metadata"] = {"surface": "windows"}
        original = {
            "task_id": "task-parent",
            "title": "修复任务",
            "message": "修复测试任务抬头",
            "status": "pending_test",
            "target_ide": "codex",
            "metadata": {},
        }
        injected = {}

        def capture_injection(target, message, task_id):
            injected.update(target=target, message=message, task_id=task_id)
            return True, "ok"

        with patch(
            "routes.task_routes_flow._load_queue",
            return_value=[],
        ), patch(
            "routes.task_routes_flow._save_queue",
        ), patch(
            "routes.task_routes_flow._inject_to_ide",
            side_effect=capture_injection,
        ):
            result, status_code = _create_and_dispatch_test_task(
                runtime,
                "task-parent",
                "trae",
                original,
                "http://127.0.0.1:5000/api/tasks/test-result",
            )

        self.assertEqual(200, status_code)
        self.assertTrue(result["success"])
        self.assertEqual("trae", injected["target"])
        self.assertIn("请验证以上任务是否已正确完成", injected["message"])
        self.assertIn("可以按需要运行测试、创建或调整测试代码", injected["message"])
        self.assertIn("保持生产/业务代码及原功能不变", injected["message"])
        self.assertNotIn("请勿修改代码", injected["message"])
        self.assertIn("### 原始需求\n\n修复测试任务抬头", injected["message"])
        self.assertNotIn("**原始任务**", injected["message"])
        self.assertNotIn("**修改 IDE**", injected["message"])
        self.assertIn("POST http://127.0.0.1:5000/api/tasks/test-result", injected["message"])
        self.assertIn('"result":"passed 或 failed"', injected["message"])
        self.assertTrue(injected["task_id"].startswith("test-task-parent-"))
        self.assertEqual("dispatched", runtime.tasks["task-parent"]["metadata"]["test_result"])
        self.assertEqual("trae", runtime.tasks["task-parent"]["metadata"]["test_ide"])
        self.assertEqual(
            "pending_test",
            runtime.tasks["task-parent"]["status"],
        )
        self.assertEqual("windows", runtime.tasks[result["test_task_id"]]["metadata"]["surface"])

    def test_busy_test_ide_keeps_test_task_queued(self):
        runtime = FakeRuntime()
        runtime.is_ide_available = lambda _ide: False
        original = {
            "task_id": "task-parent",
            "title": "修复任务",
            "message": "修复测试任务抬头",
            "status": "pending_test",
            "target_ide": "codex",
            "metadata": {},
        }

        with patch("routes.task_routes_flow._load_queue", return_value=[]), patch(
            "routes.task_routes_flow._save_queue"
        ) as save_queue, patch("routes.task_routes_flow._inject_to_ide") as inject:
            result, status_code = _create_and_dispatch_test_task(
                runtime, "task-parent", "trae", original,
                "http://127.0.0.1:5000/api/tasks/test-result",
            )

        self.assertEqual(200, status_code)
        self.assertTrue(result["queued"])
        self.assertEqual("queued", runtime.tasks["task-parent"]["metadata"]["test_result"])
        self.assertEqual("queued", runtime.tasks[result["test_task_id"]]["status"])
        inject.assert_not_called()
        self.assertEqual(1, len(save_queue.call_args.args[1]))


if __name__ == "__main__":
    unittest.main()
