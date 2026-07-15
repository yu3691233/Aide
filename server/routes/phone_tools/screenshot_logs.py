"""截图与日志只读工具。

对应 AideLink endpoint:
- GET /screenshot/full        (返回 image/jpeg 二进制流)
- GET /api/logs               (返回 {logs: [string]})
- GET /api/logs/phone         (返回 {logs: [string]})

注意：截图返回的是 JPEG 二进制，Aide 是文本模型无法直接"看"图片，
所以这里把截图描述为"已保存到服务端"并返回抓取状态/窗口信息，
而不是把 base64 塞进上下文（会爆炸式占用 token）。
"""
import base64
from . import http_client

TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "get_screenshot",
            "description": "抓取当前桌面截图。返回截图抓取状态（是否成功、窗口是否找到）和截图大小。截图保存在服务端，Aide 可通过此工具确认屏幕当前状态，但无法直接查看图像内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "截图目标，留空抓全屏；也可填 IDE 标识（如 trae）抓该 IDE 窗口"},
                    "monitor": {"type": "integer", "description": "显示器编号（多显示器时），默认 0"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_server_logs",
            "description": "查看 AideLink 服务端最近的日志（flask_new.log）。用于排查服务问题或了解最近的请求/错误。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lines": {"type": "integer", "description": "返回最近多少行，默认 50，最大 200"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_phone_logs",
            "description": "查看手机 App 端最近的日志（phone_app.log）。用于排查手机端连接/消息问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "lines": {"type": "integer", "description": "返回最近多少行，默认 50，最大 200"},
                },
                "required": [],
            },
        },
    },
]

# 截图返回给 Aide 的最大行数（避免日志爆 token）
_MAX_LOG_CHARS = 4000


def _trim_logs(logs, lines):
    """取最后 N 行，并控制总字符数。"""
    if not logs:
        return "（无日志）"
    n = min(200, max(1, lines))
    tail = logs[-n:]
    joined = "\n".join(str(l) for l in tail)
    if len(joined) > _MAX_LOG_CHARS:
        joined = "..." + joined[-_MAX_LOG_CHARS:]
    return joined


def handle(name, args):
    if name == "get_screenshot":
        query = {}
        if args.get("target"):
            query["target"] = args["target"]
        if args.get("monitor") is not None:
            query["monitor"] = args["monitor"]
        status, raw, headers = http_client.get_bytes("/screenshot/full", query=query or None, timeout=20)
        if status != 200:
            err = raw.decode("utf-8", errors="replace")[:200] if raw else ""
            return f"截图失败: HTTP {status} {err}"
        window_found = headers.get("X-Window-Found", "unknown")
        size = len(raw)
        # 不把图片 base64 塞给 Aide（会爆 token），只返回状态摘要
        # 如需查看图像，用户可在手机 App 截图面板直接看
        return f"截图成功: 窗口找到={window_found}, 图片大小={size}B。截图已在服务端生成，可在手机 App 截图面板查看。"

    if name == "get_server_logs":
        lines = int(args.get("lines", 50))
        status, data = http_client.get("/api/logs", query={"lines": lines})
        if status != 200:
            return f"获取日志失败: HTTP {status}"
        logs = data.get("logs", []) if isinstance(data, dict) else []
        return "服务端日志:\n" + _trim_logs(logs, lines)

    if name == "get_phone_logs":
        lines = int(args.get("lines", 50))
        status, data = http_client.get("/api/logs/phone", query={"lines": lines})
        if status != 200:
            return f"获取日志失败: HTTP {status}"
        logs = data.get("logs", []) if isinstance(data, dict) else []
        return "手机端日志:\n" + _trim_logs(logs, lines)

    return None
