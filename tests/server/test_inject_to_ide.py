import ctypes
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from inject_to_ide import (
    _bring_window_to_foreground,
    _is_trae_target,
    _refresh_window_focus,
    focus_calibrated_input,
)


class _Kernel32:
    def GetCurrentThreadId(self):
        return 11


class _User32:
    def __init__(self, timeout=200_000, raise_on_bring=False):
        self.timeout = timeout
        self.raise_on_bring = raise_on_bring
        self.set_timeouts = []
        self.foreground = 0
        self.attach_calls = []

    def SystemParametersInfoW(self, action, _ui_param, value, _flags):
        if action == 0x2000:
            ctypes.cast(value, ctypes.POINTER(ctypes.c_uint32)).contents.value = self.timeout
            return 1
        raw = getattr(value, "value", value)
        self.timeout = int(raw or 0)
        self.set_timeouts.append(self.timeout)
        return 1

    def GetWindowThreadProcessId(self, _hwnd, _process_id):
        return 22

    def AttachThreadInput(self, target, current, attach):
        self.attach_calls.append((target, current, bool(attach)))
        return 1

    def BringWindowToTop(self, _hwnd):
        if self.raise_on_bring:
            raise RuntimeError("activation failed")
        return 1

    def SetForegroundWindow(self, hwnd):
        self.foreground = hwnd
        return 1

    def SetActiveWindow(self, _hwnd):
        return 1

    def GetForegroundWindow(self):
        return self.foreground


class ForegroundActivationTests(unittest.TestCase):
    def test_restores_timeout_value_and_detaches_threads(self):
        user32 = _User32()

        self.assertTrue(_bring_window_to_foreground(123, user32, _Kernel32()))
        self.assertEqual(user32.set_timeouts, [0, 200_000])
        self.assertEqual(user32.timeout, 200_000)
        self.assertEqual(user32.attach_calls, [(22, 11, True), (22, 11, False)])

    def test_restores_timeout_even_when_activation_raises(self):
        user32 = _User32(raise_on_bring=True)

        with self.assertRaisesRegex(RuntimeError, "activation failed"):
            _bring_window_to_foreground(123, user32, _Kernel32())

        self.assertEqual(user32.set_timeouts, [0, 200_000])
        self.assertEqual(user32.timeout, 200_000)
        self.assertEqual(user32.attach_calls[-1], (22, 11, False))


class TraeFocusPolicyTests(unittest.TestCase):
    def test_recognizes_current_and_legacy_trae_keys(self):
        for target in ("trae", "trae_cn", "trae_solo_cn", "TRAE SOLO CN"):
            with self.subTest(target=target):
                self.assertTrue(_is_trae_target(target))

    def test_does_not_force_focus_for_other_ides(self):
        for target in ("chatgpt", "antigravity_ide", "opencode"):
            with self.subTest(target=target):
                self.assertFalse(_is_trae_target(target))

    @patch("inject_to_ide._refresh_window_focus", return_value=True)
    @patch("inject_to_ide.pyautogui.click")
    @patch("inject_to_ide.activate_window", return_value=True)
    @patch("inject_to_ide.time.sleep")
    def test_trae_prefers_window_focus_refresh_without_click(
        self, _sleep, _activate, click, refresh
    ):
        screenshot_engine = MagicMock()
        screenshot_engine.get_monitor_for_window.return_value = "primary"
        screenshot_engine.get_crop_config.return_value = {"focus_input_enabled": False}
        win = MagicMock()
        win._hWnd = 123

        with patch.dict(sys.modules, {"screenshot_engine": screenshot_engine}):
            self.assertTrue(focus_calibrated_input("trae_solo_cn", win))

        refresh.assert_called_once_with(win)
        click.assert_not_called()

    @patch("inject_to_ide._refresh_window_focus", return_value=False)
    @patch("inject_to_ide.pyautogui.click")
    @patch("inject_to_ide.activate_window", return_value=True)
    @patch("inject_to_ide.time.sleep")
    def test_trae_uses_saved_region_when_focus_refresh_fails(
        self, _sleep, _activate, click, _refresh
    ):
        config = {
            "focus_input_enabled": False,
            "input_region": {"x": 0.5, "y": 0.8, "width": 0.02, "height": 0.02},
        }
        screenshot_engine = MagicMock()
        screenshot_engine.get_monitor_for_window.return_value = "primary"
        screenshot_engine.get_crop_config.return_value = config
        screenshot_engine.get_input_focus_client_point.return_value = (510, 648)
        win = MagicMock()
        win._hWnd = 123

        with patch.dict(sys.modules, {"screenshot_engine": screenshot_engine}), patch(
            "inject_to_ide.ctypes.windll.user32"
        ) as user32:
            user32.GetClientRect.return_value = 1
            user32.ClientToScreen.return_value = 1
            self.assertTrue(focus_calibrated_input("trae_solo_cn", win))

        effective_config = screenshot_engine.get_input_focus_client_point.call_args.args[0]
        self.assertTrue(effective_config["focus_input_enabled"])
        self.assertFalse(config["focus_input_enabled"])
        click.assert_called_once_with(510, 648)


class WindowFocusRefreshTests(unittest.TestCase):
    @patch("inject_to_ide.activate_window", return_value=True)
    def test_restores_maximized_state_after_minimizing(self, activate):
        user32 = MagicMock()
        user32.IsZoomed.return_value = 1
        win = MagicMock()
        win._hWnd = 123
        win.title = "TRAE Work CN"
        sleeps = []

        self.assertTrue(_refresh_window_focus(win, user32, sleeps.append))

        self.assertEqual(user32.ShowWindow.call_args_list[0].args, (123, 6))
        self.assertEqual(user32.ShowWindow.call_args_list[1].args, (123, 3))
        self.assertEqual(sleeps, [0.25, 0.35])
        activate.assert_called_once_with(win)

    @patch("inject_to_ide.activate_window", return_value=True)
    def test_restores_normal_state_after_minimizing(self, _activate):
        user32 = MagicMock()
        user32.IsZoomed.return_value = 0
        win = MagicMock()
        win._hWnd = 456
        win.title = "IDE"

        self.assertTrue(_refresh_window_focus(win, user32, lambda _seconds: None))
        self.assertEqual(user32.ShowWindow.call_args_list[1].args, (456, 9))
