"""
IDE 扫描器 —— 从 ide_registry.json 读取配置，检测本机已安装的桌面 IDE
"""

import os
import struct
import ctypes
import fnmatch
import glob
import subprocess
from ctypes import byref, create_string_buffer, c_char_p, c_uint, string_at
from json_utils import safe_read_json, safe_write_json
from paths import BRIDGE_DIR as BASE_DIR, REGISTRY_FILE, DEFAULT_REGISTRY_FILE, MANUAL_IDES_FILE, SCANNED_IDES_FILE, IDE_ROLES_FILE, IDE_ALIASES_FILE


def _normalize_ide_key(key):
    return (key or "").strip().lower()


def load_registry():
    """加载 IDE 注册表；全新安装时从受版本控制的默认模板初始化。"""
    registry = safe_read_json(REGISTRY_FILE, default={})
    if isinstance(registry, dict) and registry:
        return registry
    defaults = safe_read_json(DEFAULT_REGISTRY_FILE, default={})
    if isinstance(defaults, dict) and defaults:
        save_registry(defaults)
        return defaults
    return {}


def save_registry(registry):
    """保存 IDE 注册表"""
    return safe_write_json(REGISTRY_FILE, registry)


def add_registry_ide(key, config):
    """添加/更新注册表中的 IDE"""
    registry = load_registry()
    registry[key] = config
    return save_registry(registry)


def remove_registry_ide(key):
    """从注册表删除 IDE"""
    registry = load_registry()
    if key in registry:
        del registry[key]
        return save_registry(registry)
    return True


def _rename_mapping_key(mapping, old_key, new_key):
    """把字典里指定的 key 改名。"""
    if not isinstance(mapping, dict) or old_key not in mapping:
        return False
    mapping[new_key] = mapping.pop(old_key)
    return True


def _rename_nested_mapping_keys(value, old_key, new_key):
    """递归重命名 JSON 对象里的字典 key。"""
    changed = False
    if isinstance(value, dict):
        if old_key in value:
            value[new_key] = value.pop(old_key)
            changed = True
        for item in value.values():
            changed = _rename_nested_mapping_keys(item, old_key, new_key) or changed
    elif isinstance(value, list):
        for item in value:
            changed = _rename_nested_mapping_keys(item, old_key, new_key) or changed
    return changed


def _replace_ide_values(value, old_key, new_key, field_names=None):
    """递归把指定字段中的旧 key 值替换为新 key。"""
    field_names = field_names or {"key", "ide", "ide_key", "target_ide", "desktop_ide"}
    changed = False
    if isinstance(value, dict):
        for field, item in list(value.items()):
            if field in field_names and item == old_key:
                value[field] = new_key
                changed = True
            else:
                changed = _replace_ide_values(item, old_key, new_key, field_names) or changed
    elif isinstance(value, list):
        for item in value:
            changed = _replace_ide_values(item, old_key, new_key, field_names) or changed
    return changed


def _rename_state_file(prefix, old_key, new_key, suffix=".json"):
    old_path = os.path.join(BASE_DIR, "state", f"{prefix}{old_key}{suffix}")
    new_path = os.path.join(BASE_DIR, "state", f"{prefix}{new_key}{suffix}")
    if os.path.exists(old_path) and old_path != new_path:
        if os.path.exists(new_path):
            return False
        try:
            os.replace(old_path, new_path)
            return True
        except Exception:
            return False
    return False


def _find_exe(directory, pattern):
    """在目录中查找 exe 或 cmd 文件"""
    if not os.path.isdir(directory):
        return None
    pattern_lower = pattern.lower()
    has_wildcard = any(ch in pattern_lower for ch in "*?[]")

    def _matches(filename: str) -> bool:
        name = filename.lower()
        if not (name.endswith(".exe") or name.endswith(".cmd")):
            return False
        if has_wildcard:
            return fnmatch.fnmatch(name, pattern_lower)
        return pattern_lower in name

    for item in os.listdir(directory):
        if _matches(item):
            return os.path.join(directory, item)
    for root, dirs, files in os.walk(directory):
        depth = root.replace(directory, "").count(os.sep)
        if depth > 2:
            dirs.clear()
            continue
        for f in files:
            if _matches(f):
                return os.path.join(root, f)
    return None


def _expand_scan_paths(path_template):
    """展开扫描路径模板，兼容普通目录和带通配符的目录。"""
    expanded = os.path.expandvars(path_template)
    if any(ch in expanded for ch in "*?[]"):
        matches = [p for p in glob.glob(expanded) if os.path.isdir(p)]
        if matches:
            return matches
    return [expanded]


def _probe_command_exe(command_name):
    """通过系统命令查找可执行文件路径，作为注册表扫描的兜底。"""
    try:
        result = subprocess.run(
            ["where.exe", command_name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            line = line.strip().strip('"')
            if line.lower().endswith(".exe") and os.path.exists(line):
                return line
    except Exception:
        pass
    return None


def _probe_codex_desktop_exe():
    """查找 Codex 桌面的 ChatGPT.exe，而不是其无界面的 codex.exe 后端。"""
    try:
        import psutil
        for proc in psutil.process_iter(["name", "exe"]):
            info = proc.info
            exe = info.get("exe") or ""
            if (info.get("name") or "").lower() == "chatgpt.exe" and os.path.isfile(exe):
                return exe
    except Exception:
        pass
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    pattern = os.path.join(program_files, "WindowsApps", "OpenAI.Codex_*", "app", "ChatGPT.exe")
    matches = [path for path in glob.glob(pattern) if os.path.isfile(path)]
    return sorted(matches, reverse=True)[0] if matches else None


def _get_version(exe_path):
    """从PE文件头读取版本信息"""
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(exe_path, None)
        if size == 0:
            return None
        buf = create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(exe_path, 0, size, buf):
            return None
        ver_ptr = c_char_p()
        ver_len = c_uint()
        if ctypes.windll.version.VerQueryValueW(buf, "\\", byref(ver_ptr), byref(ver_len)):
            data = string_at(ver_ptr, ver_len.value)
            if len(data) >= 12:
                sig = struct.unpack_from('I', data, 0)[0]
                if sig == 0xFEEF04BD:
                    ms, ls = struct.unpack_from('II', data, 4)
                    return f"{ms>>16}.{ms&0xFFFF}.{ls>>16}.{ls&0xFFFF}"
        for locale in ("040904B0", "040904E4", "000004B0", "080404B0"):
            sub = f"\\StringFileInfo\\{locale}\\FileVersion"
            if ctypes.windll.version.VerQueryValueW(buf, sub, byref(ver_ptr), byref(ver_len)):
                val = string_at(ver_ptr, ver_len.value - 1)
                if val:
                    return val.decode('utf-8', errors='ignore')[:50]
        return None
    except Exception:
        return None


def scan_installed_ides():
    """扫描本机已安装的 IDE，返回列表并持久化缓存"""
    registry = load_registry()
    results = []
    seen_keys = set()
    for ide_key, config in registry.items():
        if config.get("type") == "web":
            continue
        if ide_key == "codex":
            exe = _probe_codex_desktop_exe()
            if exe:
                results.append({
                    "key": ide_key,
                    "name": "ChatGPT (Codex)",
                    "path": exe,
                    "version": _get_version(exe),
                    "source": "scan",
                    "icon": config.get("icon", ""),
                    "color": config.get("color", "#58A6FF"),
                })
                seen_keys.add(ide_key)
                continue
        scan_paths = config.get("scan_paths", [])
        exe_pattern = config.get("exe_pattern", "")
        if not scan_paths or not exe_pattern:
            continue
        for path_template in scan_paths:
            for path in _expand_scan_paths(path_template):
                if os.path.isdir(path):
                    exe = _find_exe(path, exe_pattern)
                else:
                    exe = None
                if exe:
                    results.append({
                        "key": ide_key,
                        "name": config.get("name", ide_key),
                        "path": exe,
                        "version": _get_version(exe),
                        "source": "scan",
                        "icon": config.get("icon", ""),
                        "color": config.get("color", "#90A4AE"),
                    })
                    seen_keys.add(ide_key)
                    break
            else:
                continue
            break
    # 一个可执行文件只能对应一个 IDE 条目，避免 TRAE/TRAЕ_CN 等重叠
    # 注册规则把同一路径显示成多个 IDE。CN 文件优先保留 trae_cn，否则保留 trae。
    by_path = {}
    for item in results:
        path_key = os.path.normcase(os.path.abspath(item.get("path", "")))
        current = by_path.get(path_key)
        if current is None:
            by_path[path_key] = item
        elif "cn" in os.path.basename(item.get("path", "")).lower() and "cn" not in os.path.basename(current.get("path", "")).lower():
            by_path[path_key] = item
    results = list(by_path.values())
    _save_scanned(results)
    return results


def load_manual_ides():
    """加载手动配置的 IDE 列表"""
    return safe_read_json(MANUAL_IDES_FILE, default=[])


def save_manual_ides(ides):
    """保存手动配置的 IDE 列表"""
    return safe_write_json(MANUAL_IDES_FILE, ides)


def add_manual_ide(ide):
    """添加一个手动配置的 IDE"""
    ides = load_manual_ides()
    for i, existing in enumerate(ides):
        if existing.get("key") == ide.get("key"):
            ides[i] = ide
            save_manual_ides(ides)
            return True
    ides.append(ide)
    save_manual_ides(ides)
    return True


def remove_manual_ide(key):
    """删除一个手动配置的 IDE"""
    ides = load_manual_ides()
    ides = [i for i in ides if i.get("key") != key]
    save_manual_ides(ides)
    return True


def _load_scanned():
    """从缓存文件读取扫描结果"""
    return safe_read_json(SCANNED_IDES_FILE, default=[])


def _save_scanned(ides):
    """保存扫描结果到缓存文件"""
    return safe_write_json(SCANNED_IDES_FILE, ides)



def load_ide_roles():
    """加载所有 IDE 的额外角色配置"""
    return safe_read_json(IDE_ROLES_FILE, default={})


def save_ide_roles(roles):
    """保存所有 IDE 的额外角色配置"""
    os.makedirs(os.path.dirname(IDE_ROLES_FILE), exist_ok=True)
    return safe_write_json(IDE_ROLES_FILE, roles)


def set_primary_ide(key, enabled=True):
    """设置唯一主 IDE；enabled=False 时仅取消指定 IDE 的主角色。"""
    roles = load_ide_roles()
    if enabled:
        for role in roles.values():
            if isinstance(role, dict):
                role.pop("is_primary", None)
        roles.setdefault(key, {})["is_primary"] = True
    else:
        role = roles.get(key)
        if isinstance(role, dict):
            role.pop("is_primary", None)
            if not role:
                roles.pop(key, None)
    return save_ide_roles(roles)


def get_primary_ide_key():
    """返回当前主 IDE key；未配置时返回空字符串。"""
    roles = load_ide_roles()
    return next((key for key, role in roles.items() if isinstance(role, dict) and role.get("is_primary")), "")


def load_ide_aliases():
    """加载 IDE 别名配置"""
    return safe_read_json(IDE_ALIASES_FILE, default={})


def save_ide_aliases(aliases):
    """保存 IDE 别名配置"""
    os.makedirs(os.path.dirname(IDE_ALIASES_FILE), exist_ok=True)
    return safe_write_json(IDE_ALIASES_FILE, aliases)


def set_ide_alias(key, alias):
    """为指定 IDE 设置别名；alias 为空则删除该别名。"""
    key = (key or "").strip()
    alias = (alias or "").strip()
    if not key:
        return False
    aliases = load_ide_aliases()
    if alias:
        aliases[key] = alias
    else:
        aliases.pop(key, None)
    return save_ide_aliases(aliases)


def rename_ide_key(old_key, new_key):
    """重命名 IDE 的 Key，并把所有相关状态一并迁移。"""
    old_key = _normalize_ide_key(old_key)
    new_key = _normalize_ide_key(new_key)
    if not old_key or not new_key or old_key == new_key:
        return False, "旧 key 和新 key 不能为空且不能相同"
    if not new_key.replace("_", "").replace("-", "").replace(".", "").isalnum():
        return False, "Key 只能包含字母、数字、下划线、中划线或点"

    registry = load_registry()
    if old_key not in registry:
        return False, f"找不到 IDE key '{old_key}'"
    if new_key in registry and new_key != old_key:
        return False, f"目标 key '{new_key}' 已存在"

    registry[new_key] = registry.pop(old_key)
    save_registry(registry)

    manual = load_manual_ides()
    for item in manual:
        if item.get("key") == old_key:
            item["key"] = new_key
    save_manual_ides(manual)

    scanned = _load_scanned()
    for item in scanned:
        if item.get("key") == old_key:
            item["key"] = new_key
    _save_scanned(scanned)

    roles = load_ide_roles()
    if _rename_mapping_key(roles, old_key, new_key):
        save_ide_roles(roles)

    aliases = load_ide_aliases()
    if _rename_mapping_key(aliases, old_key, new_key):
        save_ide_aliases(aliases)

    # 状态/裁剪/设置里的 key 迁移
    status = safe_read_json(os.path.join(BASE_DIR, "state", "ide_status.json"), default={})
    if isinstance(status, dict):
        changed = False
        if _rename_mapping_key(status, old_key, new_key):
            changed = True
        if _replace_ide_values(status, old_key, new_key):
            changed = True
        if changed:
            safe_write_json(os.path.join(BASE_DIR, "state", "ide_status.json"), status)

    crops = safe_read_json(os.path.join(BASE_DIR, "state", "screenshot_crops.json"), default={})
    if isinstance(crops, dict):
        if _rename_nested_mapping_keys(crops, old_key, new_key) or _replace_ide_values(crops, old_key, new_key):
            safe_write_json(os.path.join(BASE_DIR, "state", "screenshot_crops.json"), crops)

    settings_path = os.path.join(BASE_DIR, "aidelink_settings.json")
    settings = safe_read_json(settings_path, default={})
    if isinstance(settings, dict):
        changed = False
        for field in ("desktop_ide", "desktop_ide_path"):
            if settings.get(field) == old_key:
                settings[field] = new_key
                changed = True
        if _replace_ide_values(settings, old_key, new_key, {"desktop_ide"}):
            changed = True
        if changed:
            safe_write_json(settings_path, settings)

    state_dir = os.path.join(BASE_DIR, "state")
    for file_name in os.listdir(state_dir):
        file_path = os.path.join(state_dir, file_name)
        if not os.path.isfile(file_path):
            continue
        data = safe_read_json(file_path, default=None)
        if data is None:
            continue
        changed = False
        if file_name.startswith("tasks") and file_name.endswith(".json"):
            changed = _replace_ide_values(data, old_key, new_key)
        elif file_name in (f"test_task_{old_key}.json", f"test_result_{old_key}.json"):
            changed = _replace_ide_values(data, old_key, new_key)
        elif file_name in (f"test_result_{old_key}.md",):
            changed = False
        elif file_name.startswith("task_queue_") and file_name.endswith(".json"):
            changed = False
        else:
            changed = _rename_nested_mapping_keys(data, old_key, new_key) or _replace_ide_values(data, old_key, new_key)
        if changed:
            safe_write_json(file_path, data)

    _rename_state_file("task_queue_", old_key, new_key)
    _rename_state_file("test_task_", old_key, new_key)
    _rename_state_file("test_result_", old_key, new_key)
    _rename_state_file("test_result_", old_key, new_key, suffix=".md")

    return True, f"已将 IDE key 从 '{old_key}' 迁移为 '{new_key}'"


def get_all_ides():
    """获取所有 IDE（注册表 + 扫描缓存 + 手动配置）并融合角色配置"""
    registry = load_registry()
    scanned = _load_scanned()
    manual = load_manual_ides()
    roles = load_ide_roles()
    aliases = load_ide_aliases()

    # 以注册表为基础，注入 web 类型
    result = []
    scanned_map = {i["key"]: i for i in scanned}
    manual_map = {i["key"]: i for i in manual}

    for key, config in registry.items():
        if config.get("type") == "web":
            result.append({
                "key": key,
                "name": config.get("name", key),
                "type": "web",
                "path": "",
                "version": "Remote",
                "source": "registry",
                "icon": config.get("icon", ""),
                "color": config.get("color", "#90A4AE"),
            })
        elif key in scanned_map:
            entry = scanned_map[key].copy()
            entry["icon"] = config.get("icon", entry.get("icon", ""))
            entry["color"] = config.get("color", entry.get("color", "#90A4AE"))
            result.append(entry)
        elif key in manual_map:
            entry = manual_map[key].copy()
            entry["icon"] = config.get("icon", entry.get("icon", ""))
            entry["color"] = config.get("color", entry.get("color", "#90A4AE"))
            result.append(entry)

    # 扫描到但不在注册表里的 IDE（用户手动添加过扫描路径）
    registry_keys = set(registry.keys())
    for s in scanned:
        if s["key"] not in registry_keys:
            result.append(s)

    # 手动配置中不在注册表和扫描结果里的
    existing_keys = {r["key"] for r in result}
    for m in manual:
        if m.get("key") not in existing_keys:
            result.append(m)

    # 合并角色属性并补充 type 字段
    for entry in result:
        if entry.get("key") in aliases:
            entry["alias"] = aliases[entry["key"]]
        entry["accept_test_tasks"] = roles.get(entry["key"], {}).get("accept_test_tasks", False)
        entry["is_primary"] = roles.get(entry["key"], {}).get("is_primary", False)
        if "type" not in entry:
            entry["type"] = "desktop"

    unique = {}
    for item in result:
        path = item.get("path", "")
        key = os.path.normcase(os.path.abspath(path)) if path else f"{item.get('type','desktop')}:{item.get('key')}"
        unique.setdefault(key, item)
    return list(unique.values())


def get_ide_aumid_map():
    """从注册表构建 AUMID -> IDE key 映射"""
    registry = load_registry()
    aumid_map = {}
    for key, config in registry.items():
        for aumid in config.get("aumid", []):
            aumid_map[aumid] = key
    return aumid_map


if __name__ == "__main__":
    print("=== IDE Scanner ===")
    registry = load_registry()
    print(f"\n注册表 {len(registry)} 个 IDE:")
    for key, config in registry.items():
        print(f"  {key}: {config.get('name')} ({config.get('type', 'desktop')})")

    scanned = scan_installed_ides()
    print(f"\n扫描到 {len(scanned)} 个已安装 IDE:")
    for ide in scanned:
        print(f"  {ide['key']}: {ide['name']} -> {ide['path']}")

    all_ides = get_all_ides()
    print(f"\n总计 {len(all_ides)} 个 IDE:")
    for ide in all_ides:
        print(f"  {ide['key']}: {ide['name']} [{ide.get('source', '?')}]")
