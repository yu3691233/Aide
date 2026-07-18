import os

import sys

import re

import json

import time

import hashlib

import logging

import subprocess

import threading

from pathlib import Path

from collections import defaultdict

from datetime import datetime



from flask import Blueprint, request, jsonify

from paths import BRIDGE_DIR as BASE_DIR, PROJECT_ROOT



task_bp = Blueprint('tasks', __name__)


def _task_type_for_list(task):
    """Classify persisted tasks without hiding legacy records lacking task_type."""
    explicit_type = (task.get("task_type") or "").strip().lower()
    if explicit_type:
        return explicit_type
    metadata = task.get("metadata") or {}
    if metadata.get("content_kind") == "inspiration":
        return "inspiration"
    metadata_type = (metadata.get("task_type") or "").strip().lower()
    if metadata_type:
        return metadata_type
    title = task.get("title", "") or ""
    if "bug" in title.lower() or metadata.get("bug_signature"):
        return "bug_fix"
    return "task"



from json_utils import safe_read_json, safe_write_json

from routes.task_routes_helpers import (
    _get_merged_dispatch_ids,
    _load_queue,
    _read_task_data,
    _save_queue,
)

from routes.task_routes_history import _save_prompt_history

from routes.task_routes_injection import _inject_to_ide

from routes.task_routes_scanner import (
    scan_logs_for_errors_and_create_tasks as _scan_logs_for_errors_and_create_tasks,
)

from routes.task_routes_prompt import build_prompt_candidates, read_prompt_history
from task_contracts import task_allowed_actions





def _get_current_version():

    from version_utils import detect_app_version

    return detect_app_version()



logger = logging.getLogger('manager')

from routes import task_routes_flow  # noqa: F401
from routes import task_routes_management  # noqa: F401
from routes import task_routes_workflow  # noqa: F401


def _import_manager_utils():

    from manager_utils import safe_load_tasks, LOG_FILE

    return safe_load_tasks, LOG_FILE


def map_task_for_client(t):
    """将 state/tasks.json 格式映射为前端期望的字段名。"""
    t = dict(t)
    t["message"] = t.pop("text", t.get("message", ""))
    t["text"] = t["message"]
    if "time" not in t and "created_at" in t:
        t["time"] = t["created_at"]
    if not t.get("task_type"):
        t["task_type"] = _task_type_for_list(t)
    t["version"] = t.get("app_version") or t.get("version") or ""
    metadata = t.get("metadata") or {}
    if "feedbacks" not in t and "feedbacks" in metadata:
        t["feedbacks"] = metadata["feedbacks"]
    t["device_label"] = metadata.get("device_label", "")
    delegated = t.get("source") == "primary_ide" or metadata.get("delegated_by") == "primary_ide"
    t["task_origin"] = "agent" if delegated else "user"
    t["task_origin_label"] = "Agent任务" if delegated else "用户任务"
    t["allowed_actions"] = task_allowed_actions(t)
    return t





# ============================================================

def _dispatch_next_in_queue(target_ide, queue_file, queue, contexts, task_file, task_data, runtime):

    """派发队列中的下一个任务"""

    if not queue:

        return



    task = queue[0]

    tid = task["task_id"]

    message = task["message"]

    now = datetime.now().isoformat()



    inject_ok, inject_detail = _inject_to_ide(target_ide, message, tid)



    if not inject_ok:

        logger.error(f"Queue dispatch failed for {tid}: {inject_detail}")

        if tid in contexts:

            contexts[tid]["status"] = "failed"

            contexts[tid]["error"] = inject_detail

        queue.pop(0)

        task_data["contexts"] = contexts

        safe_write_json(task_file, task_data)

        _save_queue(queue_file, queue)

        # 尝试下一个

        if queue:

            _dispatch_next_in_queue(target_ide, queue_file, queue, contexts, task_file, task_data, runtime)

        return



    # 更新状态

    runtime.mark_task_running(tid, target_ide)

    runtime.set_ide_status(target_ide, "busy", current_task_id=tid)

    if tid in contexts:

        contexts[tid]["status"] = "dispatched"

        contexts[tid]["dispatched_at"] = now

        contexts[tid]["response_preview"] = "正在执行..."



    # 保存

    task_data["contexts"] = contexts

    safe_write_json(task_file, task_data)



    _save_queue(queue_file, queue)




# ============================================================

# Route: POST /api/admin/scan_bugs

# ============================================================



@task_bp.route("/api/admin/scan_bugs", methods=["POST"])

def api_admin_scan_bugs():

    """手动触发 bug 日志扫描。

    前端 / /api/tasks 不再隐式扫描，避免每次拉任务列表都扫全量日志。
    由 watchdog 周期任务或运维手动调用；只有当 scan_logs_for_errors_and_create_tasks
    的 BUG_REPEAT_THRESHOLD 阈值被同签名累计到才建任务。
    """

    force = False

    try:

        payload = request.get_json(silent=True) or {}

        force = bool(payload.get("force", False))

    except Exception:

        force = False

    result = _scan_logs_for_errors_and_create_tasks(force=force)

    return jsonify({"ok": True, **result})



# ============================================================

# Route: POST /api/prompt/predict

# ============================================================



@task_bp.route("/api/prompt/predict", methods=["POST"])

def api_prompt_predict():

    """使用 Aide 生成3个预测提示词候选"""

    try:

        data = request.get_json(force=True)
        file_path = data.get("file", "")
        name = data.get("name", "")
        desc = data.get("desc", "")
        category = data.get("category", "feature")
        user_req = data.get("user_req", "")
        line_start_param = data.get("line_start")
        line_end_param = data.get("line_end")

        choices, nodes = build_prompt_candidates(
            file_path=file_path,
            name=name,
            desc=desc,
            category=category,
            user_req=user_req,
            line_start_param=line_start_param,
            line_end_param=line_end_param,
            logger=logger,
        )
        _save_prompt_history(nodes, category, user_req, choices)
        return jsonify({"success": True, "candidates": choices})

    except Exception as e:

        return jsonify({"success": False, "message": str(e)})





# ============================================================

# Route: GET /api/prompt/history

# ============================================================



@task_bp.route("/api/prompt/history", methods=["GET"])

def api_prompt_history():

    """获取提示词生成历史"""
    try:
        return jsonify({"success": True, "history": read_prompt_history()})

    except Exception as e:

        return jsonify({"success": False, "message": str(e), "history": []})





# ============================================================

# Route: POST /api/tasks/create_draft

# ============================================================



@task_bp.route("/tasks/create", methods=["POST"])
@task_bp.route("/api/tasks/create", methods=["POST"])

def api_tasks_create():

    """APP 端创建任务（兼容 /send 格式）"""

    data = request.get_json(force=True)

    text = data.get("text", "").strip()

    title = data.get("title", "").strip() if data.get("title") else ""

    target_ide = data.get("target_ide", "auto").strip()

    auto_dispatch = data.get("auto_dispatch", True)



    if not text:

        return jsonify({"ok": False, "message": "任务内容不能为空"}), 400



    from shared_runtime import runtime

    task = runtime.create_task(

        text=text,

        title=title or text[:60],

        source="app",

        target_ide=target_ide if target_ide != "auto" else None,

        metadata={"created_from": "app"},

    )



    # 后台异步生成任务标题（不阻塞响应）
    if not title:
        def _gen_title(tid, raw_text):
            try:
                from model_registry import call_model, get_default_model
                model_key = get_default_model()
                resp = call_model(model_key, [
                    {"role": "system", "content": "你是一个任务标题生成器。根据用户输入的任务描述，生成一个简短的中文标题（不超过20个字），只返回标题文本，不要任何解释或引号。"},
                    {"role": "user", "content": raw_text[:2000]},
                ], max_tokens=60, timeout=30)
                if resp.get("ok") and resp.get("content", "").strip():
                    generated = resp["content"].strip().split("\n")[0].strip()[:40]
                    runtime.update_task(tid, title=generated)
                    print(f"[Title] Generated title for {tid}: {generated}", flush=True)
            except Exception as e:
                print(f"[Title] Failed to generate title for {tid}: {e}", flush=True)

        threading.Thread(
            target=_gen_title,
            args=(task["task_id"], text),
            daemon=True,
        ).start()



    if auto_dispatch and target_ide != "auto":

        from dispatch_utils import dispatch_task

        ok, reply = dispatch_task(task, runtime)

        if not ok:
            # 未派发成功的 App 任务不保留为服务端失败任务；手机端会继续持有离线副本。
            tasks = [item for item in runtime.read_tasks() if item.get("task_id") != task["task_id"]]
            runtime.write_tasks(tasks)
            return jsonify({"ok": False, "message": reply}), 503

        return jsonify({"ok": ok, "task_id": task["task_id"], "reply": reply})



    return jsonify({"ok": True, "task_id": task["task_id"]})


@task_bp.route("/api/tasks/inspiration", methods=["POST"])
def api_tasks_create_inspiration():
    """Create an unassigned project inspiration through the bridge process."""
    data = request.get_json(force=True)
    text = str(data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "message": "灵感内容不能为空"}), 400

    from shared_runtime import runtime
    task = runtime.create_task(
        text=text,
        title=str(data.get("title") or text[:40]).strip(),
        source="primary_ide",
        target_ide=None,
        priority=str(data.get("priority") or "medium"),
        metadata={"created_via": "mcp", "content_kind": "inspiration"},
    )
    return jsonify({"ok": True, "task": task})





@task_bp.route("/api/tasks/create_draft", methods=["POST"])

def api_tasks_create_draft():

    """手动创建一个任务草稿/待办，直接使用用户提供的内容"""

    safe_load_tasks, _ = _import_manager_utils()

    data = request.get_json(force=True)

    message = data.get("message", "").strip()

    task_type = data.get("task_type", "code")

    parent_task_id = data.get("parent_task_id", "").strip()



    if not message:

        return jsonify({"success": False, "message": "任务内容不能为空"})



    task_file = BASE_DIR / "task_context.json"

    task_data = safe_load_tasks(task_file)

    contexts = task_data.setdefault("contexts", {})



    current_version = _get_current_version()



    # 提取标题：取第一行或前30字

    title = message.split('\n')[0].strip()[:30]

    task_sig = f"manual:{time.time()}:{message[:30]}"

    task_id = "task-" + hashlib.md5(task_sig.encode("utf-8")).hexdigest()[:8]



    new_task = {

        "task_id": task_id,

        "message": message,

        "message_keywords": ["manual", task_type],

        "response_preview": "等待派发中...",

        "all_keywords": ["manual"],

        "task_type": task_type,

        "model_used": "User Manual",

        "status": "pending",

        "version": current_version,

        "time": datetime.now().isoformat(),

        "title": title,

        "sub_tasks_count": 0

    }



    if parent_task_id:

        new_task["parent_task_id"] = parent_task_id



    contexts[task_id] = new_task



    task_data["updated_at"] = datetime.now().isoformat()

    try:

        safe_write_json(task_file, task_data)

        return jsonify({"success": True, "message": "成功加入任务列表！", "task_id": task_id})

    except Exception as e:

        return jsonify({"success": False, "message": f"创建任务失败: {e}"})







# ============================================================

# Route: GET /api/tasks

# ============================================================



@task_bp.route("/api/tasks")

def api_tasks():

    """获取历史任务与委派列表，支持 keyword/target_ide/status/since 过滤"""



    from task_runtime import TaskRuntime

    runtime = TaskRuntime(BASE_DIR)



    # 直接从 runtime tasks 读取（统一状态机）

    tasks_list = runtime.read_tasks()



    # ---- 搜索 / 过滤 ----

    keyword = request.args.get("keyword", "").strip()

    target_ide = request.args.get("target_ide", "").strip()

    status_param = request.args.get("status", "").strip()

    since = request.args.get("since", "").strip()



    # keyword: 大小写不敏感匹配 title 或 text

    if keyword:

        kw_lower = keyword.lower()

        tasks_list = [

            t for t in tasks_list

            if kw_lower in (t.get("title") or "").lower()

            or kw_lower in (t.get("text") or "").lower()

        ]



    # target_ide: 精确匹配

    if target_ide:

        tasks_list = [t for t in tasks_list if t.get("target_ide") == target_ide]



    # status: 支持逗号分隔多个状态

    if status_param:

        statuses = [s.strip() for s in status_param.split(",") if s.strip()]

        tasks_list = [t for t in tasks_list if t.get("status") in statuses]



    # since: ISO 时间字符串，过滤 created_at >= since

    if since:

        tasks_list = [t for t in tasks_list if (t.get("created_at") or "") >= since]


    # project: 过滤到指定项目（无 project 字段的旧任务全部匹配）

    project_filter = request.args.get("project", "").strip()

    if project_filter:
        def _norm_project_path(value):
            return os.path.normcase(os.path.normpath(str(value).replace("\\", "/")))

        normalized_filter = _norm_project_path(project_filter)
        tasks_list = [
            t for t in tasks_list
            if not t.get("project") or _norm_project_path(t.get("project")) == normalized_filter
        ]



    # 字段映射：兼容前端期望的字段名

    tasks_list = [map_task_for_client(t) for t in tasks_list]
    tasks_list = [t for t in tasks_list if (t.get("task_type") or "").lower() != "chat"]

    tasks_list.sort(key=lambda x: x.get("created_at", x.get("time", "")), reverse=True)

    return jsonify({"success": True, "tasks": tasks_list})




# ============================================================

# Route: POST /api/tasks/migrate-project

# ============================================================

@task_bp.route("/api/tasks/migrate-project", methods=["POST"])

def api_tasks_migrate_project():

    """将无 project 字段的旧任务设到指定项目"""

    data = request.get_json(force=True, silent=True) or {}

    target_project = data.get("project", "aidelink")

    from task_runtime import TaskRuntime

    runtime = TaskRuntime(BASE_DIR)

    tasks = runtime.read_tasks()

    migrated = 0

    for t in tasks:

        if not t.get("project"):

            t["project"] = target_project

            migrated += 1

    if migrated:

        runtime.write_tasks(tasks)

    return jsonify({"success": True, "migrated": migrated, "project": target_project})



# ============================================================

# Route: DELETE /api/tasks/<task_id>

# ============================================================



@task_bp.route("/tasks/<task_id>", methods=["DELETE"])
@task_bp.route("/api/tasks/<task_id>", methods=["DELETE"])

def api_tasks_delete(task_id):

    """删除指定任务"""

    from shared_runtime import runtime

    try:

        tasks = runtime.read_tasks()
        task = next((t for t in tasks if t.get("task_id") == task_id), None)
        if not task:
            return jsonify({"success": False, "message": f"任务 {task_id} 不存在"}), 404
        runtime.release_leases(task_id)
        target_ide = task.get("target_ide")
        from task_runtime import SUPPORTED_IDES

        if target_ide in SUPPORTED_IDES:
            current = runtime.get_ide_status(target_ide)
            if current and current.get("current_task_id") == task_id:
                runtime.release_ide(target_ide)
        tasks = [t for t in tasks if t.get("task_id") != task_id]
        runtime.write_tasks(tasks)
        return jsonify({"success": True, "message": "任务已删除"})

    except Exception as e:

        return jsonify({"success": False, "message": str(e)}), 500





@task_bp.route("/tasks/<task_id>/assign", methods=["POST"])
@task_bp.route("/api/tasks/<task_id>/assign", methods=["POST"])

def api_tasks_assign(task_id):

    """将任务分配给指定 IDE 并派发"""

    data = request.get_json(force=True)

    target_ide = data.get("target_ide", "").strip()

    if not target_ide:

        return jsonify({"success": False, "message": "缺少 target_ide"}), 400



    from shared_runtime import runtime

    task = runtime.assign_task(task_id, target_ide)

    if not task:

        return jsonify({"success": False, "message": f"任务分配失败或 IDE 不支持"}), 400



    return jsonify({"success": True, "message": f"已分配到 {target_ide}"})





# ============================================================

# Route: POST /api/tasks/<task_id>/retry

# ============================================================



@task_bp.route("/tasks/<task_id>/retry", methods=["POST"])
@task_bp.route("/api/tasks/<task_id>/retry", methods=["POST"])

def api_tasks_retry(task_id):

    """重试失败或超时的任务"""

    from task_runtime import TaskRuntime

    runtime = TaskRuntime(BASE_DIR)



    task = runtime.get_task(task_id)

    if not task:

        return jsonify({"success": False, "message": f"任务 {task_id} 不存在"})



    status = task.get("status")

    if status not in ("failed", "timeout"):

        return jsonify({"success": False, "message": f"只能重试失败或超时的任务，当前状态: {status}"}), 400



    retry_count = task.get("retry_count", 0)

    if retry_count >= 3:

        return jsonify({"success": False, "message": "重试次数已达上限"}), 400



    target_ide = task.get("target_ide")

    if not target_ide:

        return jsonify({"success": False, "message": "任务未分配目标 IDE，无法重新派发"}), 400



    # 重置状态并增加重试计数

    runtime.update_task(

        task_id,

        status="queued",

        retry_count=retry_count + 1,

        error=None,

        queued_at=datetime.now().isoformat(),

    )



    # 重新加入目标 IDE 队列

    queue_file = BASE_DIR / "state" / f"task_queue_{target_ide}.json"

    queue = _load_queue(queue_file)

    queue.append({

        "task_id": task_id,

        "title": task.get("title", task_id),

        "message": task.get("text", ""),

        "queued_at": datetime.now().isoformat(),

    })

    _save_queue(queue_file, queue)



    return jsonify({"success": True, "message": "任务已重新加入队列"})








# 兼容和工作流路由已迁移到 routes/task_routes_workflow.py

