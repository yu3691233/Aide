#!/usr/bin/env python3
import sys
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

# Add server directory to sys.path to resolve imports
BRIDGE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BRIDGE_DIR))

TASKS_FILE = BRIDGE_DIR / "state" / "tasks.json"

def log_debug(msg):
    # MCP standard: debug logging should go to stderr to avoid corrupting jsonrpc stdout
    print(f"[DEBUG] {msg}", file=sys.stderr, flush=True)

def read_tasks():
    if not TASKS_FILE.exists():
        return []
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_debug(f"Failed to read tasks: {e}")
        return []


def get_runtime():
    """Return the shared project-aware task runtime used by HTTP routes."""
    from task_runtime import TaskRuntime
    return TaskRuntime(str(BRIDGE_DIR))


def _task_text(task):
    return json.dumps(task, ensure_ascii=False, indent=2)


def handle_delegate_task(arguments):
    """Create a task owned by the primary IDE and optionally queue it."""
    text = (arguments.get("task") or arguments.get("description") or "").strip()
    target_ide = (arguments.get("target_ide") or "").strip()
    if not text or not target_ide:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 task 或 target_ide"}]}
    runtime = get_runtime()
    task = runtime.create_task(
        text,
        title=arguments.get("title"),
        source="primary_ide",
        target_ide=None,
        parent_task_id=arguments.get("parent_task_id"),
        priority=arguments.get("priority", "medium"),
        metadata={"delegated_by": "primary_ide", "worker_role": "employee"},
    )
    task = runtime.assign_task(task["task_id"], target_ide)
    if not task:
        return {"isError": True, "content": [{"type": "text", "text": "任务创建后无法分配到目标 IDE"}]}
    if arguments.get("dispatch", True):
        from dispatch_utils import dispatch_task
        ok, detail = dispatch_task(task, runtime)
        if not ok:
            return {"isError": True, "content": [{"type": "text", "text": f"任务已入队，但派发失败: {detail}\n{_task_text(task)}"}]}
    return {"content": [{"type": "text", "text": f"已派发员工任务：\n{_task_text(task)}"}]}


def handle_create_inspiration(arguments):
    """Create a project-level idea without binding or dispatching an IDE."""
    idea = (arguments.get("text") or arguments.get("idea") or "").strip()
    if not idea:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 text"}]}
    task = get_runtime().create_task(
        idea,
        title=arguments.get("title") or idea[:40],
        source="primary_ide",
        target_ide=None,
        priority=arguments.get("priority", "medium"),
        metadata={"created_via": "mcp", "content_kind": "inspiration"},
    )
    return {"content": [{"type": "text", "text": f"已记录项目灵感：\n{_task_text(task)}"}]}


def handle_get_delegated_task(arguments):
    task_id = (arguments.get("task_id") or "").strip()
    if not task_id:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 task_id"}]}
    task = get_runtime().get_task(task_id)
    if not task or task.get("source") != "primary_ide":
        return {"isError": True, "content": [{"type": "text", "text": "未找到主 IDE 委派任务"}]}
    return {"content": [{"type": "text", "text": _task_text(task)}]}


def handle_report_delegated_task(arguments):
    task_id = (arguments.get("task_id") or "").strip()
    summary = (arguments.get("summary") or "").strip()
    if not task_id or not summary:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 task_id 或 summary"}]}
    task = get_runtime().mark_task_done(task_id, summary=summary, result_ref=arguments.get("result_ref"))
    if not task:
        return {"isError": True, "content": [{"type": "text", "text": "未找到任务或回传失败"}]}
    return {"content": [{"type": "text", "text": f"子 IDE 已回传，等待主 IDE 验证：\n{_task_text(task)}"}]}


def handle_verify_delegated_task(arguments):
    task_id = (arguments.get("task_id") or "").strip()
    if not task_id:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 task_id"}]}
    task = get_runtime().confirm_task_done(task_id)
    if not task:
        return {"isError": True, "content": [{"type": "text", "text": "任务不存在或无法验证"}]}
    return {"content": [{"type": "text", "text": f"主 IDE 已验证通过：\n{_task_text(task)}"}]}

def write_tasks(tasks):
    try:
        os.makedirs(TASKS_FILE.parent, exist_ok=True)
        # Use atomic write style
        temp_file = TASKS_FILE.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, TASKS_FILE)
        return True
    except Exception as e:
        log_debug(f"Failed to write tasks: {e}")
        return False

def handle_get_tasks(arguments):
    tasks = read_tasks()
    if not tasks:
        return {"content": [{"type": "text", "text": "目前 AideLink 任务列表中没有任何任务。"}]}
    
    # Format tasks for display
    lines = ["📋 AideLink 当前任务列表："]
    for t in tasks:
        status_symbol = "⏳"
        status = t.get("status", "pending")
        if status == "running":
            status_symbol = "🏃"
        elif status == "completed":
            status_symbol = "✅"
        elif status == "failed":
            status_symbol = "❌"
        
        lines.append(f"- [{status_symbol}] ID: `{t.get('id')}` | {t.get('title', '无标题')}")
        if t.get("description"):
            lines.append(f"  描述: {t.get('description')}")
    
    return {"content": [{"type": "text", "text": "\n".join(lines)}]}

def handle_update_task(arguments):
    task_id = arguments.get("task_id")
    status = arguments.get("status")
    if not task_id or not status:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 task_id 或 status"}]}
    
    tasks = read_tasks()
    found = False
    for t in tasks:
        if t.get("id") == task_id:
            t["status"] = status
            t["updated_at"] = int(sys.float_info.max) # or current time, let's keep it simple
            found = True
            break
            
    if not found:
        return {"isError": True, "content": [{"type": "text", "text": f"未找到 ID 为 {task_id} 的任务。"}]}
    
    if write_tasks(tasks):
        return {"content": [{"type": "text", "text": f"成功将任务 `{task_id}` 的状态更新为 `{status}`。"}]}
    else:
        return {"isError": True, "content": [{"type": "text", "text": "保存任务状态失败。"}]}


def handle_ask_aide(arguments):
    """Call the configured Aide model through the running bridge service."""
    message = (arguments.get("message") or "").strip()
    if not message:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 message"}]}

    payload = {
        "message": message,
        "task_type": (arguments.get("task_type") or "chat").strip() or "chat",
    }
    model = (arguments.get("model") or "").strip()
    if model:
        payload["model"] = model

    bridge_url = os.environ.get("AIDELINK_BRIDGE_URL", "http://127.0.0.1:5000").rstrip("/")
    req = urllib.request.Request(
        f"{bridge_url}/evolution/submit",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=130) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            error = json.loads(detail).get("error") or detail
        except json.JSONDecodeError:
            error = detail or str(exc)
        return {"isError": True, "content": [{"type": "text", "text": f"Aide 调用失败: {error}"}]}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"无法连接 Aide: {exc}"}]}

    if not result.get("ok"):
        return {"isError": True, "content": [{"type": "text", "text": f"Aide 调用失败: {result.get('error', '未知错误')}"}]}

    aide_text = result.get("response", "")
    metadata = f"Aide · {result.get('model_used', 'default')} · {result.get('task_id', '')}"
    return {"content": [{"type": "text", "text": f"{aide_text}\n\n---\n{metadata}"}]}


def get_tool_definitions():
    return [
        {
            "name": "get_aidelink_tasks",
            "description": "获取 AideLink 应用后端的当前开发任务列表，了解哪些任务待办、进行中或已完成",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "update_aidelink_task",
            "description": "更新 AideLink 的任务开发进度和状态（可用于领取任务 running，或标记已完成 completed）",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "任务的唯一 ID 标识"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "running", "completed", "failed"],
                        "description": "要更新的任务状态",
                    },
                },
                "required": ["task_id", "status"],
            },
        },
        {
            "name": "ask_aide",
            "description": "调用 AideLink 中配置的 Aide 模型进行分析、咨询或轻量任务委派，适合主 IDE 降低自身上下文和额度消耗",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "交给 Aide 的完整问题或任务说明"},
                    "task_type": {"type": "string", "description": "任务类型，例如 chat、analysis、coding", "default": "chat"},
                    "model": {"type": "string", "description": "可选模型 key；省略时使用 Aide 当前默认模型"},
                },
                "required": ["message"],
            },
        },
        {
            "name": "delegate_aidelink_task",
            "description": "主 IDE 创建并派发一个员工任务给指定子 IDE，任务与用户直接创建的任务区分",
            "inputSchema": {"type": "object", "properties": {
                "task": {"type": "string"}, "title": {"type": "string"},
                "target_ide": {"type": "string"}, "parent_task_id": {"type": "string"},
                "priority": {"type": "string"}, "dispatch": {"type": "boolean", "default": True}
            }, "required": ["task", "target_ide"]},
        },
        {
            "name": "create_aidelink_inspiration",
            "description": "把值得后续优化但当前不立即执行的内容记录为当前项目灵感，不绑定或派发任何 IDE",
            "inputSchema": {"type": "object", "properties": {
                "text": {"type": "string"}, "title": {"type": "string"},
                "priority": {"type": "string", "default": "medium"}
            }, "required": ["text"]},
        },
        {
            "name": "get_delegated_aidelink_task",
            "description": "读取主 IDE 派发任务的状态、结果和子 IDE 回传",
            "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]},
        },
        {
            "name": "report_delegated_aidelink_task",
            "description": "子 IDE 回传主 IDE 派发任务的执行摘要，进入待验证状态",
            "inputSchema": {"type": "object", "properties": {
                "task_id": {"type": "string"}, "summary": {"type": "string"}, "result_ref": {"type": "string"}
            }, "required": ["task_id", "summary"]},
        },
        {
            "name": "verify_delegated_aidelink_task",
            "description": "主 IDE 完成验证后确认员工任务，结束任务闭环",
            "inputSchema": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]},
        },
    ]

def process_message(line):
    try:
        request = json.loads(line)
    except json.JSONDecodeError:
        return
    
    method = request.get("method")
    msg_id = request.get("id")
    
    if method == "initialize":
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "aidelink-tasks-mcp",
                    "version": "1.0.0"
                }
            }
        }
        send_response(response)
    
    elif method == "tools/list":
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": get_tool_definitions()
            }
        }
        send_response(response)
        
    elif method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        result = {}
        if tool_name == "get_aidelink_tasks":
            result = handle_get_tasks(arguments)
        elif tool_name == "update_aidelink_task":
            result = handle_update_task(arguments)
        elif tool_name == "ask_aide":
            result = handle_ask_aide(arguments)
        elif tool_name == "delegate_aidelink_task":
            result = handle_delegate_task(arguments)
        elif tool_name == "create_aidelink_inspiration":
            result = handle_create_inspiration(arguments)
        elif tool_name == "get_delegated_aidelink_task":
            result = handle_get_delegated_task(arguments)
        elif tool_name == "report_delegated_aidelink_task":
            result = handle_report_delegated_task(arguments)
        elif tool_name == "verify_delegated_aidelink_task":
            result = handle_verify_delegated_task(arguments)
        else:
            result = {"isError": True, "content": [{"type": "text", "text": f"未知工具: {tool_name}"}]}
            
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result
        }
        send_response(response)

def send_response(response):
    sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
    sys.stdout.flush()

def main():
    log_debug("AideLink Tasks MCP server started.")
    for line in sys.stdin:
        line = line.strip()
        if line:
            process_message(line)

if __name__ == "__main__":
    main()
