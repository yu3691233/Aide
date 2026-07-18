import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from floating_icons import IconFactory


class FloatingIconTests(unittest.TestCase):
    def test_core_icons_render_as_nonempty_rgba_images(self):
        for name in ("pin", "settings", "copy", "dispatch", "send", "list"):
            with self.subTest(name=name):
                image = IconFactory._load_common(name, 18, "#263246")
                self.assertEqual((18, 18), image.size)
                self.assertEqual("RGBA", image.mode)
                self.assertIsNotNone(image.getbbox())


if __name__ == "__main__":
    unittest.main()
