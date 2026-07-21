import os
import sys
import time
import subprocess
import ctypes
import base64

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
    sent_down = user32.SendInput(
        len(inputs_down), (INPUT * len(inputs_down))(*inputs_down), ctypes.sizeof(INPUT)
    )
    time.sleep(down_delay)

    # 2. 依次抬起（逆序）
    inputs_up = [_make_input(vk, KEYEVENTF_KEYUP) for vk in reversed(vk_codes)]
    sent_up = user32.SendInput(
        len(inputs_up), (INPUT * len(inputs_up))(*inputs_up), ctypes.sizeof(INPUT)
    )
    time.sleep(between_delay)
    return sent_down == len(inputs_down) and sent_up == len(inputs_up)


def _paste_and_enter():
    """Ctrl+V 粘贴，sleep，Enter 回车发送。绕过 pyautogui，直接走 SendInput。"""
    VK_CONTROL = 0x11
    VK_V = 0x56
    VK_RETURN = 0x0D
    if not _send_key_combination(VK_CONTROL, VK_V):
        return False
    time.sleep(0.4)
    return _send_key_combination(VK_RETURN)


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


def _bring_window_to_foreground(hwnd, user32=None, kernel32=None):
    """激活窗口，并在结束时恢复 Windows 前台锁超时。"""
    user32 = user32 or ctypes.windll.user32
    kernel32 = kernel32 or ctypes.windll.kernel32
    get_timeout = 0x2000
    set_timeout = 0x2001

    old_timeout = ctypes.c_uint32()
    timeout_changed = False
    if user32.SystemParametersInfoW(get_timeout, 0, ctypes.byref(old_timeout), 0):
        timeout_changed = bool(
            user32.SystemParametersInfoW(set_timeout, 0, ctypes.c_void_p(0), 0)
        )

    foreground_hwnd = user32.GetForegroundWindow()
    foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None)
    current_thread = kernel32.GetCurrentThreadId()
    attached = False
    if foreground_thread and foreground_thread != current_thread:
        attached = bool(user32.AttachThreadInput(foreground_thread, current_thread, True))

    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(foreground_thread, current_thread, False)
        if timeout_changed:
            # SPI_SETFOREGROUNDLOCKTIMEOUT 的 pvParam 是超时数值。
            # 传 byref(old_timeout) 会把指针地址误写成超时。
            user32.SystemParametersInfoW(
                set_timeout, 0, ctypes.c_void_p(old_timeout.value), 0
            )

    return user32.GetForegroundWindow() == hwnd


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

    activated = False
    try:
        # 绕过 Windows 焦点窃取保护：临时将前台锁定超时设为 0，
        # 这样 SetForegroundWindow 能直接成功，不需要 Alt 键模拟。
        # Alt 键会激活 Electron/VSCode 内核 IDE（如 Trae）的菜单栏，
        # 导致后续 Ctrl+V 被菜单拦截。Trae 近期更新后对此更敏感。
        activated = _bring_window_to_foreground(hwnd, user32=user32)
        actual_fore = user32.GetForegroundWindow()
        if not activated:
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
    return activated


def _is_trae_target(target):
    """Return whether an IDE key/name belongs to the Trae family."""
    normalized = "".join(ch for ch in str(target).lower() if ch.isalnum())
    return "trae" in normalized


def _refresh_window_focus(win, user32=None, sleep_fn=time.sleep):
    """最大化并激活窗口，让 IDE 恢复内部输入焦点。"""
    user32 = user32 or ctypes.windll.user32
    hwnd = win._hWnd

    try:
        print(f"[INFO] Refreshing internal focus via maximize: {win.title}")
        user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
        sleep_fn(0.35)
        return activate_window(win)
    except Exception as exc:
        print(f"[WARN] Maximize focus refresh failed: {exc}")
        return False


def focus_calibrated_input(target, win):
    """按 Web 校准的客户区比例点击输入框。

    None 表示未启用；True 表示点击成功；False 表示已启用但无法安全点击。
    """
    try:
        import screenshot_engine as se

        hwnd = win._hWnd
        config = se.get_crop_config(target, se.get_monitor_for_window(hwnd))
        is_trae = _is_trae_target(target)
        click_enabled = bool(config.get("focus_input_enabled"))
        maximize_focus_target = is_trae or target == "antigravity_ide"
        if maximize_focus_target and not click_enabled and _refresh_window_focus(win):
            print(f"[INFO] IDE restored its input focus without a calibrated click: {target}")
            return True
        if not click_enabled and not is_trae:
            return None

        if is_trae and not click_enabled:
            print(f"[WARN] Trae focus refresh failed; falling back to calibrated click: {target}")

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
        focus_config = config
        if is_trae and not click_enabled:
            focus_config = dict(config)
            focus_config["focus_input_enabled"] = True
        if not activate_window(win):
            return False
        time.sleep(0.2)
        # 窗口激活后再读取客户区 rect（窗口状态可能已变）
        if not user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
            print(f"[ERROR] Cannot read client bounds for calibrated focus: {target}")
            return False

        point = se.get_input_focus_client_point(
            focus_config,
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
    if not activate_window(win):
        return False
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
        if not activate_window(win):
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

        # AGY 粘贴实验：最大化恢复输入焦点后，通过剪贴板发送。
        if not robust_copy(text):
            print("Error: Clipboard copy failed completely!")
            return False
        time.sleep(0.3)
        print(f"[INFO] Pasting via SendInput Ctrl+V in AGY window (title='{win.title}')")
        if not _paste_and_enter():
            print("Error: SendInput was rejected; target IDE may be running at a higher privilege level")
            return False

    elif target in ("mimo", "mimocode"):
        # CLI IDE: 通过进程查找终端窗口
        win = find_saved_window(target) or find_terminal_window_for_process("mimo")
        if not win:
            print("Error: Cannot find terminal window running MiMoCode!")
            print("Please make sure MiMoCode is running in a terminal (cmd/powershell).")
            return False
        if not activate_window(win):
            return False

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
        if not activate_window(win):
            return False
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
        if not activate_window(win):
            return False
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

        if not activate_window(win):
            return False
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
            _bring_window_to_foreground(win._hWnd, user32=user32, kernel32=kernel32)
            time.sleep(0.3)

        calibrated = focus_calibrated_input(target, win)
        if calibrated is False:
            return False

        # 通用粘贴路径：直接用 SendInput 发送 Ctrl+V + Enter。
        # SendInput 走内核输入路径，比 pyautogui 更可靠（不受
        # pythonw.exe session / 焦点窃取限制影响）。任何 IDE 通用。
        # 是否点击输入框由校准页面的复选框开关（focus_input_enabled）控制。
        # 注意：Trae 更新后，关闭校准开关时可能无法聚焦输入框（侧边栏
        # 抢占焦点），此时需用户在校准页面打开"派发前点击"开关。
        print(f"[INFO] Pasting via SendInput Ctrl+V in {target.upper()} window (title='{win.title}')")
        if not _paste_and_enter():
            print("Error: SendInput was rejected; target IDE may be running at a higher privilege level")
            return False

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
    elif "--text-base64" in sys.argv:
        value_index = sys.argv.index("--text-base64") + 1
        if value_index >= len(sys.argv):
            print("Error: --text-base64 requires a value")
            sys.exit(1)
        text = base64.b64decode(sys.argv[value_index]).decode("utf-8")
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
