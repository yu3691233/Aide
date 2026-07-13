import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from screenshot_engine import _window_title_matches


class ScreenshotWindowMatchingTests(unittest.TestCase):
    def test_codex_accepts_current_chatgpt_window_title(self):
        self.assertTrue(_window_title_matches("codex", "ChatGPT"))

    def test_codex_keeps_legacy_title_compatibility(self):
        self.assertTrue(_window_title_matches("codex", "OpenAI Codex - AideLink"))

    def test_codex_does_not_match_unrelated_window(self):
        self.assertFalse(_window_title_matches("codex", "OpenCode"))


if __name__ == "__main__":
    unittest.main()
