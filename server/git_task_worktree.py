import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime

def get_project_root() -> Path:
    try:
        from paths import get_project_root as _get_root
        return _get_root()
    except Exception:
        return Path(__file__).parent.parent.resolve()

def get_worktrees_dir() -> Path:
    return get_project_root() / ".worktrees"


def _git(*args, cwd=None, timeout=120):
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True,
        cwd=cwd or get_project_root(),
        timeout=timeout,
    )
    stdout = result.stdout.decode("utf-8", errors="replace").strip()
    stderr = result.stderr.decode("utf-8", errors="replace").strip()
    return result.returncode, stdout, stderr


def _wt_path(task_id, ide):
    return get_worktrees_dir() / f"{task_id}-{ide}"


def _branch_name(task_id, ide):
    return f"task/{task_id}/{ide}"


def ensure_dir():
    get_worktrees_dir().mkdir(parents=True, exist_ok=True)


def is_ready(task_id, ide):
    return _wt_path(task_id, ide).exists()


def create(task_id, ide, base_branch="main"):
    wt = _wt_path(task_id, ide)
    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)
    ensure_dir()
    # --detach: main 已被主仓库 checkout，不能直接再 checkout
    rc, out, err = _git("worktree", "add", "--detach", str(wt), base_branch)
    if rc != 0:
        return False, f"git worktree add failed: {err}"
    branch = _branch_name(task_id, ide)
    rc, out, err = _git("checkout", "-b", branch, cwd=wt)
    if rc != 0:
        return False, f"git checkout -b failed: {err}"
    return True, str(wt)


def has_uncommitted(task_id, ide):
    wt = _wt_path(task_id, ide)
    rc, out, err = _git("status", "--porcelain", cwd=wt)
    return bool(out.strip())


def commit(task_id, ide, message=None):
    wt = _wt_path(task_id, ide)
    if not message:
        branch = _branch_name(task_id, ide)
        message = f"[AideLink] {branch}"
    rc, out, err = _git("add", "-A", cwd=wt)
    if rc != 0:
        return False, f"git add failed: {err}"
    rc, out, err = _git("commit", "-m", message, cwd=wt)
    if rc != 0:
        if "nothing to commit" in (out + err):
            return False, "nothing_to_commit"
        return False, f"git commit failed: {err}"
    return True, out


def rebase(task_id, ide):
    wt = _wt_path(task_id, ide)
    rc, out, err = _git("rebase", "main", cwd=wt)
    if rc == 0:
        return {"success": True, "conflicts": []}, None
    conflict_files = []
    rc2, out2, _ = _git("diff", "--name-only", "--diff-filter=U", cwd=wt)
    if rc2 == 0 and out2:
        conflict_files = [line.strip() for line in out2.split("\n") if line.strip()]
    return {"success": False, "conflicts": conflict_files, "error": err}, err


def get_conflict_content(task_id, ide, rel_path):
    full = _wt_path(task_id, ide) / rel_path
    if not full.exists():
        return None
    return full.read_text(encoding="utf-8", errors="replace")


def resolve_and_continue(task_id, ide, rel_path, resolved_text):
    wt = _wt_path(task_id, ide) / rel_path
    wt.write_text(resolved_text, encoding="utf-8")
    rc1, _, _ = _git("add", rel_path, cwd=_wt_path(task_id, ide))
    if rc1 != 0:
        return False, "git add failed"
    return _continue_rebase(task_id, ide)


def _continue_rebase(task_id, ide):
    return _git("rebase", "--continue", cwd=_wt_path(task_id, ide))


def abort_rebase(task_id, ide):
    rc, out, err = _git("rebase", "--abort", cwd=_wt_path(task_id, ide))
    return rc == 0, err if rc != 0 else out


def merge(task_id, ide):
    wt = _wt_path(task_id, ide)
    branch = _branch_name(task_id, ide)
    # 主仓库可能有未提交的改动，先 stash
    _git("stash", cwd=get_project_root())
    # git pull <worktree-path> <branch> --ff-only
    rc, out, err = _git("pull", str(wt), branch, "--ff-only", cwd=get_project_root())
    _git("stash", "pop", cwd=get_project_root())  # 还原
    if rc != 0:
        return False, f"git pull --ff-only failed: {err}"
    return True, out or err


def delete_branch(task_id, ide):
    rc, out, err = _git("branch", "-D", _branch_name(task_id, ide))
    return rc == 0, err if rc != 0 else out


def remove(task_id, ide):
    wt = _wt_path(task_id, ide)
    if not wt.exists():
        return True, "not found"
    rc, out, err = _git("worktree", "remove", str(wt))
    if rc != 0:
        rc, out, err = _git("worktree", "remove", "--force", str(wt))
    return rc == 0, err if rc != 0 else out


def cleanup(task_id, ide):
    delete_branch(task_id, ide)
    return remove(task_id, ide)


def detect_test_command(task):
    owned = task.get("owned_paths", [])
    # 只对 test_ 前缀的 .py 文件跑 pytest
    test_files = [p for p in owned if p.endswith(".py") and "test_" in Path(p).name]
    if test_files:
        return {
            "argv": [sys.executable, "-m", "pytest", *test_files, "-x", "-q", "--tb=short"],
            "cwd": None,
        }
    # Gradle 测试
    gradle = any(p.endswith(".kt") for p in owned)
    if gradle:
        from config import load_settings
        app_name = load_settings().get("app_project_name", "")
        return {
            "argv": [".\\gradlew.bat", "test", "--no-daemon", "-q"],
            "cwd": app_name,
        }
    return None
