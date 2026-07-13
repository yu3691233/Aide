from pathlib import Path
import sys
import tempfile
import unittest

SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))
from android_project import inspect_android_project, resolve_project_apk


def _write(path: Path, content: str = ""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class AndroidProjectTests(unittest.TestCase):
    def test_detects_nested_android_project_and_debug_apk(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            android = tmp_path / "mobile"
            _write(android / "settings.gradle.kts", 'include(":app")')
            _write(android / "gradlew.bat")
            _write(android / "app" / "build.gradle.kts", 'plugins { id("com.android.application") }\napplicationId = "com.example.demo"')
            apk = android / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
            _write(apk, "apk")

            result = inspect_android_project(str(tmp_path))

            self.assertTrue(result["is_android"])
            self.assertEqual(["mobile"], result["android_roots"])
            self.assertEqual("com.example.demo", result["modules"][0]["application_id"])
            self.assertEqual("debug", result["apks"][0]["variant"])
            self.assertTrue(result["primary_apk"].endswith("app-debug.apk"))

    def test_resolve_project_apk_rejects_file_outside_discovered_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            _write(tmp_path / "settings.gradle", 'include ":app"')
            _write(tmp_path / "gradlew")
            _write(tmp_path / "app" / "build.gradle", "plugins { id 'com.android.application' }")
            discovered = tmp_path / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
            outside = tmp_path / "outside.apk"
            _write(discovered, "apk")
            _write(outside, "apk")

            selected, _ = resolve_project_apk(str(tmp_path), str(outside))

            self.assertEqual("", selected)


if __name__ == "__main__":
    unittest.main()
