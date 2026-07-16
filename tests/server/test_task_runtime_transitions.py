"""TaskRuntime 状态转换合法性校验测试。

覆盖 T5-B 验收清单：
1. 非法 running → done 直接 update 被拒绝
2. 非法 pending_test → done 直接 update 被拒绝（必须经 confirm_task_done）
3. 合法 confirm_task_done → done 成功
4. 合法 failed 路径保持（running/dispatched/pending_test → failed）
5. 非法 status 值被拒绝
6. 旧测试保持通过（经 test_mcp_server 回归）
7. mark_task_done → pending_test 合法
8. merging → done 合法（merge_daemon 自动合并路径）
9. 未知旧状态允许迁移（历史归档兼容）
10. 同状态更新字段合法（如只改 summary）
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# 让测试能 import server.task_runtime
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "server"))

import task_runtime
from task_runtime import TaskRuntime, TaskStatusError


def _make_runtime():
    """构造一个使用临时 state 目录的 TaskRuntime，避免污染真实状态。"""
    tmp = tempfile.mkdtemp(prefix="task_runtime_transitions_")
    return TaskRuntime(tmp), tmp


def _create_task(runtime, status="draft"):
    """创建一个任务并可选地推进到指定起始状态（用专用方法，绕过校验）。"""
    task = runtime.create_task(
        "test objective",
        title="transition test",
        source="primary_ide",
        target_ide=None,
        owned_paths=[],
    )
    task_id = task["task_id"]
    # 用专用方法推进到目标起始状态
    if status == "running":
        runtime.mark_task_running(task_id, "codex")
    elif status == "pending_test":
        runtime.mark_task_running(task_id, "codex")
        runtime.mark_task_done(task_id, summary="done", result_ref="inline:test")
    elif status == "dispatched":
        runtime.mark_task_running(task_id, "codex")
        # dispatched 是 running 的等价态，直接用 update_task 带 skip
        runtime.update_task(task_id, status="dispatched", _skip_status_check=True)
    elif status == "merging":
        runtime.mark_task_running(task_id, "codex")
        runtime.mark_task_done(task_id, summary="done", result_ref="inline:test")
        runtime.update_task(task_id, status="merging", merge_stage="commit")
    return task_id


class TaskRuntimeTransitionTests(unittest.TestCase):
    def test_illegal_running_to_done_rejected(self):
        """1. 非法 running → done 直接 update 被拒绝。"""
        runtime, _ = _make_runtime()
        task_id = _create_task(runtime, status="running")
        with self.assertRaises(TaskStatusError) as ctx:
            runtime.update_task(task_id, status="done")
        self.assertIn("running", str(ctx.exception))
        self.assertIn("done", str(ctx.exception))
        # 状态未改变
        self.assertEqual("running", runtime.get_task(task_id)["status"])

    def test_illegal_pending_test_to_done_direct_update_rejected(self):
        """2. 非法 pending_test → done 直接 update 被拒绝（必须经 confirm_task_done）。"""
        runtime, _ = _make_runtime()
        task_id = _create_task(runtime, status="pending_test")
        with self.assertRaises(TaskStatusError) as ctx:
            runtime.update_task(task_id, status="done")
        self.assertIn("pending_test", str(ctx.exception))
        self.assertIn("done", str(ctx.exception))
        # 状态未改变
        self.assertEqual("pending_test", runtime.get_task(task_id)["status"])

    def test_legal_confirm_task_done_to_done_succeeds(self):
        """3. 合法 confirm_task_done → done 成功。"""
        runtime, _ = _make_runtime()
        task_id = _create_task(runtime, status="pending_test")
        task = runtime.confirm_task_done(task_id)
        self.assertIsNotNone(task)
        self.assertEqual("done", task["status"])
        self.assertEqual("done", runtime.get_task(task_id)["status"])

    def test_legal_failed_path_preserved(self):
        """4. 合法 failed 路径保持（running/dispatched/pending_test → failed）。"""
        runtime, _ = _make_runtime()
        # running → failed
        task_id = _create_task(runtime, status="running")
        task = runtime.mark_task_failed(task_id, error="boom")
        self.assertEqual("failed", task["status"])
        # pending_test → failed（死锁恢复路径）
        task_id2 = _create_task(runtime, status="pending_test")
        task2 = runtime.mark_task_failed(task_id2, error="deadlock recovery")
        self.assertEqual("failed", task2["status"])
        # 直接 update_task → failed 也应合法（任意 → failed）
        task_id3 = _create_task(runtime, status="running")
        task3 = runtime.update_task(task_id3, status="failed", error="direct fail")
        self.assertEqual("failed", task3["status"])

    def test_illegal_status_value_rejected(self):
        """5. 非法 status 值被拒绝。"""
        runtime, _ = _make_runtime()
        task_id = _create_task(runtime, status="running")
        for bad in ("finished", "complete", "ok", "", "DONE", "pending-test", 123):
            with self.assertRaises(TaskStatusError) as ctx:
                runtime.update_task(task_id, status=bad)
            self.assertIn("非法", str(ctx.exception))

    def test_mark_task_done_to_pending_test_legal(self):
        """7. mark_task_done → pending_test 合法（running → pending_test）。"""
        runtime, _ = _make_runtime()
        task_id = _create_task(runtime, status="running")
        task = runtime.mark_task_done(task_id, summary="worker report", result_ref="commit:abc123")
        self.assertEqual("pending_test", task["status"])
        self.assertEqual("commit:abc123", task["result_ref"])

    def test_merging_to_done_legal(self):
        """8. merging → done 合法（merge_daemon 自动合并路径）。"""
        runtime, _ = _make_runtime()
        task_id = _create_task(runtime, status="merging")
        # merge_daemon 直接 update_task(status="done") 应成功
        task = runtime.update_task(task_id, status="done", completed_at="2026-07-17T00:00:00")
        self.assertEqual("done", task["status"])

    def test_unknown_old_status_allows_migration(self):
        """9. 未知旧状态允许迁移（历史归档兼容）。"""
        runtime, _ = _make_runtime()
        task_id = _create_task(runtime, status="running")
        # 模拟历史归档任务状态
        runtime.update_task(task_id, status="archived", _skip_status_check=True)
        # 未知旧状态 → 已知合法状态应允许
        task = runtime.update_task(task_id, status="failed", error="legacy cleanup")
        self.assertEqual("failed", task["status"])

    def test_same_status_field_update_legal(self):
        """10. 同状态更新字段合法（如只改 summary）。"""
        runtime, _ = _make_runtime()
        task_id = _create_task(runtime, status="pending_test")
        task = runtime.update_task(task_id, summary="updated summary", result_ref="file:new/path")
        self.assertEqual("pending_test", task["status"])
        self.assertEqual("updated summary", task["summary"])
        self.assertEqual("file:new/path", task["result_ref"])

    def test_dispatched_to_done_rejected(self):
        """额外：dispatched → done 直接 update 被拒绝。"""
        runtime, _ = _make_runtime()
        task_id = _create_task(runtime, status="dispatched")
        with self.assertRaises(TaskStatusError):
            runtime.update_task(task_id, status="done")
        self.assertEqual("dispatched", runtime.get_task(task_id)["status"])

    def test_dispatched_to_pending_test_legal(self):
        """额外：dispatched → pending_test 合法（mark_task_done 从 dispatched）。"""
        runtime, _ = _make_runtime()
        task_id = _create_task(runtime, status="dispatched")
        task = runtime.mark_task_done(task_id, summary="done", result_ref="inline:test")
        self.assertEqual("pending_test", task["status"])

    def test_done_to_pending_test_rejected(self):
        """额外：done → pending_test 被拒绝（不能回退）。"""
        runtime, _ = _make_runtime()
        task_id = _create_task(runtime, status="pending_test")
        runtime.confirm_task_done(task_id)
        with self.assertRaises(TaskStatusError):
            runtime.update_task(task_id, status="pending_test")
        self.assertEqual("done", runtime.get_task(task_id)["status"])

    def test_skip_status_check_internal_only(self):
        """额外：_skip_status_check 是内部参数，外部调用无法伪造跳过。

        注：Python 无法真正阻止调用方传 _skip_status_check=True（名称改组约定），
        但 update_task 会从 fields pop 该键，调用方必须知道内部约定才能用。
        此测试确认专用方法能用，外部正常调用不会意外跳过。
        """
        runtime, _ = _make_runtime()
        task_id = _create_task(runtime, status="running")
        # 正常外部调用会被拦
        with self.assertRaises(TaskStatusError):
            runtime.update_task(task_id, status="done")
        # 专用方法能跳过
        runtime.mark_task_done(task_id, summary="done", result_ref="inline:test")
        runtime.confirm_task_done(task_id)
        self.assertEqual("done", runtime.get_task(task_id)["status"])


if __name__ == "__main__":
    unittest.main()
