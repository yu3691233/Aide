import os
import os
import sys
import json
import time
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from json_utils import safe_read_json, safe_write_json
from defaults import DEFAULT_FLASK_SERVICE_HOST, DEFAULT_FLASK_SERVICE_PORT
from paths import BRIDGE_DIR as BASE_DIR, CONFIG_FILE, HISTORY_FILE as CHAT_HISTORY_FILE, LOG_FILE

logger = logging.getLogger('manager')

_tray_mutex_handle = None


def _is_aidelink_process(proc, cmd_str, base_dir):
    """Return whether a process belongs to this AideLink installation."""
    base = str(base_dir).lower()
    try:
        exe = (proc.exe() or "").lower()
    except Exception:
        exe = ""
    try:
        cwd = (proc.cwd() or "").lower()
    except Exception:
        cwd = ""
    return base in (cmd_str or "").lower() or base in exe or base == cwd


def acquire_tray_single_instance():
    """Acquire the Windows-wide mutex shared by every AideLink tray entrypoint."""
    global _tray_mutex_handle
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_bool
        handle = kernel32.CreateMutexW(None, True, "Global\\AideLinkTraySingleton")
        if not handle:
            return True
        if ctypes.get_last_error() == 183:
            kernel32.CloseHandle(handle)
            return False
        _tray_mutex_handle = handle
        return True
    except Exception:
        # Keep legacy startup usable on restricted/non-standard Windows hosts.
        logger.exception("托盘单实例锁初始化失败，继续启动")
        return True

# ============================================================
# Constants (from manager.py)
# ============================================================
FLASK_SERVICE_HOST = DEFAULT_FLASK_SERVICE_HOST
FLASK_SERVICE_PORT = DEFAULT_FLASK_SERVICE_PORT

# ============================================================
# Kill & Restart
# ============================================================

def kill_existing_processes(exclude_pid=None):
    """停止本目录启动的 AideLink 进程并释放其端口。

    Never kill an unrelated process merely because it is named ``frpc.exe`` or
    happens to listen on port 5000; users commonly run other local projects.

    Args:
        exclude_pid: 跳过此 PID（调用方传入自身 PID 防止自杀）
    """
    import psutil
    my_pid = exclude_pid or os.getpid()
    creationflags = 0x08000000 if os.name == 'nt' else 0
    curr_dir = str(BASE_DIR)

    # 不使用 /T：IDE 可能由 Flask/托盘启动，递归结束进程树会误伤 IDE。
    # 先按窗口标题清理服务，再按脚本/PID 精确清理 AideLink 自有进程。
    for title in ("aidelink-watchdog-service*", "aidelink-bridge-service*"):
        subprocess.run(["taskkill", "/F", "/FI", f"WINDOWTITLE eq {title}"],
                       capture_output=True, creationflags=creationflags)

    pid_file = os.path.join(curr_dir, "manager.pid")
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())
            if pid != my_pid:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, creationflags=creationflags)
            os.remove(pid_file)
        except Exception:
            pass

    owned_markers = (
        "bridge_watchdog.py", "phone_chat_bridge.py", "manager.py",
        "manager_tray.py", "tray_app.py", "mascot_tray.py",
        "manager_process.py", "start_manager.py",
    )

    def stop_pid(pid):
        if not pid or pid == my_pid:
            return
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=1.5)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired, psutil.AccessDenied):
            pass
        try:
            if psutil.pid_exists(pid) and pid != my_pid:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, creationflags=creationflags)
        except Exception:
            pass

    # 多轮扫描：watchdog 退出后可能刚好留下 bridge，避免一次扫描漏掉旧进程。
    for _ in range(3):
        matched = []
        for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
            try:
                pid = proc.info["pid"]
                cmdline = proc.info.get("cmdline") or []
                cmd_str = " ".join(cmdline).lower()
                if (pid != my_pid and any(x in cmd_str for x in owned_markers)
                        and _is_aidelink_process(proc, cmd_str, curr_dir)):
                    matched.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        for pid in matched:
            stop_pid(pid)
        if not matched:
            break
        time.sleep(0.2)

    for conn in psutil.net_connections(kind="tcp"):
        if conn.laddr.port in (FLASK_SERVICE_PORT, 5001) and conn.pid and conn.pid != my_pid:
            try:
                proc = psutil.Process(conn.pid)
                cmd_str = " ".join(proc.cmdline()).lower()
                if _is_aidelink_process(proc, cmd_str, curr_dir):
                    subprocess.run(["taskkill", "/F", "/PID", str(conn.pid)], capture_output=True, creationflags=creationflags)
            except Exception:
                pass
    time.sleep(0.5)


# ============================================================
# Utility Functions
# ============================================================

def safe_load_tasks(task_file):
    if not task_file.exists():
        return {}
    try:
        with open(task_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        try:
            return json.loads(content, strict=False)
        except json.JSONDecodeError:
            pass
            
        # 尝试修复未闭合的引号
        fixed_lines = []
        for line in content.splitlines():
            stripped = line.strip()
            if '": "' in line and not (stripped.endswith('"') or stripped.endswith('",') or stripped.endswith('"[') or stripped.endswith('"{') or stripped.endswith('],') or stripped.endswith('},')):
                quotes_count = line.count('"')
                if quotes_count % 2 == 1:
                    r_stripped = line.rstrip()
                    if r_stripped.endswith(','):
                        line = r_stripped[:-1].rstrip() + '",'
                    else:
                        line = r_stripped + '"'
            fixed_lines.append(line)
            
        repaired = "\n".join(fixed_lines)
        return json.loads(repaired, strict=False)
    except Exception as e:
        logger.warning(f"Safe load tasks failed: {e}")
        return {}

def load_config():
    """加载配置文件"""
    default_config = {
        "flask_host": FLASK_SERVICE_HOST,
        "flask_port": FLASK_SERVICE_PORT,
        "auto_start": False,
        "open_browser_on_start": False,
        "allow_elevated_ide_launch": False,
        "log_level": "INFO",
        "theme": "dark",
        "frp": {
            "enabled": False,
            "server_addr": "",
            "server_port": 7000,
            "token": "",
            "type": "http",
            "custom_domains": "",
            "remote_port": 5000
        },
        "nas_ssh": {
            "host_lan": "",
            "port_lan": 22,
            "host_wan": "",
            "port_wan": 222,
            "username": "",
            "password": "",
            "config_path": "",
            "container_name": ""
        },
        "nas_frp_service": {
            "url": ""
        }
    }
    data = safe_read_json(CONFIG_FILE, default={})
    for k, v in default_config.items():
        if k not in data:
            data[k] = v
        elif isinstance(v, dict) and isinstance(data[k], dict):
            for sub_k, sub_v in v.items():
                if sub_k not in data[k]:
                    data[k][sub_k] = sub_v
    return data

def save_config(config_data):
    """保存配置文件"""
    ok = safe_write_json(CONFIG_FILE, config_data)
    if ok:
        return True, "配置已保存"
    return False, "保存失败"

def read_log_lines(log_file, n=100):
    """读取日志文件最后 N 行"""
    if not log_file.exists():
        return []
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            return [line.rstrip("\n") for line in all_lines[-n:]]
    except Exception as e:
        return [f"读取日志失败: {e}"]

def log_stream_generator(log_file):
    """SSE 日志流生成器，实时追踪日志文件新增内容"""
    if not log_file.exists():
        yield "data: [日志文件不存在]\n\n"
        return

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            # 移动到文件末尾
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    # SSE 格式：data: 消息内容\n\n
                    yield f"data: {line.rstrip()}\n\n"
                else:
                    time.sleep(0.5)
    except GeneratorExit:
        pass
    except Exception as e:
        yield f"data: [日志流错误: {e}]\n\n"

def read_phone_log_lines(n=100):
    """读取手机端上报日志文件最后 N 行"""
    phone_log = BASE_DIR / "phone_app.log"
    if not phone_log.exists():
        return ["[暂无上报的手机端日志]"]
    try:
        with open(phone_log, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            return [line.rstrip("\n") for line in all_lines[-n:]]
    except Exception as e:
        return [f"读取手机端日志失败: {e}"]

def get_chat_history(limit=100):
    """读取聊天历史"""
    data = safe_read_json(CHAT_HISTORY_FILE, default=[])
    if isinstance(data, list):
        return data[-limit:]
    return []

def get_sessions():
    """获取 IDE 会话列表（从聊天历史中提取）"""
    history = get_chat_history(500)
    sessions = {}
    for msg in history:
        if isinstance(msg, dict):
            session_id = msg.get("session_id") or msg.get("from") or "unknown"
            if session_id not in sessions:
                sessions[session_id] = {
                    "id": session_id,
                    "last_message": msg.get("content", "")[:100],
                    "last_time": msg.get("timestamp") or msg.get("time", ""),
                    "message_count": 1,
                }
            else:
                sessions[session_id]["message_count"] += 1
                ts = msg.get("timestamp") or msg.get("time", "")
                if ts > (sessions[session_id]["last_time"] or ""):
                    sessions[session_id]["last_message"] = msg.get("content", "")[:100]
                    sessions[session_id]["last_time"] = ts
    return list(sessions.values())
