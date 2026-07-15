import os
import json
from pathlib import Path
from flask import Blueprint, request, jsonify, send_from_directory
from paths import BRIDGE_DIR as BASE_DIR
from config import (
    load_settings as _load_settings,
    normalize_project_path,
    project_path_key,
    save_settings as _save_settings,
    SETTINGS_SCHEMA,
)
from android_project import inspect_android_project

config_bp = Blueprint('config', __name__)


def _import_manager_utils():
    from manager_utils import load_config, save_config, get_sessions, get_chat_history
    return load_config, save_config, get_sessions, get_chat_history


# ============================================================
# Sessions & Chat History
# ============================================================

@config_bp.route("/api/sessions")
def api_sessions():
    """返回 IDE 会话列表"""
    _, _, get_sessions, _ = _import_manager_utils()
    return jsonify({"sessions": get_sessions()})


@config_bp.route("/sessions")
def legacy_sessions():
    """旧 Android 客户端兼容：返回裸 sessions 数组。"""
    _, _, get_sessions, _ = _import_manager_utils()
    return jsonify(get_sessions())


@config_bp.route("/api/chat/history")
def api_chat_history():
    """返回聊天历史"""
    _, _, _, get_chat_history = _import_manager_utils()
    limit = request.args.get("limit", 100, type=int)
    return jsonify({"history": get_chat_history(limit)})


# ============================================================
# Config
# ============================================================

@config_bp.route("/api/config", methods=["GET"])
def api_config_get():
    """返回当前配置"""
    load_config, _, _, _ = _import_manager_utils()
    return jsonify({"config": load_config()})


@config_bp.route("/api/config", methods=["POST"])
def api_config_post():
    """更新配置"""
    _, save_config, _, _ = _import_manager_utils()
    data = request.get_json(force=True)
    success, message = save_config(data)
    return jsonify({"success": success, "message": message})


# ============================================================
# Settings
# ============================================================

@config_bp.route('/settings', methods=['GET'])
def get_settings():
    return jsonify({"settings": _load_settings(), "schema": SETTINGS_SCHEMA})

@config_bp.route('/settings', methods=['PUT'])
def update_settings():
    data = request.json or {}
    if _save_settings(data):
        return jsonify({"ok": True, "message": "Settings saved"})
    return jsonify({"ok": False, "message": "Failed to save settings"}), 500

@config_bp.route('/settings', methods=['POST'])
def patch_settings():
    data = request.json or {}
    current = _load_settings()
    current.update(data)
    if _save_settings(current):
        return jsonify({"ok": True, "message": "Settings patched"})
    return jsonify({"ok": False, "message": "Failed to patch settings"}), 500

@config_bp.route('/settings.html', methods=['GET'])
def settings_page():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "settings.html")


# ============================================================
# Active Models
# ============================================================

@config_bp.route('/api/active-models', methods=['GET'])
def get_active_models():
    import model_registry
    models = model_registry.get_active_models()
    return jsonify({
        "models": [
            {"key": k, "description": v.get("description", k)}
            for k, v in models.items()
        ]
    })


# ============================================================
# Desktop IDEs
# ============================================================

@config_bp.route('/api/desktop-ides', methods=['GET'])
def get_desktop_ides():
    import ide_scanner
    from ide_profiles import enrich_ides
    ides = ide_scanner.get_all_ides()
    # 只有 web 型条目时，说明本地桌面 IDE 缓存可能是空的；
    # 这时补一次真实扫描，避免页面只剩 MiniMax Code。
    has_desktop_ide = any(ide.get("type") != "web" for ide in ides)
    # 已有扫描缓存（即使用户刚删除后为空）时不要立即重新扫描，
    # 否则删除的 IDE 会在页面刷新时立刻回来。
    scanned_cache_exists = os.path.exists(str(ide_scanner.SCANNED_IDES_FILE))
    if not has_desktop_ide and not scanned_cache_exists:
        ides = ide_scanner.scan_installed_ides()
    return jsonify({"ides": enrich_ides(ides)})

@config_bp.route('/api/scan-ides', methods=['POST'])
def scan_ides():
    import ide_scanner
    from ide_profiles import enrich_ides
    ides = ide_scanner.scan_installed_ides()
    return jsonify({
        "success": True,
        "message": f"扫描完成，发现 {len(ides)} 个 IDE",
        "ides": enrich_ides(ides),
        "count": len(ides),
    })

@config_bp.route('/api/manual-ides', methods=['GET'])
def get_manual_ides():
    import ide_scanner
    ides = ide_scanner.load_manual_ides()
    return jsonify({"ides": ides})

@config_bp.route('/api/manual-ides', methods=['POST'])
def add_manual_ide():
    import ide_scanner
    data = request.json or {}
    key = data.get("key", "").strip()
    name = data.get("name", "").strip()
    path = data.get("path", "").strip()
    if not key or not name:
        return jsonify({"ok": False, "message": "缺少 key 或 name"}), 400
    exe_key = ide_scanner._generic_exe_key(path) if path else key
    ide = {"key": key, "name": name, "path": path, "exe_key": exe_key, "source": "manual"}
    ide_scanner.add_manual_ide(ide)
    return jsonify({"ok": True, "message": "已保存"})

@config_bp.route('/api/manual-ides', methods=['DELETE'])
def delete_manual_ide():
    import ide_scanner
    data = request.json or {}
    key = data.get("key", "").strip()
    if not key:
        return jsonify({"ok": False, "message": "缺少 key"}), 400
    ide_scanner.remove_manual_ide(key)
    return jsonify({"ok": True, "message": "已删除"})

@config_bp.route('/api/desktop-ides/<key>', methods=['DELETE'])
def delete_desktop_ide(key):
    """删除扫描/手动 IDE 的本地条目，不删除内置注册表模板。"""
    import ide_scanner
    key = (key or "").strip()
    if not key:
        return jsonify({"ok": False, "message": "缺少 key"}), 400
    removed = ide_scanner.remove_scanned_ide(key) or bool(ide_scanner.remove_manual_ide(key))
    return jsonify({"ok": True, "removed": removed, "message": "已删除本地 IDE 条目"})


@config_bp.route('/api/desktop-ides/rename', methods=['POST'])
def rename_desktop_ide_key():
    import ide_scanner
    data = request.json or {}
    old_key = data.get("key", "").strip()
    new_key = data.get("new_key", "").strip()
    if not old_key or not new_key:
        return jsonify({"ok": False, "message": "缺少旧 key 或新 key"}), 400
    ok, message = ide_scanner.rename_ide_key(old_key, new_key)
    if ok:
        return jsonify({"ok": True, "message": message})
    return jsonify({"ok": False, "message": message}), 400


# ============================================================
# Browse Path (Windows native file dialog)
# ============================================================

def _resolve_windows_shortcut(path):
    """将桌面 .lnk 解析为真实目标；解析失败时保留原路径。"""
    if not path.lower().endswith(".lnk"):
        return path
    try:
        import subprocess
        escaped = path.replace("'", "''")
        script = "$s=New-Object -ComObject WScript.Shell; $s.CreateShortcut('" + escaped + "').TargetPath"
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        target = (result.stdout or "").strip()
        if target and os.path.isfile(target):
            return target
    except Exception:
        pass
    return path

@config_bp.route('/api/browse-path', methods=['POST'])
def browse_path():
    if os.name != 'nt':
        return jsonify({"ok": False, "message": "仅 Windows 支持"}), 400
    data = request.json or {}
    title = data.get("title") or "选择文件"
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    start_dir = data.get("start_dir") or (desktop if os.path.isdir(desktop) else os.path.expanduser("~"))
    # Embeddable Python does not ship tkinter. Use the native Windows picker
    # and hide the helper console window.
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        import subprocess
        ps = ("Add-Type -AssemblyName System.Windows.Forms; "
              "$d=New-Object System.Windows.Forms.OpenFileDialog; "
              f"$d.Title={title!r}; $d.InitialDirectory={start_dir!r}; "
              "$d.Filter='IDE入口|*.lnk;*.exe;*.cmd;*.bat|所有文件|*.*'; "
              "if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){$d.FileName}")
        try:
            si = subprocess.STARTUPINFO(); si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-WindowStyle", "Hidden", "-Command", ps], capture_output=True, text=True, timeout=120, startupinfo=si, creationflags=subprocess.CREATE_NO_WINDOW)
            path = (result.stdout or "").strip()
            resolved = _resolve_windows_shortcut(path) if path else path
            return jsonify({"ok": bool(path), "path": resolved, "selected_path": path, "cancelled": not bool(path), "message": "未选择文件" if not path else ""})
        except Exception as exc:
            return jsonify({"ok": False, "message": f"无法打开 Windows 文件选择器: {exc}"}), 500

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(
            title=title,
            initialdir=start_dir,
            filetypes=[("IDE入口", "*.lnk *.exe *.cmd *.bat"), ("所有文件", "*.*")],
        )
        try:
            root.destroy()
        except Exception:
            pass
        if not path:
            return jsonify({"ok": False, "cancelled": True, "message": "用户取消"})
        resolved = _resolve_windows_shortcut(path)
        return jsonify({"ok": True, "path": resolved, "selected_path": path, "message": "已选择"})
    except Exception as e:
        return jsonify({"ok": False, "message": f"打开对话框失败: {e}"}), 500


# ============================================================
# Projects (目标项目列表)
# ============================================================

@config_bp.route('/api/projects', methods=['GET'])
def get_projects():
    settings = _load_settings()
    projects = []
    for project in settings.get("projects", []):
        enriched = dict(project)
        enriched["android"] = inspect_android_project(project.get("path", ""))
        projects.append(enriched)
    return jsonify({
        "projects": projects,
        "current_project": settings.get("current_project", ""),
    })


@config_bp.route('/api/projects', methods=['POST'])
def add_project():
    data = request.json or {}
    path = normalize_project_path(data.get("path", ""))
    if not path:
        return jsonify({"ok": False, "message": "缺少 path"}), 400
    if not os.path.isdir(path):
        return jsonify({"ok": False, "message": f"路径不存在或不是目录: {path}"}), 400
    settings = _load_settings()
    projects = settings.get("projects", [])
    if any(project_path_key(p.get("path", "")) == project_path_key(path) for p in projects):
        return jsonify({"ok": False, "message": "项目已存在"})
    name = os.path.basename(path)
    projects.append({"path": path, "name": name, "last_used": ""})
    settings["projects"] = projects
    _save_settings(settings)
    return jsonify({"ok": True, "projects": projects, "android": inspect_android_project(path)})


@config_bp.route('/api/projects/<int:idx>', methods=['DELETE'])
def delete_project(idx):
    settings = _load_settings()
    projects = settings.get("projects", [])
    if idx < 0 or idx >= len(projects):
        return jsonify({"ok": False, "message": "索引越界"}), 400
    removed = projects.pop(idx)
    settings["projects"] = projects
    # 如果删除的是当前项目，清空 current_project
    if project_path_key(settings.get("current_project", "")) == project_path_key(removed.get("path", "")):
        # Keep a usable current project when removing the active entry.
        settings["current_project"] = projects[0].get("path", "") if projects else ""
        settings["project_dir"] = settings["current_project"]
    _save_settings(settings)
    return jsonify({"ok": True, "projects": projects})


@config_bp.route('/api/projects/select', methods=['POST'])
def select_project():
    data = request.json or {}
    path = normalize_project_path(data.get("path", ""))
    if not path:
        return jsonify({"ok": False, "message": "缺少 path"}), 400
    if not os.path.isdir(path):
        return jsonify({"ok": False, "message": "路径不存在"}), 400
    settings = _load_settings()
    projects = settings.get("projects", [])
    if not any(project_path_key(p.get("path", "")) == project_path_key(path) for p in projects):
        name = os.path.basename(path)
        projects.append({"path": path, "name": name, "last_used": ""})
        settings["projects"] = projects
    settings["current_project"] = path
    settings["project_dir"] = path
    _save_settings(settings)

    # 触发项目地图扫描
    try:
        import project_scanner
        project_scanner.scan_and_save()
    except Exception as e:
        print(f"[select_project] scan failed: {e}", flush=True)

    # 广播 SSE 通知
    try:
        from routes.project_routes import _broadcast_sse
        _broadcast_sse({
            "type": "project_changed",
            "path": path,
            "name": os.path.basename(path),
        })
    except Exception:
        pass

    return jsonify({
        "ok": True,
        "current_project": path,
        "name": os.path.basename(path),
        "android": inspect_android_project(path),
    })


@config_bp.route('/api/projects/android/scan', methods=['POST'])
def scan_android_project():
    data = request.json or {}
    path = normalize_project_path(data.get("path", ""))
    if not path:
        path = _load_settings().get("current_project", "")
    if not path or not os.path.isdir(path):
        return jsonify({"ok": False, "message": "目标项目路径不存在"}), 400
    return jsonify({"ok": True, "path": path, "android": inspect_android_project(path)})


@config_bp.route('/api/browse-folder', methods=['POST'])
def browse_folder():
    if os.name != 'nt':
        return jsonify({"ok": False, "message": "仅 Windows 支持"}), 400
    data = request.json or {}
    start_dir = data.get("start_dir") or os.path.expanduser("~")
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        # Embeddable Python intentionally omits tkinter. Use the native Windows
        # dialog instead of forcing users to type a path manually.
        import subprocess
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$d=New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$d.Description='选择项目文件夹'; "
            f"$d.SelectedPath={start_dir!r}; "
            "if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){$d.SelectedPath}"
        )
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-STA", "-WindowStyle", "Hidden", "-Command", ps],
                capture_output=True, text=True, timeout=120,
                startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            path = (result.stdout or "").strip()
            if path and not os.path.isdir(path):
                path = ""
            return jsonify({"ok": bool(path), "path": path, "message": "未选择项目文件夹" if not path else ""})
        except Exception as exc:
            return jsonify({"ok": False, "message": f"无法打开 Windows 文件夹选择器: {exc}"}), 500

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askdirectory(
            title="选择项目文件夹",
            initialdir=start_dir,
        )
        try:
            root.destroy()
        except Exception:
            pass
        if not path:
            return jsonify({"ok": False, "cancelled": True, "message": "用户取消"})
        return jsonify({"ok": True, "path": path})
    except Exception as e:
        return jsonify({"ok": False, "message": f"打开对话框失败: {e}"}), 500
