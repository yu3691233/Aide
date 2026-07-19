import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.task_routes import map_task_for_client
from routes.task_routes_flow import _record_test_result


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

    def test_rejects_non_test_task_and_unknown_result(self):
        runtime = FakeRuntime()
        runtime.tasks["test-task-parent-1"]["metadata"]["is_test"] = False
        with self.assertRaisesRegex(ValueError, "不是测试任务"):
            _record_test_result(runtime, "test-task-parent-1", "passed", "ok")

        runtime.tasks["test-task-parent-1"]["metadata"]["is_test"] = True
        with self.assertRaisesRegex(ValueError, "passed 或 failed"):
            _record_test_result(runtime, "test-task-parent-1", "unknown", "ok")


if __name__ == "__main__":
    unittest.main()
