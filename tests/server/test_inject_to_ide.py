import ctypes
import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from inject_to_ide import _bring_window_to_foreground


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
