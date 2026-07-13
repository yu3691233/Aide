#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AideLink 系统托盘应用（独立版本）
==================================
精简版的系统托盘应用，不依赖 Web UI。
- pystray 托盘图标：显示在任务栏右侧
- 右键菜单：打开管理面板、启动/停止/重启服务、退出
- 左键点击：打开管理面板（浏览器访问 localhost:5001）

依赖：pystray, Pillow, psutil
"""

import os
import sys
import json
import time
import logging
import subprocess
import webbrowser
from pathlib import Path
from json_utils import safe_read_json

import psutil
import threading
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw
from manager_utils import acquire_tray_single_instance

# ============================================================
# 全局常量
# ============================================================
BASE_DIR = Path(__file__).parent.resolve()
FLASK_SERVICE_NAME = "phone_chat_bridge.py"
FLASK_SERVICE_PORT = 5000
MANAGER_PORT = 5001
PID_FILE = BASE_DIR / "manager.pid"
LOG_FILE = BASE_DIR / "flask_new.log"

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("AideLinkTray")


# ============================================================
# 进程管理
# ============================================================

def get_flask_process():
    """查找 phone_chat_bridge.py 的运行进程"""
    for proc in psutil.process_iter(attrs=["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if any(FLASK_SERVICE_NAME in part for part in cmdline):
                return psutil.Process(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def is_flask_running():
    """检查 Flask 服务是否正在运行"""
    proc = get_flask_process()
    return proc is not None and proc.is_running()


def get_status_text():
    """获取服务状态文字"""
    if is_flask_running():
        try:
            import urllib.request
            with urllib.request.urlopen(f"http://127.0.0.1:{FLASK_SERVICE_PORT}/events/stats", timeout=1) as response:
                if response.status == 200:
                    return "✅ Flask 运行中"
        except Exception:
            return "⚠️ Flask 异常 (无法连接)"
        return "✅ Flask 运行中"
    return "⏹ Flask 已停止"


def _get_current_project():
    """获取当前目标项目名称"""
    settings_file = BASE_DIR / "aidelink_settings.json"
    settings = safe_read_json(settings_file, {})
    if isinstance(settings, dict):
        cp = settings.get("current_project", "")
        if cp:
            return os.path.basename(cp)
        pd = settings.get("project_dir", "")
        if pd:
            return os.path.basename(pd)
    return None


def _load_settings_tray():
    """读取设置"""
    settings_file = BASE_DIR / "aidelink_settings.json"
    data = safe_read_json(settings_file, {})
    return data if isinstance(data, dict) else {}


def _save_settings_tray(data):
    """保存设置"""
    from json_utils import atomic_write_json
    settings_file = BASE_DIR / "aidelink_settings.json"
    atomic_write_json(settings_file, data)


def _select_project(path):
    """选择当前项目"""
    settings = _load_settings_tray()
    projects = settings.get("projects", [])
    if not any(p.get("path") == path for p in projects):
        name = os.path.basename(path)
        projects.append({"path": path, "name": name, "last_used": ""})
        settings["projects"] = projects
    settings["current_project"] = path
    _save_settings_tray(settings)
    logger.info(f"项目已切换: {path}")
    # 重启服务以应用新项目
    restart_service()


def _browse_folder_tray():
    """打开文件夹选择对话框（独立线程，避免阻塞托盘事件循环）"""
    import threading
    def _dialog():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.title("选择项目文件夹")
            root.geometry("1x1+0+0")
            root.attributes('-topmost', True)
            root.after(100, root.focus_force)
            path = filedialog.askdirectory(title="选择项目文件夹", parent=root)
            try:
                root.destroy()
            except Exception:
                pass
            if path:
                settings = _load_settings_tray()
                projects = settings.get("projects", [])
                if not any(p.get("path") == path for p in projects):
                    name = os.path.basename(path)
                    projects.append({"path": path, "name": name, "last_used": ""})
                    settings["projects"] = projects
                    _save_settings_tray(settings)
                _select_project(path)
        except Exception as e:
            logger.error(f"打开文件夹对话框失败: {e}")
    threading.Thread(target=_dialog, daemon=True).start()


def _get_tasks_file():
    """获取当前项目的任务文件（按项目隔离）"""
    try:
        settings_file = BASE_DIR / "aidelink_settings.json"
        settings = safe_read_json(settings_file, {})
        if not isinstance(settings, dict):
            settings = {}
        project_dir = settings.get("current_project", "") or settings.get("project_dir", "")
        if not project_dir:
            project_dir = settings.get("opencode_project_dir", "")
        if project_dir and os.path.isdir(project_dir):
            import hashlib
            h = hashlib.md5(os.path.normcase(os.path.normpath(project_dir)).encode('utf-8')).hexdigest()[:8]
            folder = "".join(c for c in os.path.basename(project_dir) if c.isalnum()) or "proj"
            state_dir = BASE_DIR / "state"
            f = state_dir / f"tasks_{folder}_{h}.json"
            if f.exists():
                return f
    except Exception:
        pass
    return BASE_DIR / "state" / "tasks.json"


def get_active_tasks_count():
    """获取当前派发中/执行中的任务数量"""
    tasks_file = _get_tasks_file()
    if not tasks_file.exists():
        return 0
    tasks = safe_read_json(tasks_file, [])
    if not isinstance(tasks, list):
        return 0
    active_statuses = {"queued", "dispatched", "running"}
    active_count = sum(1 for t in tasks if isinstance(t, dict) and t.get("status") in active_statuses)
    return active_count


def start_service():
    """启动 Flask 服务"""
    if is_flask_running():
        logger.info("Flask 服务已在运行中，无需启动")
        return

    script_path = BASE_DIR / FLASK_SERVICE_NAME
    if not script_path.exists():
        logger.error(f"找不到服务脚本: {script_path}")
        return

    try:
        python_exe = Path(sys.executable).parent / "pythonw.exe"
        if not python_exe.exists():
            python_exe = Path(sys.executable)

        log_file = open(str(LOG_FILE), "a", encoding="utf-8")
        subprocess.Popen(
            [str(python_exe), str(script_path)],
            cwd=str(BASE_DIR),
            stdout=log_file,
            stderr=log_file,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        time.sleep(2)
        if is_flask_running():
            logger.info("Flask 服务启动成功")
        else:
            logger.warning("Flask 服务启动后未能检测到进程")
    except Exception as e:
        logger.error(f"启动失败: {e}")


def stop_service():
    """停止 Flask 服务"""
    proc = get_flask_process()
    if not proc:
        logger.info("Flask 服务未在运行")
        return

    try:
        proc.terminate()
        proc.wait(timeout=10)
        logger.info("Flask 服务已停止")
    except psutil.TimeoutExpired:
        proc.kill()
        logger.info("Flask 服务已强制停止")
    except Exception as e:
        logger.error(f"停止失败: {e}")


def restart_service():
    """重启 Flask 服务"""
    stop_service()
    time.sleep(1)
    start_service()


# ============================================================
# 图标绘制
# ============================================================

def create_icon_image(status_color=None):
    """
    加载托盘图标（优先使用 brand_assets/ 里的定型 logo，fallback 才用黄色笑脸）。
    并在右下角绘制红/绿圈指示服务状态。
    - status_color = "red": 红色圆点指示圈（服务异常或关闭）
    - status_color = "green": 绿色圆点指示圈（正在派发/执行任务）
    - status_color = None: 无圆点（正常运行且空闲）
    """
    from pathlib import Path
    img = None
    candidates = [
        BASE_DIR / "brand_assets" / "tray-icon.png",
        BASE_DIR / "brand_assets" / "logo-application-primary-512.png",
    ]
    for p in candidates:
        if p.exists():
            img = Image.open(p).convert("RGBA")
            img.thumbnail((64, 64), Image.LANCZOS)
            break

    if img is None:
        # fallback: 手绘黄色笑脸（保留旧实现，避免无 logo 时托盘空白）
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        cx, cy = size // 2, size // 2
        r = 28

        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(255, 217, 61, 255),
            outline=(244, 163, 0, 255),
            width=2,
        )
        draw.ellipse([cx - 12, cy - 10, cx - 4, cy - 2], fill=(50, 50, 50, 255))
        draw.ellipse([cx + 4, cy - 10, cx + 12, cy - 2], fill=(50, 50, 50, 255))
        draw.ellipse([cx - 10, cy - 9, cx - 8, cy - 6], fill=(255, 255, 255, 220))
        draw.ellipse([cx + 6, cy - 9, cx + 8, cy - 6], fill=(255, 255, 255, 220))
        draw.arc([cx - 14, cy - 2, cx + 14, cy + 16], start=10, end=170, fill=(50, 50, 50, 255), width=2)
        draw.ellipse([cx - 20, cy + 6, cx - 12, cy + 13], fill=(255, 182, 193, 140))
        draw.ellipse([cx + 12, cy + 6, cx + 20, cy + 13], fill=(255, 182, 193, 140))

    if status_color in ("red", "green"):
        draw = ImageDraw.Draw(img)
        w, h = img.size
        # 在右下角绘制状态圆点
        dot_r = max(6, w // 8)
        cx, cy = w - dot_r - 2, h - dot_r - 2
        color = (244, 67, 54, 255) if status_color == "red" else (76, 175, 80, 255)
        # 绘制背景白边与实心圆
        draw.ellipse([cx - dot_r - 1, cy - dot_r - 1, cx + dot_r + 1, cy + dot_r + 1], fill=(255, 255, 255, 255))
        draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=color)

    return img


# ============================================================
# 托盘菜单
# ============================================================

def build_menu():
    """构建系统托盘右键菜单"""
    project = _get_current_project()
    title = f"AideLink — {project} — {get_status_text()}" if project else f"AideLink — {get_status_text()}"

    # 构建项目选择子菜单
    settings = _load_settings_tray()
    projects = settings.get("projects", [])
    current = settings.get("current_project", "")
    project_items = []
    for p in projects:
        pname = p.get("name", os.path.basename(p.get("path", "")))
        ppath = p.get("path", "")
        marker = "✅ " if ppath == current else "   "
        project_items.append(MenuItem(f"{marker}{pname}", lambda pp=ppath: _select_project(pp)))
    project_items.append(Menu.SEPARATOR)
    project_items.append(MenuItem("📁 浏览文件夹...", lambda: _browse_folder_tray()))

    return Menu(
        MenuItem(title, None, enabled=False),
        Menu.SEPARATOR,
        MenuItem("📂 选择项目", Menu(*project_items)),
        MenuItem(
            "📊 打开管理面板",
            lambda: webbrowser.open(f"http://localhost:{MANAGER_PORT}"),
        ),
        Menu.SEPARATOR,
        MenuItem("🚀 启动服务", lambda: start_service()),
        MenuItem("⏹ 停止服务", lambda: stop_service()),
        MenuItem("🔄 重启服务", lambda: restart_service()),
        Menu.SEPARATOR,
        MenuItem("📁 打开数据目录", lambda: os.startfile(str(BASE_DIR))),
        Menu.SEPARATOR,
        MenuItem("❌ 退出", lambda: on_exit()),
    )


def on_exit():
    """退出回调"""
    logger.info("正在退出 AideLink 托盘应用...")
    try:
        tray.stop()
    except Exception:
        pass
    os._exit(0)


# ============================================================
# 入口
# ============================================================

tray = None


def status_monitor_loop():
    """后台监控服务状态，动态更新托盘图标"""
    global tray
    last_status = "INITIAL"
    while True:
        try:
            # 1. 检查 Flask 服务是否在运行且健康
            is_running = is_flask_running()
            is_healthy = False
            if is_running:
                try:
                    import urllib.request
                    # 请求 /events/stats 以检测是否健康
                    with urllib.request.urlopen(f"http://127.0.0.1:{FLASK_SERVICE_PORT}/events/stats", timeout=2) as response:
                        if response.status == 200:
                            is_healthy = True
                except Exception:
                    is_healthy = False

            # 2. 检查是否有派发中任务
            active_tasks = 0
            if is_healthy:
                active_tasks = get_active_tasks_count()

            # 3. 确定最终状态颜色
            if not is_running or not is_healthy:
                status = "red"
            elif active_tasks > 0:
                status = "green"
            else:
                status = None

            # 4. 如果状态改变，更新图标与菜单文本
            if status != last_status:
                last_status = status
                if tray is not None:
                    new_img = create_icon_image(status)
                    tray.icon = new_img
                    tray.menu = build_menu()
        except Exception as e:
            logger.error(f"Status monitor error: {e}")
        time.sleep(2)


def main():
    """启动系统托盘应用"""
    global tray

    # 初始状态
    initial_status = "red"
    if is_flask_running():
        try:
            import urllib.request
            with urllib.request.urlopen(f"http://127.0.0.1:{FLASK_SERVICE_PORT}/events/stats", timeout=1) as response:
                if response.status == 200:
                    initial_status = "green" if get_active_tasks_count() > 0 else None
        except Exception:
            initial_status = "red"

    tray = Icon(
        name="AideLinkTray",
        icon=create_icon_image(initial_status),
        title="AideLink 管理器",
        menu=build_menu(),
    )

    # 左键点击打开管理面板
    tray.on_click = lambda icon: webbrowser.open(f"http://localhost:{MANAGER_PORT}")

    # 启动状态监控线程
    monitor_thread = threading.Thread(target=status_monitor_loop, daemon=True)
    monitor_thread.start()

    logger.info("AideLink 托盘应用已启动")
    logger.info(f"左键点击打开管理面板: http://localhost:{MANAGER_PORT}")
    tray.run()


if __name__ == "__main__":
    if acquire_tray_single_instance():
        main()
