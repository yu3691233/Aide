import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.task_routes import _task_type_for_list


class TaskListClassificationTests(unittest.TestCase):
    def test_legacy_task_without_type_remains_visible(self):
        self.assertEqual("task", _task_type_for_list({"title": "实现目标项目安装"}))

    def test_explicit_chat_remains_excludable(self):
        self.assertEqual("chat", _task_type_for_list({"task_type": "chat"}))

    def test_bug_signature_is_classified_as_bug_fix(self):
        task = {"title": "日志异常", "metadata": {"bug_signature": "abc"}}
        self.assertEqual("bug_fix", _task_type_for_list(task))

    def test_inspiration_metadata_is_exposed_to_app_as_note_type(self):
        task = {"title": "随记", "metadata": {"content_kind": "inspiration"}}
        self.assertEqual("inspiration", _task_type_for_list(task))


if __name__ == "__main__":
    unittest.main()
