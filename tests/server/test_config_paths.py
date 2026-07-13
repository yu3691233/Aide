import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from config import SETTINGS_SCHEMA, normalize_project_path, normalize_project_settings, project_path_key


class ProjectPathTests(unittest.TestCase):
    def test_normalizes_slashes_and_whitespace(self):
        self.assertEqual(r"C:\Projects\AideLink", normalize_project_path("  C:/Projects/AideLink  "))

    def test_project_key_ignores_trailing_separator(self):
        self.assertEqual(project_path_key(r"C:\Projects\AideLink"), project_path_key("C:/Projects/AideLink/"))

    def test_project_settings_deduplicates_equivalent_paths(self):
        normalized = normalize_project_settings(
            {
                "current_project": "F:/AideLink/",
                "projects": [
                    {"path": "F:/AideLink", "name": "AideLink"},
                    {"path": "F:\\AideLink\\", "name": "duplicate"},
                    {"path": "", "name": "invalid"},
                ],
            }
        )

        self.assertEqual(r"C:\Projects\AideLink", normalized["current_project"])
        self.assertEqual(1, len(normalized["projects"]))
        self.assertEqual("AideLink", normalized["projects"][0]["name"])

    def test_new_install_does_not_assume_author_android_project(self):
        self.assertEqual("", SETTINGS_SCHEMA["app_project_name"]["default"])
        self.assertEqual("auto", SETTINGS_SCHEMA["desktop_ide"]["default"])


if __name__ == "__main__":
    unittest.main()
