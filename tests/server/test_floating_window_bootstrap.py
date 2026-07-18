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
        self.quota_patcher = patch(
            "codex_quota.get_current_codex_quota",
            return_value={"available": True, "remaining_percent": 72, "period": "weekly"},
        )
        self.quota_patcher.start()
        self.project = str(Path(self.tmp.name) / "Project")
        Path(self.project).mkdir()
        self.runtime = TaskRuntime(self.tmp.name)
        self.app = Flask(__name__)
        self.app.register_blueprint(floating_window_bp)

    def tearDown(self):
        self.quota_patcher.stop()
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

    def test_bootstrap_includes_current_project_inspirations_without_counting_them_as_tasks(self):
        note = self.runtime.create_task(
            "随记正文",
            title="随记正文",
            source="primary_ide",
            target_ide=None,
            metadata={"content_kind": "inspiration"},
        )
        self.runtime.update_task(
            note["task_id"],
            project=self.project,
            _skip_status_check=True,
        )
        settings = {
            "current_project": self.project,
            "project_dir": self.project,
            "projects": [{"path": self.project, "name": "Project"}],
        }

        with patch("routes.floating_window_routes.load_settings", return_value=settings), \
             patch("shared_runtime.runtime", self.runtime), \
             patch("ide_scanner.get_all_ides", return_value=[]), \
             patch("dispatch_utils.get_ide_running_statuses", return_value={}):
            data = self.app.test_client().get("/api/floating-window/bootstrap").get_json()

        self.assertEqual(0, data["task_summary"]["total"])
        self.assertEqual(1, len(data["tasks"]))
        self.assertEqual("inspiration", data["tasks"][0]["metadata"]["content_kind"])

    def test_bootstrap_includes_latest_completed_tasks(self):
        task_id = self._create_task("done", project=self.project)
        settings = {
            "current_project": self.project,
            "project_dir": self.project,
            "projects": [{"path": self.project, "name": "Project"}],
        }

        with patch("routes.floating_window_routes.load_settings", return_value=settings), \
             patch("shared_runtime.runtime", self.runtime), \
             patch("ide_scanner.get_all_ides", return_value=[]), \
             patch("dispatch_utils.get_ide_running_statuses", return_value={}):
            data = self.app.test_client().get("/api/floating-window/bootstrap").get_json()

        self.assertEqual(task_id, data["tasks"][0]["task_id"])
        self.assertEqual("done", data["tasks"][0]["status"])

    def test_bootstrap_returns_more_than_five_completed_for_show_more(self):
        task_ids = [
            self._create_task("done", project=self.project)
            for _ in range(7)
        ]
        settings = {
            "current_project": self.project,
            "project_dir": self.project,
            "projects": [{"path": self.project, "name": "Project"}],
        }

        with patch("routes.floating_window_routes.load_settings", return_value=settings), \
             patch("shared_runtime.runtime", self.runtime), \
             patch("ide_scanner.get_all_ides", return_value=[]), \
             patch("dispatch_utils.get_ide_running_statuses", return_value={}):
            data = self.app.test_client().get("/api/floating-window/bootstrap").get_json()

        returned_ids = {task["task_id"] for task in data["tasks"]}
        self.assertTrue(set(task_ids).issubset(returned_ids))
        self.assertEqual(7, data["task_summary"]["by_status"]["done"])

    def test_bootstrap_does_not_replace_older_pending_tasks_after_five_items(self):
        task_ids = [
            self._create_task("draft", project=self.project, target_ide=None)
            for _ in range(7)
        ]
        settings = {
            "current_project": self.project,
            "project_dir": self.project,
            "projects": [{"path": self.project, "name": "Project"}],
        }

        with patch("routes.floating_window_routes.load_settings", return_value=settings), \
             patch("shared_runtime.runtime", self.runtime), \
             patch("ide_scanner.get_all_ides", return_value=[]), \
             patch("dispatch_utils.get_ide_running_statuses", return_value={}):
            data = self.app.test_client().get("/api/floating-window/bootstrap").get_json()

        returned_ids = {task["task_id"] for task in data["tasks"]}
        self.assertTrue(set(task_ids).issubset(returned_ids))

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
