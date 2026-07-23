import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import project_scanner


class ProjectScannerInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.cache_dir = self.root / "cache"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generic_html_pages_are_exposed_as_real_interfaces(self):
        page = self.root / "tools" / "prompt-generator.html"
        page.parent.mkdir()
        page.write_text(
            """<!doctype html><html><head><title>提示词生成器</title></head>
            <body><h1>智能提示词</h1><input placeholder="描述需求">
            <button>生成提示词</button><a href="history.html">历史记录</a></body></html>""",
            encoding="utf-8",
        )

        pages = project_scanner._scan_generic_web_interfaces(str(self.root))

        self.assertEqual(1, len(pages))
        self.assertIn("提示词生成器", pages[0]["name"])
        names = [node["name"] for node in pages[0]["children"]]
        self.assertIn("[按钮] 生成提示词", names)
        self.assertIn("[输入] 描述需求", names)
        self.assertIn("[链接] 历史记录", names)

    def test_cache_is_isolated_and_validated_by_current_project(self):
        first = self.root / "first"
        second = self.root / "second"
        first.mkdir()
        second.mkdir()
        with patch.object(project_scanner, "PROJECT_MAP_CACHE_DIR", str(self.cache_dir)):
            with patch.object(project_scanner, "get_project_root", return_value=first):
                project_scanner.save_map({"project_root": str(first), "categories": []})
                self.assertIsNotNone(project_scanner.load_cached())
            with patch.object(project_scanner, "get_project_root", return_value=second):
                self.assertIsNone(project_scanner.load_cached())

    def test_generic_compose_screen_discovery_does_not_require_aidelink_package(self):
        screen = self.root / "mobile" / "src" / "main" / "kotlin" / "demo" / "ui" / "HomeScreen.kt"
        screen.parent.mkdir(parents=True)
        screen.write_text(
            """package demo.ui
            @Composable
            fun HomeScreen() {
                Column {
                    Text("首页")
                    Button(onClick = {}) { Text("开始") }
                }
            }""",
            encoding="utf-8",
        )

        groups = project_scanner._scan_kotlin_screens_generic(str(self.root))

        self.assertEqual(1, len(groups))
        self.assertTrue(groups[0]["children"])
        self.assertEqual("HomeScreen", groups[0]["children"][0]["composable"])


if __name__ == "__main__":
    unittest.main()
