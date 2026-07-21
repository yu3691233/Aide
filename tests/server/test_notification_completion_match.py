"""完成通知智能匹配回归测试。

样例全部取自本机 wpndatabase.db 实测真实通知（WorkBuddy / Trae / Codex / MiniMax），
用于验证 notification_watcher.classify_completion 不再像旧实现那样 return True，
从而避免把 Trae 失败、MiniMax 等待、Codex 空通知等误判为任务完成。
"""
import sys
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import notification_watcher as nw


class TestClassifyCompletion(unittest.TestCase):
    # ---- 真实正例：完成类 ----
    def test_workbuddy_real_completion(self):
        # 实测自 wpndatabase.db，AUMID=WorkBuddy.WorkBuddy
        self.assertTrue(nw.classify_completion("任务已完成", "任务已成功完成。您可以在编辑器中查看结果。"))

    def test_trae_real_completion(self):
        self.assertTrue(nw.classify_completion("任务完成", "'修复Android浮窗快捷功能' 已完成"))

    def test_trae_real_completion_2(self):
        self.assertTrue(nw.classify_completion("任务完成", "'App端顶部增加平台图标' 已完成"))

    def test_codex_real_completion_body_phrase(self):
        # Codex 标题是任务名，正文含强完成短语
        self.assertTrue(nw.classify_completion(
            "修正测试任务派发标题",
            "已修改，所有“待测试”任务均允许用户直接完成： ... 已提交：24e6e8c",
        ))

    def test_codex_real_completion_body_phrase_2(self):
        self.assertTrue(nw.classify_completion(
            "优化 S1.5 浮窗布局交互",
            "已完成并重启生效。 - 待测试任务展开后新增“测试反馈”按钮。",
        ))

    def test_english_completion(self):
        self.assertTrue(nw.classify_completion("Task completed", "All tests passed."))
        self.assertTrue(nw.classify_completion("Done", "response ready"))

    # ---- 真实负例：旧 return True 会误判，新匹配器必须判 False ----
    def test_trae_real_failure_not_done(self):
        # Trae 失败通知：title="异常打断" body="失败了" —— 旧实现会误标完成
        self.assertFalse(nw.classify_completion("异常打断", "'Windows任务分配逻辑' 失败了"))

    def test_minimax_real_waiting_not_done(self):
        # MiniMax 等待用户确认，并非完成 —— 旧实现会误标完成
        self.assertFalse(nw.classify_completion("验证快捷回复派发修复", "等待你的确认"))

    def test_codex_real_empty_not_done(self):
        # Codex 中间态空通知 —— 旧实现会误标完成
        self.assertFalse(nw.classify_completion("", ""))

    # ---- 合成负例 ----
    def test_error_not_done(self):
        self.assertFalse(nw.classify_completion("错误", "编译失败，请检查"))

    def test_update_not_done(self):
        self.assertFalse(nw.classify_completion("有新版本", "update available"))

    def test_question_not_done(self):
        # 正文虽有"已完成"但带问号 → 不当完成（中间确认问句）
        self.assertFalse(nw.classify_completion("确认", "已完成第一步，是否继续？"))

    def test_new_message_not_done(self):
        self.assertFalse(nw.classify_completion("新消息", "你有一条新消息"))

    def test_negative_overrides_positive(self):
        # 同时命中完成与失败关键词 → 以负向为准
        self.assertFalse(nw.classify_completion("任务完成", "但测试失败，请处理"))


class TestWatcherIntegration(unittest.TestCase):
    """验证 _is_task_done_notification 委托 classify_completion，且 WorkBuddy AUMID 能被识别。"""

    def _watcher(self):
        # 不走 __init__ 的文件/DB 加载，最小桩
        w = nw.NotificationWatcher.__new__(nw.NotificationWatcher)
        w.event_bus = None
        return w

    def test_method_delegates_for_workbuddy_sample(self):
        w = self._watcher()
        notif = {"title": "任务已完成", "body": "任务已成功完成。您可以在编辑器中查看结果。"}
        self.assertTrue(w._is_task_done_notification(notif))

    def test_method_delegates_for_trae_failure(self):
        w = self._watcher()
        notif = {"title": "异常打断", "body": "'X' 失败了"}
        self.assertFalse(w._is_task_done_notification(notif))

    def test_workbuddy_aumid_in_default_map(self):
        # 自测载体：WorkBuddy 自身 AUMID 必须在默认映射里
        self.assertEqual(nw.DEFAULT_AUMID_MAP.get("WorkBuddy.WorkBuddy"), "workbuddy")

    def test_match_ide_workbuddy(self):
        w = self._watcher()
        w._config = {"aumid_map": nw.DEFAULT_AUMID_MAP}
        self.assertEqual(w._match_ide("WorkBuddy.WorkBuddy"), "workbuddy")

    def test_match_ide_codex(self):
        # 实测 Codex 桌面端 AUMID，虽未加入默认映射（其通知噪声大，需单独调参），
        # 但确认 _match_ide 对未知 AUMID 返回 None（不误归到某个 IDE）
        w = self._watcher()
        w._config = {"aumid_map": nw.DEFAULT_AUMID_MAP}
        self.assertIsNone(w._match_ide("OpenAI.Codex_2p2nqsd0c76g0!App"))

    def test_trae_series_differentiated(self):
        # Trae 多系列必须区分到不同 ide_key，避免同时安装时串台。
        # TraeSoloCN → trae_solo_cn（与 manual_ides 派发键/窗口绑定对齐）；
        # Trae Solo → trae_solo；Trae 国际版 → trae。
        w = self._watcher()
        w._config = {"aumid_map": nw.DEFAULT_AUMID_MAP}
        self.assertEqual(w._match_ide("ByteDance.TraeSoloCN"), "trae_solo_cn")
        self.assertEqual(w._match_ide("ByteDance.TraeSolo"), "trae_solo")
        self.assertEqual(w._match_ide("ByteDance.Trae"), "trae")
        # 三者两两不同，确认不再混成一个 key
        keys = {w._match_ide(a) for a in
                ("ByteDance.TraeSoloCN", "ByteDance.TraeSolo", "ByteDance.Trae")}
        self.assertEqual(len(keys), 3)


if __name__ == "__main__":
    unittest.main()
