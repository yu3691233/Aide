"""Graceful IDE window close shared by HTTP routes and the elevated helper."""

import ctypes
import os
import sys
from ctypes import wintypes


WM_CLOSE = 0x0010


def close_windows_for_pids(pids):
    wanted = {int(pid) for pid in pids if int(pid) > 0}
    if not wanted or os.name != "nt":
        return 0
    closed = 0
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(hwnd, _lparam):
        nonlocal closed
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) in wanted and user32.IsWindowVisible(hwnd):
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            closed += 1
        return True

    user32.EnumWindows(callback, 0)
    return closed


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "close":
        raise SystemExit(2)
    raise SystemExit(0 if close_windows_for_pids(sys.argv[2:]) else 1)
