import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.task_routes_flow import (
    _dispatch_prefix,
    api_tasks_complete,
    api_tasks_dispatch,
    api_tasks_edit,
)


class ManualTaskCompleteTests(unittest.TestCase):
    def test_dispatch_prefix_uses_surface_only_when_every_task_matches(self):
        windows = {"metadata": {"surface": "windows"}}
        web = {"metadata": {"surface": "web"}}
        unspecified = {"metadata": {}}

        self.assertEqual("[派发任务-Windows]", _dispatch_prefix([windows]))
        self.assertEqual("[派发任务-Web]", _dispatch_prefix([web, web]))
        self.assertEqual("[派发任务]", _dispatch_prefix([windows, web]))
        self.assertEqual("[派发任务]", _dispatch_prefix([windows, unspecified]))

    def test_dispatch_prefix_identifies_redispatched_test_task(self):
        test_windows = {"metadata": {"surface": "windows", "is_test": True}}
        test_unspecified = {"metadata": {"is_test": True}}

        self.assertEqual("[测试任务-Windows]", _dispatch_prefix([test_windows]))
        self.assertEqual("[测试任务]", _dispatch_prefix([test_unspecified]))

    def test_dispatch_preserves_task_surface_before_injection(self):
        app = Flask(__name__)
        runtime = Mock()
        runtime.get_task.return_value = {
            "task_id": "task-1",
            "metadata": {"surface": "android"},
        }
        injected = {}

        def capture_injection(_target, message, _task_id):
            injected["message"] = message
            return True, "ok"

        with app.test_request_context(
            "/api/tasks/dispatch",
            method="POST",
            json={
                "task_ids": ["task-1"],
                "target_ide": "codex",
                "surface": "web",
            },
        ), patch(
            "routes.task_routes_flow._read_task_data",
            return_value={
                "task_id": "task-1",
                "title": "修复页面",
                "message": "修复页面",
                "metadata": {"surface": "android"},
            },
        ), patch(
            "routes.task_routes_flow._inject_to_ide",
            side_effect=capture_injection,
        ), patch("task_runtime.TaskRuntime", return_value=runtime):
            response = api_tasks_dispatch()

        self.assertTrue(response.get_json()["success"])
        self.assertTrue(injected["message"].startswith("[派发任务-Android]\n"))
        updated_metadata = runtime.update_task.call_args.kwargs["metadata"]
        self.assertEqual("android", updated_metadata["surface"])

    def test_manual_complete_confirms_even_when_pending_transition_is_invalid(self):
        app = Flask(__name__)
        runtime = Mock()
        runtime.mark_task_done.side_effect = ValueError("draft cannot transition to pending_test")

        with app.test_request_context(
            "/api/tasks/complete",
            method="POST",
            json={"task_id": "task-1", "manual": True},
        ), patch("routes.task_routes_flow._read_task_data", return_value={"task_id": "task-1"}), \
             patch("task_runtime.TaskRuntime", return_value=runtime):
            response = api_tasks_complete()

        self.assertTrue(response.get_json()["success"])
        runtime.confirm_task_done.assert_called_once_with("task-1", is_manual=True)

    def test_non_manual_complete_moves_running_task_to_pending_test(self):
        app = Flask(__name__)
        runtime = Mock()

        with app.test_request_context(
            "/api/tasks/complete",
            method="POST",
            json={
                "task_id": "task-1",
                "manual": False,
                "summary": "等待测试",
            },
        ), patch(
            "routes.task_routes_flow._read_task_data",
            return_value={"task_id": "task-1", "target_ide": ""},
        ), patch(
            "routes.task_routes_flow._get_merged_dispatch_ids",
            return_value=[],
        ), patch("task_runtime.TaskRuntime", return_value=runtime):
            response = api_tasks_complete()

        self.assertTrue(response.get_json()["success"])
        runtime.mark_task_done.assert_called_once_with(
            "task-1",
            summary="等待测试",
            is_manual=False,
        )
        runtime.confirm_task_done.assert_not_called()

    def test_edit_task_reopens_as_draft_even_if_running_changes_to_pending_test(self):
        app = Flask(__name__)
        runtime = Mock()
        runtime.reopen_task_as_draft.return_value = {
            "task_id": "task-1",
            "status": "draft",
        }

        with app.test_request_context(
            "/api/tasks/edit",
            method="POST",
            json={"task_id": "task-1", "message": "修改后的正文"},
        ), patch(
            "routes.task_routes_flow._read_task_data",
            return_value={
                "task_id": "task-1",
                "status": "pending_test",
                "target_ide": "codex",
            },
        ), patch(
            "routes.task_routes_flow._load_queue",
            return_value=[
                {"task_id": "task-1", "message": "旧内容"},
                {"task_id": "task-2", "message": "保留内容"},
            ],
        ), patch(
            "routes.task_routes_flow._save_queue"
        ) as save_queue, patch("task_runtime.TaskRuntime", return_value=runtime):
            response = api_tasks_edit()

        self.assertTrue(response.get_json()["success"])
        runtime.reopen_task_as_draft.assert_called_once_with(
            "task-1",
            text="修改后的正文",
            title="修改后的正文",
        )
        self.assertEqual(
            [{"task_id": "task-2", "message": "保留内容"}],
            save_queue.call_args.args[1],
        )


if __name__ == "__main__":
    unittest.main()
