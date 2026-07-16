"""Windows integrity-level checks and narrowly scoped elevated process launch."""

from __future__ import annotations

import ctypes
import base64
import os
import subprocess
try:
    import winreg
except ImportError:  # pragma: no cover - Windows-only module
    winreg = None
from ctypes import wintypes


SECURITY_MANDATORY_HIGH_RID = 0x3000
TOKEN_QUERY = 0x0008
TOKEN_INTEGRITY_LEVEL = 25
SEE_MASK_NOCLOSEPROCESS = 0x00000040
INFINITE = 0xFFFFFFFF


class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", wintypes.LPVOID),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]


class TOKEN_MANDATORY_LABEL(ctypes.Structure):
    _fields_ = [("Label", SID_AND_ATTRIBUTES)]


def get_process_integrity_rid(pid: int | None = None) -> int | None:
    """Return a process integrity RID (medium=0x2000, high=0x3000)."""
    if os.name != "nt":
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = (
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
    )
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    advapi32.GetSidSubAuthorityCount.argtypes = (wintypes.LPVOID,)
    advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
    advapi32.GetSidSubAuthority.argtypes = (wintypes.LPVOID, wintypes.DWORD)
    process = kernel32.GetCurrentProcess() if pid is None else kernel32.OpenProcess(0x1000, False, int(pid))
    if not process:
        if pid is not None and ctypes.get_last_error() == 5:
            return SECURITY_MANDATORY_HIGH_RID
        return None
    token = wintypes.HANDLE()
    allocated = None
    try:
        if not advapi32.OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)):
            # A medium process commonly receives ACCESS_DENIED when querying
            # an elevated process token. For a visible IDE window owned by the
            # same interactive user, conservatively route through RunAs.
            if pid is not None and ctypes.get_last_error() == 5:
                return SECURITY_MANDATORY_HIGH_RID
            return None
        needed = wintypes.DWORD()
        advapi32.GetTokenInformation(token, TOKEN_INTEGRITY_LEVEL, None, 0, ctypes.byref(needed))
        if not needed.value:
            return None
        allocated = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(
            token, TOKEN_INTEGRITY_LEVEL, allocated, needed, ctypes.byref(needed)
        ):
            return None
        label = ctypes.cast(allocated, ctypes.POINTER(TOKEN_MANDATORY_LABEL)).contents
        sid = label.Label.Sid
        count = advapi32.GetSidSubAuthorityCount(sid)
        if not count:
            return None
        index = ctypes.cast(count, ctypes.POINTER(ctypes.c_ubyte)).contents.value - 1
        authority = advapi32.GetSidSubAuthority(sid, index)
        return int(authority.contents.value)
    finally:
        if token:
            kernel32.CloseHandle(token)
        if pid is not None and process:
            kernel32.CloseHandle(process)


def process_requires_elevation(pid: int, current_rid: int | None = None) -> bool:
    target_rid = get_process_integrity_rid(pid)
    current_rid = get_process_integrity_rid() if current_rid is None else current_rid
    return bool(target_rid is not None and current_rid is not None and target_rid > current_rid)


def get_window_pid(hwnd: int) -> int:
    if os.name != "nt" or not hwnd:
        return 0
    pid = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
    return int(pid.value)


def ide_window_requires_elevation(ide_key: str) -> bool:
    if os.name != "nt":
        return False
    try:
        import screenshot_engine

        window = screenshot_engine._find_target_window(ide_key)
        pid = get_window_pid(int(getattr(window, "_hWnd", 0) or 0)) if window else 0
        return bool(pid and process_requires_elevation(pid))
    except Exception:
        return False


def executable_requests_admin(executable: str) -> bool:
    """Check Windows compatibility layers for an explicit RUNASADMIN choice."""
    if os.name != "nt" or winreg is None or not executable:
        return False
    normalized = os.path.normcase(os.path.abspath(executable))
    subkey = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, subkey) as key:
                value, _kind = winreg.QueryValueEx(key, normalized)
                if "RUNASADMIN" in str(value).upper().split():
                    return True
        except (FileNotFoundError, OSError):
            continue
    return False


def run_elevated(
    executable: str,
    arguments: list[str],
    cwd: str | None = None,
    timeout_ms: int = 45_000,
    wait: bool = True,
) -> int:
    """Run one fixed executable elevated and return its real exit code."""
    if os.name != "nt":
        return subprocess.run([executable, *arguments], cwd=cwd, check=False).returncode
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32
    def ps_quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    ps_args = ",".join(ps_quote(value) for value in arguments)
    ps_script = (
        f"$a=@({ps_args}); & {ps_quote(os.path.abspath(executable))} @a; "
        "exit $LASTEXITCODE"
    )
    encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe"
    )
    info.lpParameters = subprocess.list2cmdline(["-NoProfile", "-EncodedCommand", encoded])
    info.lpDirectory = os.path.abspath(cwd) if cwd else None
    # GUI automation helpers need an interactive process in the user's desktop.
    # Hiding pythonw/console launch here can leave pyautogui without a usable
    # foreground input context on some Windows builds.
    info.nShow = 1
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        raise OSError(ctypes.get_last_error(), "无法启动管理员权限操作")
    try:
        if not wait:
            return 0
        wait_result = kernel32.WaitForSingleObject(info.hProcess, int(timeout_ms))
        if wait_result == 0x102:
            raise TimeoutError("管理员权限操作超时")
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code)):
            raise OSError(ctypes.get_last_error(), "无法读取管理员权限操作结果")
        return int(exit_code.value)
    finally:
        kernel32.CloseHandle(info.hProcess)
