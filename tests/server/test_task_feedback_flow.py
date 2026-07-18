import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.task_routes import task_bp
from routes import task_routes_flow  # noqa: F401
from task_runtime import TaskRuntime


class TaskFeedbackFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = TaskRuntime(self.tmp.name)
        task = self.runtime.create_task(
            "original task",
            title="feedback task",
            source="primary_ide",
            target_ide=None,
        )
        self.task_id = task["task_id"]
        self.runtime.update_task(
            self.task_id,
            target_ide="codex",
            status="pending_test",
            result_ref="inline:done",
            _skip_status_check=True,
        )
        self.app = Flask(__name__)
        self.app.register_blueprint(task_bp)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pending_test_feedback_moves_to_running_after_successful_injection(self):
        with patch("task_runtime.TaskRuntime", return_value=self.runtime), \
             patch("routes.task_routes_flow._inject_to_ide", return_value=(True, "ok")), \
             patch("routes.task_routes_flow.read_history", return_value=[]), \
             patch("routes.task_routes_flow.write_history"):
            response = self.app.test_client().post(
                "/api/tasks/feedback",
                json={"task_id": self.task_id, "feedback": "fix the edge case"},
            )

        self.assertEqual(200, response.status_code)
        data = response.get_json()
        self.assertTrue(data["success"])
        task = self.runtime.get_task(self.task_id)
        self.assertEqual("running", task["status"])
        self.assertEqual("codex", task["target_ide"])
        self.assertEqual("fix the edge case", task["metadata"]["feedbacks"][0]["text"])

    def test_pending_test_feedback_stays_test_failed_when_injection_fails(self):
        with patch("task_runtime.TaskRuntime", return_value=self.runtime), \
             patch("routes.task_routes_flow._inject_to_ide", return_value=(False, "window missing")), \
             patch("routes.task_routes_flow.read_history", return_value=[]), \
             patch("routes.task_routes_flow.write_history"):
            response = self.app.test_client().post(
                "/api/tasks/feedback",
                json={"task_id": self.task_id, "feedback": "still broken"},
            )

        self.assertEqual(200, response.status_code)
        data = response.get_json()
        self.assertTrue(data["success"])
        task = self.runtime.get_task(self.task_id)
        self.assertEqual("test_failed", task["status"])
        self.assertIn("用户反馈待修复", task["error"])


if __name__ == "__main__":
    unittest.main()
