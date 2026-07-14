import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import ide_scanner
from json_utils import safe_read_json, safe_write_json


class IdeRegistryDefaultsTests(unittest.TestCase):
    def test_codex_probe_prefers_chatgpt_desktop_process(self):
        process = Mock()
        process.info = {"name": "ChatGPT.exe", "exe": r"C:\Apps\Codex\ChatGPT.exe"}
        fake_psutil = Mock()
        fake_psutil.process_iter.return_value = [process]
        with patch.dict("sys.modules", {"psutil": fake_psutil}), patch(
            "ide_scanner.os.path.isfile", return_value=True
        ):
            self.assertEqual(r"C:\Apps\Codex\ChatGPT.exe", ide_scanner._probe_codex_desktop_exe())

    def test_empty_registry_is_initialized_from_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_file = Path(temp_dir) / "state" / "ide_registry.json"
            defaults_file = Path(temp_dir) / "defaults" / "ide_registry.json"
            registry_file.parent.mkdir(parents=True)
            defaults_file.parent.mkdir(parents=True)
            safe_write_json(defaults_file, {"codex": {"name": "Codex"}})
            with patch.object(ide_scanner, "REGISTRY_FILE", registry_file), patch.object(
                ide_scanner, "DEFAULT_REGISTRY_FILE", defaults_file
            ):
                self.assertEqual({"codex": {"name": "Codex"}}, ide_scanner.load_registry())
                self.assertEqual({"codex": {"name": "Codex"}}, safe_read_json(registry_file, {}))

    def test_existing_registry_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            registry_file = Path(temp_dir) / "state" / "ide_registry.json"
            defaults_file = Path(temp_dir) / "defaults" / "ide_registry.json"
            registry_file.parent.mkdir(parents=True)
            defaults_file.parent.mkdir(parents=True)
            safe_write_json(registry_file, {"custom": {"name": "Custom"}})
            safe_write_json(defaults_file, {"codex": {"name": "Codex"}})
            with patch.object(ide_scanner, "REGISTRY_FILE", registry_file), patch.object(
                ide_scanner, "DEFAULT_REGISTRY_FILE", defaults_file
            ):
                self.assertEqual({"custom": {"name": "Custom"}}, ide_scanner.load_registry())


if __name__ == "__main__":
    unittest.main()
