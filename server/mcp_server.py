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


def _string_list(value):
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_scope_path(value):
    return str(value or "").strip().replace("\\", "/").strip("/").lower()


def _paths_overlap(left, right):
    """Return path pairs whose scopes are equal or contain one another."""
    conflicts = []
    for left_path in _string_list(left):
        normalized_left = _normalize_scope_path(left_path)
        if not normalized_left:
            continue
        for right_path in _string_list(right):
            normalized_right = _normalize_scope_path(right_path)
            if not normalized_right:
                continue
            if (
                normalized_left == normalized_right
                or normalized_left.startswith(normalized_right + "/")
                or normalized_right.startswith(normalized_left + "/")
            ):
                conflicts.append([left_path, right_path])
    return conflicts


def _manager_ide_candidates(runtime, main_ide="codex"):
    """List configured IDEs, preferring an open idle non-primary worker."""
    import ide_scanner
    from dispatch_utils import get_ide_running_statuses

    ides = [item for item in ide_scanner.get_all_ides() if item.get("type", "desktop") != "web"]
    running = get_ide_running_statuses(ides)
    candidates = []
    for item in ides:
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        state = runtime.get_ide_status(key) or {}
        available = runtime.is_ide_available(key)
        is_manager = bool(item.get("is_primary", False)) or key == main_ide
        candidates.append({
            "key": key,
            "name": item.get("name") or key,
            "running": bool(running.get(key, False)),
            "status": state.get("status") or "idle",
            "is_primary": bool(item.get("is_primary", False)),
            "is_manager": is_manager,
            "available": bool(available),
        })
    candidates.sort(key=lambda item: (
        not (item["running"] and item["available"] and not item["is_manager"]),
        not item["running"],
        not item["available"],
        item["is_manager"],
        item["name"].lower(),
    ))
    recommended = next((
        item["key"] for item in candidates
        if item["running"] and item["available"] and not item["is_manager"]
    ), None)
    return candidates, recommended


def _compact_task_package(arguments):
    objective = str(arguments.get("objective") or arguments.get("task") or "").strip()
    task_type = str(arguments.get("task_type") or "research").strip().lower()
    if task_type not in {"read_only", "research", "test", "summary", "code"}:
        task_type = "research"
    main_owned_paths = _string_list(arguments.get("main_owned_paths"))
    worker_owned_paths = _string_list(arguments.get("worker_owned_paths"))
    result_ref = str(arguments.get("result_ref") or "").strip()
    result_ref_preferred = task_type in {"read_only", "research", "test", "summary"}
    package = {
        "objective": objective,
        "task_type": task_type,
        "completed": _string_list(arguments.get("completed")),
        "remaining": _string_list(arguments.get("remaining")),
        "decisions": _string_list(arguments.get("decisions")),
        "main_owned_paths": main_owned_paths,
        "worker_owned_paths": worker_owned_paths,
        "validation": _string_list(arguments.get("validation_commands")),
        "context_refs": _string_list(arguments.get("context_refs")),
        "result_ref": result_ref or None,
        "contract": {
            "do_not_modify_main_owned_paths": True,
            "return_via": "report_delegated_aidelink_task",
            "result_ref_preferred": result_ref_preferred,
            "main_ide_verifies": True,
        },
    }
    return package


def handle_prepare_delegation(arguments):
    """Build a compact, read-only manager package without creating or dispatching a task."""
    package = _compact_task_package(arguments)
    if not package["objective"]:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 objective"}]}
    conflicts = _paths_overlap(package["main_owned_paths"], package["worker_owned_paths"])
    blockers = []
    if package["task_type"] == "code" and not package["worker_owned_paths"]:
        blockers.append("code_requires_worker_owned_paths")
    if conflicts:
        blockers.append("worker_paths_overlap_main_paths")
    main_ide = str(arguments.get("main_ide") or "codex").strip().lower()
    candidates, recommended = _manager_ide_candidates(get_runtime(), main_ide=main_ide)
    payload = {
        "task_package": package,
        "ide_candidates": candidates,
        "recommended_ide": recommended,
        "file_conflicts": conflicts,
        "dispatch_allowed": not blockers,
        "dispatch_blockers": blockers,
        "choices": [
            {"id": "complete_here", "label": "不派发，由主 Codex 完成"},
            {"id": "new_codex_session", "label": "创建 Codex 新会话接力", "requires_user_confirmation": True},
            {"id": "delegate", "label": "选择 IDE 后派发", "requires_user_confirmation": True},
        ],
    }
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]}


def handle_delegate_task(arguments):
    """Create a task owned by the primary IDE and optionally queue it."""
    text = (arguments.get("task") or arguments.get("description") or "").strip()
    target_ide = (arguments.get("target_ide") or "").strip()
    if not text or not target_ide:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 task 或 target_ide"}]}
    if arguments.get("user_confirmed") is not True:
        return {"isError": True, "content": [{"type": "text", "text": (
            "尚未派发：必须先向用户展示候选，并在用户明确同意后传 user_confirmed=true。"
            "用户也可以选择“不派发，由主 Codex 完成”。"
        )}]}
    task_type = str(arguments.get("task_type") or "research").strip().lower()
    owned_paths = _string_list(arguments.get("owned_paths"))
    main_owned_paths = _string_list(arguments.get("main_owned_paths"))
    if task_type == "code" and not owned_paths:
        return {"isError": True, "content": [{"type": "text", "text": (
            "拒绝派发：员工代码任务必须声明 owned_paths，以便与主 IDE 文件范围隔离。"
        )}]}
    conflicts = _paths_overlap(main_owned_paths, owned_paths)
    if task_type == "code" and conflicts:
        return {"isError": True, "content": [{"type": "text", "text": (
            "拒绝派发：员工代码任务与主 IDE 文件范围重叠："
            + json.dumps(conflicts, ensure_ascii=False)
        )}]}
    runtime = get_runtime()
    task = runtime.create_task(
        text,
        title=arguments.get("title"),
        source="primary_ide",
        target_ide=None,
        owned_paths=owned_paths,
        parent_task_id=arguments.get("parent_task_id"),
        priority=arguments.get("priority", "medium"),
        metadata={
            "delegated_by": "primary_ide",
            "worker_role": "employee",
            "task_type": task_type,
            "main_owned_paths": main_owned_paths,
            "result_ref_preferred": task_type in {"read_only", "research", "test", "summary"},
        },
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
    """Create a project idea through the running bridge to avoid cross-process lost updates."""
    idea = (arguments.get("text") or arguments.get("idea") or "").strip()
    if not idea:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 text"}]}
    bridge_url = os.environ.get("AIDELINK_BRIDGE_URL", "http://127.0.0.1:5000").rstrip("/")
    payload = json.dumps({
        "text": idea,
        "title": arguments.get("title") or idea[:40],
        "priority": arguments.get("priority", "medium"),
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{bridge_url}/api/tasks/inspiration",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"灵感写入 Bridge 失败: {exc}"}]}
    task = result.get("task") if result.get("ok") else None
    if not isinstance(task, dict):
        return {"isError": True, "content": [{"type": "text", "text": result.get("message", "灵感创建失败")}]}
    return {"content": [{"type": "text", "text": (
        f"已记录项目灵感：`{task.get('task_id')}` | {task.get('title')} | "
        f"{task.get('status', 'draft')} | {task.get('project', '')}"
    )}]}


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
    tasks = get_runtime().read_tasks()
    scope = str(arguments.get("scope") or "actionable").strip().lower()
    limit = max(1, min(int(arguments.get("limit") or 20), 100))
    include_details = bool(arguments.get("include_details", False))
    terminal_statuses = {"done", "completed", "failed", "cancelled", "timeout"}
    if scope == "inspirations":
        tasks = [task for task in tasks if (task.get("metadata") or {}).get("content_kind") == "inspiration"]
    elif scope == "actionable":
        tasks = [task for task in tasks if str(task.get("status") or "").lower() not in terminal_statuses]
    tasks = sorted(tasks, key=lambda task: str(task.get("updated_at") or task.get("created_at") or ""), reverse=True)[:limit]
    if not tasks:
        return {"content": [{"type": "text", "text": f"当前项目没有符合 scope={scope} 的任务。"}]}
    
    # Format tasks for display
    lines = [f"当前项目任务（scope={scope}, {len(tasks)} 条）："]
    for t in tasks:
        status = str(t.get("status") or "draft")
        kind = "灵感" if (t.get("metadata") or {}).get("content_kind") == "inspiration" else "任务"
        target = t.get("target_ide") or "未分配"
        lines.append(
            f"- `{t.get('task_id')}` | {kind} | {status} | {t.get('priority', 'medium')} | "
            f"{t.get('title') or '无标题'} | {target}"
        )
        if include_details:
            text = str(t.get("text") or "").strip().replace("\n", " ")
            if text:
                lines.append(f"  {text[:300]}{'…' if len(text) > 300 else ''}")
    
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
            "inputSchema": {"type": "object", "properties": {
                "scope": {"type": "string", "enum": ["actionable", "inspirations", "all"], "default": "actionable"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "include_details": {"type": "boolean", "default": False}
            }},
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
            "name": "prepare_aidelink_delegation",
            "description": "经理模式只读准备：生成紧凑任务包和 IDE 候选，优先推荐已打开空闲 IDE，但始终保留由主 Codex 完成；不会创建或派发任务",
            "inputSchema": {"type": "object", "properties": {
                "objective": {"type": "string"},
                "main_ide": {"type": "string", "default": "codex"},
                "task_type": {"type": "string", "enum": ["read_only", "research", "test", "summary", "code"], "default": "research"},
                "completed": {"type": "array", "items": {"type": "string"}},
                "remaining": {"type": "array", "items": {"type": "string"}},
                "decisions": {"type": "array", "items": {"type": "string"}},
                "main_owned_paths": {"type": "array", "items": {"type": "string"}},
                "worker_owned_paths": {"type": "array", "items": {"type": "string"}},
                "validation_commands": {"type": "array", "items": {"type": "string"}},
                "context_refs": {"type": "array", "items": {"type": "string"}},
                "result_ref": {"type": "string"}
            }, "required": ["objective"]},
        },
        {
            "name": "delegate_aidelink_task",
            "description": "用户明确同意后，主 IDE 复用 TaskRuntime 创建并派发员工任务；未确认时拒绝且不创建任务",
            "inputSchema": {"type": "object", "properties": {
                "task": {"type": "string"}, "title": {"type": "string"},
                "target_ide": {"type": "string"}, "parent_task_id": {"type": "string"},
                "priority": {"type": "string"}, "dispatch": {"type": "boolean", "default": True},
                "user_confirmed": {"type": "boolean", "description": "仅在用户明确同意本次派发后设为 true"},
                "task_type": {"type": "string", "enum": ["read_only", "research", "test", "summary", "code"], "default": "research"},
                "main_owned_paths": {"type": "array", "items": {"type": "string"}},
                "owned_paths": {"type": "array", "items": {"type": "string"}}
            }, "required": ["task", "target_ide", "user_confirmed"]},
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
        elif tool_name == "prepare_aidelink_delegation":
            result = handle_prepare_delegation(arguments)
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
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    log_debug("AideLink Tasks MCP server started.")
    for line in sys.stdin:
        line = line.strip()
        if line:
            process_message(line)

if __name__ == "__main__":
    main()
