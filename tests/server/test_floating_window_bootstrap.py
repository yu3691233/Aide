import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.floating_window_routes import _selected_target, floating_window_bp
from task_runtime import TaskRuntime


class FloatingWindowBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = str(Path(self.tmp.name) / "Project")
        Path(self.project).mkdir()
        self.runtime = TaskRuntime(self.tmp.name)
        self.app = Flask(__name__)
        self.app.register_blueprint(floating_window_bp)

    def tearDown(self):
        self.tmp.cleanup()

    def _create_task(self, status, project=None, target_ide="codex"):
        task = self.runtime.create_task(
            "do work",
            title=f"{status} task",
            source="primary_ide",
            target_ide=None,
        )
        self.runtime.update_task(
            task["task_id"],
            status=status,
            project=project,
            target_ide=target_ide,
            _skip_status_check=True,
        )
        return task["task_id"]

    def test_bootstrap_excludes_legacy_tasks_from_strict_project_home(self):
        self._create_task("pending_test", project=self.project)
        self._create_task("running", project="")
        settings = {
            "current_project": self.project,
            "project_dir": self.project,
            "desktop_ide": "auto",
            "projects": [{"path": self.project, "name": "Project", "last_used": ""}],
        }

        with patch("routes.floating_window_routes.load_settings", return_value=settings), \
             patch("shared_runtime.runtime", self.runtime), \
             patch("ide_scanner.get_all_ides", return_value=[{"key": "codex", "name": "ChatGPT", "path": r"C:\ChatGPT.exe"}]), \
             patch("dispatch_utils.get_ide_running_statuses", return_value={"codex": True}):
            response = self.app.test_client().get("/api/floating-window/bootstrap")

        self.assertEqual(200, response.status_code)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(1, data["task_summary"]["total"])
        self.assertEqual(1, data["task_summary"]["needs_user"])
        self.assertEqual(["view", "confirm_done", "feedback", "mark_failed", "delete"], data["tasks"][0]["allowed_actions"])
        self.assertEqual("legacy_tasks_without_project_excluded", data["warnings"][0]["code"])
        self.assertTrue(data["ides"][0]["dispatchable"])

    @patch("routes.floating_window_routes._foreground_ide_key", return_value="trae")
    def test_selected_target_prefers_foreground_supported_ide(self, _foreground):
        ides = [
            {"key": "codex", "running": True, "dispatchable": True},
            {"key": "trae", "running": True, "dispatchable": True},
        ]
        self.assertEqual("trae", _selected_target({"desktop_ide": "codex"}, ides)["key"])

    @patch("routes.floating_window_routes._foreground_ide_key", return_value=None)
    def test_selected_target_uses_only_running_ide_before_last_choice(self, _foreground):
        ides = [
            {"key": "codex", "running": False, "dispatchable": False},
            {"key": "trae", "running": True, "dispatchable": True},
        ]
        self.assertEqual("trae", _selected_target({"desktop_ide": "codex"}, ides)["key"])


if __name__ == "__main__":
    unittest.main()
