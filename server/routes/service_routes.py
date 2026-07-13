import json
import os
import sys
import re
import time
import logging
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, send_from_directory
from paths import BRIDGE_DIR as BASE_DIR, PROJECT_ROOT, APK_PATH, APK_GRADLE_PATH, APK_METADATA_PATH
from version_utils import detect_app_version
from screen_control import is_screen_locked, wake_screen, ensure_screen_unlocked, get_screen_status

service_bp = Blueprint('service', __name__)

from json_utils import safe_read_json, safe_write_json
logger = logging.getLogger("AideLinkManager")


def _import_manager_utils():
    from manager_utils import FLASK_SERVICE_PORT
    return FLASK_SERVICE_PORT


def _import_service_helpers():
    from manager_process import (
        start_flask_service, stop_flask_service, restart_flask_service,
        get_service_status, get_flask_process
    )
    return start_flask_service, stop_flask_service, restart_flask_service, get_service_status, get_flask_process


def _import_bus():
    from event_bus import bus
    return bus


def get_apk_metadata():
    if APK_METADATA_PATH.exists():
        data = safe_read_json(APK_METADATA_PATH, None)
        if isinstance(data, dict) and "elements" in data and len(data["elements"]) > 0:
            elem = data["elements"][0]
            return {
                "versionCode": elem.get("versionCode", 0),
                "versionName": elem.get("versionName", "0.0.0")
            }
    return None


# ============================================================
# Service Management
# ============================================================

@service_bp.route("/api/service/start", methods=["POST"])
def api_service_start():
    """启动 Flask 服务"""
    start_flask_service, _, _, _, _ = _import_service_helpers()
    success, message = start_flask_service()
    return jsonify({"success": success, "message": message})


@service_bp.route("/api/service/stop", methods=["POST"])
def api_service_stop():
    """停止 Flask 服务"""
    _, stop_flask_service, _, _, _ = _import_service_helpers()
    success, message = stop_flask_service()
    return jsonify({"success": success, "message": message})


@service_bp.route("/api/service/restart", methods=["POST"])
def api_service_restart():
    """重启 Flask 服务"""
    _, _, restart_flask_service, _, _ = _import_service_helpers()
    success, message = restart_flask_service()
    return jsonify({"success": success, "message": message})


# ============================================================
# Version Management
# ============================================================

def get_gradle_version():
    import re
    gradle_path = Path(str(APK_GRADLE_PATH))
    if gradle_path.exists():
        try:
            content = gradle_path.read_text(encoding="utf-8")
            match = re.search(r'versionName\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1)
        except Exception:
            pass
    return None


@service_bp.route("/api/version", methods=["GET"])
def api_version():
    """获取当前版本号"""
    version = get_gradle_version()
    if version:
        # 同步回 version.json
        try:
            version_file = BASE_DIR / "version.json"
            data = safe_read_json(version_file, default={})
            if data.get("version") != version:
                data["version"] = version
                data["updated_at"] = datetime.now().isoformat()
                safe_write_json(version_file, data)
        except Exception:
            pass
        return jsonify({"success": True, "version": version})

    version_file = BASE_DIR / "version.json"
    try:
        data = safe_read_json(version_file, default={})
        if data:
            return jsonify({"success": True, "version": data.get("version", "0.0.0")})
        return jsonify({"success": True, "version": "0.0.0"})
    except Exception as e:
        return jsonify({"success": True, "version": "0.0.0"})


@service_bp.route("/api/status", methods=["GET"])
def api_status():
    """系统及服务状态统一接口 (带异常降级保护)"""
    try:
        from manager_process import get_service_status, get_system_info
        from network_utils import get_local_ip
        return jsonify({
            "service": get_service_status(),
            "system": get_system_info(),
            "manager_pid": os.getpid(),
            "local_ip": get_local_ip(),
        })
    except Exception as e:
        # 在 5000 网关桥接进程下运行时，由于没有 PySide/win32 UI 依赖，返回基础状态
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            local_ip = "127.0.0.1"

        return jsonify({
            "service": {"running": True, "pid": os.getpid(), "port": 5000},
            "system": {"cpu_percent": 0, "memory_percent": 0, "disk_percent": 0},
            "manager_pid": os.getpid(),
            "local_ip": local_ip,
            "standalone_gateway": True
        })




@service_bp.route("/api/version/bump", methods=["POST"])
def api_version_bump():
    """提升版本号（patch +1），同步更新 App build.gradle.kts 和 version.json"""
    current = detect_app_version()
    if not current:
        version_file = BASE_DIR / "version.json"
        current = "0.0.0"
        data = safe_read_json(version_file, default={})
        if data:
            current = data.get("version", "0.0.0")
        
    parts = current.split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2]) + 1
        if patch >= 10:
            patch = 0
            minor += 1
        if minor >= 10:
            minor = 0
            major += 1
        new_version = f"{major}.{minor}.{patch}"
    except (ValueError, IndexError):
        new_version = "0.0.1"

    gradle_path = Path(str(APK_GRADLE_PATH))
    gradle_updated = False
    if gradle_path.exists():
        try:
            content = gradle_path.read_text(encoding="utf-8")
            content, count_name = re.subn(r'(versionName\s*=\s*")[^"]+(")', f'\\g<1>{new_version}\\g<2>', content)
            
            code_match = re.search(r'versionCode\s*=\s*(\d+)', content)
            if code_match:
                new_code = int(code_match.group(1)) + 1
                content, count_code = re.subn(r'(versionCode\s*=\s*)\d+', f'\\g<1>{new_code}', content)
            
            gradle_path.write_text(content, encoding="utf-8")
            gradle_updated = True
        except Exception as e:
            logger.error(f"Failed to update build.gradle.kts: {e}")

    def _write_version_json(path):
        try:
            data = safe_read_json(path, default={})
            data["version"] = new_version
            data["updated_at"] = datetime.now().isoformat()
            safe_write_json(path, data)
        except Exception as e:
            logger.error(f"Failed to update {path}: {e}")

    _write_version_json(BASE_DIR / "version.json")
    _write_version_json(PROJECT_ROOT / "version.json")

    msg = f"版本号已提升至 v{new_version}"
    if gradle_updated:
        msg += " (已同步更新 App build.gradle.kts)"
    return jsonify({"success": True, "version": new_version, "message": msg})


# ============================================================
# Git Management
# ============================================================

@service_bp.route("/api/git/commit", methods=["POST"])
def api_git_commit():
    """快捷提交 Git"""
    data = request.get_json(force=True)
    msg = data.get("message", "").strip()
    if not msg:
        msg = "auto-commit from AideLink manager"
        
    try:
        add_proc = subprocess.run(["git", "add", "."], capture_output=True, text=True, cwd=str(BASE_DIR))
        if add_proc.returncode != 0:
            return jsonify({"success": False, "message": f"Git add 失败: {add_proc.stderr}"})
            
        commit_proc = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True, cwd=str(BASE_DIR))
        if commit_proc.returncode != 0:
            if "nothing to commit" in commit_proc.stdout.lower() or "nothing to commit" in commit_proc.stderr.lower():
                return jsonify({"success": True, "message": "暂无修改需要提交"})
            return jsonify({"success": False, "message": f"Git commit 失败: {commit_proc.stderr or commit_proc.stdout}"})
            
        return jsonify({"success": True, "message": f"Git 提交成功! {commit_proc.stdout.splitlines()[0] if commit_proc.stdout else ''}"})
    except Exception as e:
        return jsonify({"success": False, "message": f"运行 Git 命令异常: {e}"})


@service_bp.route("/api/git/generate-commit-msg", methods=["POST"])
def api_git_generate_commit_msg():
    """使用 Aide 根据当前的 git diff 自动生成提交日志"""
    try:
        # 获取当前未提交的变更（使用 --name-status 获取完整文件列表）
        diff_proc = subprocess.run(["git", "diff", "--name-status", "HEAD"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(BASE_DIR))
        diff_output = diff_proc.stdout.strip()
        
        # 获取详细 diff（用于理解具体变更内容，但限制长度避免 token 溢出）
        diff_detail_proc = subprocess.run(["git", "diff", "HEAD"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(BASE_DIR))
        diff_detail = diff_detail_proc.stdout.strip()
        
        # 也获取 untracked or staged files
        status_proc = subprocess.run(["git", "status", "-s"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(BASE_DIR))
        status_output = status_proc.stdout.strip()
        
        if not diff_output and not diff_detail and not status_output:
            return jsonify({"success": False, "message": "当前暂无修改，无需生成日志。"})
            
        # 汇总变更文件数量和状态
        changed_files = []
        if diff_output:
            for line in diff_output.splitlines():
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    status, path = parts
                    changed_files.append(f"[{status}] {path}")
        
        file_summary = f"共 {len(changed_files)} 个文件变更：\n" + "\n".join(changed_files) if changed_files else "无"
        
        from call_assistant import ask_assistant

        prompt = f"""
请根据以下 git 修改内容（包含文件变更列表和详细 diff），自动编写一个简洁、规范的 Git Commit Message 提交日志。

要求：
1. 提交日志应当使用中文，保持在一行以内，形式如：'feat: 添加 Aide 自动生成 Git 提交日志功能' 或 'fix: 修复任务列表未显示正确状态的问题'。
2. 不要包含任何 Markdown 格式、代码块标记、双引号或多余前缀，只输出这行纯文本 Commit Message 本身。
3. 请综合考虑所有变更文件，不要只关注部分文件。

【变更文件列表】
{file_summary}

【详细 Diff（部分）】
{diff_detail[:12000] if diff_detail else '无详细diff'}

【Git Status（未跟踪文件）】
{status_output if status_output else '无'}
"""
        sys_prompt = "你是一个专业的 Git 提交消息生成助手。只输出一行最精准简洁的纯文本提交消息。"
        
        result = ask_assistant(prompt, sys_prompt)
        # 清洗可能带有的引号或空白，并限制长度（Git规范建议72字符以内，最长100）
        clean_result = result.strip().strip('"').strip("'").strip('`')
        if len(clean_result) > 100:
            clean_result = clean_result[:100] + "..."
        return jsonify({"success": True, "commit_msg": clean_result})
    except Exception as e:
        logger.error(f"Failed to generate commit message automatically: {e}", exc_info=True)
        return jsonify({"success": False, "message": f"自动生成失败: {e}"})


# ============================================================
# Manager Restart
# ============================================================

def restart_manager_process():
    """强杀并重启整个程序（托盘 + Flask），与托盘右键「一键强杀重启」一致"""
    import sys
    import os
    import time

    print("[Manager] Force restarting all services...", flush=True)
    try:
        from manager_tray import main_window, tray_icon
        if main_window:
            main_window.hide()
    except Exception:
        pass

    try:
        from manager_tray import tray_icon
        if tray_icon:
            tray_icon.stop()
    except Exception:
        pass

    time.sleep(0.5)

    # 用 start_services.py 拉起完整服务（托盘 + Flask），与托盘菜单一致
    from paths import BRIDGE_DIR
    start_script = os.path.join(str(BRIDGE_DIR), "start_services.py")
    python = sys.executable
    subprocess.Popen(
        [python, start_script],
        cwd=str(BRIDGE_DIR),
        close_fds=True,
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else 0
    )
    os._exit(0)


@service_bp.route("/api/manager/restart", methods=["POST"])
def api_manager_restart():
    """热重启主程序"""
    threading.Thread(target=restart_manager_process).start()
    return jsonify({"success": True, "message": "正在重启管理器窗口..."})


# ============================================================
# App Version & Download
# ============================================================

@service_bp.route('/app/version', methods=['GET'])
@service_bp.route('/version', methods=['GET'])
def get_app_version():
    meta = get_apk_metadata()
    if meta:
        return jsonify({"ok": True, "versionCode": meta["versionCode"], "versionName": meta["versionName"]})
    else:
        return jsonify({"ok": False, "error": "未找到已编译的 APK 元数据，请先编译 App。"}), 404

@service_bp.route('/app/download', methods=['GET'])
@service_bp.route('/download', methods=['GET'])
def download_app():
    if APK_PATH.exists():
        directory = str(APK_PATH.parent)
        filename = APK_PATH.name
        return send_from_directory(directory, filename, as_attachment=True)
    else:
        return jsonify({"ok": False, "error": "未找到已编译的 APK 文件。"}), 404

@service_bp.route('/app/notify-update', methods=['POST'])
def notify_app_update():
    """推送应用更新通知到所有已连接的手机客户端"""
    meta = get_apk_metadata()
    if not meta:
        return jsonify({"ok": False, "error": "未找到 APK 元数据"}), 404
    bus = _import_bus()
    bus.publish("app.update_available", {
        "version_code": str(meta["versionCode"]),
        "version_name": meta["versionName"],
    })
    return jsonify({"ok": True, "message": f"已推送更新通知 v{meta['versionName']}"})


@service_bp.route('/api/test-notification', methods=['POST'])
def test_notification():
    from datetime import datetime
    bus = _import_bus()
    bus.publish("ide.notification", {
        "ide": "agy",
        "aumid": "Antigravity",
        "title": "🔔 测试通知 - AideLink",
        "body": "测试：您已经成功收到了这一条跨网络推送通知！",
        "arrival_time": datetime.now().isoformat(),
        "is_task_done": True,
        "notification_id": 999999
    })
    return jsonify({"ok": True, "message": "Test notification published"})


# ============================================================
# Screen Control
# ============================================================

@service_bp.route('/screen/status', methods=['GET'])
def screen_status():
    status = get_screen_status()
    return jsonify({
        "ok": True,
        **status
    })

@service_bp.route('/screen/settings', methods=['POST'])
def screen_settings():
    """更新屏幕唤醒设置"""
    try:
        from screen_control import load_screen_settings, save_screen_settings
        data = request.get_json() or {}
        settings = load_screen_settings()
        if "auto_skip_lock" in data:
            settings["auto_skip_lock"] = bool(data["auto_skip_lock"])
        save_screen_settings(settings)
        return jsonify({"ok": True, "settings": settings})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

@service_bp.route('/screen/wake', methods=['POST'])
def api_wake_screen():
    result = wake_screen()
    ok = result.get("ok", False) if isinstance(result, dict) else result
    if ok:
        locked = is_screen_locked()
        if locked:
            time.sleep(0.5)
            wake_screen()
    return jsonify({
        "ok": ok,
        "woke": ok,
        "locked_after": is_screen_locked() if ok else None
    })

@service_bp.route('/screen/ensure-unlocked', methods=['POST'])
def api_ensure_unlocked():
    result = ensure_screen_unlocked()
    return jsonify({
        "ok": True,
        "was_locked": result,
        "locked_now": is_screen_locked()
    })
