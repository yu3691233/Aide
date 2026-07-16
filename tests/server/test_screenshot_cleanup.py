import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from routes.screenshot_routes import _capture_to_jpeg


class _Image:
    def __init__(self):
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


class _Encoder:
    def __init__(self, scaled, raises=False):
        self.scaled = scaled
        self.raises = raises

    def _scale_for_phone(self, _image):
        return self.scaled

    def _encode_jpeg(self, _image):
        if self.raises:
            raise RuntimeError("encode failed")
        return b"jpeg"


class ScreenshotCleanupTests(unittest.TestCase):
    def test_closes_source_and_scaled_images_after_encoding(self):
        source = _Image()
        scaled = _Image()

        self.assertEqual(_capture_to_jpeg(source, _Encoder(scaled)), b"jpeg")
        self.assertEqual(source.close_calls, 1)
        self.assertEqual(scaled.close_calls, 1)

    def test_closes_both_images_when_encoding_fails(self):
        source = _Image()
        scaled = _Image()

        self.assertIsNone(_capture_to_jpeg(source, _Encoder(scaled, raises=True)))
        self.assertEqual(source.close_calls, 1)
        self.assertEqual(scaled.close_calls, 1)

    def test_does_not_double_close_when_scaling_returns_source_image(self):
        source = _Image()

        self.assertEqual(_capture_to_jpeg(source, _Encoder(source)), b"jpeg")
        self.assertEqual(source.close_calls, 1)
