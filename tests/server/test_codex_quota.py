import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

import codex_quota


class CodexQuotaTests(unittest.TestCase):
    def setUp(self):
        codex_quota._cached_at = 0.0
        codex_quota._cached_result = None
        codex_quota._executed_task_baseline = set()

    def test_fetch_uses_codex_credentials_and_converts_used_to_remaining(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "plan_type": "plus",
            "rate_limit": {
                "primary_window": {
                    "used_percent": 37,
                    "limit_window_seconds": 18000,
                    "reset_at": 123,
                },
                "secondary_window": {"used_percent": 12},
            },
        }
        with patch("codex_quota._load_current_credentials", return_value=("token", "account")), \
             patch("codex_quota.requests.get", return_value=response) as request:
            result = codex_quota.fetch_current_codex_quota()

        self.assertEqual(88, result["remaining_percent"])
        self.assertEqual("weekly", result["period"])
        self.assertEqual(
            "account",
            request.call_args.kwargs["headers"]["ChatGPT-Account-Id"],
        )
        self.assertNotIn("token", str(result))

    def test_missing_weekly_window_is_reported_as_unavailable(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"rate_limit": {}}
        with patch("codex_quota._load_current_credentials", return_value=("token", "")), \
             patch("codex_quota.requests.get", return_value=response):
            with self.assertRaisesRegex(ValueError, "周额度窗口"):
                codex_quota.fetch_current_codex_quota()

    def test_current_weekly_only_response_uses_seven_day_primary_window(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 63,
                    "limit_window_seconds": 604800,
                    "reset_at": 123,
                },
                "secondary_window": None,
            },
        }
        with patch("codex_quota._load_current_credentials", return_value=("token", "account")), \
             patch("codex_quota.requests.get", return_value=response):
            result = codex_quota.fetch_current_codex_quota()

        self.assertEqual(37, result["remaining_percent"])
        self.assertEqual(604800, result["window_seconds"])

    def test_three_newly_executed_tasks_refresh_before_cache_expiry(self):
        snapshots = [
            {"available": True, "remaining_percent": 80},
            {"available": True, "remaining_percent": 70},
        ]
        with patch("codex_quota.fetch_current_codex_quota", side_effect=snapshots) as fetch:
            first = codex_quota.get_current_codex_quota(
                executed_task_ids=["existing"],
            )
            cached = codex_quota.get_current_codex_quota(
                executed_task_ids=["existing", "new-1", "new-2"],
            )
            codex_quota._cached_at -= codex_quota._MIN_REFRESH_SECONDS + 1
            refreshed = codex_quota.get_current_codex_quota(
                executed_task_ids=["existing", "new-1", "new-2", "new-3"],
            )

        self.assertEqual(80, first["remaining_percent"])
        self.assertEqual(80, cached["remaining_percent"])
        self.assertEqual(70, refreshed["remaining_percent"])
        self.assertEqual(2, fetch.call_count)

    def test_three_tasks_do_not_refresh_inside_two_minute_floor(self):
        with patch(
            "codex_quota.fetch_current_codex_quota",
            return_value={"available": True, "remaining_percent": 80},
        ) as fetch:
            first = codex_quota.get_current_codex_quota(
                executed_task_ids=["existing"],
            )
            second = codex_quota.get_current_codex_quota(
                executed_task_ids=["existing", "new-1", "new-2", "new-3"],
            )

        self.assertEqual(first, second)
        self.assertEqual(1, fetch.call_count)

    def test_historical_executed_tasks_become_baseline_on_first_window_refresh(self):
        with patch(
            "codex_quota.fetch_current_codex_quota",
            return_value={"available": True, "remaining_percent": 80},
        ) as fetch:
            codex_quota.get_current_codex_quota(
                executed_task_ids=["old-1", "old-2", "old-3", "old-4"],
            )
            codex_quota.get_current_codex_quota(
                executed_task_ids=["old-1", "old-2", "old-3", "old-4"],
            )

        self.assertEqual(1, fetch.call_count)


if __name__ == "__main__":
    unittest.main()
