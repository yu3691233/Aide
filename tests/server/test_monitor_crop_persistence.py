import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import screenshot_engine


def monitor(name, config_key, *, primary=False):
    return {
        "name": name,
        "config_key": config_key,
        "primary": primary,
        "left": 0,
        "top": 0,
        "right": 1920,
        "bottom": 1080,
        "width": 1920,
        "height": 1080,
    }


class MonitorCropPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.crops_file = str(Path(self.temp_dir.name) / "screenshot_crops.json")
        self.crops_patch = patch.object(screenshot_engine, "CROPS_FILE", self.crops_file)
        self.window_patch = patch.object(screenshot_engine, "_find_target_window", return_value=None)
        self.crops_patch.start()
        self.window_patch.start()
        self.addCleanup(self.crops_patch.stop)
        self.addCleanup(self.window_patch.stop)

    def test_physical_monitor_configs_survive_primary_display_switch(self):
        before_switch = [
            monitor("primary", "monitor_a", primary=True),
            monitor("ext_1920_0", "monitor_b"),
        ]
        with patch.object(screenshot_engine, "get_all_monitors", return_value=before_switch):
            screenshot_engine.set_crop_config("codex", 10, 11, 12, 13, "primary")
            screenshot_engine.set_crop_config("codex", 20, 21, 22, 23, "ext_1920_0")

        after_switch = [
            monitor("ext_-1920_0", "monitor_a"),
            monitor("primary", "monitor_b", primary=True),
        ]
        with patch.object(screenshot_engine, "get_all_monitors", return_value=after_switch):
            old_primary = screenshot_engine.get_crop_config("codex", "ext_-1920_0")
            new_primary = screenshot_engine.get_crop_config("codex", "primary")

        self.assertEqual(10, old_primary["left"])
        self.assertEqual(20, new_primary["left"])

    def test_legacy_role_key_is_read_then_migrated_on_save(self):
        screenshot_engine.write_crops({
            "monitors": {
                "primary": {
                    "codex": {
                        "left": 10,
                        "right": 11,
                        "top": 12,
                        "bottom": 13,
                        "dialog_position": "center",
                        "calib_width": 1000,
                        "calib_height": 800,
                        "focus_input_enabled": False,
                        "input_region": None,
                    }
                }
            }
        })
        topology = [monitor("primary", "monitor_a", primary=True)]

        with patch.object(screenshot_engine, "get_all_monitors", return_value=topology):
            legacy = screenshot_engine.get_crop_config("codex", "primary")
            screenshot_engine.set_crop_config("codex", 30, 31, 32, 33, "primary")

        stored = screenshot_engine.read_crops()["monitors"]
        self.assertEqual(10, legacy["left"])
        self.assertEqual(30, stored["monitor_a"]["codex"]["left"])

    def test_uncalibrated_external_monitor_does_not_inherit_primary_margins(self):
        screenshot_engine.write_crops({
            "monitors": {
                "primary": {
                    "codex": {
                        "left": 99,
                        "right": 98,
                        "top": 97,
                        "bottom": 96,
                    }
                }
            }
        })
        topology = [
            monitor("primary", "monitor_a", primary=True),
            monitor("ext_1920_0", "monitor_b"),
        ]

        with patch.object(screenshot_engine, "get_all_monitors", return_value=topology):
            external = screenshot_engine.get_crop_config("codex", "ext_1920_0")

        self.assertEqual(0, external["left"])
        self.assertEqual(0, external["top"])

    def test_device_interface_key_does_not_depend_on_primary_role_or_coordinates(self):
        identity = (
            r"\\?\DISPLAY#XMI27A1#4&886c193&0&UID24647"
            r"#{e6f07b5f-ee97-4a90-b076-33f57bf4eaa7}"
        )
        primary_key = screenshot_engine._stable_monitor_config_key(identity, r"\\.\DISPLAY2")
        external_key = screenshot_engine._stable_monitor_config_key(identity, r"\\.\DISPLAY2")

        self.assertEqual(primary_key, external_key)
        self.assertTrue(primary_key.startswith("monitor_"))


if __name__ == "__main__":
    unittest.main()
