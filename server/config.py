import os
import json
import threading
from defaults import DEFAULT_BRIDGE_URL, DEFAULT_WOL_MAC, DEFAULT_OPENCODE_WEB_PORT
from paths import BRIDGE_DIR, SETTINGS_FILE

file_lock = threading.Lock()

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_URL = os.environ.get("MINIMAX_URL", "https://api.minimax.chat/v1/chat/completions")

SYSTEM_PROMPT = """你是一个部署在本地开发环境的"智能秘书代理"（Assistant Proxy）。
你的工作是协助手机端的用户，与电脑上正在运行的"主力开发智能体"进行沟通 and 进度同步。
"""

SETTINGS_SCHEMA = {
    "server_url": {"type": "string", "default": DEFAULT_BRIDGE_URL},
    "wol_mac":    {"type": "string", "default": DEFAULT_WOL_MAC},
    "app_language":     {"type": "string",  "default": "system"},
    "app_theme":        {"type": "string",  "default": "system"},
    "dynamic_color":    {"type": "boolean", "default": True},
    "notifications_enabled": {"type": "boolean", "default": True},
    "haptic_feedback":       {"type": "boolean", "default": True},
    "monitor_interval_ms": {"type": "integer", "default": 4000},
    "monitor_height_dp":   {"type": "integer", "default": 420},
    "xiaomengling_model": {"type": "string", "default": "free"},
    "desktop_ide": {"type": "string", "default": "auto"},
    "desktop_ide_path": {"type": "string", "default": ""},
    "opencode_web_urls": {"type": "object", "default": {"lan": "", "frp": ""}},
    "opencode_web_mode": {"type": "string", "default": "auto"},
    "opencode_web_connection": {"type": "string", "default": "lan"},
    "opencode_web_password": {"type": "string", "default": ""},
    "opencode_web_username": {"type": "string", "default": ""},
    "opencode_web_port": {"type": "integer", "default": DEFAULT_OPENCODE_WEB_PORT},
    "project_dir": {"type": "string", "default": ""},
    "projects": {"type": "list", "default": []},
    "current_project": {"type": "string", "default": ""},
    # 新设备不应假设仓库内存在作者的 Android 项目；已有配置仍保留原值。
    "app_project_name": {"type": "string", "default": ""},
}


def normalize_project_path(path: str) -> str:
    """Keep target project paths in Windows display form across clients."""
    if not isinstance(path, str):
        return ""
    path = path.strip()
    if not path:
        return ""
    return os.path.normpath(path).replace("/", "\\")


def project_path_key(path: str) -> str:
    normalized = normalize_project_path(path)
    return os.path.normcase(normalized).rstrip("\\")


def normalize_project_settings(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    data = dict(data)
    if "project_dir" in data:
        data["project_dir"] = normalize_project_path(data.get("project_dir", ""))
    if "current_project" in data:
        data["current_project"] = normalize_project_path(data.get("current_project", ""))

    projects = data.get("projects", [])
    if isinstance(projects, list):
        normalized_projects = []
        seen = set()
        for item in projects:
            if not isinstance(item, dict):
                continue
            project_path = normalize_project_path(item.get("path", ""))
            if not project_path:
                continue
            key = project_path_key(project_path)
            if key in seen:
                continue
            seen.add(key)
            normalized_item = dict(item)
            normalized_item["path"] = project_path
            normalized_item["name"] = normalized_item.get("name") or os.path.basename(project_path)
            normalized_projects.append(normalized_item)
        data["projects"] = normalized_projects
    return data


def load_settings() -> dict:
    from json_utils import safe_read_json
    defaults = {k: v["default"] for k, v in SETTINGS_SCHEMA.items()}
    if not os.path.exists(SETTINGS_FILE):
        return defaults
    try:
        with file_lock:
            data = safe_read_json(SETTINGS_FILE, defaults)
        # 兼容迁移：旧 opencode_project_dir → 新 project_dir / current_project
        if "opencode_project_dir" in data and "project_dir" not in data:
            data["project_dir"] = data["opencode_project_dir"]
        data = normalize_project_settings(data)
        # 迁移 project_dir → current_project + projects 列表
        pd = data.get("project_dir", "")
        cp = data.get("current_project", "")
        projs = data.get("projects", [])
        if pd and not cp:
            data["current_project"] = pd
            if not any(project_path_key(p.get("path", "")) == project_path_key(pd) for p in projs):
                import os as _os
                data["projects"] = projs + [{"path": pd, "name": _os.path.basename(pd), "last_used": ""}]
        elif cp and not pd:
            data["project_dir"] = cp
        elif cp and pd and project_path_key(cp) != project_path_key(pd):
            data["project_dir"] = cp
        data = normalize_project_settings(data)
        clean = {}
        for k, meta in SETTINGS_SCHEMA.items():
            v = data.get(k, meta["default"])
            t = meta["type"]
            if t == "boolean" and not isinstance(v, bool):
                v = meta["default"]
            elif t == "integer" and not isinstance(v, int):
                v = meta["default"]
            elif t == "string" and not isinstance(v, str):
                v = meta["default"]
            elif t == "object" and not isinstance(v, dict):
                v = meta["default"]
            elif t == "list" and not isinstance(v, list):
                v = meta["default"]
            clean[k] = v
        return clean
    except Exception:
        return defaults


def save_settings(data: dict) -> bool:
    from json_utils import safe_write_json
    data = normalize_project_settings(data)
    clean = {}
    for k, meta in SETTINGS_SCHEMA.items():
        if k not in data:
            continue
        v = data[k]
        if meta["type"] == "boolean" and not isinstance(v, bool):
            continue
        if meta["type"] == "integer" and not isinstance(v, int):
            continue
        if meta["type"] == "string" and not isinstance(v, str):
            continue
        if meta["type"] == "object" and not isinstance(v, dict):
            continue
        if meta["type"] == "list" and not isinstance(v, list):
            continue
        clean[k] = v
    return safe_write_json(SETTINGS_FILE, clean)
