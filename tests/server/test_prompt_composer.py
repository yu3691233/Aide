import unittest
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from prompt_composer import _ai_messages, compose_prompt, infer_task_type


class PromptComposerTests(unittest.TestCase):
    def test_infers_bug_and_builds_safe_fallback(self):
        result = compose_prompt({
            "component": {
                "platform": "Web",
                "name": "任务筛选输入框",
                "page": "任务页面",
                "location": "任务列表 Tab",
            },
            "user_text": "一段时间后会变红",
            "task_type": "auto",
        })

        self.assertTrue(result["ok"])
        self.assertFalse(result["used_ai"])
        self.assertEqual(result["task_type"], "bug_fix")
        self.assertEqual(result["difficulty"], "medium")
        self.assertIn("Web · 任务页面 · 任务列表 Tab · 任务筛选输入框", result["prompt"])

    def test_test_plan_adds_no_write_constraint(self):
        result = compose_prompt({
            "component": {"platform": "App", "name": "任务派发按钮"},
            "user_text": "验证任务派发是否正常",
            "task_type": "test_plan",
        })

        self.assertEqual(result["task_type"], "test_plan")
        self.assertIn("不修改代码、配置或项目文件", result["prompt"])

    def test_accepts_structured_ai_candidates(self):
        def fake_model(_messages):
            return {
                "ok": True,
                "content": '{"difficulty":"simple","candidates":[{"title":"调整输入框","understanding":"移动目标输入框","prompt":"请调整输入框位置。"}]}',
            }

        result = compose_prompt({
            "component": {"name": "输入框"},
            "user_text": "上移到标题下面",
        }, model_caller=fake_model)

        self.assertTrue(result["used_ai"])
        self.assertEqual(result["title"], "调整输入框")
        self.assertEqual(result["candidates"][0]["prompt"], "请调整输入框位置。")

    def test_image_is_passed_as_multimodal_content(self):
        captured = {}

        def fake_model(messages):
            captured["content"] = messages[-1]["content"]
            return {
                "ok": True,
                "content": '{"difficulty":"medium","component_name":"消息输入框","component_location":"聊天页底部","candidates":[{"title":"修复输入框变红","understanding":"输入框状态异常","prompt":"请检查消息输入框变红的问题。"}]}',
            }

        result = compose_prompt({
            "component": {"platform": "Android App"},
            "user_text": "一段时间后会变红",
        }, model_caller=fake_model, image_data_url="data:image/jpeg;base64,abc")

        self.assertIsInstance(captured["content"], list)
        self.assertEqual(captured["content"][1]["type"], "image_url")
        self.assertEqual(result["component_name"], "消息输入框")
        self.assertEqual(result["component_location"], "聊天页底部")

    def test_obvious_test_text_is_not_forced_into_other_types(self):
        self.assertEqual(infer_task_type("测试派发任务并整理结果"), "test_plan")

    def test_bug_signal_wins_over_investigation_wording(self):
        self.assertEqual(infer_task_type("检查输入框为什么会变红"), "bug_fix")

    def test_fallback_is_compact_and_avoids_implementation_tutorial(self):
        result = compose_prompt({
            "component": {"platform": "Desktop", "name": "浮窗输入框"},
            "user_text": "第二行时自动向上扩展",
        })

        self.assertLess(len(result["prompt"]), 200)
        self.assertIn("目标：", result["prompt"])
        self.assertIn("定位：", result["prompt"])
        self.assertNotIn("实现步骤", result["prompt"])

    def test_web_category_is_preserved_in_fallback_and_ai_payload(self):
        captured = {}

        def fake_model(messages):
            captured["payload"] = messages[-1]["content"]
            return {"ok": False, "error": "offline"}

        result = compose_prompt({
            "component": {"platform": "Windows", "name": "任务按钮"},
            "user_text": "调整点击后的任务创建流程",
            "task_type": "feature_change",
            "category": "optimize",
        }, model_caller=fake_model)

        self.assertEqual("optimize", result["category"])
        self.assertEqual("功能优化", result["category_label"])
        self.assertIn("类型：功能优化", result["prompt"])
        self.assertIn('"selected_category": "optimize"', captured["payload"])

    def test_ai_instruction_prioritizes_scope_over_implementation_steps(self):
        messages = _ai_messages(
            {"platform": "Desktop", "name": "浮窗", "page": "", "location": "", "type": "", "technical": {}},
            "缩小输入框",
            "feature_change",
            "simple",
        )
        system = messages[0]["content"]
        self.assertIn("不是教开发IDE如何写代码", system)
        self.assertIn("禁止输出实现教程", system)
        self.assertIn("禁止让IDE先扫描整个项目", system)


if __name__ == "__main__":
    unittest.main()
