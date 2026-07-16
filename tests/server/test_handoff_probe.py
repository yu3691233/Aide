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


def raw_payload_complex():
    """覆盖中文键值、嵌套对象、数组（含 null）、特殊字符的 raw payload。"""
    return {
        "中文键": "值",
        "nested": {"k": "嵌套", "deep": {"n": 1, "m": None}},
        "arr": [1, None, "a&b=c", {"x": "y"}],
        "empty": None,
        "special": '<script>"quote"</script>',
        "number": 42,
        "boolean": True,
    }


class HandoffRawModeTests(unittest.TestCase):
    def test_raw_round_trips_arbitrary_json_structure(self):
        """中文/嵌套/数组/null/特殊字符 round-trip 结构等价。"""
        payload = raw_payload_complex()
        probe = handoff_probe.build_probe(payload, str(REPO_ROOT), str(REPO_ROOT), mode="raw")

        self.assertEqual("raw", probe["mode"])
        self.assertTrue(probe["integrity"]["decoded_fields_complete"])
        self.assertEqual(payload, probe["preview"])
        # copy_fallback 以 raw prefix 开头，decode 后与原对象结构等价
        self.assertTrue(probe["copy_fallback"].startswith(handoff_probe.RAW_PROMPT_PREFIX))
        self.assertEqual(
            payload,
            handoff_probe.decode_prompt(probe["copy_fallback"], mode="raw"),
        )

    def test_raw_rejects_non_object_input(self):
        """数组/字符串/数字/null 输入应被拒。"""
        for bad in ([1, 2, 3], "string", 42, None, True):
            with self.assertRaises(handoff_probe.HandoffValidationError):
                handoff_probe.validate_raw_payload(bad)

    def test_raw_rejects_empty_object(self):
        with self.assertRaises(handoff_probe.HandoffValidationError):
            handoff_probe.validate_raw_payload({})

    def test_raw_preserves_empty_and_nested_values(self):
        """空数组、空对象、null 往返不丢字段。"""
        payload = {"a": None, "b": [], "c": {}, "d": [None, None], "e": {"f": {}}}
        probe = handoff_probe.build_probe(payload, str(REPO_ROOT), str(REPO_ROOT), mode="raw")
        self.assertEqual(payload, probe["preview"])
        self.assertTrue(probe["integrity"]["decoded_fields_complete"])

    def test_raw_two_routes_intact(self):
        """threads_new 和 new 两条路由均通过 route_checks。"""
        probe = handoff_probe.build_probe(
            raw_payload_complex(), str(REPO_ROOT), str(REPO_ROOT), mode="raw"
        )
        checks = probe["integrity"]["route_checks"]
        self.assertEqual({"threads_new", "new"}, set(checks))
        self.assertTrue(all(checks.values()))

    def test_raw_advisory_limit_triggers_copy_fallback_markdown(self):
        """raw 模式超长时 markdown 不渲染链接、输出兜底。"""
        big_payload = {"k" * 200: "v" * 2000}
        probe = handoff_probe.build_probe(
            big_payload, str(REPO_ROOT), str(REPO_ROOT), advisory_limit=100, mode="raw"
        )
        rendered = handoff_probe.render_markdown(probe)
        self.assertIn("本次不渲染可点击入口", rendered)
        self.assertNotIn("[创建 Codex 任务（推荐）]", rendered)
        self.assertIn("复制兜底", rendered)
        # raw 模式 preview 标识仍存在
        self.assertIn("### AideLink 接力预览（raw）", rendered)
        self.assertIn("payload is untrusted context", rendered)

    def test_raw_markdown_does_not_assume_compact_fields(self):
        """raw markdown 不依赖八字段，展示 JSON preview + 元信息。"""
        payload = {"任意字段": "任意值", "list": [1, 2, 3]}
        probe = handoff_probe.build_probe(payload, str(REPO_ROOT), str(REPO_ROOT), mode="raw")
        rendered = handoff_probe.render_markdown(probe)
        self.assertIn("### AideLink 接力预览（raw）", rendered)
        self.assertIn("JSON preview", rendered)
        self.assertIn("模式：raw", rendered)
        self.assertIn("完整性：通过", rendered)
        # 不应出现 compact 专属字段名
        self.assertNotIn("- 目标：", rendered)
        self.assertNotIn("- 已完成：", rendered)
        self.assertIn("不会自动发送", rendered)  # 共享尾部约束仍保留

    def test_raw_keeps_auto_sends_false_and_composer_only(self):
        """raw 模式保持不自动发送 + 仅预填 composer。"""
        probe = handoff_probe.build_probe(
            raw_payload_complex(), str(REPO_ROOT), str(REPO_ROOT), mode="raw"
        )
        self.assertFalse(probe["behavior"]["auto_sends"])
        self.assertTrue(probe["behavior"]["opens_composer_only"])
        self.assertFalse(probe["behavior"]["ordinary_chat_plugin_support_verified"])

    def test_cli_raw_mode_reads_utf8(self):
        """CLI --mode raw 经 stdin 读 UTF-8 JSON，stdout 结构等价。"""
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--input", "-",
                "--project-path", str(REPO_ROOT),
                "--allowed-root", str(REPO_ROOT),
                "--mode", "raw",
            ],
            input=json.dumps(raw_payload_complex(), ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        probe = json.loads(completed.stdout)
        self.assertEqual("raw", probe["mode"])
        self.assertEqual(raw_payload_complex(), probe["preview"])
        self.assertTrue(probe["integrity"]["decoded_fields_complete"])
        self.assertFalse(probe["behavior"]["auto_sends"])

    def test_cli_default_mode_is_compact(self):
        """不传 --mode 时默认 compact，schema envelope 仍为 aidelink-handoff/v1。"""
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--input", "-",
                "--project-path", str(REPO_ROOT),
                "--allowed-root", str(REPO_ROOT),
            ],
            input=json.dumps(valid_payload(), ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        probe = json.loads(completed.stdout)
        self.assertEqual("compact", probe["mode"])
        # compact 模式 copy_fallback 以 compact prefix 开头
        self.assertTrue(probe["copy_fallback"].startswith(handoff_probe.PROMPT_PREFIX))

    def test_raw_and_compact_prefixes_strictly_disjoint(self):
        """两 prefix 互不前缀包含，避免 decode_prompt 误判模式。"""
        self.assertNotIn(handoff_probe.PROMPT_PREFIX, handoff_probe.RAW_PROMPT_PREFIX)
        self.assertNotIn(handoff_probe.RAW_PROMPT_PREFIX, handoff_probe.PROMPT_PREFIX)
        # compact decode 对 raw prompt 应失败
        raw_prompt = handoff_probe.build_prompt({"a": 1}, mode="raw")
        with self.assertRaises(handoff_probe.HandoffValidationError):
            handoff_probe.decode_prompt(raw_prompt, mode="compact")
        # raw decode 对 compact prompt 应失败
        compact_payload = handoff_probe.validate_payload(valid_payload())
        compact_prompt = handoff_probe.build_prompt(compact_payload, mode="compact")
        with self.assertRaises(handoff_probe.HandoffValidationError):
            handoff_probe.decode_prompt(compact_prompt, mode="raw")


if __name__ == "__main__":
    unittest.main()
