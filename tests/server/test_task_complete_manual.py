import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.task_routes_flow import api_tasks_complete


class ManualTaskCompleteTests(unittest.TestCase):
    def test_manual_complete_confirms_even_when_pending_transition_is_invalid(self):
        app = Flask(__name__)
        runtime = Mock()
        runtime.mark_task_done.side_effect = ValueError("draft cannot transition to pending_test")

        with app.test_request_context(
            "/api/tasks/complete",
            method="POST",
            json={"task_id": "task-1", "manual": True},
        ), patch("routes.task_routes_flow._read_task_data", return_value={"task_id": "task-1"}), \
             patch("task_runtime.TaskRuntime", return_value=runtime):
            response = api_tasks_complete()

        self.assertTrue(response.get_json()["success"])
        runtime.confirm_task_done.assert_called_once_with("task-1", is_manual=True)


if __name__ == "__main__":
    unittest.main()
