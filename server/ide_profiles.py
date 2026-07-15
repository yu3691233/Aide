"""Versioned, independently updateable behavior profiles for desktop IDEs."""

import os
import re
import subprocess
import json
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

from json_utils import safe_read_json, safe_write_json
from paths import BRIDGE_DIR, STATE_DIR


DEFAULT_PROFILES_DIR = BRIDGE_DIR / "defaults" / "ide_profiles"
INSTALLED_PROFILES_DIR = STATE_DIR / "ide_profiles"
PROFILE_BASE_URL = os.environ.get(
    "AIDELINK_IDE_PROFILE_BASE_URL",
    "https://raw.githubusercontent.com/yu3691233/Aide/main/server/defaults/ide_profiles",
).rstrip("/")
MAX_PROFILE_BYTES = 256 * 1024

ALLOWED_CAPABILITIES = {
    "launch",
    "open_project",
    "stop",
    "bind_window",
    "calibrate",
    "install_mcp",
    "profile_update",
    "history",
}
GENERIC_CAPABILITIES = [
    "launch",
    "stop",
    "bind_window",
    "calibrate",
    "install_mcp",
    "profile_update",
]


class IdeProfileError(ValueError):
    pass


def _profile_path(directory: Path, key: str) -> Path:
    return directory / f"{key}.json"


def _normalize_key(key: str) -> str:
    value = str(key or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise IdeProfileError("IDE key 格式无效")
    return value


def _version_tuple(value: str):
    parts = re.findall(r"\d+", str(value or ""))
    return tuple(int(item) for item in parts[:4]) or (0,)


def validate_profile(data, expected_key=None):
    if not isinstance(data, dict):
        raise IdeProfileError("IDE 适配配置必须是 JSON 对象")
    key = _normalize_key(data.get("key"))
    if expected_key and key != _normalize_key(expected_key):
        raise IdeProfileError("IDE 适配配置 key 与请求不一致")
    if data.get("schema_version") != 1:
        raise IdeProfileError("不支持的 IDE 适配配置 schema_version")
    version = str(data.get("version") or "").strip()
    if not re.fullmatch(r"\d+(?:\.\d+){0,3}", version):
        raise IdeProfileError("IDE 适配配置 version 格式无效")

    capabilities = data.get("capabilities", [])
    if not isinstance(capabilities, list):
        raise IdeProfileError("capabilities 必须是数组")
    capabilities = list(dict.fromkeys(str(item) for item in capabilities))
    unknown = set(capabilities) - ALLOWED_CAPABILITIES
    if unknown:
        raise IdeProfileError(f"不支持的 IDE 能力: {', '.join(sorted(unknown))}")

    launch = data.get("launch", {})
    if not isinstance(launch, dict):
        raise IdeProfileError("launch 必须是对象")
    launch_mode = launch.get("mode", "executable")
    if launch_mode not in {"executable", "appx"}:
        raise IdeProfileError("launch.mode 仅支持 executable/appx")
    if launch_mode == "appx" and not str(launch.get("aumid") or "").strip():
        raise IdeProfileError("AppX 启动配置缺少 aumid")

    project = data.get("project", {"mode": "none"})
    if not isinstance(project, dict):
        raise IdeProfileError("project 必须是对象")
    project_mode = project.get("mode", "none")
    if project_mode not in {"none", "argument", "uri"}:
        raise IdeProfileError("project.mode 仅支持 none/argument/uri")
    if project_mode == "uri":
        template = str(project.get("template") or "")
        if "{project_uri}" not in template:
            raise IdeProfileError("URI 项目模板必须包含 {project_uri}")
        scheme = urlparse(template.replace("{project_uri}", "x")).scheme
        if not scheme:
            raise IdeProfileError("URI 项目模板缺少协议")

    history = data.get("history", {"mode": "none"})
    if not isinstance(history, dict):
        raise IdeProfileError("history 必须是对象")
    history_mode = history.get("mode", "none")
    if history_mode not in {"none", "codex_session_index"}:
        raise IdeProfileError("history.mode 不受支持")
    if history_mode == "codex_session_index":
        template = str(history.get("open_template") or "")
        if "{thread_id}" not in template or urlparse(template.replace("{thread_id}", "test")).scheme != "codex":
            raise IdeProfileError("Codex 历史会话配置缺少有效的 open_template")

    normalized = dict(data)
    normalized.update({
        "schema_version": 1,
        "key": key,
        "version": version,
        "display_name": str(data.get("display_name") or key),
        "capabilities": capabilities,
        "launch": dict(launch),
        "project": dict(project),
        "history": dict(history),
    })
    return normalized


def _generic_profile(key):
    return {
        "schema_version": 1,
        "key": _normalize_key(key),
        "version": "0.0.0",
        "display_name": key,
        "capabilities": list(GENERIC_CAPABILITIES),
        "launch": {"mode": "executable"},
        "project": {"mode": "none"},
        "history": {"mode": "none"},
        "source": "generic",
    }


def load_profile(key):
    key = _normalize_key(key)
    candidates = [
        ("installed", _profile_path(INSTALLED_PROFILES_DIR, key)),
        ("bundled", _profile_path(DEFAULT_PROFILES_DIR, key)),
    ]
    valid_profiles = []
    for source, path in candidates:
        data = safe_read_json(path, None)
        try:
            profile = validate_profile(data, expected_key=key)
            profile["source"] = source
            valid_profiles.append(profile)
        except IdeProfileError:
            continue
    if valid_profiles:
        return max(
            valid_profiles,
            key=lambda item: (_version_tuple(item["version"]), item["source"] == "installed"),
        )
    return _generic_profile(key)


def profile_summary(key):
    profile = load_profile(key)
    return {
        "profile_version": profile["version"],
        "profile_source": profile["source"],
        "capabilities": profile["capabilities"],
    }


def enrich_ides(ides):
    result = []
    for ide in ides:
        item = dict(ide)
        if item.get("type", "desktop") != "web":
            item.update(profile_summary(item.get("key", "")))
        result.append(item)
    return result


def update_profile(key, force=False, base_url=None):
    key = _normalize_key(key)
    url = f"{(base_url or PROFILE_BASE_URL).rstrip('/')}/{quote(key)}.json"
    if urlparse(url).scheme != "https":
        raise IdeProfileError("IDE 适配更新源必须使用 HTTPS")
    response = requests.get(url, timeout=(5, 15), headers={"Accept": "application/json"})
    response.raise_for_status()
    if len(response.content) > MAX_PROFILE_BYTES:
        raise IdeProfileError("IDE 适配配置超过大小限制")
    profile = validate_profile(response.json(), expected_key=key)
    current = load_profile(key)
    if not force and _version_tuple(profile["version"]) <= _version_tuple(current["version"]):
        return False, current, "当前已是最新适配配置"
    INSTALLED_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    if not safe_write_json(_profile_path(INSTALLED_PROFILES_DIR, key), profile):
        raise IdeProfileError("IDE 适配配置写入失败")
    saved = load_profile(key)
    return True, saved, f"{key} 适配配置已更新到 {saved['version']}"


def _creation_flags():
    if os.name != "nt":
        return 0
    return subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW


def launch_ide(profile, ide_info):
    launch = profile.get("launch", {})
    if launch.get("mode") == "appx":
        target = f"shell:AppsFolder\\{launch['aumid']}"
        subprocess.Popen(
            ["explorer.exe", target],
            creationflags=_creation_flags(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return target
    ide_path = str(ide_info.get("path") or "")
    if not ide_path:
        raise IdeProfileError("未找到 IDE 安装路径")
    subprocess.Popen(
        [ide_path],
        creationflags=_creation_flags(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return ide_path


def open_project(profile, ide_info, project_path):
    project = profile.get("project", {})
    mode = project.get("mode", "none")
    if mode == "uri":
        template = str(project.get("template") or "")
        target = template.format(project_uri=quote(str(project_path), safe=""))
        if os.name != "nt" or not hasattr(os, "startfile"):
            raise IdeProfileError("URI 项目切换当前仅支持 Windows")
        os.startfile(target)  # type: ignore[attr-defined]
        return target
    if mode == "argument":
        ide_path = str(ide_info.get("path") or "")
        if not ide_path:
            raise IdeProfileError("未找到 IDE 安装路径")
        subprocess.Popen(
            [ide_path, str(project_path)],
            creationflags=_creation_flags(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return str(project_path)
    raise IdeProfileError(f"{profile.get('display_name', profile.get('key'))} 暂不支持切换项目")


def list_history(profile, limit=30):
    history = profile.get("history", {})
    if history.get("mode") != "codex_session_index":
        raise IdeProfileError("当前 IDE 适配配置不支持历史会话")
    index_path = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")) / "session_index.jsonl"
    if not index_path.is_file():
        return []

    items = {}
    with index_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except (TypeError, ValueError):
                continue
            thread_id = str(item.get("id") or "").strip().lower()
            if not re.fullmatch(r"[0-9a-f-]{20,64}", thread_id):
                continue
            items[thread_id] = {
                "id": thread_id,
                "title": str(item.get("thread_name") or "未命名会话").strip() or "未命名会话",
                "updated_at": str(item.get("updated_at") or ""),
            }
    return sorted(items.values(), key=lambda item: item["updated_at"], reverse=True)[:max(1, min(int(limit), 100))]


def open_history(profile, thread_id):
    history = profile.get("history", {})
    if history.get("mode") != "codex_session_index":
        raise IdeProfileError("当前 IDE 适配配置不支持历史会话")
    thread_id = str(thread_id or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f-]{20,64}", thread_id):
        raise IdeProfileError("历史会话 ID 格式无效")
    target = str(history.get("open_template") or "").format(thread_id=thread_id)
    if urlparse(target).scheme != "codex":
        raise IdeProfileError("历史会话链接协议无效")
    if os.name != "nt" or not hasattr(os, "startfile"):
        raise IdeProfileError("历史会话跳转当前仅支持 Windows")
    os.startfile(target)  # type: ignore[attr-defined]
    return target
