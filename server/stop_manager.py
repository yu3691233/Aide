#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AideLink 管理工具 — 停止脚本
==================================
功能：
- 通过 PID 文件查找并停止管理器进程
- 清理 PID 文件
- 可选：同时停止 Flask 服务 (phone_chat_bridge.py)

使用方法：
  python stop_manager.py           # 仅停止管理器
  python stop_manager.py --all     # 停止管理器 + Flask 服务
  python stop_manager.py --force   # 强制终止（使用 SIGKILL）
"""

import os
import sys
import time
import signal
import psutil
from pathlib import Path

# ============================================================
# 常量
# ============================================================
BASE_DIR = Path(__file__).parent.resolve()
PID_FILE = BASE_DIR / "manager.pid"
FLASK_SERVICE_NAME = "phone_chat_bridge.py"
WATCHDOG_SERVICE_NAME = "bridge_watchdog.py"


def get_manager_pid():
    """
    从 PID 文件读取管理器 PID。
    返回 int 或 None。
    """
    if not PID_FILE.exists():
        return None

    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        return pid
    except (ValueError, OSError):
        PID_FILE.unlink(missing_ok=True)
        return None


def stop_manager(force=False):
    """
    停止 AideLink 管理器进程。

    Args:
        force: True 使用强制终止 (kill)，False 使用优雅终止 (terminate)

    Returns:
        (success: bool, message: str)
    """
    pid = get_manager_pid()
    if pid is None:
        return False, "未找到 PID 文件，管理器可能未在运行"

    try:
        proc = psutil.Process(pid)
        if not proc.is_running():
            PID_FILE.unlink(missing_ok=True)
            return False, f"进程 {pid} 已不在运行"

        # 验证是否是管理器进程
        cmdline = " ".join(proc.cmdline())
        if not any(name in cmdline for name in ("manager.py", "manager_tray.py", "tray_app.py")):
            PID_FILE.unlink(missing_ok=True)
            return False, f"PID {pid} 不是管理器进程，已清理 PID 文件"

        if force:
            proc.kill()
            proc.wait(timeout=5)
            PID_FILE.unlink(missing_ok=True)
            return True, f"管理器进程 {pid} 已强制终止"
        else:
            proc.terminate()
            try:
                proc.wait(timeout=10)
                PID_FILE.unlink(missing_ok=True)
                return True, f"管理器进程 {pid} 已停止"
            except psutil.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
                PID_FILE.unlink(missing_ok=True)
                return True, f"管理器进程 {pid} 已强制终止（超时）"

    except psutil.NoSuchProcess:
        PID_FILE.unlink(missing_ok=True)
        return False, f"进程 {pid} 不存在"
    except Exception as e:
        return False, f"停止失败: {e}"


def stop_flask_service(force=False):
    """
    停止 phone_chat_bridge.py (Flask 服务)。

    Args:
        force: True 使用强制终止

    Returns:
        (success: bool, message: str)
    """
    for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if any(FLASK_SERVICE_NAME in part for part in cmdline):
                if force:
                    proc.kill()
                    proc.wait(timeout=5)
                else:
                    proc.terminate()
                    proc.wait(timeout=10)
                return True, f"Flask 服务 (PID: {proc.pid}) 已停止"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except psutil.TimeoutExpired:
            proc.kill()
            return True, f"Flask 服务 (PID: {proc.pid}) 已强制终止"
        except Exception:
            continue

    return False, "Flask 服务未在运行"


def stop_watchdog(force=False):
    """Stop the supervisor before stopping Flask, preventing an immediate respawn."""
    stopped = 0
    for proc in psutil.process_iter(attrs=["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if WATCHDOG_SERVICE_NAME not in cmdline:
                continue
            if force:
                proc.kill()
            else:
                proc.terminate()
            proc.wait(timeout=5)
            stopped += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except psutil.TimeoutExpired:
            try:
                proc.kill()
                stopped += 1
            except Exception:
                pass
    return stopped > 0, f"Watchdog 已停止 ({stopped})" if stopped else "Watchdog 未在运行"


def stop_aidelink_processes(force=True):
    """Stop every AideLink child in this installation, including stale trays."""
    base = str(BASE_DIR).lower()
    stopped = 0
    for proc in psutil.process_iter(attrs=["pid", "cmdline"]):
        try:
            if proc.pid == os.getpid():
                continue
            cmdline = " ".join(proc.info.get("cmdline") or [])
            # The Flask worker is launched as the embedded runtime's python.exe
            # and may not contain one of the child-script markers. Restrict the
            # match to this installation so unrelated Python applications stay
            # untouched, then stop any process whose command line belongs here.
            if base not in cmdline.lower():
                try:
                    exe = (proc.exe() or "").lower()
                except Exception:
                    exe = ""
                if base not in exe:
                    continue
            if force:
                proc.kill()
            else:
                proc.terminate()
            proc.wait(timeout=5)
            stopped += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception:
            pass
    return stopped


def main():
    """主入口"""
    args = sys.argv[1:]

    force = "--force" in args
    stop_all = "--all" in args

    print("=" * 50)
    print("AideLink 管理器 — 停止")
    print("=" * 50)

    # 停止管理器
    success, msg = stop_manager(force=force)
    print(f"  管理器: {msg}")

    # 停止 Flask 服务
    if stop_all:
        watchdog_success, watchdog_msg = stop_watchdog(force=True if force else False)
        print(f"  Watchdog: {watchdog_msg}")
        success2, msg2 = stop_flask_service(force=force)
        print(f"  Flask: {msg2}")
        print(f"  子进程: 已停止 {stop_aidelink_processes(force=True)} 个")

    # 清理 PID 文件（确保）
    PID_FILE.unlink(missing_ok=True)
    print("=" * 50)


if __name__ == "__main__":
    main()
