import os
import subprocess
import time
import threading
import traceback
from pathlib import Path
from datetime import datetime
from json_utils import safe_read_json, safe_write_json

from task_runtime import TaskRuntime, PROJECT_ROOT as RT_PROJECT_ROOT
import git_task_worktree as gwt

BASE_DIR = Path(__file__).parent
from paths import PROJECT_ROOT
POLL_INTERVAL = 60


def _load_tasks_file():
    return safe_read_json(BASE_DIR / "state" / "tasks.json", [])


def _save_tasks_file(tasks):
    os.makedirs(BASE_DIR / "state", exist_ok=True)
    safe_write_json(BASE_DIR / "state" / "tasks.json", tasks)


def _log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[MergeDaemon] {ts} {msg}")


def _run_tests(task, test_cmd):
    if not test_cmd:
        return True, "", "no test command"
    _log(f"Running tests: {test_cmd}")
    # 在 git worktree 内运行测试（文件可能在 worktree 中）
    task_id = task["task_id"]
    ide = task.get("target_ide")
    wt_path = gwt._wt_path(task_id, ide) if ide and gwt.is_ready(task_id, ide) else PROJECT_ROOT
    command = test_cmd.get("argv", []) if isinstance(test_cmd, dict) else []
    relative_cwd = test_cmd.get("cwd") if isinstance(test_cmd, dict) else None
    if not command:
        return False, "invalid test command", -1
    command_cwd = Path(wt_path) / relative_cwd if relative_cwd else wt_path
    result = subprocess.run(
        command,
        shell=False,
        capture_output=True,
        cwd=command_cwd,
        timeout=300,
    )
    ok = result.returncode == 0 or result.returncode == 5  # 5 = no tests collected
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    # 测试工具不存在（如 pytest 未安装），跳过测试
    if "No module named" in stderr and not ok:
        _log(f"Test tool not available, skipping tests")
        return True, "skipped (tool not available)", 0
    output = (stdout + "\n" + stderr).strip()
    return ok, output[:2000], result.returncode


def _process_testing_task(runtime, task):
    task_id = task["task_id"]
    ide = task.get("target_ide")
    if not ide:
        runtime.update_task(task_id, status="failed", error="no target_ide")
        return
    if not gwt.is_ready(task_id, ide):
        _log(f"Task {task_id}: no worktree; skipping legacy merge daemon")
        return

    runtime.update_task(task_id, status="merging", merge_stage="commit")
    committed, msg = gwt.commit(task_id, ide)
    if not committed and msg != "nothing_to_commit":
        _log(f"Task {task_id}: commit failed: {msg}")
        runtime.update_task(task_id, status="test_failed", error=f"commit failed: {msg}")
        return

    _log(f"Task {task_id}: rebasing to main...")
    runtime.update_task(task_id, status="merging", merge_stage="rebase")
    result, err = gwt.rebase(task_id, ide)
    if not result["success"]:
        _log(f"Task {task_id}: rebase conflict: {result['conflicts']}")
        runtime.update_task(
            task_id,
            status="merge_conflict",
            error=f"Rebase conflict: {', '.join(result['conflicts'])}",
            merge_conflicts=result["conflicts"],
        )
        return

    test_cmd = gwt.detect_test_command(task)
    _log(f"Task {task_id}: test cmd={test_cmd}")
    runtime.update_task(task_id, status="merging", merge_stage="test")
    test_ok, test_out, rc = _run_tests(task, test_cmd)
    if not test_ok:
        _log(f"Task {task_id}: tests failed (rc={rc})")
        runtime.update_task(
            task_id,
            status="test_failed",
            error=f"Tests failed (exit={rc})",
            test_output=test_out,
        )
        return

    _log(f"Task {task_id}: merging to main...")
    runtime.update_task(task_id, status="merging", merge_stage="merge")
    merge_ok, merge_msg = gwt.merge(task_id, ide)
    if not merge_ok:
        _log(f"Task {task_id}: merge failed: {merge_msg}")
        runtime.update_task(
            task_id,
            status="merge_conflict",
            error=f"Merge to main failed: {merge_msg}",
        )
        return

    _log(f"Task {task_id}: cleaning up worktree...")
    gwt.cleanup(task_id, ide)

    runtime.update_task(
        task_id,
        status="done",
        completed_at=datetime.now().isoformat(),
        test_output=test_out,
        merge_stage=None,
    )
    _log(f"Task {task_id}: done")


def _poll_loop():
    _log("Merge daemon started")
    runtime = TaskRuntime(BASE_DIR)
    while True:
        try:
            tasks = runtime.read_tasks()
            testing_tasks = [t for t in tasks if t.get("status") in ("testing", "pending_test")]
            for task in testing_tasks:
                try:
                    _process_testing_task(runtime, task)
                except Exception as e:
                    _log(f"Error processing {task['task_id']}: {e}")
                    traceback.print_exc()
                    runtime.update_task(
                        task["task_id"],
                        status="test_failed",
                        error=f"daemon error: {e}",
                    )
        except Exception as e:
            _log(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)


def start():
    thread = threading.Thread(target=_poll_loop, daemon=True, name="merge-daemon")
    thread.start()
    return thread
