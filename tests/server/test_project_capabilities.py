import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from project_capabilities import clear_project_capability_cache, inspect_project_capabilities


class ProjectCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        clear_project_capability_cache()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_general_project_when_no_markers(self):
        with patch("project_capabilities.inspect_android_project", return_value={"is_android": False}):
            result = inspect_project_capabilities(str(self.root))
        self.assertEqual(["general"], result["capabilities"])
        self.assertFalse(result["web"]["is_web"])

    def test_web_project_from_package_json_and_src(self):
        (self.root / "package.json").write_text("{}", encoding="utf-8")
        (self.root / "src").mkdir()
        with patch("project_capabilities.inspect_android_project", return_value={"is_android": False}):
            result = inspect_project_capabilities(str(self.root))
        self.assertEqual(["web"], result["capabilities"])
        self.assertEqual("web", result["preferred_surface"])
        self.assertTrue(result["web"]["is_web"])

    def test_mixed_web_android_project_keeps_both_capabilities(self):
        (self.root / "web").mkdir()
        (self.root / "web" / "vite.config.ts").write_text("export default {}", encoding="utf-8")
        with patch("project_capabilities.inspect_android_project", return_value={"is_android": True}):
            result = inspect_project_capabilities(str(self.root))
        self.assertEqual(["web", "android"], result["capabilities"])
        self.assertEqual("android", result["preferred_surface"])

    def test_aidelink_style_project_detects_flask_web_and_windows_float(self):
        server = self.root / "server"
        server.mkdir()
        (server / "templates").mkdir()
        (server / "static").mkdir()
        (server / "floating_window_app.py").write_text("", encoding="utf-8")
        with patch("project_capabilities.inspect_android_project", return_value={"is_android": True}):
            result = inspect_project_capabilities(str(self.root))

        self.assertEqual(["web", "android", "windows"], result["capabilities"])
        self.assertTrue(result["web"]["is_web"])
        self.assertTrue(result["windows"]["is_windows"])


if __name__ == "__main__":
    unittest.main()
