"""任务管理只读工具：列出任务、查询单任务、查看队列状态。

对应 AideLink endpoint:
- GET /api/tasks
- GET /api/tasks/queue_status
- GET /queues/<ide>/next
"""
from . import http_client

TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "列出 AideLink 中的任务。可按状态/目标 IDE/关键词过滤。返回任务的标题、状态、目标 IDE、创建时间等摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "按状态过滤，多个用逗号分隔。可选值: pending, queued, running, completed, failed"},
                    "target_ide": {"type": "string", "description": "按目标 IDE 过滤，如 trae, claude, codex"},
                    "keyword": {"type": "string", "description": "按标题/正文关键词过滤（大小写不敏感）"},
                    "limit": {"type": "integer", "description": "最多返回条数，默认 20，最大 50"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_queue_status",
            "description": "查看所有 IDE 的任务队列状态：每个 IDE 的待执行任务数、当前任务、待处理任务列表。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "peek_next_task",
            "description": "查看某个 IDE 队列中下一个待执行的任务（不弹出、不修改状态）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "ide": {"type": "string", "description": "IDE 标识，如 trae, claude, codex, antigravity"},
                },
                "required": ["ide"],
            },
        },
    },
]


def _truncate(text, limit=200):
    if not text:
        return ""
    s = str(text)
    return s if len(s) <= limit else s[:limit] + "..."


def _summarize_task(t):
    """把任务对象压缩成 Aide 友好的单行摘要。"""
    tid = t.get("task_id", "?")
    title = _truncate(t.get("title") or t.get("text") or "", 60)
    status = t.get("status", "?")
    target = t.get("target_ide") or "-"
    created = t.get("time") or t.get("created_at") or "-"
    return f"[{tid}] {status} → {target} | {title} ({created})"


def handle(name, args):
    if name == "list_tasks":
        query = {}
        if args.get("status"):
            query["status"] = args["status"]
        if args.get("target_ide"):
            query["target_ide"] = args["target_ide"]
        if args.get("keyword"):
            query["keyword"] = args["keyword"]
        status, data = http_client.get("/api/tasks", query=query or None)
        if status != 200:
            return f"查询失败: HTTP {status}"
        tasks = data.get("tasks", []) if isinstance(data, dict) else []
        limit = min(50, max(1, int(args.get("limit", 20))))
        tasks = tasks[:limit]
        if not tasks:
            return "当前没有匹配的任务"
        lines = [_summarize_task(t) for t in tasks]
        return f"任务列表（共 {len(tasks)} 条）:\n" + "\n".join(lines)

    if name == "get_queue_status":
        status, data = http_client.get("/api/tasks/queue_status")
        if status != 200:
            return f"查询失败: HTTP {status}"
        queues = data.get("queues", {}) if isinstance(data, dict) else {}
        if not queues:
            return "当前没有活动的任务队列"
        lines = []
        for ide, info in queues.items():
            count = info.get("count", 0)
            current = info.get("current") or "无"
            pending = info.get("pending", [])
            lines.append(f"{ide}: 待执行 {count} | 当前 {current} | 队列 {[p if isinstance(p, str) else p.get('task_id', '?') for p in pending[:5]]}")
        return "队列状态:\n" + "\n".join(lines)

    if name == "peek_next_task":
        ide = (args.get("ide") or "").strip()
        if not ide:
            return "错误：缺少 ide 参数"
        status, data = http_client.get(f"/queues/{ide}/next")
        if status != 200:
            return f"查询失败: HTTP {status}"
        if isinstance(data, dict) and data.get("ok") is False:
            return f"IDE '{ide}' 队列为空或不存在: {data.get('error', '')}"
        task = data.get("task") if isinstance(data, dict) else None
        if not task:
            return f"IDE '{ide}' 队列中没有待执行任务"
        return "下一个任务:\n" + _summarize_task(task) + f"\n正文: {_truncate(task.get('text') or task.get('message'), 300)}"

    return None
