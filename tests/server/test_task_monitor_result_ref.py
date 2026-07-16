"""TaskMonitor result_ref 死锁修复回归测试（v2，按 T3 主 IDE 复核修正）。

覆盖：
1. result_ref_required 委派任务：read_only/research/test/summary 或 owned_paths=[] 不被旧 commit 自动推进。
2. result_ref_required 委派任务：合法 code+owned_paths 匹配新提交 → 自动完成写 commit:<hash> result_ref。
3. pending_test+result_ref=null 死锁任务可经 mcp_server 补报或 fail 恢复；已有 result_ref 禁止覆盖/降级。
4. verify result_ref 硬门槛不放宽。
5. 普通任务（非 result_ref_required，含 research/test/summary 或 owned_paths=[]）保持既有自动完成语义。
6. 测试隔离 _try_dispatch_next_queued/后台线程，确保 Windows 上整套连续运行三轮稳定通过。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import mcp_server
import task_monitor
from task_runtime import TaskRuntime


def _completed_proc(stdout=""):
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = stdout
    return proc


class TaskMonitorResultRefTests(unittest.TestCase):
    def _make_monitor(self, runtime):
        monitor = task_monitor.TaskMonitor.__new__(task_monitor.TaskMonitor)
        monitor.check_interval = 60
        monitor.worktree_timeout_min = 10
        monitor._running = False
        monitor._thread = None
        monitor._last_commit_hash = None
        monitor._last_worktree_mtime = {}
        monitor._known_ide_pids = {}
        return monitor

    def _patch_runtime(self, runtime):
        return patch("task_monitor._get_task_runtime", return_value=runtime)

    # 所有涉及 mark_task_done/mark_task_failed/mark_task_running 的测试统一隔离
    # _try_dispatch_next_queued，避免后台 daemon 线程持有 ide_status.json 文件锁
    # 导致 Windows 上 TemporaryDirectory 清理失败（WinError 32）。
    def _runtime_patches(self):
        return (
            patch.object(TaskRuntime, "_ensure_timeout_scanner"),
            patch.object(TaskRuntime, "_try_dispatch_next_queued", return_value=None),
        )

    # ---------- _skip_auto_complete 单元测试 ----------

    def test_skip_auto_complete_only_for_result_ref_required_read_only_types(self):
        """#1: result_ref_required=true 时，read_only/research/test/summary 跳过。"""
        for task_type in ("read_only", "research", "test", "summary"):
            task = {
                "task_id": "t-ro", "owned_paths": ["tests/server"],
                "metadata": {"task_type": task_type, "result_ref_required": True},
            }
            self.assertTrue(
                task_monitor.TaskMonitor._skip_auto_complete(task),
                f"task_type={task_type} + result_ref_required 应跳过自动完成",
            )

    def test_skip_auto_complete_only_for_result_ref_required_empty_owned_paths(self):
        """#2: result_ref_required=true + owned_paths=[] 跳过。"""
        task = {
            "task_id": "t-noowned", "owned_paths": [],
            "metadata": {"task_type": "code", "result_ref_required": True},
        }
        self.assertTrue(task_monitor.TaskMonitor._skip_auto_complete(task))

    def test_does_not_skip_auto_complete_for_result_ref_required_code_with_owned_paths(self):
        """合法 result_ref_required code+owned_paths 不跳过，后续写 commit: result_ref。"""
        task = {
            "task_id": "t-code", "owned_paths": ["server/mcp_server.py"],
            "metadata": {"task_type": "code", "result_ref_required": True},
        }
        self.assertFalse(task_monitor.TaskMonitor._skip_auto_complete(task))

    def test_normal_task_not_skipped_regardless_of_type_or_owned_paths(self):
        """#5: 非 result_ref_required 普通任务保持原自动完成语义，不跳过。

        覆盖 research/test/summary/空 owned_paths 等历史会被错误跳过的场景。
        """
        cases = [
            {"task_type": "research", "owned_paths": [], "result_ref_required": False},
            {"task_type": "test", "owned_paths": [], "result_ref_required": False},
            {"task_type": "summary", "owned_paths": [], "result_ref_required": False},
            {"task_type": "read_only", "owned_paths": [], "result_ref_required": False},
            {"task_type": "code", "owned_paths": [], "result_ref_required": False},
            {"task_type": "research", "owned_paths": ["tests/server"], "result_ref_required": False},
            # 完全无 metadata 的旧任务
            {"task_type": None, "owned_paths": [], "result_ref_required": False},
        ]
        for case in cases:
            metadata = {}
            if case["task_type"] is not None:
                metadata["task_type"] = case["task_type"]
            task = {
                "task_id": "t-normal", "owned_paths": case["owned_paths"],
                "metadata": metadata,
            }
            self.assertFalse(
                task_monitor.TaskMonitor._skip_auto_complete(task),
                f"普通任务应保持原自动完成语义: {case}",
            )

    # ---------- 端到端：旧 commit 不推进 result_ref_required 只读委派任务 ----------

    def test_old_commit_does_not_advance_read_only_delegated_task(self):
        """#1 端到端：旧 commit + result_ref_required 只读委派任务 → 不调 mark_task_done。"""
        p1, p2 = self._runtime_patches()
        with tempfile.TemporaryDirectory() as temp_dir, p1, p2:
            runtime = TaskRuntime(temp_dir)
            task = runtime.create_task(
                "只读审计", source="primary_ide", target_ide=None,
                owned_paths=[], metadata={
                    "delegated_by": "primary_ide", "worker_role": "employee",
                    "task_type": "research", "result_ref_required": True,
                },
            )
            task_id = task["task_id"]
            runtime.assign_task(task_id, "trae_solo_cn")
            runtime.mark_task_running(task_id, "trae_solo_cn")
            runtime.set_ide_status("trae_solo_cn", "busy", current_task_id=task_id)

            monitor = self._make_monitor(runtime)
            monitor._last_commit_hash = "oldhash0000000000000000000000000000000000"

            with patch("task_monitor.subprocess.run") as run_mock, self._patch_runtime(runtime):
                run_mock.side_effect = [
                    _completed_proc("newhash0000000000000000000000000000000000"),
                    _completed_proc("feat: unrelated change"),
                    _completed_proc("README.md"),
                ]
                monitor._check_git()

            final = runtime.get_task(task_id)
            self.assertEqual("running", final["status"])
            self.assertIsNone(final["result_ref"])

    def test_old_commit_does_not_advance_empty_owned_paths_delegated_task(self):
        """#2 端到端：result_ref_required + owned_paths=[] code 委派任务也不被旧 commit 推进。"""
        p1, p2 = self._runtime_patches()
        with tempfile.TemporaryDirectory() as temp_dir, p1, p2:
            runtime = TaskRuntime(temp_dir)
            task = runtime.create_task(
                "无文件归属任务", source="primary_ide", target_ide=None,
                owned_paths=[], metadata={
                    "task_type": "code", "result_ref_required": True,
                },
            )
            task_id = task["task_id"]
            runtime.assign_task(task_id, "trae_solo_cn")
            runtime.mark_task_running(task_id, "trae_solo_cn")
            runtime.set_ide_status("trae_solo_cn", "busy", current_task_id=task_id)

            monitor = self._make_monitor(runtime)
            monitor._last_commit_hash = "oldhash0000000000000000000000000000000000"

            with patch("task_monitor.subprocess.run") as run_mock, self._patch_runtime(runtime):
                run_mock.side_effect = [
                    _completed_proc("newhash0000000000000000000000000000000000"),
                    _completed_proc("feat: change"),
                    _completed_proc("server/mcp_server.py"),
                ]
                monitor._check_git()

            final = runtime.get_task(task_id)
            self.assertEqual("running", final["status"])

    # ---------- 端到端：合法 code 任务自动完成写 commit: result_ref ----------

    def test_code_task_with_matching_commit_writes_commit_result_ref(self):
        """#2 端到端：result_ref_required code+owned_paths 匹配新提交 → pending_test + commit:<hash>。"""
        p1, p2 = self._runtime_patches()
        with tempfile.TemporaryDirectory() as temp_dir, p1, p2:
            runtime = TaskRuntime(temp_dir)
            task = runtime.create_task(
                "代码任务", source="primary_ide", target_ide=None,
                owned_paths=["server/mcp_server.py"], metadata={
                    "task_type": "code", "result_ref_required": True,
                },
            )
            task_id = task["task_id"]
            runtime.assign_task(task_id, "trae_solo_cn")
            runtime.mark_task_running(task_id, "trae_solo_cn")
            runtime.set_ide_status("trae_solo_cn", "busy", current_task_id=task_id)

            monitor = self._make_monitor(runtime)
            monitor._last_commit_hash = "oldhash0000000000000000000000000000000000"
            full_new_hash = "abc123def456789012345678901234567890abcd"

            with patch("task_monitor.subprocess.run") as run_mock, self._patch_runtime(runtime):
                run_mock.side_effect = [
                    _completed_proc(full_new_hash),
                    _completed_proc("fix: mcp server bug"),
                    _completed_proc("server/mcp_server.py"),
                ]
                monitor._check_git()

            final = runtime.get_task(task_id)
            self.assertEqual("pending_test", final["status"])
            self.assertEqual(f"commit:{full_new_hash}", final["result_ref"])
            self.assertIn("abc123de", final["summary"])

    def test_normal_code_task_keeps_legacy_behavior_no_result_ref(self):
        """#5: 非 result_ref_required 普通 code 任务保持原行为：自动完成不带 result_ref。"""
        p1, p2 = self._runtime_patches()
        with tempfile.TemporaryDirectory() as temp_dir, p1, p2:
            runtime = TaskRuntime(temp_dir)
            task = runtime.create_task(
                "旧 code 任务", source="user", target_ide=None,
                owned_paths=["server/mcp_server.py"], metadata={"task_type": "code"},
            )
            task_id = task["task_id"]
            runtime.assign_task(task_id, "trae_solo_cn")
            runtime.mark_task_running(task_id, "trae_solo_cn")
            runtime.set_ide_status("trae_solo_cn", "busy", current_task_id=task_id)

            monitor = self._make_monitor(runtime)
            monitor._last_commit_hash = "oldhash0000000000000000000000000000000000"

            with patch("task_monitor.subprocess.run") as run_mock, self._patch_runtime(runtime):
                run_mock.side_effect = [
                    _completed_proc("newhash0000000000000000000000000000000000"),
                    _completed_proc("feat: legacy"),
                    _completed_proc("server/mcp_server.py"),
                ]
                monitor._check_git()

            final = runtime.get_task(task_id)
            self.assertEqual("pending_test", final["status"])
            self.assertIsNone(final["result_ref"])

    def test_normal_read_only_task_keeps_legacy_auto_complete(self):
        """#5: 非 result_ref_required 普通 research 任务也保持原自动完成行为。"""
        p1, p2 = self._runtime_patches()
        with tempfile.TemporaryDirectory() as temp_dir, p1, p2:
            runtime = TaskRuntime(temp_dir)
            task = runtime.create_task(
                "旧 research 任务", source="user", target_ide=None,
                owned_paths=[], metadata={"task_type": "research"},
            )
            task_id = task["task_id"]
            runtime.assign_task(task_id, "trae_solo_cn")
            runtime.mark_task_running(task_id, "trae_solo_cn")
            runtime.set_ide_status("trae_solo_cn", "busy", current_task_id=task_id)

            monitor = self._make_monitor(runtime)
            monitor._last_commit_hash = "oldhash0000000000000000000000000000000000"

            with patch("task_monitor.subprocess.run") as run_mock, self._patch_runtime(runtime):
                run_mock.side_effect = [
                    _completed_proc("newhash0000000000000000000000000000000000"),
                    _completed_proc("feat: legacy research"),
                    _completed_proc("docs/notes.md"),
                ]
                monitor._check_git()

            final = runtime.get_task(task_id)
            # 普通任务保持原有自动完成语义：owned=[] 时旧逻辑直接 mark_task_done 不带 result_ref
            self.assertEqual("pending_test", final["status"])
            self.assertIsNone(final["result_ref"])

    # ---------- pending_test 死锁恢复 + 已有 result_ref 禁止覆盖 ----------

    def test_pending_test_deadlock_recoverable_via_supplement_then_verify(self):
        """#3+#4: pending_test+result_ref=null → 补报 → verify 通过。"""
        p1, p2 = self._runtime_patches()
        with tempfile.TemporaryDirectory() as temp_dir, p1, p2:
            runtime = TaskRuntime(temp_dir)
            with patch("mcp_server.get_runtime", return_value=runtime):
                delegated = mcp_server.handle_delegate_task({
                    "task": "死锁恢复", "target_ide": "trae_solo_cn",
                    "user_confirmed": True, "dispatch": False,
                    "task_type": "research", "owned_paths": [],
                })
                task_id = json.loads(delegated["content"][0]["text"])["task_id"]
                runtime.mark_task_running(task_id, "trae_solo_cn")
                runtime.mark_task_done(task_id, summary="抢跑无证据")
                self.assertEqual("pending_test", runtime.get_task(task_id)["status"])
                self.assertIsNone(runtime.get_task(task_id)["result_ref"])

                # 缺 result_ref 时 report 拒绝、verify 拒绝
                rejected = mcp_server.handle_report_delegated_task({
                    "task_id": task_id, "summary": "仍缺证据",
                })
                self.assertTrue(rejected["isError"])
                rejected_verify = mcp_server.handle_verify_delegated_task({
                    "task_id": task_id, "verification_summary": "无证据",
                })
                self.assertTrue(rejected_verify["isError"])

                # 补报：带 result_ref，状态保持 pending_test
                supplemented = mcp_server.handle_report_delegated_task({
                    "task_id": task_id, "summary": "补报证据",
                    "result_ref": "inline:已通过只读审查",
                })
                self.assertEqual(
                    "pending_test",
                    json.loads(supplemented["content"][0]["text"])["status"],
                )
                self.assertEqual(
                    "inline:已通过只读审查",
                    runtime.get_task(task_id)["result_ref"],
                )

                # verify 现在可通过（result_ref 硬要求未放宽）
                verified = mcp_server.handle_verify_delegated_task({
                    "task_id": task_id, "verification_summary": "主 IDE 确认",
                })
                self.assertEqual("done", json.loads(verified["content"][0]["text"])["status"])

    def test_supplement_path_rejected_when_result_ref_already_present(self):
        """#1: pending_test + 已有 result_ref 禁止补报覆盖。"""
        p1, p2 = self._runtime_patches()
        with tempfile.TemporaryDirectory() as temp_dir, p1, p2:
            runtime = TaskRuntime(temp_dir)
            with patch("mcp_server.get_runtime", return_value=runtime):
                delegated = mcp_server.handle_delegate_task({
                    "task": "已有证据", "target_ide": "trae_solo_cn",
                    "user_confirmed": True, "dispatch": False,
                    "task_type": "test", "owned_paths": ["tests/server"],
                })
                task_id = json.loads(delegated["content"][0]["text"])["task_id"]
                runtime.mark_task_running(task_id, "trae_solo_cn")
                # 正常回传带 result_ref
                runtime.mark_task_done(
                    task_id, summary="正常完成", result_ref="commit:orig123",
                )
                self.assertEqual("commit:orig123", runtime.get_task(task_id)["result_ref"])

                # 试图补报覆盖应被拒
                rejected = mcp_server.handle_report_delegated_task({
                    "task_id": task_id, "summary": "试图覆盖",
                    "result_ref": "commit:new456",
                })
                self.assertTrue(rejected["isError"])
                self.assertIn("已有 result_ref", rejected["content"][0]["text"])
                # 原证据未被覆盖
                self.assertEqual("commit:orig123", runtime.get_task(task_id)["result_ref"])

    def test_pending_test_deadlock_recoverable_via_fail(self):
        """#3 失败路径：pending_test+result_ref=null → fail → failed 释放。"""
        p1, p2 = self._runtime_patches()
        with tempfile.TemporaryDirectory() as temp_dir, p1, p2:
            runtime = TaskRuntime(temp_dir)
            with patch("mcp_server.get_runtime", return_value=runtime):
                delegated = mcp_server.handle_delegate_task({
                    "task": "死锁释放", "target_ide": "trae_solo_cn",
                    "user_confirmed": True, "dispatch": False,
                    "task_type": "research", "owned_paths": [],
                })
                task_id = json.loads(delegated["content"][0]["text"])["task_id"]
                runtime.mark_task_running(task_id, "trae_solo_cn")
                runtime.mark_task_done(task_id, summary="抢跑无证据")

                failed = mcp_server.handle_fail_delegated_task({
                    "task_id": task_id,
                    "error": "死锁，转 failed 释放给主 IDE",
                    "result_ref": "inline:部分证据",
                })
                self.assertEqual(
                    "failed",
                    json.loads(failed["content"][0]["text"])["status"],
                )
                self.assertEqual("failed", runtime.get_task(task_id)["status"])
                self.assertEqual(
                    "inline:部分证据",
                    runtime.get_task(task_id)["result_ref"],
                )

    def test_fail_path_rejected_when_result_ref_already_present(self):
        """#1: pending_test + 已有 result_ref 禁止降级为 failed。"""
        p1, p2 = self._runtime_patches()
        with tempfile.TemporaryDirectory() as temp_dir, p1, p2:
            runtime = TaskRuntime(temp_dir)
            with patch("mcp_server.get_runtime", return_value=runtime):
                delegated = mcp_server.handle_delegate_task({
                    "task": "已有证据不降级", "target_ide": "trae_solo_cn",
                    "user_confirmed": True, "dispatch": False,
                    "task_type": "test", "owned_paths": ["tests/server"],
                })
                task_id = json.loads(delegated["content"][0]["text"])["task_id"]
                runtime.mark_task_running(task_id, "trae_solo_cn")
                runtime.mark_task_done(
                    task_id, summary="正常完成", result_ref="commit:abc789",
                )

                rejected = mcp_server.handle_fail_delegated_task({
                    "task_id": task_id, "error": "试图降级",
                })
                self.assertTrue(rejected["isError"])
                self.assertIn("已有 result_ref", rejected["content"][0]["text"])
                # 状态保持 pending_test，未降级
                self.assertEqual("pending_test", runtime.get_task(task_id)["status"])

    def test_verify_keeps_result_ref_hard_gate_after_supplement_path(self):
        """#4: 补报路径不放宽 verify：pending_test + result_ref=null 仍被 verify 拒绝。"""
        from unittest.mock import Mock
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "task-stuck", "source": "primary_ide", "status": "pending_test",
            "metadata": {"result_ref_required": True}, "result_ref": None,
        }
        with patch("mcp_server.get_runtime", return_value=runtime):
            result = mcp_server.handle_verify_delegated_task({
                "task_id": "task-stuck", "verification_summary": "试图绕过 result_ref",
            })

        self.assertTrue(result["isError"])
        self.assertIn("result_ref", result["content"][0]["text"])
        runtime.confirm_task_done.assert_not_called()

    # ---------- 进程退出路径：result_ref_required 任务改 mark_task_failed ----------

    def test_process_exit_fails_result_ref_required_task_instead_of_deadlock(self):
        """#4 进程退出路径：result_ref_required 任务进程退出 → mark_task_failed（不死锁）。"""
        p1, p2 = self._runtime_patches()
        with tempfile.TemporaryDirectory() as temp_dir, p1, p2:
            runtime = TaskRuntime(temp_dir)
            task = runtime.create_task(
                "委派任务", source="primary_ide", target_ide=None,
                owned_paths=["server/mcp_server.py"], metadata={
                    "task_type": "code", "result_ref_required": True,
                },
            )
            task_id = task["task_id"]
            runtime.assign_task(task_id, "trae_solo_cn")
            runtime.mark_task_running(task_id, "trae_solo_cn")
            runtime.set_ide_status("trae_solo_cn", "busy", current_task_id=task_id)

            monitor = self._make_monitor(runtime)
            with self._patch_runtime(runtime):
                # 第一次：检测到 PID 存在
                with patch.object(monitor, "_get_ide_pids", return_value={1234}):
                    monitor._check_processes()
                # 第二次：PID 消失
                with patch.object(monitor, "_get_ide_pids", return_value=set()):
                    monitor._check_processes()

            final = runtime.get_task(task_id)
            # 关键：result_ref_required 任务进程退出后是 failed 而非 pending_test
            self.assertEqual("failed", final["status"])
            self.assertIn("result_ref_required", final.get("error", ""))


if __name__ == "__main__":
    unittest.main()
