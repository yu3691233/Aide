import unittest

from PIL import Image

from capture_window import _is_blank_image


class CaptureWindowBlankImageTests(unittest.TestCase):
    def test_detects_black_and_white_capture_failures(self):
        self.assertTrue(_is_blank_image(Image.new("RGB", (100, 100), "black")))
        self.assertTrue(_is_blank_image(Image.new("RGB", (100, 100), "white")))

    def test_keeps_real_window_content(self):
        image = Image.new("RGB", (100, 100), "white")
        for x in range(25, 75):
            for y in range(25, 75):
                image.putpixel((x, y), (30, 30, 30))
        self.assertFalse(_is_blank_image(image))


if __name__ == "__main__":
    unittest.main()
