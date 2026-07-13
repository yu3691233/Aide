import hashlib
import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime

from flask import jsonify, request

from paths import BRIDGE_DIR as BASE_DIR
from .task_routes import task_bp
from json_utils import safe_write_json


def _import_manager_utils():
    from manager_utils import safe_load_tasks, LOG_FILE
    return safe_load_tasks, LOG_FILE


logger = logging.getLogger("manager")


@task_bp.route("/api/tasks/merge_same_targets", methods=["POST"])
def api_tasks_merge_same_targets():
    """将多个同一目标位置且同一组件的待处理任务，合并到一起"""
    safe_load_tasks, _ = _import_manager_utils()
    task_file = BASE_DIR / "task_context.json"
    task_data = safe_load_tasks(task_file)
    contexts = task_data.setdefault("contexts", {})

    def get_target_and_component(msg):
        if not msg:
            return "Unknown", "Unknown"
        target = "Unknown"
        m = re.search(r"目标文件:\s*([^\n\r]+)", msg)
        if m:
            target = m.group(1).strip()
        else:
            m2 = re.search(r"文件:\s*([^\n\r]+)", msg)
            if m2:
                target = m2.group(1).strip()

        component = "Unknown"
        m3 = re.search(r"组件/类/函数:\s*([^\n\r]+)", msg)
        if m3:
            component = m3.group(1).strip()
        return target, component

    pending_tasks = []
    for tid, ctx in contexts.items():
        if ctx.get("status") == "pending":
            pending_tasks.append(ctx)

    groups = defaultdict(list)
    for t in pending_tasks:
        target, component = get_target_and_component(t.get("message", ""))
        if target != "Unknown" and component != "Unknown":
            groups[(target, component)].append(t)

    merged_count = 0
    new_task_ids = []

    for (target, component), tasks in groups.items():
        if len(tasks) < 2:
            continue

        task_descriptions = []
        for i, t in enumerate(tasks, 1):
            task_descriptions.append(f"任务 {i} (ID: {t['task_id']}):\n{t['message']}")

        merge_prompt = (
            f"请将以下针对同一目标位置（{target}）且相同组件（{component}）的多个开发/修改任务，合并成一个统一的、结构清晰的开发任务描述。\n"
            f"保留所有任务的具体修改需求，去除重复的内容，输出格式应与原来类似，包含：\n"
            f"【内容】(合并后的详细说明)\n\n"
            f"【代码修改与优化任务】\n"
            f"目标文件: {target}\n"
            f"组件/类/函数: {component}\n\n"
            f"以下是待合并的任务列表：\n"
            + "\n---\n".join(task_descriptions)
        )

        system_prompt = "你是一个专业的软件开发助手，擅长合并和整理开发需求，输出精简、无遗漏、排版优美的中文开发任务。"

        merged_message = None
        try:
            from call_assistant import ask_assistant

            merged_message = ask_assistant(merge_prompt, system_prompt)
        except Exception as e:
            logger.error(f"Failed to call ask_assistant: {e}")

        if not merged_message or merged_message.startswith("Error") or merged_message.startswith("Exception"):
            merged_message = (
                f"【内容】{task_descriptions[0].split(':', 1)[-1].strip() if ':' in task_descriptions[0] else task_descriptions[0]}\n"
                f"\n"
                f"【代码修改与优化任务 - 自动合并】\n"
                f"目标文件: {target}\n"
                f"组件/类/函数: {component}\n"
                + "\n---\n".join([t.get("message", "") for t in tasks])
            )

        new_task_id = "task-" + hashlib.md5(f"merged:{time.time()}:{target}:{component}".encode("utf-8")).hexdigest()[:8]
        types = [t.get("task_type", "code") for t in tasks]
        new_task_type = "bug_fix" if "bug_fix" in types else "code"

        contexts[new_task_id] = {
            "task_id": new_task_id,
            "message": merged_message,
            "message_keywords": ["manual", new_task_type, "merged"],
            "response_preview": "等待派发中 (由多个任务合并)...",
            "all_keywords": ["manual", "merged"],
            "task_type": new_task_type,
            "model_used": "MiniMax Merged",
            "status": "pending",
            "time": datetime.now().isoformat()
        }

        for t in tasks:
            contexts[t["task_id"]]["status"] = "done"
            contexts[t["task_id"]]["response_preview"] = f"已合并至任务 {new_task_id}"

        merged_count += len(tasks)
        new_task_ids.append(new_task_id)

    if merged_count > 0:
        task_data["updated_at"] = datetime.now().isoformat()
        try:
            safe_write_json(task_file, task_data)
            return jsonify({"success": True, "message": f"成功将 {merged_count} 个任务合并为 {len(new_task_ids)} 个任务！"})
        except Exception as e:
            return jsonify({"success": False, "message": f"保存合并任务失败: {e}"})
    return jsonify({"success": True, "message": "没有发现可以合并的同目标位置待处理任务。"})


@task_bp.route("/api/tasks/commit-hook", methods=["POST"])
def api_commit_hook():
    """Git post-commit hook 回调：检测到 commit 时由 hook 调用"""
    try:
        data = request.get_json() or {}
        commit = data.get("commit", "")
        message = data.get("message", "")
        files = data.get("files", [])

        from task_runtime import TaskRuntime

        runtime = TaskRuntime(str(BASE_DIR))
        ide_status = runtime.read_ide_status()
        completed = []
        for ide, status in ide_status.items():
            if status.get("status") != "busy":
                continue
            task_id = status.get("current_task_id")
            if not task_id:
                continue
            task = runtime.get_task(task_id)
            if not task or task.get("status") not in ("running", "dispatched"):
                continue

            owned = task.get("owned_paths", [])
            if owned:
                matched = any(
                    any(f.startswith(op.rstrip("/")) or op.rstrip("/").startswith(f) for op in owned)
                    for f in files if f
                )
                if not matched:
                    continue

            updated = runtime.mark_task_done(task_id, summary=f"Git commit: {commit} - {message}")
            if updated:
                completed.append({"task_id": task_id, "ide": ide, "commit": commit})
                logger.info(f"[commit-hook] Task {task_id} marked done (commit {commit})")

        if completed:
            return jsonify({"ok": True, "completed": completed})
        return jsonify({"ok": True, "completed": [], "note": "没有匹配到活跃任务"})
    except Exception as e:
        logger.error(f"commit-hook error: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@task_bp.route("/api/tasks/monitor-stuck", methods=["GET"])
def api_monitor_stuck():
    """检测可能卡住的任务：截图中心区域无变化 + 超时"""
    try:
        from task_runtime import TaskRuntime

        runtime = TaskRuntime(str(BASE_DIR))
        ide_status = runtime.read_ide_status()
        stuck_tasks = []
        for ide, status in ide_status.items():
            if status.get("status") != "busy":
                continue
            task_id = status.get("current_task_id")
            if not task_id:
                continue
            task = runtime.get_task(task_id)
            if not task or task.get("status") != "running":
                continue
            started_at = task.get("started_at")
            if started_at:
                try:
                    started = datetime.fromisoformat(started_at)
                    elapsed_min = (datetime.now() - started).total_seconds() / 60
                    if elapsed_min > 30:
                        stuck_tasks.append({
                            "task_id": task_id,
                            "ide": ide,
                            "elapsed_min": round(elapsed_min, 1),
                            "title": task.get("title", ""),
                        })
                except Exception:
                    pass

        return jsonify({"ok": True, "stuck_tasks": stuck_tasks})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@task_bp.route("/api/tasks/notifications", methods=["GET"])
def api_task_notifications():
    """获取任务状态变更通知（手机轮询用）"""
    try:
        since_id = request.args.get("since_id", 0, type=int)
        from event_bus import bus

        events = bus.recent(
            since_id=since_id,
            types=["task.done", "task.pending_test", "task.failed", "task.possibly_done"],
            limit=20
        )
        return jsonify({"ok": True, "events": events})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
