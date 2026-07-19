import hashlib
import logging
import threading
import time
from datetime import datetime

from flask import jsonify, request

from paths import BRIDGE_DIR as BASE_DIR
from event_bus import bus
from shared_runtime import read_history, write_history
from .task_routes_helpers import _get_merged_dispatch_ids, _load_queue, _read_task_data, _save_queue
from .task_routes_injection import _inject_to_ide
from .task_routes import task_bp


logger = logging.getLogger("manager")

_SURFACE_LABELS = {
    "android": "Android",
    "web": "Web",
    "windows": "Windows",
}


def _dispatch_prefix(dispatch_items):
    prefix = (
        "测试任务"
        if dispatch_items and all(
            bool((item.get("metadata") or {}).get("is_test"))
            for item in dispatch_items
        )
        else "派发任务"
    )
    surfaces = {
        str((item.get("metadata") or {}).get("surface") or "").strip().lower()
        for item in dispatch_items
    }
    surfaces.discard("")
    if len(surfaces) == 1 and all(
        str((item.get("metadata") or {}).get("surface") or "").strip().lower() in surfaces
        for item in dispatch_items
    ):
        surface = next(iter(surfaces))
        label = _SURFACE_LABELS.get(surface)
        if label:
            return f"[{prefix}-{label}]"
    return f"[{prefix}]"


def _publish_task_feedback(task_id, target_ide, title, feedback, message, fb_count):
    bus.publish("task.feedback", {
        "task_id": task_id,
        "ide": target_ide,
        "target_ide": target_ide,
        "title": title or task_id,
        "body": message,
        "feedback": feedback,
        "feedback_count": fb_count,
    })


def _record_test_result(runtime, test_task_id, outcome, summary, evidence=""):
    test_task = runtime.get_task(test_task_id)
    if not test_task:
        raise ValueError(f"测试任务 {test_task_id} 不存在")
    metadata = dict(test_task.get("metadata") or {})
    if not metadata.get("is_test"):
        raise ValueError(f"任务 {test_task_id} 不是测试任务")
    parent_task_id = test_task.get("parent_task_id") or metadata.get("source_task_id")
    parent_task = runtime.get_task(parent_task_id) if parent_task_id else None
    if not parent_task:
        raise ValueError("找不到测试任务对应的原任务")

    normalized_outcome = str(outcome or "").strip().lower()
    if normalized_outcome not in {"passed", "failed"}:
        raise ValueError("result 必须是 passed 或 failed")
    clean_summary = str(summary or "").strip()
    if not clean_summary:
        raise ValueError("summary 不能为空")

    now = datetime.now().isoformat()
    parent_metadata = dict(parent_task.get("metadata") or {})
    report = {
        "result": normalized_outcome,
        "summary": clean_summary,
        "evidence": str(evidence or "").strip(),
        "test_ide": test_task.get("target_ide") or "",
        "test_task_id": test_task_id,
        "tested_at": now,
    }
    reports = list(parent_metadata.get("test_reports") or [])
    reports.append(report)
    parent_metadata.update({
        "test_result": normalized_outcome,
        "test_summary": clean_summary,
        "test_evidence": report["evidence"],
        "test_ide": report["test_ide"],
        "test_task_id": test_task_id,
        "tested_at": now,
        "test_reports": reports[-20:],
    })
    runtime.update_task(
        parent_task_id,
        metadata=parent_metadata,
        updated_at=now,
    )
    runtime.update_task(
        test_task_id,
        summary=clean_summary,
        result_ref=report["evidence"] or f"inline:{clean_summary}",
        updated_at=now,
    )
    return parent_task_id, report


@task_bp.route("/api/tasks/test-result", methods=["POST"])
def api_tasks_test_result():
    """测试 IDE 回传验证结果，并写回原待测试任务。"""
    data = request.get_json(force=True)
    test_task_id = str(data.get("test_task_id") or "").strip()
    if not test_task_id:
        return jsonify({"success": False, "message": "缺少 test_task_id"}), 400

    from task_runtime import TaskRuntime

    runtime = TaskRuntime(BASE_DIR)
    try:
        parent_task_id, report = _record_test_result(
            runtime,
            test_task_id,
            data.get("result"),
            data.get("summary"),
            data.get("evidence"),
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    test_task = runtime.get_task(test_task_id) or {}
    test_ide = test_task.get("target_ide") or ""
    try:
        if test_task.get("status") in {"running", "dispatched"}:
            runtime.mark_task_done(
                test_task_id,
                summary=report["summary"],
                result_ref=report["evidence"] or f"inline:{report['summary']}",
            )
        if (runtime.get_task(test_task_id) or {}).get("status") == "pending_test":
            runtime.confirm_task_done(test_task_id, is_manual=True)
        if test_ide:
            queue_file = BASE_DIR / "state" / f"task_queue_{test_ide}.json"
            queue = [
                item for item in _load_queue(queue_file)
                if item.get("task_id") != test_task_id
            ]
            _save_queue(queue_file, queue)
            runtime.set_ide_status(test_ide, "idle", current_task_id=None)
    except Exception as exc:
        logger.warning("Test result recorded but child cleanup failed: %s", exc)

    return jsonify({
        "success": True,
        "parent_task_id": parent_task_id,
        "test_result": report["result"],
        "message": "测试结果已写回原任务",
    })


def _create_and_dispatch_test_task(runtime, task_id, test_ide, orig_task, callback_url):
    orig_message = orig_task.get("message", "")
    orig_title = orig_task.get("title", task_id)
    now = datetime.now().isoformat()
    test_task_id = f"test-{task_id}-{int(time.time())}"
    test_message = (
        f"## 测试任务（请勿修改代码）\n\n"
        f"请验证以上任务是否已正确完成。仅检查代码、运行测试并报告结果；"
        f"不要修改代码，也不要提交任何变更。\n\n"
        f"### 原始需求\n\n{orig_message}\n\n"
        f"### 测试要求\n\n"
        f"1. 请检查上述修改是否正确实现\n"
        f"2. 运行相关测试验证功能\n"
        f"3. 如发现问题，记录具体位置和现象\n"
        f"4. **不要修改任何代码**，只做验证\n\n"
        f"测试完成后，直接在聊天中报告测试结果。"
    )

    parent_full_task = runtime.get_task(task_id) or {}
    parent_metadata = dict(parent_full_task.get("metadata") or {})
    for field in (
        "test_result", "test_summary", "test_evidence",
        "test_ide", "test_task_id", "tested_at",
    ):
        parent_metadata.pop(field, None)
    runtime.update_task(task_id, metadata=parent_metadata, updated_at=now)

    tasks = runtime.read_tasks()
    tasks.append({
        "task_id": test_task_id,
        "parent_task_id": task_id,
        "title": f"[测试] {orig_title}",
        "text": test_message,
        "source": "manager-test",
        "target_ide": test_ide,
        "status": "queued",
        "priority": "medium",
        "image": None,
        "owned_paths": [],
        "worktree_path": None,
        "result_ref": None,
        "summary": None,
        "error": None,
        "metadata": {"source_task_id": task_id, "is_test": True},
        "created_at": now,
        "updated_at": now,
        "queued_at": now,
        "started_at": None,
        "completed_at": None,
    })
    runtime.write_tasks(tasks)

    queue_file = BASE_DIR / "state" / f"task_queue_{test_ide}.json"
    queue = _load_queue(queue_file)
    queue.append({
        "task_id": test_task_id,
        "title": f"[测试] {orig_title}",
        "message": test_message,
        "queued_at": now,
    })
    _save_queue(queue_file, queue)

    if len(queue) == 1:
        inject_ok, inject_detail = _inject_to_ide(test_ide, test_message, test_task_id)
        if inject_ok:
            runtime.mark_task_running(test_task_id, test_ide)
            runtime.set_ide_status(test_ide, "busy", current_task_id=test_task_id)
        else:
            runtime.update_task(
                test_task_id,
                status="failed",
                error=inject_detail,
                updated_at=now,
            )
            return {
                "success": False,
                "message": f"测试任务派发失败: {inject_detail}",
            }, 500

    dispatched_metadata = dict(parent_metadata)
    dispatched_metadata.update({
        "test_result": "dispatched",
        "test_ide": test_ide,
        "test_task_id": test_task_id,
        "tested_at": now,
    })
    runtime.update_task(task_id, metadata=dispatched_metadata, updated_at=now)

    return {
        "success": True,
        "test_task_id": test_task_id,
        "parent_task_id": task_id,
        "message": f"测试任务 {test_task_id} 已派发到 {test_ide.upper()}",
    }, 200


@task_bp.route("/api/tasks/dispatch", methods=["POST"])
def api_tasks_dispatch():
    """将选定任务合并成一条提示词派发到指定 IDE，不创建新任务。"""
    data = request.get_json(force=True)
    print(f"[DEBUG] api_tasks_dispatch received: {data}", flush=True)
    task_ids = data.get("task_ids", [])
    target_ide = data.get("target_ide")
    selected_surface = str(data.get("surface") or "").strip().lower()
    if selected_surface not in _SURFACE_LABELS:
        selected_surface = ""
    if not task_ids or not target_ide:
        print(f"[DEBUG] api_tasks_dispatch missing params. task_ids={task_ids}, target_ide={target_ide}", flush=True)
        return jsonify({"success": False, "message": "缺少任务ID或目标 IDE"})

    from task_runtime import TaskRuntime

    runtime = TaskRuntime(BASE_DIR)
    now = datetime.now().isoformat()
    errors = []
    dispatch_items = []
    seen_ids = set()

    for tid in task_ids:
        if tid in seen_ids:
            continue
        seen_ids.add(tid)
        task_data = _read_task_data(tid, runtime)
        if not task_data:
            errors.append(f"任务 {tid} 未找到")
            continue
        metadata = dict(task_data.get("metadata") or {})
        if selected_surface:
            metadata["surface"] = selected_surface
        dispatch_items.append({
            "task_id": tid,
            "title": task_data.get("title", tid),
            "message": task_data.get("message", ""),
            "metadata": metadata,
        })

    if not dispatch_items:
        return jsonify({"success": False, "message": "没有有效任务"})

    representative = dispatch_items[0]
    merged_ids = [item["task_id"] for item in dispatch_items]
    dispatch_prefix = _dispatch_prefix(dispatch_items)

    if len(dispatch_items) == 1:
        item = dispatch_items[0]
        merged_message = item.get("message") or item.get("title") or item["task_id"]
        merged_message = dispatch_prefix + "\n" + merged_message
    else:
        merged_message_parts = [
            f"{dispatch_prefix}【AideLink 批量合并派发】目标IDE: {target_ide.upper()}, 共{len(dispatch_items)}个任务",
            "直接完成下面全部任务，按编号说明结果:",
        ]
        for index, item in enumerate(dispatch_items, start=1):
            message = item.get("message") or ""
            merged_message_parts.append(f"{index}. {message}")
        merged_message = "\n".join(merged_message_parts)

    for item in dispatch_items:
        tid = item["task_id"]
        try:
            current = runtime.get_task(tid) or {}
            metadata = dict(current.get("metadata") or {})
            if selected_surface:
                metadata["surface"] = selected_surface
            metadata["merged_dispatch_ids"] = merged_ids
            metadata["merged_dispatch_representative"] = representative["task_id"]
            runtime.update_task(
                tid,
                target_ide=target_ide,
                dispatched_at=now,
                queued_at=None,
                metadata=metadata,
                updated_at=now,
            )
        except Exception as e:
            logger.error(f"Failed to update task {tid}: {e}")
            errors.append(f"任务 {tid} 状态更新失败")

    inject_ok, inject_detail = _inject_to_ide(target_ide, merged_message, representative["task_id"])
    if inject_ok:
        runtime.set_ide_status(target_ide, "busy", current_task_id=representative["task_id"])
        for item in dispatch_items:
            try:
                runtime.mark_task_running(item["task_id"], target_ide)
            except Exception:
                pass
    else:
        for item in dispatch_items:
            try:
                runtime.update_task(
                    item["task_id"],
                    status="failed",
                    error=inject_detail,
                    updated_at=datetime.now().isoformat(),
                )
            except Exception:
                pass
        try:
            runtime.set_ide_status(target_ide, "idle", current_task_id=None, error=inject_detail)
        except Exception:
            pass
        return jsonify({
            "success": False,
            "message": f"派发失败: {inject_detail}",
        }), 500

    return jsonify({
        "success": len(errors) == 0,
        "message": f"已将 {len(dispatch_items)} 个任务合并派发到 {target_ide.upper()}，正在后台注入执行..." + (f"，失败: {'; '.join(errors)}" if errors else "")
    })


@task_bp.route("/api/tasks/complete", methods=["POST"])
def api_tasks_complete():
    """标记任务完成，并自动注入队列中下一个任务"""
    data = request.get_json(force=True)
    task_id = data.get("task_id")
    manual = data.get("manual", False)

    if not task_id:
        return jsonify({"success": False, "message": "缺少任务 ID"})

    from task_runtime import TaskRuntime

    runtime = TaskRuntime(BASE_DIR)
    task_info = _read_task_data(task_id, runtime)
    if not task_info:
        return jsonify({"success": False, "message": f"任务 {task_id} 不存在"})

    target_ide = task_info.get("target_ide") or ""
    now = datetime.now().isoformat()
    merged_ids = _get_merged_dispatch_ids(runtime, task_id)

    if manual:
        try:
            runtime.mark_task_done(task_id, summary=data.get("summary", "已完成"), is_manual=True)
        except Exception:
            pass
        runtime.confirm_task_done(task_id, is_manual=True)
        for merged_tid in merged_ids:
            if merged_tid == task_id:
                continue
            try:
                runtime.mark_task_done(merged_tid, summary=data.get("summary", "已完成"), is_manual=True)
            except Exception:
                pass
            runtime.confirm_task_done(merged_tid, is_manual=True)
        return jsonify({"success": True, "message": f"任务 {task_id} 已完成"})

    try:
        runtime.mark_task_done(task_id, summary=data.get("summary", "已完成"), is_manual=False)
        for merged_tid in merged_ids:
            if merged_tid == task_id:
                continue
            runtime.update_task(
                merged_tid,
                status="pending_test",
                summary=data.get("summary", "已完成"),
                error=None,
                updated_at=now,
            )
    except Exception:
        pass

    if merged_ids:
        try:
            runtime.set_ide_status(target_ide, "idle", current_task_id=None)
        except Exception:
            pass
        return jsonify({"success": True, "message": f"合并派发任务组已完成", "remaining": 0})

    remaining = 0
    if target_ide:
        queue_file = BASE_DIR / "state" / f"task_queue_{target_ide}.json"
        queue = _load_queue(queue_file)
        if queue and queue[0]["task_id"] == task_id:
            queue.pop(0)
        else:
            queue = [t for t in queue if t["task_id"] != task_id]
        _save_queue(queue_file, queue)
        remaining = len(queue)

        if queue:
            next_task = queue[0]
            next_msg = next_task["message"]
            next_tid = next_task["task_id"]
            if len(queue) > 1:
                next_msg += f"\n\n---\n[队列提示] 还有 {len(queue) - 1} 个任务等待执行。"

            inject_ok, inject_detail = _inject_to_ide(target_ide, next_msg, next_tid)
            try:
                if inject_ok:
                    runtime.mark_task_running(next_tid, target_ide)
                    runtime.set_ide_status(target_ide, "busy", current_task_id=next_tid)
                else:
                    runtime.update_task(next_tid, status="failed", error=inject_detail, updated_at=now)
                    runtime.set_ide_status(target_ide, "idle", current_task_id=None, error=inject_detail)
            except Exception:
                pass
        else:
            try:
                runtime.set_ide_status(target_ide, "idle", current_task_id=None)
            except Exception:
                pass

    return jsonify({"success": True, "message": f"任务 {task_id} 已完成", "remaining": remaining})


@task_bp.route("/api/tasks/queue_status")
def api_tasks_queue_status():
    """获取各 IDE 的任务队列状态"""
    state_dir = BASE_DIR / "state"
    result = {}
    if state_dir.exists():
        for f in state_dir.glob("task_queue_*.json"):
            ide_key = f.stem.replace("task_queue_", "")
            queue = _load_queue(f)
            result[ide_key] = {
                "count": len(queue),
                "current": queue[0]["task_id"] if queue else None,
                "pending": [t["task_id"] for t in queue[1:]] if len(queue) > 1 else [],
            }
    return jsonify({"success": True, "queues": result})


@task_bp.route("/api/tasks/feedback", methods=["POST"])
def api_tasks_feedback():
    """对任务补充反馈，运行中任务会重新派发，已完成/失败任务只记录备注。"""
    data = request.get_json(force=True)
    task_id = data.get("task_id", "").strip()
    feedback = data.get("feedback", "").strip()
    if not task_id or not feedback:
        return jsonify({"success": False, "message": "缺少任务ID或反馈内容"})

    from task_runtime import TaskRuntime

    runtime = TaskRuntime(BASE_DIR)
    task_info = _read_task_data(task_id, runtime)
    if not task_info:
        return jsonify({"success": False, "message": f"任务 {task_id} 不存在"})

    target_ide = task_info.get("target_ide") or ""
    status = (task_info.get("status") or "").lower()

    now = datetime.now().isoformat()
    full_task = runtime.get_task(task_id)
    if full_task and isinstance(full_task.get("metadata"), dict):
        feedbacks = full_task["metadata"].setdefault("feedbacks", [])
    else:
        feedbacks = []
    feedbacks.append({"time": now, "text": feedback})
    history = read_history()
    history.append({
        "sender": "user",
        "text": feedback,
        "time": datetime.now().strftime("%H:%M:%S"),
        "target": target_ide,
        "task_id": task_id,
    })

    orig_message = (full_task.get("metadata", {}).get("original_message")
                    if full_task and isinstance(full_task.get("metadata"), dict)
                    else None)
    if not orig_message:
        orig_message = task_info.get("message", "")
        if full_task and isinstance(full_task.get("metadata"), dict):
            full_task["metadata"]["original_message"] = orig_message

    fb_count = len(feedbacks)
    # task-20260710-143025-123 -> #143025-123
    _parts = task_id.split("-")
    short_id = "-".join(_parts[-2:]) if len(_parts) >= 2 else task_id
    task_prefix = f"[任务反馈 #{short_id}]"

    if fb_count == 1:
        # 第 1 次反馈：带原任务消息，让 IDE 知道是哪个任务的反馈
        combined = (
            f"{task_prefix}\n"
            f"{orig_message}\n\n"
            f"---\n\n## 补充反馈\n\n{feedback}\n\n"
            f"请在已有实现基础上修改，仅处理最新反馈中提到的内容。"
        )
    else:
        # 第 2 次起：IDE 已知任务上下文，只发新反馈，避免冗余
        combined = (
            f"{task_prefix}\n"
            f"## 补充反馈（第 {fb_count} 次）\n\n"
            f"（前 {fb_count - 1} 次反馈已记录，此处不再重复）\n\n"
            f"{feedback}\n\n"
            f"请在已有实现基础上修改，仅处理最新反馈中提到的内容。"
        )

    def _save_feedback_metadata(extra_fields=None):
        tasks = runtime.read_tasks()
        for t in tasks:
            if t.get("task_id") == task_id:
                if not isinstance(t.get("metadata"), dict):
                    t["metadata"] = {}
                t["metadata"]["feedbacks"] = feedbacks
                t["metadata"]["original_message"] = orig_message
                t["metadata"]["response_preview"] = f"第 {fb_count} 次补充反馈"
                if extra_fields:
                    t.update(extra_fields)
                break
        runtime.write_tasks(tasks)

    try:
        _save_feedback_metadata()
    except Exception as e:
        logger.error(f"Failed to save feedbacks metadata: {e}")

    if status in ("done", "failed"):
        feedback_message = f"第 {fb_count} 次反馈已记录到 {task_id}，已完成任务不会自动重新派发"
        history.append({
            "sender": "agent",
            "text": f"反馈已记录到任务 {task_id}，已完成/失败任务不会自动重新派发。",
            "time": datetime.now().strftime("%H:%M:%S"),
            "target": target_ide,
            "task_id": task_id,
        })
        write_history(history)
        _publish_task_feedback(task_id, target_ide, task_info.get("title", ""), feedback, feedback_message, fb_count)
        return jsonify({
            "success": True,
            "message": feedback_message,
        })

    if not target_ide:
        feedback_message = f"第 {fb_count} 次反馈已记录，任务未分配 IDE"
        history.append({
            "sender": "agent",
            "text": f"反馈已记录到任务 {task_id}，任务未分配 IDE。",
            "time": datetime.now().strftime("%H:%M:%S"),
            "target": "",
            "task_id": task_id,
        })
        write_history(history)
        _publish_task_feedback(task_id, target_ide, task_info.get("title", ""), feedback, feedback_message, fb_count)
        return jsonify({"success": True, "message": feedback_message})

    dispatch_msg = ""
    from task_runtime import SUPPORTED_IDES

    if status == "pending_test":
        try:
            runtime.update_task(
                task_id,
                status="test_failed",
                error=f"用户反馈待修复: {feedback[:200]}",
                updated_at=now,
            )
        except Exception as e:
            logger.error(f"Failed to move pending_test task to test_failed before feedback dispatch: {e}")
            return jsonify({
                "success": False,
                "message": f"任务状态转换失败，未派发反馈: {e}",
            }), 409

    if target_ide in SUPPORTED_IDES:
        inject_ok, inject_detail = _inject_to_ide(target_ide, combined, task_id)
        if inject_ok:
            try:
                runtime.mark_task_running(task_id, target_ide)
                runtime.set_ide_status(target_ide, "busy", current_task_id=task_id)
                dispatch_msg = f"，已派发到 {target_ide.upper()}"
            except Exception as e:
                logger.error(f"Feedback injected but task state update failed for {task_id}: {e}")
                runtime.mark_task_failed(task_id, f"反馈已注入但状态转换失败: {e}")
                return jsonify({
                    "success": False,
                    "message": f"反馈已注入，但任务状态转换失败: {e}",
                }), 500
        else:
            dispatch_msg = f"，派发失败: {inject_detail}"
    else:
        dispatch_msg = "，已加入队列等待派发"

    history.append({
        "sender": "agent",
        "text": f"第 {fb_count} 次反馈已追加到任务 {task_id}{dispatch_msg}",
        "time": datetime.now().strftime("%H:%M:%S"),
        "target": target_ide,
        "task_id": task_id,
    })
    write_history(history)
    feedback_message = f"第 {fb_count} 次反馈已追加到 {task_id}{dispatch_msg}"
    _publish_task_feedback(task_id, target_ide, task_info.get("title", ""), feedback, feedback_message, fb_count)

    return jsonify({
        "success": True,
        "message": feedback_message,
    })


@task_bp.route("/api/tasks/edit", methods=["POST"])
def api_tasks_edit():
    """编辑任务内容并退回待派发。"""
    data = request.get_json(force=True)
    task_id = data.get("task_id", "").strip()
    new_message = data.get("message", "").strip()
    if not task_id or not new_message:
        return jsonify({"success": False, "message": "缺少任务ID或内容"})

    from task_runtime import TaskRuntime

    runtime = TaskRuntime(BASE_DIR)
    task_info = _read_task_data(task_id, runtime)
    if not task_info:
        return jsonify({"success": False, "message": f"任务 {task_id} 不存在"})

    editable_statuses = {
        "pending", "draft", "queued", "dispatched", "running",
        "pending_test", "test_failed", "merge_conflict", "failed", "timeout",
    }
    if task_info.get("status") not in editable_statuses:
        return jsonify({"success": False, "message": "当前状态不允许编辑"})

    try:
        updated = runtime.reopen_task_as_draft(
            task_id,
            text=new_message,
            title=new_message[:60] if new_message else task_id,
        )
        if not updated:
            return jsonify({"success": False, "message": f"任务 {task_id} 不存在"})
    except Exception as e:
        logger.error(f"Failed to update task in edit: {e}")
        return jsonify({"success": False, "message": f"任务更新失败: {e}"}), 500

    target_ide = task_info.get("target_ide") or ""
    if target_ide:
        queue_file = BASE_DIR / "state" / f"task_queue_{target_ide}.json"
        queue = _load_queue(queue_file)
        queue = [item for item in queue if item.get("task_id") != task_id]
        _save_queue(queue_file, queue)

    return jsonify({"success": True, "message": "任务已更新并退回待派发"})


@task_bp.route("/api/tasks/test", methods=["POST"])
def api_tasks_test():
    """派发测试任务到另一个 IDE（不修改代码，只验证）"""
    data = request.get_json(force=True)
    task_id = data.get("task_id", "").strip()
    test_ide = data.get("test_ide", "").strip().lower()
    if not task_id or not test_ide:
        return jsonify({"success": False, "message": "缺少任务ID或测试 IDE"})

    from task_runtime import TaskRuntime

    runtime = TaskRuntime(BASE_DIR)
    orig_task = _read_task_data(task_id, runtime)
    if not orig_task:
        return jsonify({"success": False, "message": f"任务 {task_id} 不存在"})

    try:
        result, status_code = _create_and_dispatch_test_task(
            runtime,
            task_id,
            test_ide,
            orig_task,
            request.host_url.rstrip("/") + "/api/tasks/test-result",
        )
    except Exception as e:
        logger.error(f"Failed to register test task: {e}")
        return jsonify({"success": False, "message": f"测试任务派发失败: {e}"}), 500
    return jsonify(result), status_code
