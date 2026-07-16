import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import windows_privilege


class WindowsPrivilegeTests(unittest.TestCase):
    @patch("windows_privilege.get_process_integrity_rid")
    def test_process_requires_elevation_only_for_higher_target(self, integrity):
        integrity.return_value = 0x3000
        self.assertTrue(windows_privilege.process_requires_elevation(42, current_rid=0x2000))
        self.assertFalse(windows_privilege.process_requires_elevation(42, current_rid=0x3000))

    @patch("windows_privilege.process_requires_elevation", return_value=True)
    @patch("windows_privilege.get_window_pid", return_value=42)
    def test_ide_window_uses_resolved_window_owner(self, get_pid, requires):
        class Window:
            _hWnd = 123

        with patch.dict(sys.modules, {"screenshot_engine": unittest.mock.Mock(
            _find_target_window=unittest.mock.Mock(return_value=Window())
        )}):
            self.assertTrue(windows_privilege.ide_window_requires_elevation("antigravity_ide"))
        get_pid.assert_called_once_with(123)
        requires.assert_called_once_with(42)


if __name__ == "__main__":
    unittest.main()
