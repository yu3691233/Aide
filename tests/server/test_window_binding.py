import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from window_binding import binding_match_score, select_best_candidate


class WindowBindingTests(unittest.TestCase):
    def test_process_identity_survives_title_change(self):
        binding = {"title": "Codex", "exe_name": "chatgpt.exe", "window_class": "Chrome_WidgetWin_1"}
        candidate = {"title": "ChatGPT", "exe_name": "chatgpt.exe", "window_class": "Chrome_WidgetWin_1", "width": 1200, "height": 900}
        self.assertGreaterEqual(binding_match_score(binding, candidate), 100)

    def test_rejects_same_title_from_wrong_process(self):
        binding = {"title": "ChatGPT", "exe_name": "chatgpt.exe"}
        browser = {"title": "ChatGPT", "exe_name": "chrome.exe", "width": 1600, "height": 1000}
        self.assertEqual(-1, binding_match_score(binding, browser))

    def test_prefers_largest_window_when_identity_is_equal(self):
        binding = {"exe_name": "chatgpt.exe"}
        small = {"hwnd": 1, "title": "ChatGPT", "exe_name": "chatgpt.exe", "width": 300, "height": 200}
        large = {"hwnd": 2, "title": "ChatGPT", "exe_name": "chatgpt.exe", "width": 1200, "height": 900}
        self.assertEqual(2, select_best_candidate(binding, [small, large])["hwnd"])


if __name__ == "__main__":
    unittest.main()
