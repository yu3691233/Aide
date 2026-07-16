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


def _manager_ide_candidates(runtime, main_ide="codex", include_stopped=False, limit=5):
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
    candidates = [
        item for item in candidates
        if not item["is_manager"] and (item["running"] or include_stopped)
    ]
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
    return candidates[:max(1, min(int(limit or 5), 20))], recommended


def _compact_task_package(arguments):
    objective = str(arguments.get("objective") or arguments.get("task") or "").strip()
    task_type = str(arguments.get("task_type") or "research").strip().lower()
    if task_type not in {"read_only", "research", "test", "summary", "code"}:
        task_type = "research"
    main_owned_paths = _string_list(arguments.get("main_owned_paths"))
    worker_owned_paths = _string_list(arguments.get("worker_owned_paths"))
    result_ref = str(arguments.get("result_ref") or "").strip()
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
            "result_ref_required": True,
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
    candidates, recommended = _manager_ide_candidates(
        get_runtime(),
        main_ide=main_ide,
        include_stopped=bool(arguments.get("include_stopped", False)),
        limit=arguments.get("candidate_limit", 5),
    )
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


def _worker_task_prompt(task_id, text, task_type, main_owned_paths, owned_paths):
    return "\n".join([
        "[AideLink 员工任务]",
        f"task_id: {task_id}",
        f"task_type: {task_type}",
        f"目标: {text}",
        f"主 IDE 占用范围（禁止修改）: {json.dumps(main_owned_paths, ensure_ascii=False)}",
        f"员工可修改范围: {json.dumps(owned_paths, ensure_ascii=False)}",
        "完成要求: 只处理本任务；运行约定验证；不要自行把任务标记 done。",
        "成功回传: 调用 report_delegated_aidelink_task，提交 summary 和 result_ref。",
        "result_ref 示例: commit:<sha>、file:<path>、test:<command/result>、inline:<evidence>。",
        "失败回传: 调用 fail_delegated_aidelink_task，说明 error 和已有 result_ref。",
        "主 IDE 将读取回传、独立验证，再调用 verify_delegated_aidelink_task 完成任务。",
    ])


def handle_get_workflow(arguments):
    role = str(arguments.get("role") or "manager").strip().lower()
    if role == "worker":
        workflow = {
            "role": "worker",
            "steps": [
                "用 get_delegated_aidelink_task 读取 task_id",
                "只在 owned_paths 内工作，不修改 main_owned_paths",
                "完成验证并保存证据引用",
                "成功调用 report_delegated_aidelink_task；失败调用 fail_delegated_aidelink_task",
                "等待主 IDE 验证，不自行调用 verify",
            ],
        }
    else:
        workflow = {
            "role": "manager",
            "steps": [
                "用 prepare_aidelink_delegation 生成紧凑包和真实打开的候选",
                "向用户展示主 IDE 完成、新 Codex 会话、员工 IDE 三类选择",
                "仅在用户明确同意后调用 delegate_aidelink_task",
                "用 get_delegated_aidelink_task 检查 summary 与 result_ref 并独立验证",
                "验证通过后调用 verify_delegated_aidelink_task；证据不足则不要完成",
            ],
        }
    return {"content": [{"type": "text", "text": json.dumps(workflow, ensure_ascii=False, separators=(",", ":"))}]}


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
            "result_ref_required": True,
            "objective": text,
        },
    )
    task = runtime.update_task(
        task["task_id"],
        text=_worker_task_prompt(task["task_id"], text, task_type, main_owned_paths, owned_paths),
    )
    task = runtime.assign_task(task["task_id"], target_ide)
    if not task:
        return {"isError": True, "content": [{"type": "text", "text": "任务创建后无法分配到目标 IDE"}]}
    should_dispatch = bool(arguments.get("dispatch", True))
    if should_dispatch:
        from dispatch_utils import dispatch_task
        ok, detail = dispatch_task(task, runtime)
        if not ok:
            return {"isError": True, "content": [{"type": "text", "text": f"任务 {task['task_id']} 已入队，但派发失败: {detail}"}]}
    result = {
        "task_id": task["task_id"],
        "status": "running" if should_dispatch else task.get("status"),
        "target_ide": target_ide,
        "next": "等待员工 result_ref 回传" if should_dispatch else "任务已入队，尚未注入 IDE",
    }
    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, separators=(",", ":"))}]}


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
    fields = (
        "task_id", "title", "text", "status", "target_ide", "owned_paths",
        "summary", "result_ref", "error", "updated_at", "metadata",
    )
    payload = {key: task.get(key) for key in fields}
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]}


def handle_report_delegated_task(arguments):
    task_id = (arguments.get("task_id") or "").strip()
    summary = (arguments.get("summary") or "").strip()
    if not task_id or not summary:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 task_id 或 summary"}]}
    result_ref = str(arguments.get("result_ref") or "").strip()
    runtime = get_runtime()
    current = runtime.get_task(task_id)
    if not current or current.get("source") != "primary_ide":
        return {"isError": True, "content": [{"type": "text", "text": "未找到主 IDE 委派任务"}]}
    if current.get("status") not in {"running", "dispatched"}:
        return {"isError": True, "content": [{"type": "text", "text": f"任务当前状态 {current.get('status')} 不允许员工回传"}]}
    if (current.get("metadata") or {}).get("result_ref_required") and not result_ref:
        return {"isError": True, "content": [{"type": "text", "text": "缺少 result_ref；请提供 commit/file/test/inline 证据引用"}]}
    task = runtime.mark_task_done(task_id, summary=summary, result_ref=result_ref or None)
    if not task:
        return {"isError": True, "content": [{"type": "text", "text": "未找到任务或回传失败"}]}
    result = {"task_id": task_id, "status": "pending_test", "summary": summary, "result_ref": result_ref, "next": "等待主 IDE 独立验证"}
    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, separators=(",", ":"))}]}


def handle_fail_delegated_task(arguments):
    task_id = str(arguments.get("task_id") or "").strip()
    error = str(arguments.get("error") or "").strip()
    if not task_id or not error:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 task_id 或 error"}]}
    runtime = get_runtime()
    current = runtime.get_task(task_id)
    if not current or current.get("source") != "primary_ide":
        return {"isError": True, "content": [{"type": "text", "text": "未找到主 IDE 委派任务"}]}
    if current.get("status") not in {"running", "dispatched"}:
        return {"isError": True, "content": [{"type": "text", "text": f"任务当前状态 {current.get('status')} 不允许失败回传"}]}
    result_ref = str(arguments.get("result_ref") or "").strip()
    task = runtime.mark_task_failed(task_id, error=error)
    if result_ref:
        task = runtime.update_task(task_id, result_ref=result_ref)
    result = {"task_id": task_id, "status": "failed", "error": error, "result_ref": result_ref or None}
    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, separators=(",", ":"))}]}


def handle_verify_delegated_task(arguments):
    task_id = (arguments.get("task_id") or "").strip()
    verification_summary = str(arguments.get("verification_summary") or "").strip()
    if not task_id or not verification_summary:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 task_id 或 verification_summary"}]}
    runtime = get_runtime()
    current = runtime.get_task(task_id)
    if not current or current.get("source") != "primary_ide":
        return {"isError": True, "content": [{"type": "text", "text": "未找到主 IDE 委派任务"}]}
    if current.get("status") != "pending_test":
        return {"isError": True, "content": [{"type": "text", "text": f"仅 pending_test 任务可验证，当前为 {current.get('status')}"}]}
    if (current.get("metadata") or {}).get("result_ref_required") and not current.get("result_ref"):
        return {"isError": True, "content": [{"type": "text", "text": "员工任务缺少 result_ref，不能标记完成"}]}
    metadata = dict(current.get("metadata") or {})
    metadata["manager_verification"] = verification_summary
    runtime.update_task(task_id, metadata=metadata)
    task = runtime.confirm_task_done(task_id)
    if not task:
        return {"isError": True, "content": [{"type": "text", "text": "任务不存在或无法验证"}]}
    result = {"task_id": task_id, "status": "done", "verification_summary": verification_summary}
    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, separators=(",", ":"))}]}

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
            "name": "get_aidelink_workflow",
            "description": "获取主 IDE 经理或辅助 IDE 员工的最小协作步骤，避免加载完整历史",
            "inputSchema": {"type": "object", "properties": {
                "role": {"type": "string", "enum": ["manager", "worker"], "default": "manager"}
            }},
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
                "result_ref": {"type": "string"},
                "include_stopped": {"type": "boolean", "default": False},
                "candidate_limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5}
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
            "description": "辅助 IDE 回传执行摘要和证据引用，任务进入 pending_test 等待主 IDE 验证",
            "inputSchema": {"type": "object", "properties": {
                "task_id": {"type": "string"}, "summary": {"type": "string"}, "result_ref": {"type": "string"}
            }, "required": ["task_id", "summary", "result_ref"]},
        },
        {
            "name": "fail_delegated_aidelink_task",
            "description": "辅助 IDE 无法完成任务时回传失败原因和已有证据，释放 IDE 占用",
            "inputSchema": {"type": "object", "properties": {
                "task_id": {"type": "string"}, "error": {"type": "string"}, "result_ref": {"type": "string"}
            }, "required": ["task_id", "error"]},
        },
        {
            "name": "verify_delegated_aidelink_task",
            "description": "主 IDE 独立检查 result_ref 后确认 pending_test 员工任务，标记为 done",
            "inputSchema": {"type": "object", "properties": {
                "task_id": {"type": "string"}, "verification_summary": {"type": "string"}
            }, "required": ["task_id", "verification_summary"]},
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
        elif tool_name == "get_aidelink_workflow":
            result = handle_get_workflow(arguments)
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
        elif tool_name == "fail_delegated_aidelink_task":
            result = handle_fail_delegated_task(arguments)
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
