from paths import BRIDGE_DIR as BASE_DIR

from json_utils import safe_read_json, safe_write_json


def _load_queue(queue_file):
    """加载任务队列"""
    return safe_read_json(queue_file, default=[])


def _save_queue(queue_file, queue):
    """保存任务队列"""
    try:
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        safe_write_json(queue_file, queue)
    except Exception as e:
        import logging

        logging.error(f"Failed to save queue: {e}")


def _read_task_data(task_id, runtime=None):
    """读取任务数据。优先从 TaskRuntime (state/tasks.json) 读取，未找到时回退到 task_context.json。

    返回 dict: {title, message, status, target_ide, ...} 或 None
    """
    if runtime is None:
        from task_runtime import TaskRuntime

        runtime = TaskRuntime(BASE_DIR)

    task = runtime.get_task(task_id)
    if task:
        return {
            "task_id": task.get("task_id", task_id),
            "title": task.get("title", task_id),
            "message": task.get("text", ""),
            "status": task.get("status", "draft"),
            "target_ide": task.get("target_ide"),
            "source": "runtime",
            "metadata": task.get("metadata", {}),
        }

    legacy_file = BASE_DIR / "task_context.json"
    legacy_data = safe_read_json(legacy_file, default={})
    ctx = legacy_data.get("contexts", {}).get(task_id)
    if ctx:
        return {
            "task_id": ctx.get("task_id", task_id),
            "title": ctx.get("title", task_id),
            "message": ctx.get("message", ""),
            "status": ctx.get("status", "draft"),
            "target_ide": ctx.get("target_ide"),
            "source": "legacy",
            "metadata": {},
        }
    return None


def _get_merged_dispatch_ids(runtime, task_id):
    task = runtime.get_task(task_id) or {}
    metadata = task.get("metadata") or {}
    merged_ids = metadata.get("merged_dispatch_ids") or []
    if not isinstance(merged_ids, list):
        return []
    return [tid for tid in merged_ids if isinstance(tid, str) and tid]
