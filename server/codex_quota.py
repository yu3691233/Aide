"""Read the current Codex login quota without persisting credentials."""

import json
import threading
import time
from pathlib import Path

import requests


USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
AUTH_FILE = Path.home() / ".codex" / "auth.json"
_CACHE_TTL_SECONDS = 300
_MIN_REFRESH_SECONDS = 120
_cache_lock = threading.Lock()
_cached_at = 0.0
_cached_result = None
_executed_task_baseline = set()


def _load_current_credentials():
    payload = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    tokens = payload.get("tokens") or {}
    access_token = str(tokens.get("access_token") or "").strip()
    account_id = str(tokens.get("account_id") or payload.get("account_id") or "").strip()
    if not access_token:
        raise ValueError("Codex 登录信息缺少 access_token")
    return access_token, account_id


def _remaining_percent(window):
    if not isinstance(window, dict):
        return None
    used = window.get("used_percent")
    if not isinstance(used, (int, float)):
        return None
    return max(0, min(100, round(100 - used)))


def _weekly_window(rate_limit):
    secondary = rate_limit.get("secondary_window")
    if _remaining_percent(secondary) is not None:
        return secondary
    primary = rate_limit.get("primary_window")
    window_seconds = primary.get("limit_window_seconds") if isinstance(primary, dict) else None
    if _remaining_percent(primary) is not None and isinstance(window_seconds, (int, float)):
        # The current Codex API exposes the weekly-only quota as primary_window.
        if window_seconds >= 6 * 24 * 60 * 60:
            return primary
    return None


def fetch_current_codex_quota(timeout=8):
    access_token, account_id = _load_current_credentials()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    if account_id:
        headers["ChatGPT-Account-Id"] = account_id
    response = requests.get(USAGE_URL, headers=headers, timeout=timeout)
    response.raise_for_status()
    usage = response.json()
    rate_limit = usage.get("rate_limit") or {}
    weekly = _weekly_window(rate_limit)
    weekly_remaining = _remaining_percent(weekly)
    if weekly_remaining is None:
        raise ValueError("Codex 配额响应缺少周额度窗口")
    return {
        "available": True,
        "remaining_percent": weekly_remaining,
        "period": "weekly",
        "plan_type": usage.get("plan_type"),
        "reset_at": weekly.get("reset_at"),
        "window_seconds": weekly.get("limit_window_seconds"),
        "updated_at": int(time.time()),
    }


def get_current_codex_quota(force=False, executed_task_ids=None):
    global _cached_at, _cached_result, _executed_task_baseline
    now = time.monotonic()
    current_executed = {
        str(task_id).strip()
        for task_id in (executed_task_ids or [])
        if str(task_id).strip()
    }
    with _cache_lock:
        newly_executed = current_executed - _executed_task_baseline
        cache_age = now - _cached_at
        task_threshold_reached = (
            _cached_result is not None
            and len(newly_executed) >= 3
            and cache_age >= _MIN_REFRESH_SECONDS
        )
        if (
            not force
            and not task_threshold_reached
            and _cached_result is not None
            and cache_age < _CACHE_TTL_SECONDS
        ):
            return dict(_cached_result)
        try:
            result = fetch_current_codex_quota()
        except (OSError, ValueError, requests.RequestException, json.JSONDecodeError) as exc:
            result = {"available": False, "error": str(exc)}
        _cached_result = result
        _cached_at = now
        _executed_task_baseline = current_executed
        return dict(result)
