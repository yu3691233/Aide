#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AideLink 管理工具 — 一键启动脚本
==================================
功能：
- 检查管理器是否已在运行（通过 PID 文件）
- 启动 manager.py（带系统托盘 + Web 管理界面）
- 创建 PID 文件记录进程 ID

使用方法：
  python start_manager.py           # 启动管理器
  python start_manager.py --check   # 仅检查状态
  python start_manager.py --web-only  # 仅启动 Web 管理界面（无托盘）
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from manager_utils import kill_existing_processes

# ============================================================
# 常量
# ============================================================
BASE_DIR = Path(__file__).parent.resolve()
MANAGER_SCRIPT = BASE_DIR / "manager.py"
TRAY_SCRIPT = BASE_DIR / "tray_app.py"
PID_FILE = BASE_DIR / "manager.pid"
MANAGER_PORT = 5001


def check_already_running():
    """
    检查管理器是否已在运行。
    通过 PID 文件判断，同时验证进程是否真实存在。
    返回 True 表示已在运行。
    """
    if not PID_FILE.exists():
        return False

    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        # PID 文件损坏，清理
        PID_FILE.unlink(missing_ok=True)
        return False

    # 检查进程是否存在
    import psutil
    try:
        proc = psutil.Process(pid)
        if proc.is_running():
            # 验证是否是 manager 进程
            cmdline = " ".join(proc.cmdline())
            if "manager.py" in cmdline or "tray_app.py" in cmdline:
                return True
            else:
                # PID 被其他进程占用，清理
                PID_FILE.unlink(missing_ok=True)
                return False
    except psutil.NoSuchProcess:
        # 进程不存在，清理 PID 文件
        PID_FILE.unlink(missing_ok=True)
        return False


def check_port_in_use(port):
    """检查端口是否被占用"""
    import psutil
    for conn in psutil.net_connections(kind="tcp"):
        if conn.laddr.port == port and conn.status == "LISTEN":
            return True
    return False


def start_manager(with_tray=True):
    """
    启动管理器。

    Args:
        with_tray: True 启动 manager.py（含托盘），False 启动 tray_app.py（仅托盘）
    """
    if check_already_running() or check_port_in_use(MANAGER_PORT):
        print("[INFO] 发现旧管理器进程，正在清理后重启...")
        kill_existing_processes()
        time.sleep(1)

    # 选择启动脚本
    script = MANAGER_SCRIPT if with_tray else TRAY_SCRIPT
    if not script.exists():
        print(f"[ERROR] 找不到启动脚本: {script}")
        sys.exit(1)

    # 确定 Python 解释器
    python_exe = sys.executable

    print(f"[INFO] 正在启动 AideLink 管理器...")
    print(f"[INFO] 脚本: {script}")

    # 启动进程（独立进程，不阻塞当前脚本）
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        [python_exe, str(script)],
        cwd=str(BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )

    # 等待一小段时间确认启动
    time.sleep(2)

    if check_already_running():
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        print(f"[OK] AideLink 管理器已启动 (PID: {pid})")
        print(f"[OK] 管理面板: http://localhost:{MANAGER_PORT}")
        print(f"[OK] 右键点击任务栏托盘图标打开菜单")
    else:
        print("[WARN] 管理器已启动但 PID 文件未生成，可能启动失败")
        print("[INFO] 请检查日志: flask_new.log")


def show_status():
    """显示管理器状态"""
    import psutil

    print("=" * 50)
    print("AideLink 管理器状态")
    print("=" * 50)

    if check_already_running():
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        try:
            proc = psutil.Process(pid)
            create_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(proc.create_time()))
            print(f"  状态: ✅ 运行中")
            print(f"  PID: {pid}")
            print(f"  启动时间: {create_time}")
        except psutil.NoSuchProcess:
            print(f"  状态: ⚠️ PID 文件存在但进程已退出")
            PID_FILE.unlink(missing_ok=True)
    else:
        print(f"  状态: ⏹ 未运行")

    print(f"  管理端口: {MANAGER_PORT}")
    print(f"  端口占用: {'是' if check_port_in_use(MANAGER_PORT) else '否'}")
    print(f"  PID 文件: {PID_FILE}")
    print("=" * 50)


def main():
    """主入口"""
    # 解析简单的命令行参数
    args = sys.argv[1:]

    if "--check" in args:
        show_status()
        return

    if "--web-only" in args:
        print("[INFO] 仅启动系统托盘应用（不含 Web 管理界面）...")
        start_manager(with_tray=False)
        return

    print("=" * 50)
    print("AideLink 管理器 — 一键启动")
    print("=" * 50)
    start_manager(with_tray=True)


if __name__ == "__main__":
    main()
