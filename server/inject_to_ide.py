import os
import sys
import time
import subprocess
import ctypes

# Set DPI Awareness to ensure pygetwindow and pyautogui use the same physical coordinates
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import pyperclip
import pygetwindow as gw
import pyautogui
import psutil


def _send_key_combination(*vk_codes, down_delay=0.02, between_delay=0.02):
    """直接用 ctypes / SendInput 发送键盘组合（不依赖 pyautogui/keyboard 库）。

    与 subprocess 子进程的 pyautogui.hotkey 不同，SendInput 走的是
    Windows 内核输入路径，不受 pythonw.exe session / 焦点窃取限制影响，
    适合在已经 AttachThreadInput 抢占焦点的窗口里发键。
    """
    user32 = ctypes.windll.user32

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("ki", KEYBDINPUT),
            ("padding", ctypes.c_ubyte * 8),
        ]

    def _make_input(vk, flags=0):
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.ki.wVk = vk
        inp.ki.wScan = 0
        inp.ki.dwFlags = flags
        inp.ki.time = 0
        inp.ki.dwExtraInfo = None
        return inp

    # 1. 依次按下所有修饰键 + 主键
    inputs_down = [_make_input(vk) for vk in vk_codes]
    user32.SendInput(len(inputs_down), (INPUT * len(inputs_down))(*inputs_down), ctypes.sizeof(INPUT))
    time.sleep(down_delay)

    # 2. 依次抬起（逆序）
    inputs_up = [_make_input(vk, KEYEVENTF_KEYUP) for vk in reversed(vk_codes)]
    user32.SendInput(len(inputs_up), (INPUT * len(inputs_up))(*inputs_up), ctypes.sizeof(INPUT))
    time.sleep(between_delay)


def _paste_and_enter():
    """Ctrl+V 粘贴，sleep，Enter 回车发送。绕过 pyautogui，直接走 SendInput。"""
    VK_CONTROL = 0x11
    VK_V = 0x56
    VK_RETURN = 0x0D
    _send_key_combination(VK_CONTROL, VK_V)
    time.sleep(0.4)
    _send_key_combination(VK_RETURN)


def robust_copy(text, retries=10, delay=0.2):
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    for i in range(retries):
        try:
            if user32.OpenClipboard(0):
                user32.EmptyClipboard()
                hMem = kernel32.GlobalAlloc(0x0042, (len(text) + 1) * 2)
                if hMem:
                    pMem = kernel32.GlobalLock(hMem)
                    if pMem:
                        ctypes.cdll.msvcrt.wcscpy_s(ctypes.c_wchar_p(pMem), len(text) + 1, text)
                        kernel32.GlobalUnlock(hMem)
                        if user32.SetClipboardData(13, hMem):
                            user32.CloseClipboard()
                            if user32.OpenClipboard(0):
                                hData = user32.GetClipboardData(13)
                                if hData:
                                    pVal = kernel32.GlobalLock(hData)
                                    if pVal:
                                        val = ctypes.c_wchar_p(pVal).value
                                        kernel32.GlobalUnlock(hData)
                                        user32.CloseClipboard()
                                        if val == text:
                                            print(f"[INFO] Win32 API clipboard copy OK on try {i+1}")
                                            return True
                                user32.CloseClipboard()
                            print(f"[WARN] Win32 clipboard verify failed on try {i+1}")
                        else:
                            user32.CloseClipboard()
                    else:
                        kernel32.GlobalFree(hMem)
                        user32.CloseClipboard()
                else:
                    user32.CloseClipboard()
            else:
                print(f"[WARN] OpenClipboard failed on try {i+1}, retrying...")
        except Exception as e:
            print(f"[WARN] Win32 clipboard copy try {i+1} failed: {e}")
            try:
                user32.CloseClipboard()
            except Exception:
                pass
        time.sleep(delay)

    for i in range(3):
        try:
            pyperclip.copy(text)
            if pyperclip.paste() == text:
                print(f"[INFO] pyperclip copy OK on try {i+1}")
                return True
        except Exception as e:
            print(f"[WARN] pyperclip try {i+1} failed: {e}")
            time.sleep(delay)

    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        p = subprocess.Popen(['clip'], stdin=subprocess.PIPE, text=True, encoding='utf-8', close_fds=True, creationflags=flags)
        p.communicate(input=text)
        time.sleep(0.3)
        print("[INFO] clip.exe fallback invoked (unverified)")
        return True
    except Exception as e:
        print(f"[ERROR] clip.exe fallback failed: {e}")

    return False

def activate_window(win):
    user32 = ctypes.windll.user32
    hwnd = win._hWnd

    print(f"[INFO] Activating window hwnd={hwnd}, title={win.title}")

    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)   # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5)   # SW_SHOW
    except Exception as e:
        print("[WARN] ShowWindow failed:", e)

    try:
        # 先尝试 attach thread input：让当前线程和目标窗口线程共享输入状态，
        # 这样 SetForegroundWindow / SetFocus 不会因为焦点窃取保护被拒。
        kernel32 = ctypes.windll.kernel32
        fg_thread = user32.GetWindowThreadProcessId(hwnd, None)
        cur_thread = kernel32.GetCurrentThreadId()
        attached = False
        if fg_thread and fg_thread != cur_thread:
            user32.AttachThreadInput(fg_thread, cur_thread, True)
            attached = True

        try:
            # Alt 键模拟：发送一次 Alt down+up 让当前线程获得 SetForegroundWindow
            # 权限，绕过 Windows 焦点窃取保护（后台进程不能直接抢前台焦点）。
            user32.keybd_event(18, 0, 0, 0)   # VK_MENU down
            time.sleep(0.05)
            user32.keybd_event(18, 0, 2, 0)   # VK_MENU up
            time.sleep(0.05)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(fg_thread, cur_thread, False)

        actual_fore = user32.GetForegroundWindow()
        if actual_fore != hwnd:
            actual_title = ""
            try:
                length = user32.GetWindowTextLengthW(actual_fore) + 1
                buf = ctypes.create_unicode_buffer(length)
                user32.GetWindowTextW(actual_fore, buf, length)
                actual_title = buf.value or ""
            except Exception:
                pass
            print(f"[WARN] Failed to bring window to foreground! Active window is still hwnd={actual_fore}, title={actual_title!r}, expected hwnd={hwnd}/title={win.title!r}")
        else:
            print("[INFO] Successfully brought window to foreground.")
    except Exception as e:
        print("[WARN] Foreground force activation failed:", e)

    time.sleep(0.4)


def focus_calibrated_input(target, win):
    """按 Web 校准的客户区比例点击输入框。

    None 表示未启用；True 表示点击成功；False 表示已启用但无法安全点击。
    """
    try:
        import screenshot_engine as se

        hwnd = win._hWnd
        config = se.get_crop_config(target, se.get_monitor_for_window(hwnd))
        if not config.get("focus_input_enabled"):
            return None

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        user32 = ctypes.windll.user32
        client_rect = RECT()
        origin = POINT(0, 0)
        if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
            print(f"[ERROR] Cannot read client bounds for calibrated focus: {target}")
            return False
        point = se.get_input_focus_client_point(
            config,
            client_rect.right - client_rect.left,
            client_rect.bottom - client_rect.top,
        )
        if point is None:
            print(f"[ERROR] Calibrated input region is missing or invalid for {target}")
            return False
        if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            print(f"[ERROR] Cannot convert calibrated focus point for {target}")
            return False

        click_x = origin.x + point[0]
        click_y = origin.y + point[1]
        activate_window(win)
        time.sleep(0.2)
        print(f"[INFO] Clicking calibrated input for {target.upper()} at ({click_x}, {click_y})")
        pyautogui.click(click_x, click_y)
        time.sleep(0.35)
        return True
    except Exception as exc:
        print(f"[ERROR] Calibrated input focus failed for {target}: {exc}")
        return False

def _normalize_title(value):
    return "".join(ch for ch in value.lower() if ch.isalnum())

def _window_process_name(win):
    user32 = ctypes.windll.user32
    try:
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(win._hWnd, ctypes.byref(pid))
        return psutil.Process(pid.value).name().lower()
    except Exception:
        return ""

def find_window_by_aliases(title_aliases=None, process_names=None):
    """按窗口标题别名或进程名查找可见窗口。"""
    title_aliases = title_aliases or []
    process_names = {name.lower() for name in (process_names or []) if name}
    normalized_aliases = [_normalize_title(alias) for alias in title_aliases if alias]

    for w in gw.getAllWindows():
        if w.width <= 0 or w.height <= 0 or not w.title or not w.title.strip():
            continue
        title_lower = w.title.lower()
        normalized_title = _normalize_title(title_lower)
        if any(alias in title_lower or alias in normalized_title for alias in title_aliases):
            return w
        if process_names and _window_process_name(w) in process_names:
            return w
        if any(alias and alias in normalized_title for alias in normalized_aliases):
            return w
    return None

def find_saved_window(target):
    """Resolve the window selected in Web IDE management before heuristic matching."""
    try:
        from window_binding import find_bound_window, get_binding

        binding = get_binding(target)
        if not binding:
            return None
        win = find_bound_window(target, gw.getAllWindows())
        if win:
            print(
                f"[INFO] Using saved window binding for '{target}': "
                f"hwnd={win._hWnd}, title={win.title!r}"
            )
        else:
            print(f"[WARN] Saved window binding for '{target}' did not match a current window")
        return win
    except Exception as exc:
        print(f"[WARN] Failed to resolve saved window binding for '{target}': {exc}")
        return None

def find_terminal_window_for_process(process_name):
    """找到包含指定进程的终端窗口（WindowsTerminal / cmd / powershell）"""
    user32 = ctypes.windll.user32

    def get_pid(hwnd):
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def get_proc_name(pid):
        try:
            return psutil.Process(pid).name().lower()
        except Exception:
            return ""

    def pid_has_mimo_descendant(pid, depth=0):
        """检查该 PID 的后代进程里是否有指定进程"""
        if depth > 10:
            return False
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=False):
                cname = child.name().lower()
                ccmd = ' '.join(child.cmdline()).lower()
                # 精确匹配：进程名以 process_name 开头，或命令行包含完整进程名
                if cname.startswith(process_name.lower()) or process_name.lower() in ccmd:
                    return True
                if pid_has_mimo_descendant(child.pid, depth + 1):
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return False

    # 终端进程名列表（WindowsTerminal / conhost / pwsh / powershell / cmd）
    terminal_names = ['windowsterminal', 'conhost', 'pwsh', 'powershell', 'cmd']

    # 遍历所有可见窗口，找终端窗口，检查是否有 process_name 后代
    for w in gw.getAllWindows():
        if not w.title or not w.title.strip():
            continue
        try:
            wpid = get_pid(w._hWnd)
            pname = get_proc_name(wpid)
            if any(t in pname for t in terminal_names):
                if pid_has_mimo_descendant(wpid):
                    print(f"[INFO] Found terminal window for '{process_name}': hwnd={w._hWnd}, title='{w.title}', pid={wpid}")
                    return w
        except Exception:
            continue

    # 兜底：按窗口标题匹配（仅当 process_name 匹配时才用标题回退）
    for w in gw.getAllWindows():
        if not w.title or not w.title.strip():
            continue
        title_lower = w.title.lower()
        pn = process_name.lower()
        if pn in title_lower or pn.replace("-", "").replace(" ", "") in title_lower.replace("-", "").replace(" ", ""):
            print(f"[INFO] Fallback: found terminal window by title for '{process_name}': hwnd={w._hWnd}, title='{w.title}'")
            return w
        # 别名匹配：mimo 也匹配 mimocode / mc
        if pn == "mimo" and ("mimocode" in title_lower or "mc " in title_lower):
            print(f"[INFO] Fallback: found terminal window by title for '{process_name}': hwnd={w._hWnd}, title='{w.title}'")
            return w

    return None


def resolve_target_window(target):
    """Resolve an IDE window using the same binding-first rules as message injection."""
    target = (target or "").strip().lower()
    win = find_saved_window(target)
    if win:
        return win
    if target in ("mimo", "mimocode"):
        return find_terminal_window_for_process("mimo")
    if target == "trae":
        return find_window_by_aliases(("trae",), ("trae.exe",))
    if target == "antigravity_ide":
        return find_window_by_aliases(("antigravity",), ("antigravity.exe",))
    if target in ("oc", "opencode"):
        return find_window_by_aliases(("opencode",), ("opencode.exe",)) or find_terminal_window_for_process("opencode")
    if target == "codex":
        return find_window_by_aliases(
            ("codex", "openai codex", "chatgpt", "openai"),
            ("codex.exe", "chatgpt.exe", "chatgptdesktop.exe"),
        ) or find_terminal_window_for_process("codex")

    try:
        import ide_scanner
        ide_info = next((item for item in ide_scanner.get_all_ides() if item.get("key") == target), None) or {}
    except Exception:
        ide_info = {}
    aliases = [target, ide_info.get("name", "")]
    path = ide_info.get("path") or ""
    exe_name = os.path.basename(path).lower() if path else ""
    process_names = [exe_name] if exe_name else []
    return find_window_by_aliases(aliases, process_names) or (
        find_terminal_window_for_process(os.path.splitext(exe_name)[0]) if exe_name else None
    )


def paste_current_clipboard(target):
    """Paste existing clipboard data without sending, honoring binding and focus calibration."""
    win = resolve_target_window(target)
    if not win:
        print(f"[ERROR] Cannot resolve window for clipboard paste target: {target}")
        return False
    activate_window(win)
    focus_result = focus_calibrated_input(target, win)
    if focus_result is False:
        return False
    # None means the user explicitly did not enable pre-dispatch clicking.
    # Preserve the window's last focused control instead of guessing a coordinate.
    VK_CONTROL = 0x11
    VK_V = 0x56
    _send_key_combination(VK_CONTROL, VK_V)
    time.sleep(0.5)
    print(f"[INFO] Pasted current clipboard into {target.upper()} without Enter")
    return True

def inject(target, text, worktree_path=None):
    if target in ("antigravity_ide",):
        # GUI IDE: 优先使用 Web IDE 管理中保存的窗口绑定。
        title_keyword = "Antigravity"
        win = find_saved_window(target)
        wins = [w for w in gw.getAllWindows() if title_keyword.lower() in w.title.lower()] if not win else []
        if not win and not wins:
            print(f"Error: Window containing '{title_keyword}' not found!")
            return False
        win = win or wins[0]
        activate_window(win)

        if not robust_copy(text):
            print("Error: Clipboard copy failed completely!")
            return False

        calibrated_focus = focus_calibrated_input(target, win)
        if calibrated_focus is False:
            return False
        if calibrated_focus is None:
            print(f"[INFO] Focus chat input in {target.upper()} via Ctrl+Alt+I & Ctrl+Alt+Y")
            pyautogui.keyUp('ctrl')
            pyautogui.keyUp('alt')
            pyautogui.keyUp('shift')
            pyautogui.hotkey('ctrl', 'alt', 'i')
            time.sleep(0.2)
            pyautogui.hotkey('ctrl', 'alt', 'y')
            time.sleep(0.5)

            left, top = win.left, win.top
            width, height = win.width, win.height
            bottom = win.bottom
            click_x = left + int(width * 0.78)
            click_y = bottom - 80
            print(f"[INFO] Clicking right-side chat input at: ({click_x}, {click_y})")
            pyautogui.click(click_x, click_y)
            time.sleep(0.4)

        pyautogui.keyUp('ctrl')
        pyautogui.keyUp('alt')
        pyautogui.keyUp('shift')
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.25)
        pyautogui.press('enter')

    elif target in ("trae", "trae_cn"):
        # GUI IDE: 按 GetForegroundWindow() 当前前台窗口优先（Trae 当前激活的可能是
        # Electron 子窗口，pygetwindow.getAllWindows() 不一定包含它）。
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        def _title_of(hwnd):
            try:
                length = user32.GetWindowTextLengthW(hwnd) + 1
                buf = ctypes.create_unicode_buffer(length)
                user32.GetWindowTextW(hwnd, buf, length)
                return buf.value or ""
            except Exception:
                return ""

        fg_hwnd = user32.GetForegroundWindow()
        fg_title = _title_of(fg_hwnd)
        print(f"[INFO] Current foreground hwnd={fg_hwnd}, title={fg_title!r}")

        # 找出真正持有键盘焦点的窗口（可能是 Trae 的某个子窗口/输入控件）
        focused_hwnd = None
        try:
            class GUITHREADINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("flags", ctypes.c_ulong),
                    ("hwndActive", ctypes.c_ulong),
                    ("hwndFocus", ctypes.c_ulong),
                    ("hwndCapture", ctypes.c_ulong),
                    ("hwndMenuOwner", ctypes.c_ulong),
                    ("hwndMoveSize", ctypes.c_ulong),
                    ("hwndCaret", ctypes.c_ulong),
                    ("rcCaret", ctypes.wintypes.RECT),
                ]
            gui = GUITHREADINFO()
            gui.cbSize = ctypes.sizeof(GUITHREADINFO)
            if user32.GetGUIThreadInfo(0, ctypes.byref(gui)):
                focused_hwnd = gui.hwndFocus
                focused_title = _title_of(focused_hwnd)
                print(f"[INFO] Current keyboard focus hwnd={focused_hwnd}, title={focused_title!r}")
        except Exception as e:
            print(f"[WARN] GetGUIThreadInfo failed: {e}")

        win = None
        if "trae" in fg_title.lower() or (focused_hwnd and "trae" in _title_of(focused_hwnd).lower()):
            # 直接复用前台窗口——这就是用户当前活动的 Trae 窗口，焦点已经在输入框了
            win = type("Window", (), {})()  # 占位对象
            win._hWnd = fg_hwnd
            win.title = fg_title
            try:
                rect = ctypes.wintypes.RECT()
                user32.GetWindowRect(fg_hwnd, ctypes.byref(rect))
                win.left = rect.left
                win.top = rect.top
                win.width = rect.right - rect.left
                win.height = rect.bottom - rect.top
            except Exception:
                win.left = win.top = 0
                win.width = win.height = 0
            print(f"[INFO] Reusing current foreground Trae window hwnd={fg_hwnd}")
        else:
            # 前台不是 Trae，回退到 pygetwindow 搜索所有 Trae 标题的窗口
            all_wins = [w for w in gw.getAllWindows() if w.width > 0 and w.height > 0 and "trae" in w.title.lower()]
            if not all_wins:
                print("Error: Window containing 'Trae' not found and current foreground is not Trae!")
                return False
            candidates = sorted(all_wins, key=lambda w: w.width * w.height, reverse=True)
            titles = [f"hwnd={w._hWnd}/{w.width}x{w.height}/title={w.title!r}" for w in candidates]
            print(f"[INFO] Foreground is not Trae, trying candidates: {titles}")

            # 尝试用 LockSetForegroundWindow 解除焦点窃取保护
            LSFW_UNLOCK = 2
            try:
                user32.LockSetForegroundWindow(LSFW_UNLOCK)
            except Exception:
                pass

            for cand in candidates:
                try:
                    if user32.IsIconic(cand._hWnd):
                        print(f"[INFO] Skip iconic hwnd={cand._hWnd}/title={cand.title!r}")
                        continue
                    if not user32.IsWindowVisible(cand._hWnd):
                        print(f"[INFO] Skip invisible hwnd={cand._hWnd}/title={cand.title!r}")
                        continue
                    fg_thread = user32.GetWindowThreadProcessId(cand._hWnd, None)
                    cur_thread = kernel32.GetCurrentThreadId()
                    attached = False
                    if fg_thread and fg_thread != cur_thread:
                        attached = user32.AttachThreadInput(fg_thread, cur_thread, True)
                    try:
                        # Alt 键模拟：绕过焦点窃取保护
                        user32.keybd_event(18, 0, 0, 0)   # VK_MENU down
                        time.sleep(0.05)
                        user32.keybd_event(18, 0, 2, 0)   # VK_MENU up
                        time.sleep(0.05)
                        user32.BringWindowToTop(cand._hWnd)
                        user32.SetForegroundWindow(cand._hWnd)
                        user32.SetActiveWindow(cand._hWnd)
                    finally:
                        if attached:
                            user32.AttachThreadInput(fg_thread, cur_thread, False)
                    time.sleep(0.3)
                    new_fg = user32.GetForegroundWindow()
                    if new_fg == cand._hWnd:
                        win = cand
                        print(f"[INFO] Picked Trae window hwnd={cand._hWnd}/{cand.width}x{cand.height}/title={cand.title!r}")
                        break
                    else:
                        new_fg_title = _title_of(new_fg)
                        print(f"[WARN] Activate failed for hwnd={cand._hWnd}, foreground is still hwnd={new_fg}/title={new_fg_title!r}")
                except Exception as e:
                    print(f"[WARN] Activate attempt failed for hwnd={getattr(cand, '_hWnd', '?')}: {e}")

        if win is None:
            # 所有候选窗口都激活失败。可能是系统 UI（如搜索栏）锁住了前台。
            # 尝试发送 ESC 关闭遮挡 UI，然后重试一次最大的候选窗口。
            best = candidates[0] if candidates else None
            if best:
                print(f"[INFO] All candidates failed; sending ESC to dismiss blocking UI, then retry on hwnd={best._hWnd}")
                VK_ESCAPE = 0x1B
                user32.keybd_event(VK_ESCAPE, 0, 0, 0)
                time.sleep(0.05)
                user32.keybd_event(VK_ESCAPE, 0, 2, 0)
                time.sleep(0.3)
                # 重试激活
                fg_thread = user32.GetWindowThreadProcessId(best._hWnd, None)
                cur_thread = kernel32.GetCurrentThreadId()
                attached = False
                if fg_thread and fg_thread != cur_thread:
                    attached = user32.AttachThreadInput(fg_thread, cur_thread, True)
                try:
                    user32.keybd_event(18, 0, 0, 0)   # VK_MENU down
                    time.sleep(0.05)
                    user32.keybd_event(18, 0, 2, 0)   # VK_MENU up
                    time.sleep(0.05)
                    user32.BringWindowToTop(best._hWnd)
                    user32.SetForegroundWindow(best._hWnd)
                    user32.SetActiveWindow(best._hWnd)
                finally:
                    if attached:
                        user32.AttachThreadInput(fg_thread, cur_thread, False)
                time.sleep(0.3)
                new_fg = user32.GetForegroundWindow()
                if new_fg == best._hWnd:
                    win = best
                    print(f"[INFO] Retry succeeded: picked Trae window hwnd={best._hWnd}")
                else:
                    # 仍然失败——兜底用最大候选窗口继续粘贴，避免完全无法派发
                    print(f"[WARN] Retry still failed (fg={new_fg}/{_title_of(new_fg)!r}), using fallback: proceed with hwnd={best._hWnd} anyway")
                    win = best
            else:
                print("Error: No Trae candidate windows found!")
                return False

        if not robust_copy(text):
            print("Error: Clipboard copy failed completely!")
            return False

        # robust_copy 可能把焦点抢走；重新确认前台窗口
        print("[INFO] Re-checking foreground window after clipboard copy")
        time.sleep(0.3)
        post_fg = user32.GetForegroundWindow()
        post_title = _title_of(post_fg)
        if post_fg != win._hWnd:
            print(f"[WARN] Foreground changed after clipboard: expected hwnd={win._hWnd}/title={win.title!r}, got hwnd={post_fg}/title={post_title!r}")
            # 尝试再次把 Trae 抢回来
            fg_thread = user32.GetWindowThreadProcessId(win._hWnd, None)
            cur_thread = kernel32.GetCurrentThreadId()
            attached = False
            if fg_thread and fg_thread != cur_thread:
                attached = user32.AttachThreadInput(fg_thread, cur_thread, True)
            try:
                user32.BringWindowToTop(win._hWnd)
                user32.SetForegroundWindow(win._hWnd)
            finally:
                if attached:
                    user32.AttachThreadInput(fg_thread, cur_thread, False)
            time.sleep(0.3)
        final_fg = user32.GetForegroundWindow()
        print(f"[INFO] Pre-paste foreground hwnd={final_fg}, title={_title_of(final_fg)!r}")

        if focus_calibrated_input(target, win) is False:
            return False

        # Trae 激活后焦点通常在对话输入框，不点击，直接 Ctrl+V 粘贴
        # 用 SendInput 而不是 pyautogui：pythonw.exe 子进程的 pyautogui 在
        # 一些 Windows session 下不会真正把键发到目标窗口的输入框。
        print(f"[INFO] Pasting via SendInput Ctrl+V in Trae window (title='{win.title}')")
        _paste_and_enter()

    elif target in ("mimo", "mimocode"):
        # CLI IDE: 通过进程查找终端窗口
        win = find_saved_window(target) or find_terminal_window_for_process("mimo")
        if not win:
            print("Error: Cannot find terminal window running MiMoCode!")
            print("Please make sure MiMoCode is running in a terminal (cmd/powershell).")
            return False
        activate_window(win)

        if not robust_copy(text):
            print("Error: Clipboard copy failed completely!")
            return False

        if focus_calibrated_input(target, win) is False:
            return False

        # 先 cd 到 worktree（如果有），然后粘贴执行
        if worktree_path:
            print(f"[INFO] Changing to worktree: {worktree_path}")
            pyautogui.write(f"cd {worktree_path}\n")
            time.sleep(0.5)
        print(f"[INFO] Pasting via Ctrl+V in terminal window (title='{win.title}')")
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.3)
        pyautogui.press('enter')

    elif target == "oc":
        # 桌面端 OpenCode：先按标题找 GUI 窗口，无果再找终端窗口
        win = find_saved_window(target)
        wins = [w for w in gw.getAllWindows() if w.width > 0 and w.height > 0 and "opencode" in w.title.lower()] if not win else []
        win = win or (wins[0] if wins else find_terminal_window_for_process("opencode"))
        if not win:
            print("Error: Cannot find window running OpenCode!")
            print("Please make sure OpenCode is running.")
            return False
        activate_window(win)
        time.sleep(0.5)

        if not robust_copy(text):
            print("Error: Clipboard copy failed completely!")
            return False

        if focus_calibrated_input(target, win) is False:
            return False

        print(f"[INFO] Pasting via Ctrl+V in OpenCode window (title='{win.title}')")
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.5)
        pyautogui.press('enter')

    elif target == "codex":
        # OpenAI Codex IDE：优先使用 Web IDE 管理中保存的窗口绑定。
        win = find_saved_window(target) or find_window_by_aliases(
            title_aliases=(
                "codex",
                "openai codex",
                "openai",
                "chatgpt",
                "chat gpt",
                "chat-gpt",
                "chatgpt - openai",
                "chatgpt desktop",
                "chatgpt app",
            ),
            process_names=(
                "codex.exe",
                "openai codex.exe",
                "chatgpt.exe",
                "chatgptdesktop.exe",
                "openai chatgpt.exe",
            ),
        ) or find_terminal_window_for_process("codex")
        if not win:
            # 兜底再扫一次，尽量匹配包含 OpenAI/ChatGPT 的窗口标题。
            fallback = [
                w for w in gw.getAllWindows()
                if w.width > 0 and w.height > 0 and w.title
                and any(token in w.title.lower() for token in ("codex", "chatgpt", "openai"))
            ]
            if fallback:
                win = sorted(fallback, key=lambda w: w.width * w.height, reverse=True)[0]
            else:
                print("Error: Cannot find window for Codex!")
                print("Please make sure Codex IDE / ChatGPT window is running.")
                return False
        activate_window(win)
        time.sleep(0.5)

        if not robust_copy(text):
            print("Error: Clipboard copy failed completely!")
            return False

        calibrated_focus = focus_calibrated_input(target, win)
        if calibrated_focus is False:
            return False
        # 未启用“派发前点击”时保留窗口原有焦点，不再猜测坐标点击。

        print(f"[INFO] Pasting via Ctrl+V in Codex window (title='{win.title}')")
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.3)
        pyautogui.press('enter')

    else:
        win = find_saved_window(target)
        try:
            import ide_scanner
            ide_info = next((item for item in ide_scanner.get_all_ides() if item.get("key") == target), None)
        except Exception:
            ide_info = None

        if not win and (not ide_info or ide_info.get("type") == "web"):
            print(f"Error: Unknown target '{target}'")
            return False

        ide_info = ide_info or {}
        title_aliases = [target]
        if ide_info.get("name"):
            title_aliases.append(ide_info["name"])
        path = ide_info.get("path") or ""
        exe_name = os.path.basename(path).lower() if path else ""
        process_names = [exe_name] if exe_name else []
        win = win or find_window_by_aliases(title_aliases=title_aliases, process_names=process_names)
        if not win and exe_name:
            win = find_terminal_window_for_process(os.path.splitext(exe_name)[0])
        if not win:
            print(f"Error: Cannot find window for '{target}'")
            print("Please make sure the IDE window is already open.")
            return False

        activate_window(win)
        time.sleep(0.5)

        if not robust_copy(text):
            print("Error: Clipboard copy failed completely!")
            return False

        # robust_copy 可能抢走前台焦点，重新确认并抢回目标窗口
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        time.sleep(0.3)
        post_fg = user32.GetForegroundWindow()
        if post_fg != win._hWnd:
            print(f"[WARN] Foreground changed after clipboard copy, re-activating {target.upper()} window")
            fg_thread = user32.GetWindowThreadProcessId(win._hWnd, None)
            cur_thread = kernel32.GetCurrentThreadId()
            attached = False
            if fg_thread and fg_thread != cur_thread:
                attached = user32.AttachThreadInput(fg_thread, cur_thread, True)
            try:
                user32.BringWindowToTop(win._hWnd)
                user32.SetForegroundWindow(win._hWnd)
            finally:
                if attached:
                    user32.AttachThreadInput(fg_thread, cur_thread, False)
            time.sleep(0.3)

        if focus_calibrated_input(target, win) is False:
            return False

        # 不点击输入框，直接用 SendInput 发送 Ctrl+V + Enter。
        # SendInput 走内核输入路径，比 pyautogui 更可靠（不受
        # pythonw.exe session / 焦点窃取限制影响）。任何 IDE 通用。
        print(f"[INFO] Pasting via SendInput Ctrl+V in {target.upper()} window (title='{win.title}')")
        _paste_and_enter()

    print(f"Successfully injected message into {target.upper()} window!")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inject_to_ide.py <target> [--stdin | <text>] [--worktree <path>]")
        sys.exit(1)

    target = sys.argv[1]

    worktree_path = None
    if "--worktree" in sys.argv:
        idx = sys.argv.index("--worktree")
        if idx + 1 < len(sys.argv):
            worktree_path = sys.argv[idx + 1]

    restore_image = None
    if "--restore-image" in sys.argv:
        idx = sys.argv.index("--restore-image")
        if idx + 1 < len(sys.argv):
            restore_image = sys.argv[idx + 1]

    if "--stdin" in sys.argv:
        # 从 stdin 读取消息（避免命令行参数截断/转义）
        # stdin 默认编码是系统 locale（中文 = GBK），但上游写入的是 UTF-8，必须强制用 utf-8 读
        if hasattr(sys.stdin, 'reconfigure'):
            sys.stdin.reconfigure(encoding='utf-8')
        text = sys.stdin.read()
    elif len(sys.argv) >= 3:
        # 排除掉 --restore-image 及其参数
        args = sys.argv[2:]
        if "--restore-image" in args:
            r_idx = args.index("--restore-image")
            # 移除 --restore-image <val>
            args = args[:r_idx] + args[r_idx+2:]
        if "--worktree" in args:
            w_idx = args.index("--worktree")
            args = args[:w_idx] + args[w_idx+2:]
        text = args[0] if args else ""
    else:
        print("Error: No message provided. Use --stdin or pass text as argument.")
        sys.exit(1)

    if not text.strip():
        print("Error: Empty message")
        sys.exit(1)

    success = inject(target, text, worktree_path)
    
    if success and restore_image:
        def set_image_to_clipboard(image_path):
            import os
            import subprocess
            if os.name != 'nt':
                return False
            try:
                abs_path = os.path.abspath(image_path)
                if not os.path.exists(abs_path):
                    return False
                ps_cmd = f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::SetImage([System.Drawing.Image]::FromFile('{abs_path}'))"
                creationflags = 0x08000000 # CREATE_NO_WINDOW
                subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, creationflags=creationflags)
                print(f"[INFO] Restored image to clipboard: {abs_path}")
                return True
            except Exception as e:
                print(f"[ERROR] Restore image to clipboard failed: {e}")
                return False
        set_image_to_clipboard(restore_image)

    sys.exit(0 if success else 1)
