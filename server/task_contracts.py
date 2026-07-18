from collections import Counter

from config import project_path_key


KEY_TASK_STATUSES = (
    "pending_test",
    "test_failed",
    "merge_conflict",
    "running",
    "dispatched",
    "queued",
    "draft",
    "failed",
    "timeout",
)
KEY_TASK_PRIORITY = {status: index for index, status in enumerate(KEY_TASK_STATUSES)}


def task_allowed_actions(task):
    status = (task.get("status") or "").lower()
    target_ide = bool(task.get("target_ide"))
    actions = ["view"]
    if status in {"draft", "queued", "pending"}:
        actions += ["edit", "assign"]
        if target_ide:
            actions.append("dispatch")
    elif status in {"dispatched", "running"}:
        actions += ["feedback", "mark_failed"]
    elif status == "pending_test":
        actions += ["confirm_done", "feedback", "mark_failed"]
    elif status in {"test_failed", "merge_conflict"}:
        actions += ["feedback", "retry", "mark_failed"]
    elif status in {"failed", "timeout"}:
        actions.append("retry")
    elif status in {"done", "completed"}:
        actions.append("feedback_note")
    actions.append("delete")
    return list(dict.fromkeys(actions))


def is_inspiration(task):
    metadata = task.get("metadata") or {}
    return metadata.get("content_kind") == "inspiration"


def task_matches_project(task, project_path, strict_project=True):
    if not project_path:
        return True
    task_project = task.get("project")
    if not task_project:
        return not strict_project
    return project_path_key(task_project) == project_path_key(project_path)


def _reverse_time_value(task):
    value = str(task.get("updated_at") or task.get("created_at") or "")
    digits = "".join(ch for ch in value if ch.isdigit())
    return -int(digits or "0")


def summarize_tasks_for_project(tasks, project_path="", strict_project=True, limit=5):
    filtered = []
    skipped_legacy_without_project = 0
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if is_inspiration(task):
            continue
        if project_path and strict_project and not task.get("project"):
            skipped_legacy_without_project += 1
            continue
        if not task_matches_project(task, project_path, strict_project=strict_project):
            continue
        if (task.get("task_type") or "").lower() == "chat":
            continue
        filtered.append(dict(task))

    counts = Counter(task.get("status") or "unknown" for task in filtered)
    active_statuses = {"queued", "dispatched", "running", "pending_test", "test_failed", "merge_conflict"}
    key_tasks = [
        task for task in filtered
        if (task.get("status") or "") in KEY_TASK_STATUSES
    ]
    key_tasks.sort(key=lambda task: (
        KEY_TASK_PRIORITY.get(task.get("status") or "", len(KEY_TASK_PRIORITY)),
        _reverse_time_value(task),
    ))

    warnings = []
    if skipped_legacy_without_project:
        warnings.append({
            "code": "legacy_tasks_without_project_excluded",
            "count": skipped_legacy_without_project,
        })

    return {
        "summary": {
            "total": len(filtered),
            "active": sum(counts.get(status, 0) for status in active_statuses),
            "needs_user": counts.get("pending_test", 0) + counts.get("test_failed", 0) + counts.get("merge_conflict", 0),
            "by_status": dict(counts),
        },
        "tasks": key_tasks[:limit],
        "warnings": warnings,
    }
