"""
共享调度函数
从 phone_chat_bridge.py 提取的 IDE 检测和任务派发逻辑
"""
import os
import sys
import subprocess
import base64
from datetime import datetime

from paths import BRIDGE_DIR, IN_FILE, UPLOAD_FOLDER
from config import load_settings


def is_port_in_use(port):
    """检查端口是否被占用"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return False
        except socket.error:
            return True


def _process_matches_ide(ide_info, proc_name, proc_exe, cmdline):
    """Return whether one process belongs to a configured desktop IDE."""
    ide_key = (ide_info.get("key") or "").strip().lower()
    ide_name = (ide_info.get("name") or "").strip().lower()
    ide_path = ide_info.get("path") or ""
    exe_filename = os.path.basename(ide_path).lower() if ide_path else ""
    proc_filename = os.path.basename(proc_exe).lower() if proc_exe else ""

    # `opencode serve` is OC Web, not the OpenCode desktop application.
    if ide_key == "oc" and "serve" in cmdline:
        return False

    # A desktop IDE counts as open only when its configured executable owns a
    # visible top-level window.  Exact executable matching prevents helper
    # processes such as `minimax-mcp.exe` from being mistaken for MiniMax Code.
    if exe_filename and proc_filename == exe_filename:
        return _has_visible_window_for_pid(proc_exe)
    if exe_filename:
        return False

    normalized_proc_name = os.path.splitext(proc_name)[0].strip()
    if ide_name and normalized_proc_name == ide_name:
        return _has_visible_window_for_pid(proc_exe)
    return len(ide_key) > 2 and normalized_proc_name == ide_key and _has_visible_window_for_pid(proc_exe)


def _has_visible_window_for_pid(proc_exe):
    """Return whether the process owns a visible top-level window."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        import pygetwindow as gw
        import psutil
        user32 = ctypes.windll.user32
        get_pid = user32.GetWindowThreadProcessId
        for window in gw.getAllWindows():
            hwnd = int(getattr(window, "_hWnd", 0) or 0)
            title = str(getattr(window, "title", "") or "").strip()
            is_visible = getattr(window, "isVisible", None)
            if callable(is_visible):
                is_visible = is_visible()
            else:
                is_visible = getattr(window, "visible", True)
            if not hwnd or not title or not is_visible:
                continue
            owner_pid = ctypes.c_ulong()
            get_pid(hwnd, ctypes.byref(owner_pid))
            if owner_pid.value:
                try:
                    owner_exe = (psutil.Process(owner_pid.value).exe() or "").lower()
                    if owner_exe == proc_exe.lower():
                        return True
                except Exception:
                    continue
    except Exception:
        # If window inspection is unavailable, retain the conservative legacy
        # behavior instead of falsely reporting the IDE as stopped.
        return True
    return False


def get_ide_running_statuses(all_ides=None):
    """Inspect processes once and return a running flag for every configured IDE."""
    import ide_scanner

    ides = all_ides if all_ides is not None else ide_scanner.get_all_ides()
    statuses = {ide_info.get("key", ""): False for ide_info in ides}
    if not ides:
        return statuses

    try:
        import psutil
        for proc in psutil.process_iter(["name", "exe", "cmdline"]):
            try:
                proc_info = proc.info
                proc_name = (proc_info.get("name") or "").lower()
                proc_exe = (proc_info.get("exe") or "").lower()
                cmdline = " ".join(proc_info.get("cmdline") or []).lower()
                for ide_info in ides:
                    ide_key = ide_info.get("key", "")
                    if not statuses.get(ide_key) and _process_matches_ide(
                        ide_info, proc_name, proc_exe, cmdline
                    ):
                        statuses[ide_key] = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except ImportError:
        pass
    return statuses


def is_ide_running(ide):
    """检查指定 IDE 是否在运行（用 ide_key、name、path 做多重匹配）"""
    import ide_scanner

    all_ides = ide_scanner.get_all_ides()
    ide_info = next((item for item in all_ides if item["key"] == ide), None)
    if not ide_info:
        return False
    return get_ide_running_statuses([ide_info]).get(ide, False)


def is_ide_reachable(ide):
    """检测 IDE 是否可达。先用 `is_ide_running` 精确检测，
    如果无法确定则保守返回 True（让 inject_to_ide.py 做实际窗口查找）。"""
    if ide == "oc_web":
        return True
    if is_ide_running(ide):
        return True
    from task_runtime import SUPPORTED_IDES

    # 已知桌面 IDE 默认可达（需配合 inject_to_ide.py 做窗口匹配）
    if ide in SUPPORTED_IDES:
        return True
    return False


def set_image_to_clipboard(image_path):
    """通过 PowerShell 把图片本身写入 Windows 系统剪贴板"""
    if os.name != 'nt':
        return False
    try:
        import base64
        # 绝对路径
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            return False
        ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile(@'
{abs_path}
'@)
$bmp = New-Object System.Drawing.Bitmap $img
$img.Dispose()
[System.Windows.Forms.Clipboard]::SetImage($bmp)
Start-Sleep -Milliseconds 100
$bmp.Dispose()
"""
        encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
        creationflags = 0x08000000  # CREATE_NO_WINDOW
        result = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-EncodedCommand", encoded],
            capture_output=True,
            text=True, encoding='utf-8', errors='replace',
            creationflags=creationflags,
            timeout=10,
        )
        if result.returncode != 0:
            print(f"[ERROR] set_image_to_clipboard PowerShell failed: {result.stderr}", flush=True)
            return False
        return True
    except Exception as e:
        print(f"[ERROR] set_image_to_clipboard failed: {e}", flush=True)
        return False


def inject_text_to_desktop(ide, message, task_id="", restore_image=None):
    """Single desktop injection path shared by App, MCP, and queue dispatch."""
    log_file_path = os.path.join(BRIDGE_DIR, "inject.log")
    injector_path = os.path.join(BRIDGE_DIR, "inject_to_ide.py")
    with open(log_file_path, "a", encoding="utf-8") as log_file:
        log_file.write(
            f"\n--- Spawning inject_to_ide.py for {task_id} at "
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n"
        )
        log_file.flush()
        from windows_privilege import ide_window_requires_elevation, run_elevated

        if ide_window_requires_elevation(ide):
            encoded_text = base64.b64encode(message.encode("utf-8")).decode("ascii")
            args = [injector_path, ide, "--text-base64", encoded_text]
            if restore_image:
                args += ["--restore-image", restore_image]
            log_file.write(f"[INFO] Target {ide} is elevated; routing through RunAs injector.\n")
            log_file.flush()
            try:
                returncode = run_elevated(sys.executable, args, BRIDGE_DIR, timeout_ms=30_000)
            except TimeoutError:
                return False, f"管理员注入超时（30s），请确认 {ide.upper()} 窗口已打开"
            except OSError as exc:
                return False, f"{ide.upper()} 以管理员身份运行，提权请求未完成: {exc}"
            if returncode != 0:
                return False, f"管理员注入失败（exit={returncode}），请检查窗口绑定和权限设置"
            return True, "注入成功"

        cmd = [sys.executable, injector_path, ide, "--stdin"]
        if restore_image:
            cmd += ["--restore-image", restore_image]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=log_file,
            stderr=log_file,
            creationflags=flags,
        )
        try:
            proc.communicate(input=message.encode("utf-8"), timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            return False, f"注入超时（30s），请确认 {ide.upper()} 终端窗口已打开"
        if proc.returncode != 0:
            return False, f"注入失败（exit={proc.returncode}），请检查 inject.log"
        return True, "注入成功"


def dispatch_task(task, runtime):
    """派发任务到指定 IDE
    
    Args:
        task: 任务字典，包含 task_id, target_ide, text 等字段
        runtime: TaskRuntime 实例
    
    Returns:
        (success: bool, message: str)
    """
    from task_runtime import SUPPORTED_IDES
    
    ide = (task or {}).get("target_ide")
    if ide not in SUPPORTED_IDES:
        return False, "不支持的 IDE 目标"

    task_id = task["task_id"]
    task_text = task.get("text", "")

    if not is_ide_reachable(ide):
        return False, f"{ide.upper()} 不可达，请确认 IDE 已启动"

    try:
        # Web OpenCode：本机 Web 端，走 HTTP API
        if ide == "oc_web":
            from opencode_client import send_prompt

            result = send_prompt(task_text, task_id=task_id, directory=task.get("project", ""))
            metadata = dict(task.get("metadata") or {})
            metadata["opencode_session_id"] = result["session_id"]
            runtime.update_task(task_id, metadata=metadata)
            runtime.mark_task_running(task_id, ide)
            runtime.set_ide_status(ide, "busy", current_task_id=task_id)
            return True, f"任务 `{task_id}` 已提交到 OpenCode 会话 {result['session_id']}"

        # 桌面 IDE（trae/antigravity_ide/mimo/mimocode/oc/codex）：剪贴板注入。
        from task_runtime import SUPPORTED_IDES

        if ide in SUPPORTED_IDES:
            with open(IN_FILE, "w", encoding="utf-8") as f:
                f.write(task_text)

            prefixed_msg = (
                "[快捷回复]\n"
                f"{task_text}"
            )

            # 如果有图片，则传递给 inject_to_ide.py 用于在注入后恢复剪贴板
            img_rel = task.get("image")
            img_abs_for_restore = None
            if img_rel:
                if img_rel.startswith("/uploads/"):
                    img_abs_for_restore = os.path.join(UPLOAD_FOLDER, os.path.basename(img_rel))
                else:
                    img_abs_for_restore = os.path.abspath(img_rel) if os.path.isabs(img_rel) else os.path.join(BRIDGE_DIR, img_rel)
                if not os.path.exists(img_abs_for_restore):
                    img_abs_for_restore = None

            injected, detail = inject_text_to_desktop(
                ide, prefixed_msg, task_id=task_id, restore_image=img_abs_for_restore
            )
            if not injected:
                return False, detail

            runtime.mark_task_running(task_id, ide)
            runtime.set_ide_status(ide, "busy", current_task_id=task_id)
            return True, f"任务 `{task_id}` 已派发到 {ide.upper()}，正在唤醒 IDE。"

        # CLI IDE（oc/mimo）：HTTP API
        import requests
        port = 4096 if ide == "oc" else 4097
        resp = requests.post(
            f"http://127.0.0.1:{port}/prompt_async",
            json={"message": task_text, "task_id": task_id},
            timeout=5
        )
        if resp.status_code == 200:
            runtime.mark_task_running(task_id, ide)
            runtime.set_ide_status(ide, "busy", current_task_id=task_id)
            runtime.update_task(task_id, metadata={"remote_response": resp.text})
            return True, f"任务 `{task_id}` 已提交到 {ide.upper()} 后台队列。"

        runtime.update_task(task_id, status="failed", error=resp.text)
        return False, f"任务 `{task_id}` 提交到 {ide.upper()} 失败: {resp.text}"
    except Exception as e:
        runtime.update_task(task_id, status="failed", error=str(e))
        return False, f"任务 `{task_id}` 派发失败: {e}"
