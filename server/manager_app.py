"""
Flask 应用初始化 + 仪表盘路由 + 状态 API。
"""
import os
from pathlib import Path
from flask import Flask, jsonify, render_template, request
from json_utils import safe_read_json, safe_write_json

from paths import SETTINGS_FILE
from manager_utils import BASE_DIR, logger

# ============================================================
# Flask 应用
# ============================================================

manager_app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))
manager_app.config["JSON_AS_ASCII"] = False


def _load_manager_settings() -> dict:
    return safe_read_json(SETTINGS_FILE, default={})


def _save_manager_settings(data: dict) -> bool:
    current = _load_manager_settings()
    current.update(data)
    return safe_write_json(SETTINGS_FILE, current)


@manager_app.route("/")
def index():
    return render_template("dashboard.html", mimo_workspace=os.environ.get("AIDELINK_WORKSPACE_DIR", str(BASE_DIR)))


@manager_app.route("/settings", methods=["GET"])
def manager_get_settings():
    return jsonify({"settings": _load_manager_settings()})

@manager_app.route("/settings", methods=["POST"])
def manager_patch_settings():
    data = request.json or {}
    ok = _save_manager_settings(data)
    return jsonify({"ok": ok, "message": "Settings saved" if ok else "Failed to save"})


@manager_app.route("/api/status")
def api_status():
    from manager_process import get_service_status, get_system_info
    from network_utils import get_local_ip
    return jsonify({
        "service": get_service_status(),
        "system": get_system_info(),
        "manager_pid": os.getpid(),
        "local_ip": get_local_ip(),
    })


# ============================================================
# 注册所有 Blueprint
# ============================================================

from routes import register_all_routes
register_all_routes(manager_app)

# ============================================================
# 启动后台 Merge Daemon（自动测试 + git merge）
# 默认关闭：普通派发直接在用户当前项目目录执行，不依赖 worktree。
# ============================================================

if os.environ.get("AIDELINK_ENABLE_WORKTREE_MERGE", "").lower() in ("1", "true", "yes"):
    import merge_daemon
    merge_daemon.start()
    logger.info("Worktree merge daemon enabled")
else:
    logger.info("Worktree merge daemon disabled by default")
