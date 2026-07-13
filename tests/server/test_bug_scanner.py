import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes import task_routes_scanner as scanner


def _make_traceback(file_path, line, func, error_line, level="ERROR"):
    return (
        f"2026-07-10 10:00:00,000 - {level} - some message\n"
        f"Traceback (most recent call last):\n"
        f'  File "{file_path}", line {line}, in {func}\n'
        f"    some_func()\n"
        f"{error_line}\n"
    )


class BugScannerSignatureTests(unittest.TestCase):
    def test_signature_stable_across_runs(self):
        sig_a = scanner._make_signature(
            "C:/project/server/foo.py", "123", "ValueError: bad value 1700000000",
        )
        sig_b = scanner._make_signature(
            "C:\\project\\server\\foo.py", "123", "ValueError: bad value 1700000123",
        )
        # 时间戳被规范化、路径分隔符被规范化 → 同一签名
        self.assertEqual(sig_a, sig_b)

    def test_signature_changes_when_file_or_line_changes(self):
        sig_a = scanner._make_signature("server/foo.py", "10", "ValueError: x")
        sig_b = scanner._make_signature("server/foo.py", "11", "ValueError: x")
        sig_c = scanner._make_signature("server/bar.py", "10", "ValueError: x")
        self.assertNotEqual(sig_a, sig_b)
        self.assertNotEqual(sig_a, sig_c)

    def test_signature_normalizes_hex_address(self):
        norm = scanner._normalize_error_line("TypeError at 0xdeadbeef")
        self.assertIn("0xADDR", norm)
        self.assertNotIn("0xdeadbeef", norm)


class BugScannerFalsePositiveTests(unittest.TestCase):
    def test_site_packages_filtered(self):
        self.assertTrue(scanner._is_false_positive(
            "C:/Python311/Lib/site-packages/requests/adapters.py", "RuntimeError: nope",
        ))

    def test_internal_core_filtered(self):
        self.assertTrue(scanner._is_false_positive(
            "C:/project/server/_core.py", "RuntimeError: nope",
        ))

    def test_normal_user_file_not_filtered(self):
        self.assertFalse(scanner._is_false_positive(
            "C:/project/server/phone_routes.py", "RuntimeError: bad",
        ))

    def test_warning_substrings_filtered(self):
        self.assertTrue(scanner._is_false_positive(
            "server/foo.py", "DeprecationWarning: old api",
        ))

    def test_test_marker_filtered(self):
        self.assertTrue(scanner._is_false_positive(
            "server/foo.py", "tests/test_foo.py: assert failed",
        ))


class BugScannerParseTests(unittest.TestCase):
    def test_only_error_level_picked(self):
        log = (
            _make_traceback("server/warn.py", "1", "f", "UserWarning: x", level="WARNING")
            + _make_traceback("server/bad.py", "42", "g", "ValueError: x", level="ERROR")
        )
        parsed = scanner._parse_tracebacks(log)
        self.assertEqual(1, len(parsed))
        self.assertEqual("server/bad.py", parsed[0][0])
        self.assertEqual("42", parsed[0][1])

    def test_debug_level_skipped(self):
        log = _make_traceback("server/x.py", "1", "f", "DEBUG: blah", level="DEBUG")
        self.assertEqual([], scanner._parse_tracebacks(log))

    def test_incremental_dedup(self):
        log = _make_traceback("server/bad.py", "42", "g", "ValueError: x", level="ERROR")
        first = scanner._parse_tracebacks(log)
        second = scanner._parse_tracebacks(log)
        self.assertEqual(1, len(first))
        self.assertEqual(1, len(second))
        sig_a = scanner._make_signature(first[0][0], first[0][1], first[0][3])
        sig_b = scanner._make_signature(second[0][0], second[0][1], second[0][3])
        self.assertEqual(sig_a, sig_b)

    def test_false_positive_skipped(self):
        log = _make_traceback(
            "C:/Python311/Lib/site-packages/foo/_core.py", "1", "f", "RuntimeError: x",
            level="ERROR",
        )
        self.assertEqual([], scanner._parse_tracebacks(log))


if __name__ == "__main__":
    unittest.main()