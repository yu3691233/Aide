import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "plugins" / "aidelink-handoff" / "scripts" / "build_handoff_probe.py"
SPEC = importlib.util.spec_from_file_location("aidelink_handoff_probe", SCRIPT_PATH)
handoff_probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(handoff_probe)


def valid_payload():
    return {
        "objective": "完成接力探针",
        "completed": ["已读取契约"],
        "changed_files": [],
        "decisions": ["不自动发送"],
        "validation": ["单元测试待运行"],
        "remaining": ["验证桌面客户端"],
        "risks": ["普通 Chat 可见性未知"],
        "next_step": "打开预填任务并人工发送",
    }


class HandoffProbeTests(unittest.TestCase):
    def test_builds_two_utf8_safe_routes_and_round_trips_all_fields(self):
        probe = handoff_probe.build_probe(valid_payload(), str(REPO_ROOT), str(REPO_ROOT))

        self.assertEqual(set(valid_payload()), set(probe["integrity"]["required_fields"]))
        self.assertTrue(probe["integrity"]["decoded_fields_complete"])
        self.assertEqual({"threads_new", "new"}, set(probe["links"]))
        self.assertNotIn("完成接力探针", probe["links"]["threads_new"])
        self.assertNotIn("\n", probe["copy_fallback"])
        self.assertFalse(probe["behavior"]["auto_sends"])

        query = parse_qs(urlparse(probe["links"]["threads_new"]).query)
        self.assertEqual(str(REPO_ROOT), query["path"][0])
        self.assertEqual(valid_payload(), handoff_probe.decode_prompt(query["prompt"][0]))

    def test_rejects_missing_or_extra_handoff_fields(self):
        missing = valid_payload()
        missing.pop("risks")
        with self.assertRaises(handoff_probe.HandoffValidationError):
            handoff_probe.validate_payload(missing)

        extra = valid_payload()
        extra["history"] = ["too much context"]
        with self.assertRaises(handoff_probe.HandoffValidationError):
            handoff_probe.validate_payload(extra)

    def test_rejects_project_outside_allowed_root(self):
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as outside:
            with self.assertRaises(handoff_probe.HandoffValidationError):
                handoff_probe.build_probe(valid_payload(), outside, allowed)

    def test_chinese_length_matrix_is_monotonic_and_decodes_exactly(self):
        counts = [100, 300, 500, 750, 1000]
        probe = handoff_probe.build_probe(
            valid_payload(), str(REPO_ROOT), str(REPO_ROOT), matrix_counts=counts
        )
        matrix = probe["length_matrix"]

        self.assertEqual(counts, [row["chinese_chars"] for row in matrix])
        self.assertTrue(all(row["decoded_matches"] for row in matrix))
        lengths = [row["encoded_url_chars"] for row in matrix]
        self.assertEqual(sorted(lengths), lengths)
        self.assertGreater(lengths[-1], lengths[0])

    def test_markdown_preview_escapes_untrusted_field_markup(self):
        payload = valid_payload()
        payload["objective"] = "[伪链接](https://example.invalid)"
        probe = handoff_probe.build_probe(payload, str(REPO_ROOT), str(REPO_ROOT))

        rendered = handoff_probe.render_markdown(probe)
        self.assertIn(r"\[伪链接\]\(https://example\.invalid\)", rendered)
        self.assertIn("- 已完成：", rendered)
        self.assertIn("- 风险：", rendered)

    def test_markdown_uses_copy_fallback_when_link_exceeds_advisory_limit(self):
        probe = handoff_probe.build_probe(
            valid_payload(), str(REPO_ROOT), str(REPO_ROOT), advisory_limit=100
        )

        rendered = handoff_probe.render_markdown(probe)
        self.assertIn("本次不渲染可点击入口", rendered)
        self.assertNotIn("[创建 Codex 任务（推荐）]", rendered)
        self.assertIn("复制兜底", rendered)

    def test_plugin_and_marketplace_manifests_match(self):
        plugin_path = REPO_ROOT / "plugins" / "aidelink-handoff" / ".codex-plugin" / "plugin.json"
        marketplace_path = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
        plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        entry = marketplace["plugins"][0]

        self.assertEqual("aidelink-handoff", plugin["name"])
        self.assertEqual(plugin["name"], entry["name"])
        self.assertEqual("./plugins/aidelink-handoff", entry["source"]["path"])
        self.assertEqual("AVAILABLE", entry["policy"]["installation"])
        self.assertEqual("ON_INSTALL", entry["policy"]["authentication"])

    def test_cli_reads_and_writes_utf8(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--input",
                "-",
                "--project-path",
                str(REPO_ROOT),
                "--allowed-root",
                str(REPO_ROOT),
            ],
            input=json.dumps(valid_payload(), ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("完成接力探针", json.loads(completed.stdout)["preview"]["objective"])


if __name__ == "__main__":
    unittest.main()
