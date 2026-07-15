import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import ide_profiles


class IdeProfileTests(unittest.TestCase):
    def test_bundled_codex_profile_declares_project_deep_link(self):
        profile = ide_profiles.load_profile("codex")
        self.assertEqual("uri", profile["project"]["mode"])
        self.assertIn("open_project", profile["capabilities"])
        self.assertEqual("bundled", profile["source"])

    def test_uri_project_open_uses_windows_protocol_handler_and_encodes_path(self):
        profile = ide_profiles.load_profile("codex")
        with patch.object(ide_profiles.os, "name", "nt"), patch.object(
            ide_profiles.os, "startfile", create=True
        ) as startfile:
            target = ide_profiles.open_project(profile, {}, r"F:\My Project\demo")

        self.assertEqual("codex://threads/new?path=F%3A%5CMy%20Project%5Cdemo", target)
        startfile.assert_called_once_with(target)

    def test_codex_history_reads_index_and_opens_canonical_deep_link(self):
        profile = ide_profiles.load_profile("codex")
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "session_index.jsonl"
            index.write_text(
                '{"id":"019f6463-8f6f-7811-a641-320cb188dce7","thread_name":"较早会话","updated_at":"2026-07-14T10:00:00Z"}\n'
                '{"id":"019f6463-8f6f-7811-a641-320cb188dce8","thread_name":"最新会话","updated_at":"2026-07-15T10:00:00Z"}\n',
                encoding="utf-8",
            )
            with patch.dict(ide_profiles.os.environ, {"CODEX_HOME": tmp}):
                sessions = ide_profiles.list_history(profile)

        self.assertEqual("最新会话", sessions[0]["title"])
        thread_id = sessions[0]["id"]
        with patch.object(ide_profiles.os, "name", "nt"), patch.object(
            ide_profiles.os, "startfile", create=True
        ) as startfile:
            target = ide_profiles.open_history(profile, thread_id)
        self.assertEqual(f"codex://threads/{thread_id}", target)
        startfile.assert_called_once_with(target)

    def test_update_writes_only_requested_profile_override(self):
        payload = {
            "schema_version": 1,
            "key": "codex",
            "version": "9.0.0",
            "display_name": "ChatGPT",
            "capabilities": ["launch", "profile_update"],
            "launch": {"mode": "appx", "aumid": "OpenAI.Codex_test!App"},
            "project": {"mode": "none"},
        }
        response = Mock()
        response.content = json.dumps(payload).encode("utf-8")
        response.json.return_value = payload
        response.raise_for_status.return_value = None

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            ide_profiles, "INSTALLED_PROFILES_DIR", Path(tmp)
        ), patch.object(ide_profiles.requests, "get", return_value=response):
            updated, saved, _ = ide_profiles.update_profile("codex")
            files = list(Path(tmp).glob("*.json"))

        self.assertTrue(updated)
        self.assertEqual("9.0.0", saved["version"])
        self.assertEqual(["codex.json"], [item.name for item in files])

    def test_older_installed_override_does_not_mask_newer_bundled_profile(self):
        bundled = ide_profiles.load_profile("codex")
        older = dict(bundled)
        older["version"] = "1.0.0"
        older["capabilities"] = [item for item in older["capabilities"] if item != "history"]
        older["history"] = {"mode": "none"}
        with tempfile.TemporaryDirectory() as tmp:
            installed_dir = Path(tmp)
            (installed_dir / "codex.json").write_text(json.dumps(older), encoding="utf-8")
            with patch.object(ide_profiles, "INSTALLED_PROFILES_DIR", installed_dir):
                loaded = ide_profiles.load_profile("codex")
        self.assertEqual("1.1.0", loaded["version"])
        self.assertEqual("bundled", loaded["source"])
        self.assertIn("history", loaded["capabilities"])

    def test_rejects_profile_with_wrong_key(self):
        profile = ide_profiles.load_profile("codex")
        profile["key"] = "antigravity_ide"
        with self.assertRaises(ide_profiles.IdeProfileError):
            ide_profiles.validate_profile(profile, expected_key="codex")


if __name__ == "__main__":
    unittest.main()
