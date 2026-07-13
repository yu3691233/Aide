import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from git_task_worktree import detect_test_command


class TestCommandTests(unittest.TestCase):
    def test_python_tests_are_returned_as_argument_list(self):
        command = detect_test_command({"owned_paths": ["tests/test_task.py"]})
        self.assertEqual(["-m", "pytest", "tests/test_task.py", "-x", "-q", "--tb=short"], command["argv"][1:])
        self.assertIsNone(command["cwd"])

    def test_gradle_tests_use_working_directory_instead_of_shell_cd(self):
        with patch("config.load_settings", return_value={"app_project_name": "AideLink-app"}):
            command = detect_test_command({"owned_paths": ["app/src/Main.kt"]})
        self.assertEqual([".\\gradlew.bat", "test", "--no-daemon", "-q"], command["argv"])
        self.assertEqual("AideLink-app", command["cwd"])


if __name__ == "__main__":
    unittest.main()
