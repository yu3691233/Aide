"""IDE 与设备状态只读工具。

对应 AideLink endpoint:
- GET /api/ide/active_status
- GET /api/ide-window-bindings/candidates?key=<ide>
- GET /api/devices
- GET /api/active-models
"""
from . import http_client

TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "list_ides",
            "description": "列出所有 IDE 的运行状态：哪些 IDE 开着、哪个正在执行任务、当前任务 ID。用于回答'现在有哪些 IDE 可用'。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_devices",
            "description": "列出已连接的 Android 设备：设备别名、IP、是否在线、ADB 是否连接、型号等。用于回答'现在有哪些手机/设备连着'。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_active_models",
            "description": "列出当前启用的 AI 模型列表。用于回答'Aide 现在用哪个模型'。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _truncate(text, limit=80):
    if not text:
        return ""
    s = str(text)
    return s if len(s) <= limit else s[:limit] + "..."


def handle(name, args):
    if name == "list_ides":
        status, data = http_client.get("/api/ide/active_status")
        if status != 200:
            return f"查询失败: HTTP {status}"
        ides = data.get("ides", []) if isinstance(data, dict) else []
        if not ides:
            return "当前没有可用的 IDE"
        lines = []
        running_count = 0
        for ide in ides:
            key = ide.get("key", "?")
            name_str = ide.get("name", key)
            running = ide.get("running", False)
            st = ide.get("status", "?")
            current = ide.get("current_task_id")
            if running:
                running_count += 1
            tag = "✅运行" if running else "⏹停止"
            cur = f" 正在执行 {current}" if current else ""
            lines.append(f"{tag} {name_str}({key}) 状态={st}{cur}")
        return f"IDE 状态（{running_count}/{len(ides)} 运行中）:\n" + "\n".join(lines)

    if name == "list_devices":
        status, data = http_client.get("/api/devices")
        if status != 200:
            return f"查询失败: HTTP {status}"
        devices = data.get("devices", []) if isinstance(data, dict) else []
        if not devices:
            return "当前没有已连接的设备"
        lines = []
        online_count = 0
        for d in devices:
            alias = d.get("alias") or d.get("serial") or "?"
            online = d.get("is_online", False)
            adb = d.get("is_adb_connected", False)
            model = _truncate(d.get("model") or "", 30)
            ip = d.get("online_ip") or d.get("ip") or "-"
            if online:
                online_count += 1
            tag = "🟢在线" if online else "⚪离线"
            adb_tag = "ADB✓" if adb else "ADB✗"
            lines.append(f"{tag} {alias} {adb_tag} {model} @ {ip}")
        return f"设备列表（{online_count}/{len(devices)} 在线）:\n" + "\n".join(lines)

    if name == "list_active_models":
        status, data = http_client.get("/api/active-models")
        if status != 200:
            return f"查询失败: HTTP {status}"
        models = data.get("models", []) if isinstance(data, dict) else []
        if not models:
            return "当前没有启用的模型"
        lines = [f"- {m.get('key', '?')}: {_truncate(m.get('description', ''), 60)}" for m in models]
        return "已启用模型:\n" + "\n".join(lines)

    return None
