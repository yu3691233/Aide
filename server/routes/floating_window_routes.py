import ctypes
import os
from ctypes import wintypes
from datetime import datetime

import psutil
from flask import Blueprint, jsonify, request

from config import load_settings, normalize_project_path, project_path_key
from paths import BRIDGE_DIR as BASE_DIR
from project_capabilities import enrich_project, inspect_project_capabilities
from routes.task_routes import map_task_for_client
from task_contracts import is_inspiration, summarize_tasks_for_project, task_matches_project


floating_window_bp = Blueprint("floating_window", __name__)

_EXECUTED_TASK_STATUSES = {
    "queued", "dispatched", "running", "pending_test", "test_failed",
    "done", "completed", "failed", "timeout",
}


def _executed_task_ids(tasks):
    return [
        task.get("task_id")
        for task in tasks
        if isinstance(task, dict)
        and str(task.get("status") or "").strip().lower() in _EXECUTED_TASK_STATUSES
        and task.get("task_id")
    ]


def _current_project(settings):
    current = normalize_project_path(settings.get("current_project") or settings.get("project_dir") or "")
    projects = settings.get("projects", [])
    match = next(
        (
            item for item in projects
            if project_path_key(item.get("path", "")) == project_path_key(current)
        ),
        None,
    )
    if match:
        return enrich_project(match)
    if current:
        return enrich_project({"path": current, "name": current.rsplit("\\", 1)[-1]})
    return None


def _ide_statuses():
    import ide_scanner
    from dispatch_utils import get_ide_running_statuses
    from shared_runtime import runtime

    all_ides = ide_scanner.get_all_ides()
    running_statuses = get_ide_running_statuses(all_ides)
    result = []
    for ide_info in all_ides:
        key = ide_info.get("key", "")
        runtime_status = runtime.get_ide_status(key) or {}
        runtime_state = runtime_status.get("status", "idle")
        running = bool(running_statuses.get(key, False))
        busy = runtime_state == "busy"
        dispatchable = running and not busy
        blocking_reasons = []
        if not running:
            blocking_reasons.append("ide_not_running")
        if busy:
            blocking_reasons.append("ide_busy")
        result.append({
            "key": key,
            "name": ide_info.get("name", key),
            "path": ide_info.get("path", ""),
            "icon_url": (
                f"{request.host_url.rstrip('/')}/api/desktop-ides/{key}/icon"
                if ide_info.get("path") and key else ""
            ),
            "running": running,
            "status": runtime_state,
            "busy": busy,
            "current_task_id": runtime_status.get("current_task_id"),
            "dispatchable": dispatchable,
            "blocking_reasons": blocking_reasons,
            "block_reason": blocking_reasons[0] if blocking_reasons else None,
            "lease_expires_at": runtime_status.get("lease_expires_at"),
            "error": runtime_status.get("error"),
            "is_primary": bool(ide_info.get("is_primary", False)),
        })
    return result


def _foreground_ide_key(ides):
    """Return the supported IDE owning the foreground window without activating it."""
    if os.name != "nt":
        return None
    try:
        hwnd = int(ctypes.windll.user32.GetForegroundWindow() or 0)
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None
        process = psutil.Process(pid.value)
        actual_path = os.path.normcase(os.path.abspath(process.exe() or ""))
        actual_name = (process.name() or os.path.basename(actual_path)).lower()
    except (OSError, psutil.Error, AttributeError):
        return None

    for ide in ides:
        if not ide.get("running"):
            continue
        target_path = os.path.normcase(os.path.abspath(ide.get("path") or ""))
        target_name = os.path.basename(target_path).lower()
        if target_path and actual_path == target_path:
            return ide.get("key")
        if target_name and actual_name == target_name:
            return ide.get("key")
    return None


def _selected_target(settings, ides):
    foreground_key = _foreground_ide_key(ides)
    if foreground_key:
        return next((item for item in ides if item["key"] == foreground_key), None)

    running = [item for item in ides if item.get("running")]
    if len(running) == 1:
        return running[0]

    configured = str(settings.get("desktop_ide") or "auto").strip().lower()
    if configured and configured != "auto":
        match = next((item for item in ides if item["key"] == configured and item.get("running")), None)
        if match:
            return match
    return next((item for item in ides if item.get("dispatchable")), None)


@floating_window_bp.route("/api/floating-window/bootstrap", methods=["GET"])
def api_floating_window_bootstrap():
    settings = load_settings()
    project = _current_project(settings)
    project_path = project.get("path") if project else ""

    from shared_runtime import runtime

    strict = request.args.get("strict_project", "1") != "0"
    all_tasks = runtime.read_tasks()
    summary = summarize_tasks_for_project(
        all_tasks,
        project_path=project_path,
        strict_project=strict,
        limit=50,
    )
    inspirations = [
        task for task in all_tasks
        if isinstance(task, dict)
        and is_inspiration(task)
        and task_matches_project(task, project_path, strict_project=strict)
    ]
    inspirations.sort(
        key=lambda task: str(task.get("updated_at") or task.get("created_at") or ""),
        reverse=True,
    )
    completed = [
        task for task in all_tasks
        if isinstance(task, dict)
        and not is_inspiration(task)
        and (task.get("status") or "").lower() in {"done", "completed"}
        and task_matches_project(task, project_path, strict_project=strict)
    ]
    completed.sort(
        key=lambda task: str(task.get("completed_at") or task.get("updated_at") or ""),
        reverse=True,
    )
    ides = _ide_statuses()
    selected = _selected_target(settings, ides)
    from codex_quota import get_current_codex_quota

    return jsonify({
        "ok": True,
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project": project,
        "capabilities": project.get("capabilities", ["general"]) if project else ["general"],
        "ides": ides,
        "selected_target": selected,
        # This endpoint is polled only by the live floating window. The quota
        # module keeps a five-minute cache and refreshes early after three newly
        # executed tasks.
        "codex_quota": get_current_codex_quota(
            executed_task_ids=_executed_task_ids(all_tasks),
        ),
        "task_summary": summary["summary"],
        "tasks": [
            map_task_for_client(task)
            for task in [*summary["tasks"], *completed[:50], *inspirations[:20]]
        ],
        "warnings": summary["warnings"],
    })
