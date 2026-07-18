import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.phone_routes import phone_bp


class FloatingWindowSendFlowTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(phone_bp)

    def test_send_route_injects_text_into_explicit_selected_ide(self):
        history = []
        inject = Mock(return_value=(True, "已注入"))
        with patch("routes.phone_routes.read_history", side_effect=lambda: list(history)), \
             patch("routes.phone_routes.write_history", side_effect=lambda value: history.__setitem__(slice(None), value)), \
             patch("routes.phone_routes._get_phone_deps", return_value=(Mock(), Mock(), Mock(), ["trae", "codex"])), \
             patch("routes.phone_routes._get_screen_deps", return_value=(lambda: False, Mock())), \
             patch("routes.phone_routes._get_settings_loader", return_value=lambda: {}), \
             patch("routes.task_routes_injection._inject_to_ide", inject):
            response = self.app.test_client().post(
                "/send",
                json={"text": "浮窗发送验证", "target": "trae"},
            )

        self.assertEqual(200, response.status_code)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual("trae", data["routed_to"])
        inject.assert_called_once_with("trae", "浮窗发送验证", "")


if __name__ == "__main__":
    unittest.main()
