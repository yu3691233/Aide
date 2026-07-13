import json
import sys
import tempfile
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from json_utils import append_to_json_list, read_history, safe_read_json, safe_write_json


class JsonUtilsTests(unittest.TestCase):
    def test_safe_write_round_trip_preserves_unicode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            expected = {"message": "测试", "items": [1, 2, 3]}

            self.assertTrue(safe_write_json(path, expected))
            self.assertEqual(expected, safe_read_json(path, {}))
            self.assertFalse((path.parent / ".state.json.tmp").exists())

    def test_safe_read_returns_default_for_invalid_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "broken.json"
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual({"fallback": True}, safe_read_json(path, {"fallback": True}))

    def test_append_list_applies_max_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.json"
            for number in range(5):
                self.assertTrue(append_to_json_list(path, number, max_size=3))
            self.assertEqual([2, 3, 4], json.loads(path.read_text(encoding="utf-8")))

    def test_read_history_returns_tail_and_rejects_non_list(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "history.json"
            self.assertTrue(safe_write_json(path, list(range(10))))
            self.assertEqual([7, 8, 9], read_history(path, limit=3))
            self.assertTrue(safe_write_json(path, {"unexpected": True}))
            self.assertEqual([], read_history(path, limit=3))


if __name__ == "__main__":
    unittest.main()
