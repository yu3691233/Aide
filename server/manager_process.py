import os
import sys
import time
import socket
import subprocess
import logging
import psutil
from pathlib import Path
from paths import BRIDGE_DIR as BASE_DIR, LOG_FILE

logger = logging.getLogger('manager')

# ============================================================
# 全局常量
# ============================================================
FLASK_SERVICE_SCRIPT = "phone_chat_bridge.py"
FLASK_SERVICE_PORT = 5000
WATCHDOG_SCRIPT = "bridge_watchdog.py"
MANAGER_PORT = 5001
PID_FILE = BASE_DIR / "manager.pid"

# ============================================================
# 进程管理辅助函数
# ============================================================

def get_flask_process():
    """
    查找 phone_chat_bridge.py 的运行进程。
    返回 psutil.Process 对象或 None。
    """
    for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if any(FLASK_SERVICE_SCRIPT in part for part in cmdline):
                return psutil.Process(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def get_watchdog_process():
    """查找 bridge_watchdog.py 的运行进程"""
    for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            cmd_str = " ".join(cmdline).lower()
            if "bridge_watchdog.py" in cmd_str:
                return psutil.Process(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def is_flask_running():
    """检查 Flask 服务是否正在运行"""
    proc = get_flask_process()
    return proc is not None and proc.is_running()


def get_flask_pid():
    """获取 Flask 服务的 PID，未运行则返回 None"""
    proc = get_flask_process()
    return proc.pid if proc else None


def start_flask_service():
    """
    通过 watchdog 启动 phone_chat_bridge.py 服务。
    返回 (success: bool, message: str)
    """
    if is_flask_running():
        return False, "Flask 服务已在运行中"

    watchdog_script = "bridge_watchdog.py"
    script_path = BASE_DIR / watchdog_script
    if not script_path.exists():
        return False, f"找不到守护服务脚本: {script_path}"

    try:
        # 使用 python.exe + CREATE_NO_WINDOW 启动（pythonw.exe 下 stdout 重定向不可靠）
        python_exe = Path(sys.executable)

        log_file = open(str(LOG_FILE), "a", encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen(
            [str(python_exe), "-u", str(script_path)],
            cwd=str(BASE_DIR),
            stdout=log_file,
            stderr=log_file,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        # 等待一小段时间让 watchdog 启动 bridge
        time.sleep(2.5)
        if is_flask_running():
            return True, f"Flask 服务已通过守护进程拉起 (PID: {get_flask_pid()})"
        else:
            # 即使没检测到，如果 watchdog 起了，也可能是启动延迟，返回守护进程状态
            watchdog_proc = get_watchdog_process()
            if watchdog_proc:
                return True, f"守护进程已启动 (PID: {watchdog_proc.pid})，但桥接服务仍在初始化..."
            return False, "守护进程启动后未能检测到进程"
    except Exception as e:
        return False, f"启动失败: {e}"


def stop_flask_service():
    """
    停止守护进程和 phone_chat_bridge.py 服务。
    返回 (success: bool, message: str)
    """
    # 1. 先停掉 watchdog，防止它重拉
    watchdog_proc = get_watchdog_process()
    if watchdog_proc:
        try:
            watchdog_proc.terminate()
            watchdog_proc.wait(timeout=5)
        except Exception:
            try:
                watchdog_proc.kill()
            except Exception:
                pass

    # 2. 再停掉 Flask 服务
    proc = get_flask_process()
    if not proc:
        return True, "Flask 服务已停止"

    try:
        proc.terminate()
        proc.wait(timeout=5)
        if not proc.is_running():
            return True, "Flask 服务已停止"
        else:
            proc.kill()
            proc.wait(timeout=3)
            return True, "Flask 服务已强制停止"
    except psutil.TimeoutExpired:
        proc.kill()
        return True, "Flask 服务已强制停止（超时）"
    except Exception as e:
        return False, f"停止失败: {e}"


def restart_flask_service():
    """
    重启 Flask 服务。
    返回 (success: bool, message: str)
    """
    stop_flask_service()
    time.sleep(1)
    return start_flask_service()


def get_service_status():
    """获取服务状态信息"""
    from datetime import datetime
    proc = get_flask_process()
    if proc and proc.is_running():
        create_time = datetime.fromtimestamp(proc.create_time())
        uptime = datetime.now() - create_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return {
            "running": True,
            "pid": proc.pid,
            "port": FLASK_SERVICE_PORT,
            "create_time": create_time.strftime("%Y-%m-%d %H:%M:%S"),
            "uptime": f"{hours}小时 {minutes}分 {seconds}秒",
            "cpu_percent": proc.cpu_percent(interval=0.5),
            "memory_mb": round(proc.memory_info().rss / 1024 / 1024, 1),
        }
    return {
        "running": False,
        "pid": None,
        "port": FLASK_SERVICE_PORT,
        "create_time": None,
        "uptime": None,
        "cpu_percent": 0,
        "memory_mb": 0,
    }


def get_system_info():
    """获取系统资源使用信息"""
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "memory_total_mb": round(psutil.virtual_memory().total / 1024 / 1024, 0),
        "memory_used_mb": round(psutil.virtual_memory().used / 1024 / 1024, 0),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_total_gb": round(psutil.disk_usage(str(BASE_DIR)).total / 1024 / 1024 / 1024, 1),
        "disk_used_gb": round(psutil.disk_usage(str(BASE_DIR)).used / 1024 / 1024 / 1024, 1),
        "disk_percent": psutil.disk_usage(str(BASE_DIR)).percent,
    }
