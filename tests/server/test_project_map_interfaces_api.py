import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.project_routes import project_bp


class ProjectMapInterfacesApiTests(unittest.TestCase):
    def test_web_interfaces_preserve_legacy_pages_and_components(self):
        project_map = {
            "project_root": "F:/demo",
            "categories": [{
                "id": "web_manager_ui",
                "name": "Web",
                "children": [
                    {
                        "id": "dashboard",
                        "name": "📊 仪表盘",
                        "children": [],
                    },
                    {
                        "id": "tasks",
                        "name": "📋 任务管理",
                        "children": [{
                            "id": "task-area",
                            "name": "任务列表",
                            "children": [{
                                "id": "add",
                                "name": "按钮: 添加任务",
                            }],
                        }],
                    },
                ],
            }],
        }
        app = Flask(__name__)
        app.register_blueprint(project_bp)

        with patch("project_scanner.load_cached", return_value=project_map):
            response = app.test_client().get(
                "/api/project-map/interfaces?surface=web"
            )

        payload = response.get_json()
        pages = payload["interfaces"][0]["pages"]
        self.assertEqual(["📊 仪表盘", "📋 任务管理"], [
            page["name"] for page in pages
        ])
        self.assertEqual([], pages[0]["components"])
        self.assertEqual("[按钮] 添加任务", pages[1]["components"][0]["name"])
        self.assertEqual("任务列表", pages[1]["components"][0]["area"])
        self.assertEqual("按钮", payload["interfaces"][0]["component_types"][0]["type"])


if __name__ == "__main__":
    unittest.main()
