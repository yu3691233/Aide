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
    """List configured IDEs as equal task targets, preferring open idle instances."""
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
        candidates.append({
            "key": key,
            "name": item.get("name") or key,
            "running": bool(running.get(key, False)),
            "status": state.get("status") or "idle",
            "available": bool(available),
        })
    candidates = [
        item for item in candidates
        if item["running"] or include_stopped
    ]
    candidates.sort(key=lambda item: (
        not (item["running"] and item["available"]),
        not item["running"],
        not item["available"],
        item["name"].lower(),
    ))
    recommended = next((
        item["key"] for item in candidates
        if item["running"] and item["available"]
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
            {"id": "complete_here", "label": "在当前 IDE 继续完成"},
            {"id": "new_session", "label": "创建新会话接力", "requires_user_confirmation": True},
            {"id": "delegate", "label": "选择任意 IDE 派发", "requires_user_confirmation": True},
        ],
    }
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]}


def _worker_task_prompt(task_id, text, task_type, main_owned_paths, owned_paths):
    return "\n".join([
        "[AideLink 协作任务]",
        f"task_id: {task_id}",
        f"task_type: {task_type}",
        f"目标: {text}",
        f"其他任务占用范围（禁止修改）: {json.dumps(main_owned_paths, ensure_ascii=False)}",
        f"本任务可修改范围: {json.dumps(owned_paths, ensure_ascii=False)}",
        "完成要求: 只处理本任务；运行约定验证；不要自行把任务标记 done。",
        "成功回传: 调用 report_delegated_aidelink_task，提交 summary 和 result_ref。",
        "result_ref 示例: commit:<sha>、file:<path>、test:<command/result>、inline:<evidence>。",
        "失败回传: 调用 fail_delegated_aidelink_task，说明 error 和已有 result_ref。",
        "发起任务的会话将读取回传、独立验证，再调用 verify_delegated_aidelink_task 完成任务。",
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
            "delegated_by": "ide_session",
            "worker_role": "collaborator",
            "task_type": task_type,
            "main_owned_paths": main_owned_paths,
            # validation 与 _compact_task_package 同源（validation_commands），
            # 写入 metadata 让 get_delegated_task 能结构化返回，员工不必解析 prompt。
            "validation": _string_list(arguments.get("validation_commands")),
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
    # 补齐结构化字段：员工不再需要解析 prompt 文本获取 main_owned_paths/validation/task_type。
    # 来源优先从 metadata 提取（delegate_task 写入位置），缺失时回退到空值，不破坏旧任务兼容。
    metadata = task.get("metadata") or {}
    payload["main_owned_paths"] = metadata.get("main_owned_paths", [])
    payload["validation"] = metadata.get("validation", [])
    payload["task_type"] = metadata.get("task_type", "research")
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
    current_status = current.get("status")
    requires_ref = bool((current.get("metadata") or {}).get("result_ref_required"))
    if requires_ref and not result_ref:
        return {"isError": True, "content": [{"type": "text", "text": "缺少 result_ref；请提供 commit/file/test/inline 证据引用"}]}

    if current_status in {"running", "dispatched"}:
        # 正常回传：进入 pending_test 等待主 IDE 验证。
        task = runtime.mark_task_done(task_id, summary=summary, result_ref=result_ref or None)
        if not task:
            return {"isError": True, "content": [{"type": "text", "text": "未找到任务或回传失败"}]}
        result = {"task_id": task_id, "status": "pending_test", "summary": summary, "result_ref": result_ref, "next": "等待主 IDE 独立验证"}
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, separators=(",", ":"))}]}

    if current_status == "pending_test":
        # 补报路径：仅当任务被自动完成路径推进到 pending_test 且 result_ref 仍为空（死锁）时允许。
        # 已有有效 result_ref 的 pending_test 任务禁止覆盖，交主 IDE verify 决策。
        # verify 闭环对 result_ref 的硬要求不变（handle_verify_delegated_task L379-380）。
        if current.get("result_ref"):
            return {"isError": True, "content": [{"type": "text", "text": "任务已有 result_ref，补报路径不允许覆盖；请等待主 IDE 验证"}]}
        task = runtime.update_task(task_id, summary=summary, result_ref=result_ref or None)
        if not task:
            return {"isError": True, "content": [{"type": "text", "text": "补报失败：任务不存在或写入失败"}]}
        result = {"task_id": task_id, "status": "pending_test", "summary": summary, "result_ref": result_ref, "next": "已补报 result_ref，等待主 IDE 独立验证"}
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, separators=(",", ":"))}]}

    return {"isError": True, "content": [{"type": "text", "text": f"任务当前状态 {current_status} 不允许员工回传"}]}


def handle_fail_delegated_task(arguments):
    task_id = str(arguments.get("task_id") or "").strip()
    error = str(arguments.get("error") or "").strip()
    if not task_id or not error:
        return {"isError": True, "content": [{"type": "text", "text": "缺少必填参数 task_id 或 error"}]}
    runtime = get_runtime()
    current = runtime.get_task(task_id)
    if not current or current.get("source") != "primary_ide":
        return {"isError": True, "content": [{"type": "text", "text": "未找到主 IDE 委派任务"}]}
    current_status = current.get("status")
    # pending_test 仅当 result_ref 缺失（死锁）时允许失败回传释放给主 IDE；
    # 已有有效 result_ref 的 pending_test 任务禁止降级为 failed，交主 IDE verify 决策。
    if current_status == "pending_test" and current.get("result_ref"):
        return {"isError": True, "content": [{"type": "text", "text": "任务已有 result_ref，pending_test 不允许降级为 failed；请等待主 IDE 验证"}]}
    if current_status not in {"running", "dispatched", "pending_test"}:
        return {"isError": True, "content": [{"type": "text", "text": f"任务当前状态 {current_status} 不允许失败回传"}]}
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


def _bridge_get_json(path, timeout=10):
    """GET helper that returns parsed JSON or raises URLError/ValueError."""
    bridge_url = os.environ.get("AIDELINK_BRIDGE_URL", "http://127.0.0.1:5000").rstrip("/")
    req = urllib.request.Request(f"{bridge_url}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _bridge_post_json(path, payload, timeout=90):
    """POST helper that returns parsed JSON. Raises HTTPError/URLError/ValueError."""
    bridge_url = os.environ.get("AIDELINK_BRIDGE_URL", "http://127.0.0.1:5000").rstrip("/")
    req = urllib.request.Request(
        f"{bridge_url}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def handle_adb_install_project_apk(arguments):
    """One-click APK install: resolve device → ensure ADB → install APK on target project.

    Requires user_confirmed=true (high-risk write op). All HTTP calls hit the local
    AideLink bridge which owns enable-wireless push and ADB install workflows.

    Resolution order:
      1. alias provided & found in /api/devices aliases → use alias's ip/port
      2. alias missing or not found, but ip provided & active in /api/debug/connected → use ip
      3. alias missing, ip missing, exactly one active IP → use it automatically
      4. alias missing, ip missing, multiple active IPs → return list, ask user
    """
    if arguments.get("user_confirmed") is not True:
        return {
            "isError": True,
            "content": [{"type": "text", "text": "缺少 user_confirmed=true，本工具是高风险写操作，必须用户明确同意后才能执行"}],
        }

    alias = (arguments.get("alias") or "").strip()
    explicit_ip = (arguments.get("ip") or "").strip()

    project_path = (arguments.get("project_path") or "").strip()
    apk_path = (arguments.get("apk_path") or "").strip()
    try:
        timeout = int(arguments.get("timeout") or 60)
    except (TypeError, ValueError):
        timeout = 60
    timeout = max(15, min(timeout, 180))

    # 1. Resolve device: try alias first, fallback to /api/debug/connected active IPs.
    try:
        devices_payload = _bridge_get_json("/api/devices", timeout=10)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"isError": True, "content": [{"type": "text", "text": f"查询设备列表失败 ({exc.code}): {detail}"}]}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"isError": True, "content": [{"type": "text", "text": f"无法连接 AideLink 服务: {exc}"}]}

    aliases = (devices_payload or {}).get("aliases") or {}
    device_entry = aliases.get(alias) if alias else None

    resolved_alias = None
    resolved_ip = None
    resolved_port = None

    if device_entry:
        resolved_alias = alias
        resolved_ip = device_entry.get("ip") or explicit_ip
        resolved_port = device_entry.get("port")
    else:
        # fallback：查活跃 IP 列表
        try:
            active_payload = _bridge_get_json("/api/debug/connected", timeout=10)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            active_payload = {}
        # active_payload: {ip: "Ns ago"}，过滤出 120s 内活跃的
        active_ips = []
        for ip_key, ago_text in (active_payload or {}).items():
            try:
                seconds = float(str(ago_text).split("s")[0])
            except (ValueError, IndexError):
                seconds = 999
            if seconds <= 120:
                active_ips.append((ip_key, seconds))
        active_ips.sort(key=lambda x: x[1])  # 最近活跃优先

        if explicit_ip:
            resolved_ip = explicit_ip
            for a, info in aliases.items():
                if info.get("ip") == explicit_ip or explicit_ip in (info.get("ips") or []):
                    resolved_alias = a
                    if not resolved_port:
                        resolved_port = info.get("port")
                    break
        elif active_ips:
            if len(active_ips) == 1:
                resolved_ip = active_ips[0][0]
                for a, info in aliases.items():
                    if info.get("ip") == resolved_ip or resolved_ip in (info.get("ips") or []):
                        resolved_alias = a
                        if not resolved_port:
                            resolved_port = info.get("port")
                        break
            else:
                listing = "\n".join(f"- {ip} (last seen {ago:.0f}s ago)" for ip, ago in active_ips)
                return {
                    "isError": True,
                    "content": [{"type": "text", "text": (
                        f"检测到 {len(active_ips)} 台活跃设备，请用 ip 参数指定目标设备：\n{listing}\n"
                        "或者在 web 端 /settings 设备管理里给目标设备设置 alias 后传 alias 参数。"
                    )}],
                }
        else:
            available = ", ".join(sorted(aliases.keys())) or "(无)"
            return {
                "isError": True,
                "content": [{"type": "text", "text": (
                    f"alias={alias or '(空)'} 未找到，且 /api/debug/connected 无活跃 IP。"
                    f"已配置别名: {available}。"
                    "请确认 App 在前台且已通过 AideLink 服务保持在线（events/stream 心跳）。"
                )}],
            }

    if not resolved_ip:
        return {
            "isError": True,
            "content": [{"type": "text", "text": "无法解析目标设备 IP：alias 和 ip 均未提供有效值"}],
        }

    if not resolved_port:
        try:
            resolved_port = int(arguments.get("port") or 5555)
        except (TypeError, ValueError):
            resolved_port = 5555

    # 2. Fetch settings (used both for default current_project and whitelist check).
    settings_payload = {}
    try:
        settings_payload = _bridge_get_json("/settings", timeout=10)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        settings_payload = {}
    settings_root = (settings_payload or {}).get("settings") or {}

    # 3. Resolve project_path: default to current_project.
    if not project_path:
        project_path = (settings_root.get("current_project") or "").strip()

    if not project_path:
        return {
            "isError": True,
            "content": [{"type": "text", "text": (
                "未指定 project_path 且无法从 /api/settings 读取 current_project，请显式传入 project_path"
            )}],
        }

    # 4. Verify project_path is in settings.projects whitelist.
    projects = settings_root.get("projects") or []
    if not any(str(item.get("path", "")).strip().lower() == project_path.lower() for item in projects):
        available_paths = ", ".join(str(item.get("path", "")) for item in projects) or "(空)"
        return {
            "isError": True,
            "content": [{"type": "text", "text": (
                f"目标项目 {project_path} 不在 settings.projects 白名单。可用: {available_paths}。"
                "请在 web 端 /settings 项目管理里添加。"
            )}],
        }

    # 4. Ensure ADB device: /api/adb/connect (server publishes enable-wireless + waits App report).
    # alias 优先传给服务端（让 _ensure_adb_device 走 alias 的 ips 候选）；
    # 否则用 ip + port 直接走服务端的 _publish_wireless_request 链路。
    connect_request = {"timeout": timeout}
    if resolved_alias:
        connect_request["alias"] = resolved_alias
    else:
        connect_request["ip"] = resolved_ip
        connect_request["port"] = resolved_port
    try:
        connect_payload = _bridge_post_json(
            "/api/adb/connect",
            connect_request,
            timeout=timeout + 10,
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            err_msg = json.loads(detail).get("error") or detail
        except json.JSONDecodeError:
            err_msg = detail or str(exc)
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"[ensure_device] ADB 连接失败: {err_msg}"}],
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"[ensure_device] 无法连接 AideLink 服务: {exc}"}],
        }

    if not connect_payload.get("ok"):
        # 诊断：查询目标设备当前 AideLink 在线/ADB 连接状态，帮助用户判断失败原因
        diag_hint = ""
        try:
            diag_payload = _bridge_get_json("/api/devices", timeout=5)
            diag_devices = (diag_payload or {}).get("devices") or []
            target_dev = None
            for d in diag_devices:
                if (resolved_alias and d.get("alias") == resolved_alias) or \
                   (resolved_ip and (d.get("ip") == resolved_ip or resolved_ip in (d.get("ips") or []))):
                    target_dev = d
                    break
            if target_dev:
                import time as _diag_time
                aide_online = "在线" if target_dev.get("is_online") else "离线"
                adb_conn = "已连接" if target_dev.get("is_adb_connected") else "未连接"
                last_ts = target_dev.get("last_active") or 0
                ago = f"{int(_diag_time.time() - last_ts)}s 前" if last_ts else "无记录"
                diag_hint = (
                    f"\n诊断：AideLink={aide_online}，ADB={adb_conn}，最后活跃={ago}。"
                )
                if target_dev.get("is_online") and not target_dev.get("is_adb_connected"):
                    diag_hint += "AideLink 在线但 ADB 未恢复——可能是 App 在后台无法响应 enable-wireless 命令，或无线调试被系统限制。建议：将 App 切到前台后重试，或在设备上手动开启无线调试。"
                elif not target_dev.get("is_online"):
                    diag_hint += "AideLink 离线——App 未运行或网络不通。建议：在设备上打开 AideLink App。"
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            pass
        return {
            "isError": True,
            "content": [{"type": "text", "text": (
                f"[ensure_device] alias={resolved_alias or '(无)'} ip={resolved_ip} 无法建立 ADB 连接: "
                f"{connect_payload.get('error', '未知错误')}。"
                f"{diag_hint}"
                "请确认 App 处于前台、无线调试开关可用，并重试。"
            )}],
        }

    device_ip = connect_payload.get("ip") or resolved_ip
    device_port = int(connect_payload.get("port") or resolved_port)

    # 5. Install APK via /api/adb/project-install.
    install_payload = {"ip": device_ip, "port": device_port, "project_path": project_path}
    if apk_path:
        install_payload["apk_path"] = apk_path
    try:
        install_resp = _bridge_post_json(
            "/api/adb/project-install",
            install_payload,
            timeout=timeout + 30,
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            err_msg = json.loads(detail).get("error") or detail
        except json.JSONDecodeError:
            err_msg = detail or str(exc)
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"[install] 安装失败: {err_msg}"}],
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "isError": True,
            "content": [{"type": "text", "text": f"[install] 无法连接 AideLink 服务: {exc}"}],
        }

    if not install_resp.get("ok"):
        return {
            "isError": True,
            "content": [{"type": "text", "text": (
                f"[install] alias={resolved_alias or '(无)'} ip={device_ip} APK 安装失败: "
                f"{install_resp.get('error', '未知错误')}"
            )}],
        }

    success = {
        "ok": True,
        "alias": resolved_alias,
        "ip": device_ip,
        "port": device_port,
        "device": connect_payload.get("device") or f"{device_ip}:{device_port}",
        "project_path": project_path,
        "apk_path": install_resp.get("apk_path") or apk_path,
        "application_id": install_resp.get("application_id", ""),
        "method": connect_payload.get("method", "adb_connect"),
        "install_output": (install_resp.get("output") or "").strip(),
        "message": install_resp.get("message") or "APK 安装完成",
    }
    return {"content": [{"type": "text", "text": json.dumps(success, ensure_ascii=False, indent=2)}]}


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
        {
            "name": "adb_install_project_apk",
            "description": (
                "一键安装目标项目 APK：通过 alias 或 ip 识别目标设备，"
                "自动启用无线调试 + adb connect + 安装 + 启动 launcher。"
                "必须 user_confirmed=true。设备解析顺序："
                "1) alias 已配置 → 用 alias；"
                "2) alias 缺失或未找到 + ip 提供 → 用 ip；"
                "3) alias/ip 都缺 + 仅一台活跃设备 → 自动选用；"
                "4) alias/ip 都缺 + 多台活跃设备 → 返回列表让用户指定 ip。"
            ),
            "inputSchema": {"type": "object", "properties": {
                "alias": {"type": "string", "description": "可选；设备别名（用户在 web 端 /settings 设备管理里设置）"},
                "ip": {"type": "string", "description": "可选；目标设备 IP（与 alias 二选一；alias 未配置时用此字段）"},
                "port": {"type": "integer", "minimum": 1, "maximum": 65535, "default": 5555,
                            "description": "可选；目标设备无线调试端口，默认 5555"},
                "project_path": {"type": "string", "description": "目标项目路径，默认走 settings.current_project"},
                "apk_path": {"type": "string", "description": "可选 APK 绝对路径；省略时取 project 下 primary_apk"},
                "timeout": {"type": "integer", "minimum": 15, "maximum": 180, "default": 60,
                            "description": "等待 enable-wireless + adb connect + install 的总超时（秒）"},
                "user_confirmed": {"type": "boolean", "description": "高风险写操作必须 ===true"},
            }, "required": ["user_confirmed"]},
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
        elif tool_name == "adb_install_project_apk":
            result = handle_adb_install_project_apk(arguments)
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
