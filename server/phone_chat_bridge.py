import ctypes
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import os
import sys
import json
import time
import re
import subprocess
import threading
from datetime import datetime

# ── 自动加载 .env（必须在任何配置读取之前）
# 支持 AIDELINK_ENV_PATH 环境变量指定 .env 路径，默认回退到 ../.env
_env_path = os.environ.get("AIDELINK_ENV_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k, _v = _k.strip(), _v.strip().strip("\"'")
                    if _k and not os.environ.get(_k):
                        os.environ[_k] = _v
    except Exception:
        pass
from flask import Flask, request, jsonify, Response, send_from_directory, render_template
from werkzeug.utils import secure_filename
import gc
# Werkzeug serving monkeypatch to prevent Windows socket abort OSError from spamming tracebacks
try:
    import werkzeug.serving
    if OSError not in werkzeug.serving.connection_dropped_errors:
        werkzeug.serving.connection_dropped_errors = werkzeug.serving.connection_dropped_errors + (OSError,)
except Exception:
    pass

try:
    import logging
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
except Exception:
    pass
from PIL import ImageGrab, Image
import io
import requests
import pyperclip
import ctypes
from ctypes import wintypes
from task_runtime import TaskRuntime, SUPPORTED_IDES
from event_bus import bus
import model_registry
import ide_scanner
from notification_watcher import get_watcher
import capture_window
from routes import register_all_routes
from json_utils import safe_read_json, safe_write_json, atomic_write_json
from paths import BRIDGE_DIR, HISTORY_FILE, CLIPBOARD_FILE, IN_FILE, UPLOAD_FOLDER, SETTINGS_FILE, SCREEN_CONFIG_FILE
from config import MINIMAX_API_KEY, MINIMAX_URL, SYSTEM_PROMPT, SETTINGS_SCHEMA, load_settings as _load_settings, save_settings as _save_settings, file_lock
from frp_service import start_frp_client
from mdns_service import register_mdns_service
from upload_policy import configure_upload_limits


app = Flask(__name__, template_folder=os.path.join(BRIDGE_DIR, "templates"))
configure_upload_limits(app)
register_all_routes(app)

# 确保 adb-server 处于启动状态，彻底消除后续 adb 命令时因启动 daemon 产生终端黑框弹窗的问题
try:
    _cf = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.run(["adb", "start-server"], capture_output=True, creationflags=_cf)
except Exception:
    pass

print("[IDE-Scanner] Performing startup IDE scan...")
try:
    scanned = ide_scanner.scan_installed_ides()
    print(f"[IDE-Scanner] Found {len(scanned)} installed IDE(s)")
except Exception as e:
    print(f"[IDE-Scanner] Scan failed: {e}")

# OC Web 代理已迁移到 routes/oc_web_routes.py

# Base Paths
from shared_runtime import runtime

# 已连接设备追踪（设备 WiFi IP → 最后活跃时间）
import time as _time
from connected_devices import track_ip, update_device_alias, get_connected
import connected_devices as _cd

@app.before_request
def _track_device():
    """记录访问服务器的设备 IP，自动更新设备别名"""
    track_ip(request.remote_addr)
    device_ip = request.headers.get("X-Device-IP", "").strip()
    device_serial = request.headers.get("X-Device-Serial", "").strip()
    if device_ip:
        update_device_alias(device_ip, device_serial or None)

# /api/debug/connected 已迁移到 routes/misc_routes.py

# 启动任务监控（Git hook + 文件监控 + 进程监控）
from task_monitor import start_all_monitors
start_all_monitors()

os.makedirs(UPLOAD_FOLDER, exist_ok=True)



from shared_runtime import init_files, read_history, write_history, read_clipboard, write_clipboard

@app.route('/')
def index():
    """将 Web 控制面板直接挂载在 5000 端口服务"""
    return render_template("dashboard.html", mimo_workspace=os.environ.get("AIDELINK_WORKSPACE_DIR", str(BRIDGE_DIR)))

def _normalize_owned_paths(value):
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []

@app.route('/tasks.html', methods=['GET'])
def tasks_page():
    return send_from_directory(os.path.join(BRIDGE_DIR, "static"), "tasks.html")


# 项目地图 API 已迁移到 routes/project_routes.py
# /project-map → /api/project-map
# /project-map/scan → /api/project-map/scan
# /project-map/lock → /project-map/lock

# UI 定位器路由已迁移到 routes/ui_locator_routes.py
# /sessions 已迁移到 routes/config_routes.py
# /tasks, /tasks/create, /tasks/<task_id>, /tasks/<task_id>/assign,
# /tasks/<task_id>/complete 已迁移到 routes/task_routes.py
# /debug/notify, /tasks/<task_id>/confirm, /tasks/<task_id>/fail,
# /queues/<ide>/next, /ide/<ide>/heartbeat, /ide/<ide>/release,
# /tasks/<task_id>/worktree*, /tasks/<task_id>/patch, /tasks/<task_id>/merge,
# /leases 已迁移到 routes/task_routes.py 和 routes/ide_routes.py






# 进化任务路由已迁移到 routes/evolution_routes.py

# /api/adb/logcat 已迁移到 routes/device_routes.py
# /api/test/dispatch, /api/test/result 已迁移到 routes/task_routes.py


if __name__ == '__main__':
    port = int(os.environ.get("AIDELINK_FLASK_SERVICE_PORT", "5000"))
    config_path = os.path.join(BRIDGE_DIR, 'config.json')
    if os.path.exists(config_path):
        try:
            cfg = safe_read_json(config_path, {})
            if "AIDELINK_FLASK_SERVICE_PORT" not in os.environ:
                port = cfg.get("flask_port", port) if isinstance(cfg, dict) else port
        except Exception:
            pass
            
    start_frp_client()
    register_mdns_service(port)

    # 启动 Windows 通知监控（捕获 IDE 任务完成通知）
    try:
        # 设置控制台窗口标题为独特的标识符，以便 taskkill 强杀
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW("aidelink-bridge-service")
            
        watcher = get_watcher(bus)
        if watcher:
            watcher.start()
    except Exception as e:
        print(f"[WARN] Failed to start notification watcher: {e}", flush=True)

    # 启动 CLI IDE 完成检测线程（mimo/oc 不发 Windows 通知，需要轮询检测）
    def _cli_completion_loop():
        import time as _time
        from task_runtime import TaskRuntime, SUPPORTED_IDES
        while True:
            try:
                _time.sleep(15)  # 每 15 秒检查一次
                ide_status_file = os.path.join(BRIDGE_DIR, "state", "ide_status.json")
                tasks_file = os.path.join(BRIDGE_DIR, "state", "tasks.json")
                if not os.path.exists(ide_status_file) or not os.path.exists(tasks_file):
                    continue
                ide_status = safe_read_json(ide_status_file, {})
                tasks = safe_read_json(tasks_file, [])

                cli_ides = ("mimo", "oc")
                rt = TaskRuntime(BRIDGE_DIR)
                for ide_key in cli_ides:
                    status_info = ide_status.get(ide_key, {})
                    current_task_id = status_info.get("current_task_id")
                    if not current_task_id:
                        continue
                    task = next((t for t in tasks if t.get("task_id") == current_task_id), None)
                    if not task or task.get("status") != "running":
                        continue

                    # 检测方式1：IDE 不再 busy
                    if status_info.get("status") != "busy":
                        rt.mark_task_done(current_task_id, summary="CLI IDE 完成（IDE 空闲检测）")
                        print(f"[CLI-Check] {ide_key}: task {current_task_id} done (idle)", flush=True)
                        continue

                    # 检测方式2：worktree 有 result
                    worktree = task.get("worktree_path")
                    if worktree and os.path.isdir(os.path.join(worktree, "result")):
                        rt.mark_task_done(current_task_id, summary="CLI IDE 完成（worktree result）")
                        print(f"[CLI-Check] {ide_key}: task {current_task_id} done (result)", flush=True)
            except Exception as e:
                print(f"[CLI-Check] Error: {e}", flush=True)

    threading.Thread(target=_cli_completion_loop, daemon=True, name="CLI-Completion-Check").start()
    print("[CLI-Check] Started background CLI completion checker", flush=True)

    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
