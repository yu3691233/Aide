import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from phone_chat_bridge import app
from routes.task_routes import map_task_for_client
from task_classification import normalize_classification, parse_classification_response
from task_contracts import is_internal_test_task, summarize_tasks_for_project


class FakeRuntime:
    def __init__(self):
        self.tasks = {
            "task-1": {
                "task_id": "task-1",
                "title": "修复任务筛选",
                "text": "筛选结果不正确",
                "status": "draft",
                "metadata": {},
            }
        }

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def update_task(self, task_id, **fields):
        self.tasks[task_id].update(fields)
        return self.tasks[task_id]


class TaskClassificationTests(unittest.TestCase):
    def test_normalize_keeps_multiple_user_choices_and_deduplicates(self):
        result = normalize_classification({
            "surface": "WEB",
            "task_type": "bug_fix",
            "functional_areas": ["订单", "订单", "支付"],
            "ui_location": "任务页右侧",
            "state": "confirmed",
            "source": "user",
        })
        self.assertEqual("web", result["surface"])
        self.assertEqual(["订单", "支付"], result["functional_areas"])
        self.assertEqual("confirmed", result["state"])

    def test_legacy_task_is_visible_as_unclassified(self):
        mapped = map_task_for_client({
            "task_id": "legacy",
            "text": "原始内容",
            "status": "draft",
            "metadata": {"surface": "android"},
        })
        self.assertEqual("unclassified", mapped["classification_state"])
        self.assertEqual("android", mapped["surface"])
        self.assertEqual("原始内容", mapped["text"])

    def test_test_dispatch_records_are_hidden_from_user_task_summary(self):
        parent = {
            "task_id": "task-1",
            "project": "F:/aide",
            "status": "pending_test",
            "metadata": {"test_task_id": "test-task-1"},
        }
        child = {
            "task_id": "test-task-1",
            "parent_task_id": "task-1",
            "project": "F:/aide",
            "status": "pending_test",
            "metadata": {"is_test": True, "source_task_id": "task-1"},
        }
        self.assertTrue(is_internal_test_task(child))
        summary = summarize_tasks_for_project(
            [parent, child],
            project_path="F:/aide",
            strict_project=True,
            limit=10,
        )
        self.assertEqual(["task-1"], [task["task_id"] for task in summary["tasks"]])

    def test_batch_confirmation_updates_metadata_only(self):
        runtime = FakeRuntime()
        module = SimpleNamespace(runtime=runtime)
        with patch.dict(sys.modules, {"shared_runtime": module}):
            response = app.test_client().post("/api/tasks/classification", json={
                "task_ids": ["task-1", "missing"],
                "classification": {
                    "surface": "web",
                    "task_type": "bug_fix",
                    "functional_areas": ["订单", "支付"],
                    "state": "confirmed",
                    "source": "user",
                },
            })

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual(["task-1"], payload["updated_task_ids"])
        self.assertEqual(["missing"], payload["missing_task_ids"])
        self.assertEqual("筛选结果不正确", runtime.tasks["task-1"]["text"])
        stored = runtime.tasks["task-1"]["metadata"]["classification"]
        self.assertEqual("confirmed", stored["state"])
        self.assertEqual(["订单", "支付"], stored["functional_areas"])

    def test_ai_suggestion_is_returned_without_persisting(self):
        runtime = FakeRuntime()
        shared_runtime = SimpleNamespace(runtime=runtime)
        model_registry = SimpleNamespace(
            get_default_model=lambda: "test-model",
            call_model=lambda *_args, **_kwargs: {
                "ok": True,
                "content": (
                    '{"surface":"web","task_type":"bug_fix",'
                    '"functional_areas":["订单","支付"],'
                    '"ui_location":"任务筛选区"}'
                ),
            },
        )
        with patch.dict(sys.modules, {
            "shared_runtime": shared_runtime,
            "model_registry": model_registry,
        }):
            response = app.test_client().post(
                "/api/tasks/classification/suggest",
                json={"task_id": "task-1"},
            )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertFalse(payload["persisted"])
        self.assertEqual("suggested", payload["suggestion"]["state"])
        self.assertEqual(["订单", "支付"], payload["suggestion"]["functional_areas"])
        self.assertEqual({}, runtime.tasks["task-1"]["metadata"])

    def test_ai_suggestion_accepts_fenced_json_with_explanation(self):
        parsed = parse_classification_response(
            '建议如下：\n```json\n{"surface":"web","task_type":"optimization"}\n```'
        )
        self.assertEqual("web", parsed["surface"])
        self.assertEqual("optimization", parsed["task_type"])

    def test_ai_failure_returns_non_persistent_rule_fallback(self):
        runtime = FakeRuntime()
        shared_runtime = SimpleNamespace(runtime=runtime)
        model_registry = SimpleNamespace(
            get_default_model=lambda: "test-model",
            call_model=lambda *_args, **_kwargs: {"ok": False, "error": "offline"},
        )
        with patch.dict(sys.modules, {
            "shared_runtime": shared_runtime,
            "model_registry": model_registry,
        }):
            response = app.test_client().post(
                "/api/tasks/classification/suggest",
                json={"task_id": "task-1"},
            )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertTrue(payload["fallback"])
        self.assertEqual("bug_fix", payload["suggestion"]["task_type"])
        self.assertEqual({}, runtime.tasks["task-1"]["metadata"])

    def test_new_task_text_can_be_classified_before_creation(self):
        model_registry = SimpleNamespace(
            get_default_model=lambda: "test-model",
            call_model=lambda *_args, **_kwargs: {
                "ok": True,
                "content": '{"surface":"android","task_type":"feature","functional_areas":[]}',
            },
        )
        with patch.dict(sys.modules, {"model_registry": model_registry}):
            response = app.test_client().post(
                "/api/tasks/classification/suggest",
                json={"text": "Android 添加快捷入口"},
            )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertIsNone(payload["task_id"])
        self.assertEqual("android", payload["suggestion"]["surface"])


if __name__ == "__main__":
    unittest.main()
