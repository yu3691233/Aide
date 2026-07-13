import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from task_runtime import TaskRuntime


class _FakeThread:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False

    def is_alive(self):
        return self.started

    def start(self):
        self.started = True


class TaskRuntimeScannerTests(unittest.TestCase):
    def test_only_one_timeout_scanner_is_started_per_base_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            created = []

            def make_thread(**kwargs):
                thread = _FakeThread(**kwargs)
                created.append(thread)
                return thread

            key = str(Path(temp_dir).resolve()).lower()
            TaskRuntime._timeout_scanner_threads.pop(key, None)
            try:
                with patch("task_runtime.threading.Thread", side_effect=make_thread):
                    TaskRuntime(temp_dir)
                    TaskRuntime(temp_dir)

                self.assertEqual(1, len(created))
                self.assertTrue(created[0].started)
                self.assertIn(key, TaskRuntime._timeout_scanner_threads)
                self.assertIs(TaskRuntime(temp_dir)._lock, TaskRuntime(temp_dir)._lock)
            finally:
                TaskRuntime._timeout_scanner_threads.pop(key, None)
                TaskRuntime._state_locks.pop(key, None)


if __name__ == "__main__":
    unittest.main()
