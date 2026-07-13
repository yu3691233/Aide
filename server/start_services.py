import os
import sys
import subprocess

# Python Embeddable Runtime uses a restrictive ``._pth`` file and may not
# add the script directory automatically when launched by wscript.exe.
# Ensure packaged startup resolves the server's local modules.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from manager_utils import kill_existing_processes


def start_services():
    kill_existing_processes()

    curr_dir = os.path.dirname(os.path.abspath(__file__))
    python_exe = sys.executable

    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

    # 启动 watchdog（管理桥接服务生命周期）
    watchdog_path = os.path.join(curr_dir, "bridge_watchdog.py")
    subprocess.Popen(
        [python_exe, "-u", watchdog_path],
        cwd=curr_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    print("Started bridge_watchdog.py daemon in background")

    # 启动系统托盘应用
    tray_path = os.path.join(curr_dir, "manager_tray.py")
    subprocess.Popen(
        [python_exe, "-u", tray_path],
        cwd=curr_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
    )
    print("Started manager_tray.py daemon in background")


if __name__ == "__main__":
    start_services()
