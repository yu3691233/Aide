import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.ide_routes import ide_bp


class WindowBindingRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(ide_bp)
        self.client = self.app.test_client()

    @patch("window_binding.list_window_candidates")
    @patch("window_binding.get_binding")
    def test_candidates_contract(self, get_binding, list_candidates):
        get_binding.return_value = {"exe_name": "chatgpt.exe"}
        list_candidates.return_value = [{"hwnd": 42, "title": "ChatGPT"}]
        response = self.client.get("/api/ide-window-bindings/candidates?key=codex")
        self.assertEqual(200, response.status_code)
        self.assertEqual("codex", response.get_json()["key"])
        self.assertEqual(42, response.get_json()["windows"][0]["hwnd"])

    @patch("window_binding.bind_window_by_hwnd")
    def test_save_binding_contract(self, bind_window):
        bind_window.return_value = {"hwnd": 42, "title": "ChatGPT"}
        response = self.client.post("/api/ide-window-bindings", json={"key": "codex", "hwnd": 42})
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["success"])
        bind_window.assert_called_once_with("codex", 42)

    def test_save_binding_rejects_invalid_window(self):
        response = self.client.post("/api/ide-window-bindings", json={"key": "codex", "hwnd": "invalid"})
        self.assertEqual(400, response.status_code)
        self.assertFalse(response.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
