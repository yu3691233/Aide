import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import ide_scanner
from routes.ide_routes import ide_bp


class IdePrimaryRoleTests(unittest.TestCase):
    def test_setting_primary_replaces_previous_primary_and_preserves_other_roles(self):
        roles = {
            "oc": {"is_primary": True, "accept_test_tasks": True},
            "codex": {"accept_test_tasks": False},
        }

        with patch.object(ide_scanner, "load_ide_roles", return_value=roles), patch.object(
            ide_scanner, "save_ide_roles", return_value=True
        ) as save_roles:
            self.assertTrue(ide_scanner.set_primary_ide("codex", True))

        saved = save_roles.call_args.args[0]
        self.assertNotIn("is_primary", saved["oc"])
        self.assertTrue(saved["oc"]["accept_test_tasks"])
        self.assertTrue(saved["codex"]["is_primary"])

    def test_primary_role_route_rejects_web_target(self):
        app = Flask(__name__)
        app.register_blueprint(ide_bp)
        with patch.object(
            ide_scanner,
            "get_all_ides",
            return_value=[{"key": "oc_web", "type": "web"}],
        ):
            response = app.test_client().post(
                "/api/ide/set-primary-role",
                json={"key": "oc_web", "enabled": True},
            )

        self.assertEqual(404, response.status_code)
        self.assertFalse(response.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
