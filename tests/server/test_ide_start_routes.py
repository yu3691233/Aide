import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.ide_routes import ide_bp


class IdeStartRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(ide_bp)
        self.client = self.app.test_client()
        self.codex = {
            "key": "codex",
            "name": "ChatGPT",
            "path": r"C:\Apps\ChatGPT.exe",
            "type": "desktop",
        }

    def test_running_chatgpt_is_activated_without_launch_or_project_switch(self):
        with patch("ide_scanner.get_all_ides", return_value=[self.codex]), patch(
            "ide_scanner.load_registry", return_value={}
        ), patch("routes.ide_routes._is_ide_running_local", return_value=True), patch(
            "screenshot_engine._activate_target_window"
        ) as activate, patch("ide_profiles.launch_ide") as launch:
            response = self.client.post("/ide/codex/start")

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["ok"])
        activate.assert_called_once_with("codex", focus_input=False)
        launch.assert_not_called()

    def test_stopped_chatgpt_uses_profile_launcher_without_stopping_first(self):
        with patch("ide_scanner.get_all_ides", return_value=[self.codex]), patch(
            "ide_scanner.load_registry", return_value={}
        ), patch(
            "routes.ide_routes._is_ide_running_local", side_effect=[False, True]
        ), patch("routes.ide_routes.time.sleep"), patch(
            "ide_profiles.launch_ide", return_value=r"shell:AppsFolder\OpenAI.Codex_test!App"
        ) as launch, patch("ide_scanner.scan_installed_ides", return_value=[self.codex]):
            response = self.client.post("/ide/codex/start")

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["ok"])
        launch.assert_called_once()

    def test_profile_aumid_allows_start_when_scan_cache_has_no_codex(self):
        with patch("ide_scanner.get_all_ides", return_value=[]), patch(
            "ide_scanner.scan_installed_ides", side_effect=[[], [self.codex]]
        ), patch("ide_scanner.load_registry", return_value={}), patch(
            "routes.ide_routes._is_ide_running_local", side_effect=[False, True]
        ) as running, patch("routes.ide_routes.time.sleep"), patch(
            "ide_profiles.launch_ide", return_value="shell:AppsFolder\\test"
        ) as launch:
            response = self.client.post("/ide/codex/start")

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["ok"])
        self.assertEqual("codex", running.call_args_list[0].args[0])
        self.assertEqual("", launch.call_args.args[1]["path"])

    def test_open_project_is_separate_and_only_accepts_configured_project(self):
        with tempfile.TemporaryDirectory(prefix="AideLink project ") as project_dir, patch(
            "ide_scanner.get_all_ides", return_value=[self.codex]
        ), patch("config.load_settings", return_value={
            "projects": [{"path": project_dir}],
            "current_project": project_dir,
        }), patch("ide_profiles.open_project", return_value="codex://threads/new") as open_project, patch(
            "ide_project_bindings.save_binding", return_value=True
        ):
            response = self.client.post("/ide/codex/open-project", json={"path": project_dir})

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["ok"])
        open_project.assert_called_once()
        self.assertEqual(project_dir, open_project.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
