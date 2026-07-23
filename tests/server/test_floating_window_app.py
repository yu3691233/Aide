import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import floating_window_app as fwa


class FloatingWindowAppModelTests(unittest.TestCase):
    def test_pending_test_and_completed_groups_are_collapsed_by_default(self):
        self.assertEqual(
            frozenset({"待测试", "已完成"}),
            fwa.DEFAULT_COLLAPSED_GROUPS,
        )

    def test_empty_bootstrap_renders_safe_empty_states(self):
        model = fwa.build_home_model({})
        self.assertEqual("暂无项目", model["title"])
        self.assertEqual([], model["ides"])
        self.assertEqual([], model["tasks"])
        self.assertEqual("未选择 IDE", model["selected_target"])

    def test_success_after_connection_error_forces_render_even_with_same_signature(self):
        app = object.__new__(fwa.FloatingWindowApp)
        model = fwa.build_home_model({})
        app.connection_failed = True
        app.last_render_signature = __import__("json").dumps(
            model, ensure_ascii=False, sort_keys=True, default=str
        )
        app._render = Mock()

        app._apply_refresh_result(fwa.RefreshResult(True, model))

        app._render.assert_called_once_with(model)
        self.assertFalse(app.connection_failed)

    def test_bootstrap_model_uses_project_ide_summary_and_tasks(self):
        model = fwa.build_home_model({
            "project": {"name": "AideLink", "capabilities": ["web", "android"]},
            "ides": [
                {"key": "trae", "name": "Trae", "running": True, "dispatchable": True, "busy": False},
                {"key": "codex", "name": "Codex", "running": True, "dispatchable": False, "busy": True},
                {"key": "oc", "name": "OpenCode", "running": False, "dispatchable": False},
            ],
            "selected_target": {"key": "trae", "name": "Trae"},
            "task_summary": {
                "needs_user": 2,
                "by_status": {"draft": 2, "pending_test": 1, "running": 1, "queued": 1, "done": 3},
            },
            "tasks": [
                {"title": "桌面浮窗服务端适配", "status": "running", "target_ide": "trae", "version": "1.0.1"},
            ],
        })

        self.assertEqual("AideLink 📱🌐", model["title"])
        self.assertEqual(["web", "android"], model["capabilities"])
        self.assertEqual(["●", "🟡", "○"], [item["dot"] for item in model["ides"]])
        self.assertEqual({"待派发": 2, "待测试": 1, "进行中": 2, "已完成": 3}, model["summary"])
        self.assertEqual("执行中", model["tasks"][0]["status"])
        self.assertEqual("general", model["tasks"][0]["surface"])
        self.assertEqual("1.0.1", model["tasks"][0]["version"])

    def test_task_groups_match_dispatch_and_completed_semantics(self):
        self.assertEqual("待派发", fwa._task_group_name({"status": "待派发"}))
        self.assertEqual("进行中", fwa._task_group_name({"status": "已派发"}))
        self.assertEqual("进行中", fwa._task_group_name({"status": "排队中"}))
        self.assertEqual("待测试", fwa._task_group_name({"status": "待测试"}))
        self.assertEqual("待测试", fwa._task_group_name({"status": "超时"}))
        self.assertEqual("已完成", fwa._task_group_name({"status": "已完成"}))

    def test_legacy_timeout_is_counted_as_pending_test(self):
        model = fwa.build_home_model({
            "task_summary": {
                "by_status": {"draft": 1, "timeout": 2},
            },
        })

        self.assertEqual(1, model["summary"]["待派发"])
        self.assertEqual(2, model["summary"]["待测试"])

    def test_latest_running_task_uses_updated_time(self):
        tasks = [
            {"task_id": "older", "updated_at": "2026-07-19T10:00:00"},
            {"task_id": "newer", "updated_at": "2026-07-19T11:00:00"},
        ]
        self.assertEqual("newer", fwa._latest_task_id(tasks))

    def test_task_surface_groups_android_and_web_tasks(self):
        model = fwa.build_home_model({
            "project": {"name": "AideLink", "capabilities": ["web", "android"]},
            "tasks": [
                {"title": "APK 安装异常", "metadata": {"platform": "Android"}},
                {"title": "登录页面调整", "metadata": {"platform": "Web"}},
            ],
        })

        self.assertEqual(["android", "web"], [task["surface"] for task in model["tasks"]])

    def test_generated_think_title_falls_back_to_task_text(self):
        model = fwa.build_home_model({
            "tasks": [{"title": "<think>The user wants...", "text": "修复登录页提示词"}],
        })

        self.assertEqual("修复登录页提示词", model["tasks"][0]["title"])

    def test_single_running_ide_is_selected_and_closed_target_is_replaced(self):
        ides = [
            {"key": "codex", "running": False, "dispatchable": False},
            {"key": "trae", "running": True, "dispatchable": True},
        ]
        self.assertEqual("trae", fwa.choose_selected_ide("codex", ides))

    def test_busy_running_ide_remains_selectable(self):
        self.assertEqual("codex", fwa.choose_selected_ide(
            None,
            [{"key": "codex", "running": True, "dispatchable": False, "busy": True}],
        ))

    def test_stopped_ide_clears_selection(self):
        self.assertIsNone(fwa.choose_selected_ide(
            "codex",
            [{"key": "codex", "running": False, "dispatchable": False}],
        ))

    def test_visible_task_actions_are_uniform_for_every_status(self):
        for status in ("待派发", "待测试", "执行中", "超时", "失败", "已完成"):
            with self.subTest(status=status):
                self.assertEqual(("copy", "view", "more"), fwa.VISIBLE_TASK_ACTIONS)

    def test_initial_window_position_restores_and_clamps_saved_coordinates(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.root = Mock()
        app._virtual_screen_bounds = Mock(return_value=(0, 0, 1440, 900))
        app._monitor_work_area_at = Mock(return_value=(0, 0, 1440, 900))
        app.window_width = fwa.WINDOW_WIDTH
        app.min_window_height = 500
        app.max_window_height = 720
        with tempfile.TemporaryDirectory() as folder:
            state_file = Path(folder) / "window.json"
            state_file.write_text('{"x": 2000, "y": 800}', encoding="utf-8")
            with patch("floating_window_app.WINDOW_STATE_FILE", state_file):
                position = app._initial_window_position(560)

        self.assertEqual((1070, 340), position)

    def test_monitor_profile_expands_on_large_external_display(self):
        app = object.__new__(fwa.FloatingWindowApp)

        app._set_monitor_profile((0, 0, 1440, 900))
        self.assertEqual((370, 500, 720), (
            app.window_width, app.min_window_height, app.max_window_height,
        ))

        app._set_monitor_profile((1440, 0, 2560, 1440))
        self.assertEqual((480, 760, 1040), (
            app.window_width, app.min_window_height, app.max_window_height,
        ))

    def test_expanded_task_actions_add_pending_test_only_for_running_task(self):
        expected = (
            ("edit", "编辑"),
            ("smart_prompt", "智能提示词"),
            ("complete", "已完成"),
            ("delete", "删除"),
        )
        self.assertEqual(expected, fwa.FloatingWindowApp._expanded_actions({"status": "待派发"}))
        self.assertEqual(
            (
                ("edit", "编辑"),
                ("smart_prompt", "智能提示词"),
                ("pending_test", "待测试"),
                ("complete", "已完成"),
                ("delete", "删除"),
            ),
            fwa.FloatingWindowApp._expanded_actions({"status": "执行中"}),
        )
        self.assertIn(
            ("dispatch_test", "派发测试"),
            fwa.FloatingWindowApp._expanded_actions({"status": "待测试"}),
        )
        self.assertIn(
            ("confirm_done", "已完成"),
            fwa.FloatingWindowApp._expanded_actions({"status": "待测试"}),
        )
        self.assertIn(
            ("confirm_done", "确认完成"),
            fwa.FloatingWindowApp._expanded_actions({
                "status": "待测试",
                "test_result": "passed",
            }),
        )
        self.assertNotIn(
            ("test_feedback", "测试反馈"),
            fwa.FloatingWindowApp._expanded_actions({
                "status": "待测试",
                "test_result": "passed",
            }),
        )
        self.assertIn(
            ("send_test_feedback", "反馈开发 IDE"),
            fwa.FloatingWindowApp._expanded_actions({
                "status": "待测试",
                "test_result": "failed",
            }),
        )
        self.assertIn(
            ("confirm_done", "已完成"),
            fwa.FloatingWindowApp._expanded_actions({
                "status": "待测试",
                "test_result": "failed",
            }),
        )
        self.assertIn(
            ("dispatch_test", "重新测试"),
            fwa.FloatingWindowApp._expanded_actions({
                "status": "待测试",
                "test_result": "failed",
            }),
        )

    def test_test_result_visual_state_only_applies_to_pending_test(self):
        self.assertEqual("passed", fwa._task_test_result({
            "status": "待测试",
            "test_result": "passed",
        }))
        self.assertEqual("dispatched", fwa._task_test_result({
            "status": "待测试",
            "test_result": "dispatched",
        }))
        self.assertEqual("queued", fwa._task_test_result({
            "status": "待测试",
            "test_result": "queued",
        }))
        self.assertEqual("failed", fwa._task_test_result({
            "status": "pending_test",
            "test_result": "failed",
        }))
        self.assertEqual("", fwa._task_test_result({
            "status": "执行中",
            "test_result": "failed",
        }))

    def test_copy_uses_full_body_and_removes_reasoning_fragments(self):
        copied = fwa.task_copy_text({
            "title": "修复登录问题",
            "text": "<think>private reasoning</think>\n完整任务正文\nThe user wants internal details",
        })
        self.assertIn("完整任务正文", copied)
        self.assertNotIn("think", copied.lower())
        self.assertNotIn("The user wants", copied)

    def test_inspiration_kind_is_preserved_for_notes_tab(self):
        model = fwa.build_home_model({
            "tasks": [{
                "title": "界面想法",
                "metadata": {"content_kind": "inspiration"},
            }],
        })

        self.assertEqual("inspiration", model["tasks"][0]["content_kind"])

    def test_select_tab_rejects_unknown_values(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.active_tab = "create"
        app.current_model = {}
        app._render = Mock()

        app.select_tab("unknown")

        self.assertEqual("create", app.active_tab)
        app._render.assert_not_called()

    def test_tabs_only_expose_create_manage_and_tools(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.active_tab = "create"
        app.current_model = {}
        app._render = Mock()

        for tab in ("create", "manage", "tools"):
            app.select_tab(tab)
            self.assertEqual(tab, app.active_tab)
        app.select_tab("notes")
        self.assertEqual("tools", app.active_tab)

    def test_prompt_task_types_match_web_generator(self):
        self.assertEqual(
            (
                ("unspecified", "未指定"),
                ("feature", "新增功能"),
                ("optimize", "功能优化"),
                ("bug", "修复bug"),
                ("other", "其他"),
            ),
            fwa.PROMPT_TASK_TYPES,
        )

    def test_task_card_height_grows_for_full_wrapped_title(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.expanded_task_id = None
        short_height = app._task_card_height({"title": "短任务", "task_id": "1"})
        long_height = app._task_card_height({"text": "较长任务正文" * 12, "task_id": "2"})

        self.assertGreater(long_height, short_height)

    def test_clicking_card_toggles_more_action(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.expanded_task_id = None
        app.current_model = {}
        app._render = Mock()

        app.toggle_task_more("task-1")
        self.assertEqual("task-1", app.expanded_task_id)
        app.toggle_task_more("task-1")
        self.assertIsNone(app.expanded_task_id)

    def test_group_header_toggles_collapsed_state(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.collapsed_groups = set()
        app.current_model = {}
        app._render = Mock()

        app.toggle_group("进行中")
        self.assertIn("进行中", app.collapsed_groups)
        app.toggle_group("进行中")
        self.assertNotIn("进行中", app.collapsed_groups)

    def test_show_more_completed_loads_next_five(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.completed_display_limit = 5
        app.current_model = {}
        app._render = Mock()

        app.show_more_completed()

        self.assertEqual(10, app.completed_display_limit)
        app._render.assert_called_once_with({})

    def test_select_ide_without_input_only_changes_ui_state(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.selected_ide_key = "codex"
        app.current_model = {}
        app._render = Mock()
        app._input_text = Mock(return_value="")
        app._send_input = Mock()

        app.select_ide("trae")

        self.assertEqual("trae", app.selected_ide_key)
        app._render.assert_called_once_with({})
        app._send_input.assert_not_called()

    def test_select_ide_with_input_only_switches_dispatch_target(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.selected_ide_key = "codex"
        app.current_model = {}
        app._render = Mock()
        app._input_text = Mock(return_value="发送内容")
        app._send_input = Mock()

        app.select_ide("trae")

        self.assertEqual("trae", app.selected_ide_key)
        app._send_input.assert_not_called()

    def test_return_does_nothing_on_manage_tab(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.active_tab = "manage"
        app.create_task = Mock()
        app._insert_input_newline = Mock(return_value="break")

        plain_event = type("Event", (), {"state": 0})()
        ctrl_event = type("Event", (), {"state": 0x0004})()

        self.assertIsNone(app._handle_input_return(plain_event))
        app.create_task.assert_not_called()
        self.assertEqual("break", app._handle_input_return(ctrl_event))
        app._insert_input_newline.assert_called_once_with()

    def test_return_creates_task_on_create_tab(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.active_tab = "create"
        app.create_task = Mock()
        app._insert_input_newline = Mock(return_value="break")
        plain_event = type("Event", (), {"state": 0})()
        ctrl_event = type("Event", (), {"state": 0x0004})()

        self.assertEqual("break", app._handle_input_return(plain_event))
        app.create_task.assert_called_once_with()
        self.assertEqual("break", app._handle_input_return(ctrl_event))
        app._insert_input_newline.assert_called_once_with()

    def test_send_uses_selected_ide_and_send_route(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.selected_ide_key = "trae"
        app._input_text = Mock(return_value="修复问题")
        app._run_api = Mock()

        app._send_input()

        self.assertEqual("/send", app._run_api.call_args.args[0])
        self.assertEqual(
            {"text": "修复问题", "target": "trae"},
            app._run_api.call_args.kwargs["payload"],
        )

    def test_create_task_uses_existing_draft_route(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.selected_ide_key = "codex"
        app._input_text = Mock(return_value="任务正文")
        app._run_api = Mock()

        app.create_task()
        self.assertEqual("/api/tasks/create", app._run_api.call_args.args[0])
        self.assertFalse(app._run_api.call_args.kwargs["payload"]["auto_dispatch"])
        # 创建任务只进入待派发，点击任务卡片的派发按钮时才使用选中的 IDE。
        self.assertEqual("auto", app._run_api.call_args.kwargs["payload"]["target_ide"])
        self.assertEqual("floating_window", app._run_api.call_args.kwargs["payload"]["source"])

        # 没有选中运行中的 IDE 时回退到 "auto"（未分配）
        app.selected_ide_key = None
        app._run_api.reset_mock()
        app.create_task()
        self.assertEqual("auto", app._run_api.call_args.kwargs["payload"]["target_ide"])

    def test_smart_prompt_uses_selected_type_and_component_location(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.prompt_task_type = "bug"
        app.prompt_component_name = "创建任务按钮"
        app.prompt_component_location = "浮窗创建任务页底部"
        app.current_model = {"capabilities": ["windows"]}
        app.selected_surface = None
        app._input_text = Mock(return_value="点击后没有进入待派发")
        app._run_api = Mock()

        app.compose_smart_prompt()

        payload = app._run_api.call_args.kwargs["payload"]
        self.assertEqual("bug_fix", payload["task_type"])
        self.assertEqual("bug", payload["category"])
        self.assertEqual("Windows", payload["component"]["platform"])
        self.assertEqual("创建任务按钮", payload["component"]["name"])
        self.assertEqual("浮窗创建任务页底部", payload["component"]["location"])

    def test_create_task_merges_component_context_and_classification(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.prompt_task_type = "bug"
        app.prompt_component_name = "任务类型按钮组"
        app.prompt_component_location = "创建任务页智能提示词卡片"
        app.current_model = {"capabilities": ["windows"]}
        app.selected_surface = None
        app._input_text = Mock(return_value="切换类型后样式没有更新")
        app._run_api = Mock()

        app.create_task()

        payload = app._run_api.call_args.kwargs["payload"]
        self.assertIn("目标：切换类型后样式没有更新", payload["text"])
        self.assertIn("定位：Windows · 创建任务页智能提示词卡片 · 任务类型按钮组", payload["text"])
        self.assertEqual("bug_fix", payload["task_type"])
        self.assertEqual("bug_fix", payload["classification"]["task_type"])
        self.assertEqual(
            "创建任务页智能提示词卡片",
            payload["classification"]["ui_location"],
        )

    def test_windows_component_locator_prefers_project_map_before_region_capture(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.current_model = {"capabilities": ["windows"]}
        app.selected_surface = None
        app.windows_component_locator = Mock()
        app.locate_windows_target = Mock()
        app._run_api = Mock()

        app.open_prompt_component_locator()

        app._run_api.assert_called_once()
        self.assertEqual(
            "/api/project-map/interfaces?surface=windows",
            app._run_api.call_args.args[0],
        )
        app.windows_component_locator.assert_not_called()
        app.locate_windows_target.assert_not_called()

    def test_windows_component_locator_starts_component_capture_mode(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app._start_region_capture = Mock()

        app.windows_component_locator()

        self.assertEqual("create", app.active_tab)
        app._start_region_capture.assert_called_once_with(mode="component")

    def test_component_prompt_payload_uses_windows_image_and_web_category(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.prompt_task_type = "optimize"
        hint = {"selected_box": [100, 100, 300, 200], "screen_size": [1000, 800]}

        payload = app._component_prompt_payload("/uploads/component.png", hint)

        self.assertEqual("/uploads/component.png", payload["image"])
        self.assertEqual("optimize", payload["category"])
        self.assertEqual("feature_change", payload["task_type"])
        self.assertEqual("Windows", payload["component"]["platform"])
        self.assertIn("顶部", payload["component"]["location"])

    def test_component_capture_keeps_context_and_marks_selected_box(self):
        image = fwa.Image.new("RGB", (800, 600), "white")

        result = fwa.FloatingWindowApp._prepare_windows_component_image(
            image, (300, 250, 500, 350)
        )

        self.assertGreater(result.width, 200)
        self.assertGreater(result.height, 100)
        red_pixels = sum(
            1
            for y in range(result.height)
            for x in range(result.width)
            for pixel in (result.getpixel((x, y)),)
            if pixel[0] > 220 and pixel[1] < 80 and pixel[2] < 80
        )
        self.assertGreater(red_pixels, 0)

    def test_component_recognition_result_refills_create_form(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.prompt_component_name = ""
        app.prompt_component_location = ""
        app.current_model = {}
        app._schedule_input_draft_save = Mock()
        app._render = Mock()
        app._set_status = Mock()

        app._apply_windows_component_result({
            "image_used": True,
            "component_name": "保存按钮",
            "component_location": "设置窗口右下角",
        })

        self.assertEqual("保存按钮", app.prompt_component_name)
        self.assertEqual("设置窗口右下角", app.prompt_component_location)
        app._render.assert_called_once_with({})

    def test_multiplatform_task_create_includes_selected_surface(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app._input_text = Mock(return_value="修复桌面浮窗")
        app._run_api = Mock()
        app.current_model = {"capabilities": ["android", "web", "windows"]}
        app.selected_surface = "windows"

        app.create_task()

        payload = app._run_api.call_args.kwargs["payload"]
        self.assertEqual("windows", payload["surface"])

    def test_dispatch_existing_task_does_not_override_task_surface(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.selected_ide_key = "codex"
        app.selected_surface = "web"
        app._run_api = Mock()

        app.execute_task_action("dispatch", {"task_id": "task-1"})

        self.assertEqual("/api/tasks/dispatch", app._run_api.call_args.args[0])
        self.assertEqual(
            {
                "task_ids": ["task-1"],
                "target_ide": "codex",
            },
            app._run_api.call_args.kwargs["payload"],
        )

    def test_single_platform_task_create_omits_surface_selector_value(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app._input_text = Mock(return_value="修复安卓页面")
        app._run_api = Mock()
        app.current_model = {"capabilities": ["android"]}
        app.selected_surface = "android"

        app.create_task()

        self.assertNotIn("surface", app._run_api.call_args.kwargs["payload"])

    def test_project_platforms_use_stable_display_order(self):
        self.assertEqual(
            ["android", "web", "windows"],
            fwa._project_platforms(["windows", "android", "web"]),
        )

    def test_context_tools_require_selection_only_for_multiplatform_project(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.selected_surface = None
        self.assertEqual("android", app._active_tool_surface(["android"]))
        self.assertIsNone(app._active_tool_surface(["android", "web"]))
        app.selected_surface = "web"
        self.assertEqual("web", app._active_tool_surface(["android", "web"]))

    def test_android_device_picker_prefers_connected_device(self):
        result = {
            "devices": [
                {"alias": "offline"},
                {"alias": "phone", "is_adb_connected": True},
            ],
        }
        self.assertEqual(
            "phone",
            fwa.FloatingWindowApp._pick_android_device(result)["alias"],
        )

    def test_created_task_is_optimistically_added_without_replacing_previous_pending(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app._input_text = Mock(return_value="第二条待派发")
        app.current_model = {
            "capabilities": ["general"],
            "tasks": [{"task_id": "older", "status": "待派发", "text": "第一条待派发"}],
        }
        app._run_api = Mock()
        app._render = Mock()
        app._set_input_text = Mock()
        app._set_status = Mock()
        app.refresh = Mock()

        app.create_task()
        callback = app._run_api.call_args.kwargs["on_success"]
        callback({"task_id": "newer"})

        rendered_tasks = app._render.call_args.args[0]["tasks"]
        self.assertEqual(["newer", "older"], [task["task_id"] for task in rendered_tasks])

    def test_task_confirm_uses_allowed_server_action_route(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app._run_api = Mock()

        app.execute_task_action("confirm_done", {"task_id": "task-1"})

        self.assertEqual("/api/tasks/task-1/confirm", app._run_api.call_args.args[0])

    def test_edit_task_moves_content_into_shared_input(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app._input_text = Mock(return_value="原输入")
        app._set_input_text = Mock()
        app.input_box = Mock()
        app._set_status = Mock()
        app.current_model = {}
        app._render = Mock()

        app.execute_task_action("edit", {"task_id": "task-1", "text": "任务正文"})

        self.assertEqual("task-1", app.editing_task_id)
        self.assertEqual("create", app.active_tab)
        self.assertEqual("原输入", app.input_draft_before_task_edit)
        app._set_input_text.assert_called_once_with("任务正文")

    def test_test_feedback_uses_original_context_but_submits_only_new_result(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app._input_text = Mock(return_value="原输入")
        app._set_input_text = Mock()
        app.input_box = Mock()
        app._set_status = Mock()
        app._run_api = Mock()
        app.current_model = {}
        app._render = Mock()

        app.execute_task_action(
            "test_feedback",
            {"task_id": "task-1", "text": "原任务正文", "status": "待测试"},
        )
        context = app.test_feedback_context
        self.assertIn("原任务正文", context)
        self.assertTrue(context.endswith(fwa.TEST_FEEDBACK_MARKER))

        app._input_text.return_value = context + "登录按钮仍然无响应"
        app.create_task()

        self.assertEqual("/api/tasks/feedback", app._run_api.call_args.args[0])
        self.assertEqual(
            {
                "task_id": "task-1",
                "feedback": "登录按钮仍然无响应",
            },
            app._run_api.call_args.kwargs["payload"],
        )

    def test_test_feedback_requires_content_after_context(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.test_feedback_task_id = "task-1"
        app.test_feedback_context = "上下文" + fwa.TEST_FEEDBACK_MARKER
        app._input_text = Mock(return_value=app.test_feedback_context)
        app._set_status = Mock()
        app._run_api = Mock()

        app.create_task()

        app._run_api.assert_not_called()
        self.assertIn("测试反馈", app._set_status.call_args.args[0])

    def test_test_feedback_ignores_modified_original_context(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.test_feedback_task_id = "task-1"
        app.test_feedback_context = "原任务上下文：\n原文" + fwa.TEST_FEEDBACK_MARKER
        app._input_text = Mock(
            return_value="原任务上下文：\n被误改的原文"
            + fwa.TEST_FEEDBACK_MARKER
            + "测试仍然失败"
        )
        app._set_status = Mock()
        app._run_api = Mock()

        app.create_task()

        self.assertEqual(
            {"task_id": "task-1", "feedback": "测试仍然失败"},
            app._run_api.call_args.kwargs["payload"],
        )

    def test_complete_task_uses_manual_complete_route(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app._run_api = Mock()

        app.execute_task_action("complete", {"task_id": "task-1"})

        self.assertEqual("/api/tasks/complete", app._run_api.call_args.args[0])
        self.assertEqual(
            {"task_id": "task-1", "manual": True},
            app._run_api.call_args.kwargs["payload"],
        )

    def test_pending_test_action_uses_non_manual_complete_route(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app._run_api = Mock()

        app.execute_task_action("pending_test", {"task_id": "task-1"})

        self.assertEqual("/api/tasks/complete", app._run_api.call_args.args[0])
        self.assertEqual(
            {
                "task_id": "task-1",
                "manual": False,
                "summary": "等待测试",
            },
            app._run_api.call_args.kwargs["payload"],
        )

    def test_dispatch_test_action_uses_dedicated_test_route(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.selected_ide_key = "trae"
        app._run_api = Mock()

        app.execute_task_action("dispatch_test", {"task_id": "task-1"})

        self.assertEqual("/api/tasks/test", app._run_api.call_args.args[0])
        self.assertEqual(
            {"task_id": "task-1", "test_ide": "trae"},
            app._run_api.call_args.kwargs["payload"],
        )

    def test_dispatch_selected_tests_uses_batch_test_route(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.selected_ide_key = "trae"
        app.selected_test_task_ids = {"task-1", "task-2"}
        app.current_model = {"tasks": [{"task_id": "task-2"}, {"task_id": "task-1"}]}
        app._run_api = Mock()
        app._set_status = Mock()

        app.dispatch_selected_tests()

        self.assertEqual("/api/tasks/test", app._run_api.call_args.args[0])
        payload = app._run_api.call_args.kwargs["payload"]
        self.assertEqual({"task-1", "task-2"}, set(payload["task_ids"]))
        self.assertEqual(["task-2", "task-1"], payload["task_ids"])
        self.assertEqual("trae", payload["test_ide"])

    def test_test_checkboxes_only_enter_through_multi_select_mode(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.test_selection_mode = False
        app.selected_test_task_ids = {"task-1"}
        app.collapsed_groups = {"待测试"}
        app.current_model = {}
        app._render = Mock()

        app.toggle_test_selection_mode()
        self.assertTrue(app.test_selection_mode)
        self.assertNotIn("待测试", app.collapsed_groups)

        app.toggle_test_selection_mode()
        self.assertFalse(app.test_selection_mode)
        self.assertEqual(set(), app.selected_test_task_ids)

    def test_window_signal_sends_requested_command(self):
        received = []
        ready = threading.Event()
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        test_port = probe.getsockname()[1]
        probe.close()

        def server():
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", test_port))
            sock.listen(1)
            ready.set()
            conn, _addr = sock.accept()
            with conn:
                received.append(conn.recv(32))
            sock.close()

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        ready.wait(timeout=1)
        with patch("floating_window_app.SHOW_SIGNAL_PORT", test_port):
            self.assertTrue(fwa.send_window_signal("close", timeout=1))
        thread.join(timeout=1)
        self.assertEqual([b"close"], received)

    def test_duplicate_instance_main_exits_after_signal(self):
        instance = Mock()
        instance.acquire.return_value = False
        with patch("floating_window_app.SingleInstance", return_value=instance), \
             patch("floating_window_app.send_window_signal", return_value=True) as send_signal:
            self.assertEqual(0, fwa.main())
        send_signal.assert_called_once_with("activate")

    def test_close_destroys_window(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.root = Mock()

        app.close()

        app.root.destroy.assert_called_once_with()
        app.root.withdraw.assert_not_called()

    def test_component_target_pool_is_project_scoped_and_builds_short_phrase(self):
        app = object.__new__(fwa.FloatingWindowApp)
        app.current_model = {"project_path": "F:/demo"}
        app.component_pools = {}
        app._save_input_draft = Mock()
        target = {
            "id": "web-task-content",
            "surface": "web",
            "page": "任务管理",
            "area": "项目界面地图",
            "name": "[下拉框] Android客户端",
        }

        app._add_component_target(target)

        self.assertEqual([target], app.component_pools["F:/demo"])
        self.assertEqual(
            "Web端-任务管理-项目界面地图-Android客户端",
            app._component_phrase(target),
        )
        app.current_model = {"project_path": "F:/other"}
        self.assertEqual([], app._current_component_pool())


if __name__ == "__main__":
    unittest.main()
