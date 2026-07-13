import os
from datetime import datetime

from flask import jsonify, request

from json_utils import safe_read_json, safe_write_json
from paths import BRIDGE_DIR
from .task_routes import task_bp


@task_bp.route('/tasks/<task_id>/confirm', methods=['POST'])
@task_bp.route('/api/tasks/<task_id>/confirm', methods=['POST'])
def confirm_task(task_id):
    """用户确认任务完成：pending_test → done"""
    from shared_runtime import runtime

    task = runtime.confirm_task_done(task_id, is_manual=True)
    if not task:
        return jsonify({"ok": False, "error": "Task not found"}), 404
    return jsonify({"ok": True, "task": task})


@task_bp.route('/tasks/<task_id>/fail', methods=['POST'])
@task_bp.route('/api/tasks/<task_id>/fail', methods=['POST'])
def fail_task(task_id):
    from shared_runtime import runtime

    data = request.json or {}
    error = data.get("error", "Unknown error")
    task = runtime.mark_task_failed(task_id, error, is_manual=True)
    if not task:
        return jsonify({"ok": False, "error": "Task not found"}), 404
    return jsonify({"ok": True, "task": task})


@task_bp.route('/tasks/<task_id>/complete', methods=['POST'])
@task_bp.route('/api/tasks/<task_id>/complete', methods=['POST'])
def api_task_complete_by_id(task_id):
    """APP 端按 URL 路径完成任务"""
    from shared_runtime import runtime

    task = runtime.confirm_task_done(task_id, is_manual=True)
    if not task:
        return jsonify({"ok": False, "error": "Task not found"}), 404
    return jsonify({"ok": True, "task": task})


@task_bp.route('/queues/<ide>/next')
def next_queue_task(ide):
    from shared_runtime import runtime
    from task_runtime import SUPPORTED_IDES

    ide = ide.strip().lower()
    if ide not in SUPPORTED_IDES:
        return jsonify({"ok": False, "error": "Unsupported IDE"}), 400
    task = runtime.next_task_for_ide(ide)
    return jsonify({"ok": True, "task": task})


@task_bp.route('/tasks/<task_id>/worktree', methods=['POST'])
def prepare_task_worktree(task_id):
    from shared_runtime import runtime

    snapshot, error = runtime.prepare_worktree(task_id)
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, "snapshot": snapshot, "task": runtime.get_task(task_id)})


@task_bp.route('/tasks/<task_id>/worktree/file', methods=['PUT'])
def update_task_worktree_file(task_id):
    from shared_runtime import runtime

    data = request.json or {}
    rel_path = data.get("path", "")
    content = data.get("content", "")
    ok, error = runtime.update_worktree_file(task_id, rel_path, content)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True})


@task_bp.route('/tasks/<task_id>/patch', methods=['GET', 'POST'])
@task_bp.route('/tasks/<task_id>/merge', methods=['POST'])
def task_patch(task_id):
    from shared_runtime import runtime

    if request.method == 'POST':
        data = request.json or {}
        conflicts = data.get("conflicts", "abort")
        force = bool(data.get("force", False))
        result, error = runtime.apply_patch(task_id, conflicts=conflicts, force=force)
        if error:
            return jsonify({"ok": False, "error": error}), 400
        if result.get("aborted"):
            return jsonify({"ok": False, "result": result, "error": "merge aborted due to live file conflicts"}), 409
        return jsonify({"ok": True, "result": result, "task": runtime.get_task(task_id)})

    result, error = runtime.collect_patch(task_id)
    if error:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True, **result})


@task_bp.route('/tasks/<task_id>/worktree/drop', methods=['POST'])
def drop_task_worktree(task_id):
    from shared_runtime import runtime

    ok, error = runtime.drop_worktree(task_id)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400
    return jsonify({"ok": True})


@task_bp.route('/leases')
def list_leases():
    from shared_runtime import runtime

    leases = runtime.read_leases()
    normalized = {}
    now = datetime.now()

    for path, lease in leases.items():
        try:
            expires = datetime.fromisoformat(lease.get("expires_at")) if lease.get("expires_at") else None
        except Exception:
            expires = None
        normalized[path] = {
            **lease,
            "expired": bool(expires and expires <= now),
        }

    return jsonify({"ok": True, "leases": normalized})


@task_bp.route("/api/test/result", methods=["GET", "POST"])
def api_test_result():
    """获取测试执行结果，或由测试 IDE 上报执行报告"""
    from shared_runtime import read_history

    if request.method == "POST":
        data = request.json or {}
        ide_key = data.get("ide_key")
        result = data.get("result")
        if not ide_key or not result:
            return jsonify({"ok": False, "error": "Missing 'ide_key' or 'result'"}), 400

        try:
            import time

            res_data = {
                "ide_key": ide_key,
                "result": result,
                "timestamp": time.time()
            }
            result_file = os.path.join(BRIDGE_DIR, "state", f"test_result_{ide_key}.json")
            os.makedirs(os.path.dirname(result_file), exist_ok=True)
            safe_write_json(result_file, res_data)
            return jsonify({"ok": True, "message": "测试结果上报成功"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    ide_key = request.args.get("ide_key")
    if not ide_key:
        return jsonify({"ok": False, "error": "Missing 'ide_key'"}), 400

    task_file = os.path.join(BRIDGE_DIR, "state", f"test_task_{ide_key}.json")
    if not os.path.exists(task_file):
        return jsonify({"ok": False, "error": f"找不到目标 IDE '{ide_key}' 的已分发测试任务"}), 404

    try:
        task_data = safe_read_json(task_file, {})
        history_start_len = task_data.get("history_start_len", 0)
        history = read_history()
        new_replies = history[history_start_len:]
        agent_reply = None
        for item in new_replies:
            sender = item.get("sender", "").lower()
            if sender in ("agent", "assistant"):
                agent_reply = item
                break

        if agent_reply:
            return jsonify({
                "ok": True,
                "status": "completed",
                "data": {
                    "ide_key": ide_key,
                    "result": agent_reply.get("text", ""),
                    "timestamp": agent_reply.get("time", "")
                }
            })

        json_file = os.path.join(BRIDGE_DIR, "state", f"test_result_{ide_key}.json")
        if os.path.exists(json_file):
            data = safe_read_json(json_file, {})
            return jsonify({"ok": True, "status": "completed", "data": data})

        md_file = os.path.join(BRIDGE_DIR, "state", f"test_result_{ide_key}.md")
        if os.path.exists(md_file):
            with open(md_file, "r", encoding="utf-8") as f:
                md_content = f.read()
            return jsonify({
                "ok": True,
                "status": "completed",
                "data": {
                    "ide_key": ide_key,
                    "result": md_content,
                    "timestamp": os.path.getmtime(md_file)
                }
            })

        return jsonify({"ok": False, "status": "running", "message": "测试任务正在执行中，请稍后..."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
