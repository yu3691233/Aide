import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import screenshot_engine
from screenshot_engine import _normalize_input_region, get_input_focus_client_point


class InputFocusCalibrationTests(unittest.TestCase):
    def test_disabled_calibration_does_not_return_click_point(self):
        config = {
            "focus_input_enabled": False,
            "input_region": {"x": 0.25, "y": 0.8, "width": 0.5, "height": 0.1},
        }
        self.assertIsNone(get_input_focus_client_point(config, 1000, 800))

    def test_enabled_calibration_clicks_region_center(self):
        config = {
            "focus_input_enabled": True,
            "input_region": {"x": 0.2, "y": 0.75, "width": 0.6, "height": 0.1},
        }
        self.assertEqual(get_input_focus_client_point(config, 1000, 800), (500, 640))

    def test_region_outside_client_area_is_rejected(self):
        with self.assertRaises(ValueError):
            _normalize_input_region({"x": 0.8, "y": 0.8, "width": 0.3, "height": 0.1})

    def test_invalid_saved_region_fails_closed(self):
        config = {
            "focus_input_enabled": True,
            "input_region": {"x": 0.2, "y": 0.8, "width": 0, "height": 0.1},
        }
        self.assertIsNone(get_input_focus_client_point(config, 1000, 800))

    def test_enabled_region_is_persisted_with_crop_config(self):
        region = {"x": 0.2, "y": 0.75, "width": 0.6, "height": 0.1}
        with tempfile.TemporaryDirectory() as temp_dir:
            crops_file = str(Path(temp_dir) / "screenshot_crops.json")
            with patch.object(screenshot_engine, "CROPS_FILE", crops_file), \
                    patch.object(screenshot_engine, "_find_target_window", return_value=None):
                result = screenshot_engine.set_crop_config(
                    "custom", 1, 2, 3, 4, "primary",
                    calib_width=1000, calib_height=800,
                    focus_input_enabled=True, input_region=region,
                )
                saved = screenshot_engine.get_crop_config("custom", "primary")

        self.assertTrue(result["focus_input_enabled"])
        self.assertEqual(saved["input_region"], region)

    def test_enabling_without_marked_region_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            crops_file = str(Path(temp_dir) / "screenshot_crops.json")
            with patch.object(screenshot_engine, "CROPS_FILE", crops_file), \
                    patch.object(screenshot_engine, "_find_target_window", return_value=None):
                with self.assertRaises(ValueError):
                    screenshot_engine.set_crop_config(
                        "custom", 0, 0, 0, 0, "primary",
                        focus_input_enabled=True,
                    )


if __name__ == "__main__":
    unittest.main()
