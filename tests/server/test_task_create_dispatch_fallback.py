import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.task_routes import task_bp


class FakeRuntime:
    def __init__(self):
        self.tasks = []

    def create_task(self, **kwargs):
        task = {"task_id": "task-test", **kwargs}
        self.tasks.append(task)
        return task

    def read_tasks(self):
        return list(self.tasks)

    def write_tasks(self, tasks):
        self.tasks = list(tasks)


class TaskCreateDispatchFallbackTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(task_bp)
        self.client = self.app.test_client()
        self.runtime = FakeRuntime()

    @patch("dispatch_utils.dispatch_task", return_value=(False, "IDE unavailable"))
    def test_failed_auto_dispatch_removes_server_task(self, _dispatch):
        with patch("shared_runtime.runtime", self.runtime):
            response = self.client.post(
                "/api/tasks/create",
                json={
                    "text": "offline fallback",
                    "title": "offline fallback",
                    "target_ide": "codex",
                    "auto_dispatch": True,
                },
            )

        self.assertEqual(503, response.status_code)
        self.assertFalse(response.get_json()["ok"])
        self.assertEqual([], self.runtime.tasks)

    @patch("dispatch_utils.dispatch_task", return_value=(True, "ok"))
    def test_successful_auto_dispatch_keeps_server_task(self, _dispatch):
        with patch("shared_runtime.runtime", self.runtime):
            response = self.client.post(
                "/api/tasks/create",
                json={
                    "text": "dispatch me",
                    "title": "dispatch me",
                    "target_ide": "codex",
                    "auto_dispatch": True,
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual(["task-test"], [task["task_id"] for task in self.runtime.tasks])

    def test_inspiration_is_unassigned_and_created_by_primary_ide(self):
        with patch("shared_runtime.runtime", self.runtime):
            response = self.client.post(
                "/api/tasks/inspiration",
                json={"text": "later improvement", "title": "idea", "priority": "high"},
            )

        self.assertEqual(200, response.status_code)
        task = response.get_json()["task"]
        self.assertIsNone(task["target_ide"])
        self.assertEqual("primary_ide", task["source"])
        self.assertEqual("inspiration", task["metadata"]["content_kind"])

    def test_multiplatform_surface_is_persisted_in_task_metadata(self):
        with patch("shared_runtime.runtime", self.runtime):
            response = self.client.post(
                "/api/tasks/create",
                json={
                    "text": "fix desktop float",
                    "target_ide": "auto",
                    "auto_dispatch": False,
                    "surface": "windows",
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("windows", self.runtime.tasks[0]["metadata"]["surface"])
        self.assertEqual("windows", response.get_json()["surface"])

    def test_floating_window_source_is_persisted(self):
        with patch("shared_runtime.runtime", self.runtime):
            response = self.client.post(
                "/api/tasks/create",
                json={
                    "text": "created from desktop cockpit",
                    "target_ide": "auto",
                    "auto_dispatch": False,
                    "source": "floating_window",
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("floating_window", self.runtime.tasks[0]["source"])
        self.assertEqual(
            "floating_window",
            self.runtime.tasks[0]["metadata"]["created_from"],
        )

    def test_unknown_task_source_falls_back_to_app(self):
        with patch("shared_runtime.runtime", self.runtime):
            response = self.client.post(
                "/api/tasks/create",
                json={
                    "text": "unknown client",
                    "target_ide": "auto",
                    "auto_dispatch": False,
                    "source": "spoofed-client",
                },
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("app", self.runtime.tasks[0]["source"])

    def test_non_dispatch_create_stays_unassigned_for_pending_list(self):
        with patch("shared_runtime.runtime", self.runtime):
            response = self.client.post(
                "/api/tasks/create",
                json={
                    "text": "create without dispatch",
                    "target_ide": "codex",
                    "auto_dispatch": False,
                },
            )

        self.assertEqual(200, response.status_code)
        task = self.runtime.tasks[0]
        self.assertIsNone(task["target_ide"])
        self.assertEqual("codex", task["metadata"]["preferred_target_ide"])


if __name__ == "__main__":
    unittest.main()
