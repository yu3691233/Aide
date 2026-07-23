"""Optional, user-correctable task classification contract."""

import json
import re

SURFACES = frozenset({"general", "web", "android", "windows"})
TASK_TYPES = frozenset({
    "feature",
    "optimization",
    "bug_fix",
    "testing",
    "other",
    "refactor",
    "research",
    "documentation",
    "operation",
})
CLASSIFICATION_STATES = frozenset({"unclassified", "suggested", "confirmed"})
MAX_FUNCTIONAL_AREAS = 8


def _clean_text(value, max_length):
    return str(value or "").strip()[:max_length]


def normalize_classification(raw, *, default_state="unclassified"):
    raw = raw if isinstance(raw, dict) else {}
    surface = _clean_text(raw.get("surface"), 20).lower()
    task_type = _clean_text(raw.get("task_type"), 30).lower()
    state = _clean_text(raw.get("state"), 20).lower() or default_state

    if surface not in SURFACES:
        surface = ""
    if task_type not in TASK_TYPES:
        task_type = ""
    if state not in CLASSIFICATION_STATES:
        state = default_state

    areas = []
    for item in raw.get("functional_areas") or []:
        value = _clean_text(item, 40)
        if value and value not in areas:
            areas.append(value)
        if len(areas) >= MAX_FUNCTIONAL_AREAS:
            break

    return {
        "surface": surface,
        "ui_location": _clean_text(raw.get("ui_location"), 120),
        "functional_areas": areas,
        "task_type": task_type,
        "state": state,
        "source": _clean_text(raw.get("source"), 20).lower() or "user",
    }


def classification_for_task(task):
    metadata = task.get("metadata") or {}
    stored = metadata.get("classification")
    if isinstance(stored, dict):
        return normalize_classification(stored)

    legacy_surface = _clean_text(metadata.get("surface"), 20).lower()
    legacy_type = _clean_text(task.get("task_type") or metadata.get("task_type"), 30).lower()
    return normalize_classification({
        "surface": legacy_surface,
        "task_type": legacy_type,
        "state": "unclassified",
        "source": "legacy",
    })


def parse_classification_response(content):
    """Accept plain JSON, fenced JSON, or a short explanation around one JSON object."""
    text = str(content or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("分类结果不是 JSON 对象")
    return parsed


def heuristic_classification(title, text):
    """Deterministic fallback: useful when the model is unavailable, never authoritative."""
    content = f"{title or ''}\n{text or ''}".lower()

    def has(*keywords):
        return any(keyword.lower() in content for keyword in keywords)

    if has("bug", "错误", "异常", "失败", "崩溃", "修复", "无反应"):
        task_type = "bug_fix"
    elif has("优化", "改进", "调整", "重构", "体验"):
        task_type = "optimization"
    elif has("新增", "添加", "支持", "实现", "增加"):
        task_type = "feature"
    else:
        task_type = "other"

    if has("android", "app", "手机"):
        surface = "android"
    elif has("web", "网页", "浏览器"):
        surface = "web"
    elif has("windows", "桌面端", "浮窗", "pc"):
        surface = "windows"
    else:
        surface = "general"

    return normalize_classification({
        "surface": surface,
        "task_type": task_type,
        "functional_areas": [],
        "ui_location": "",
        "state": "suggested",
        "source": "rule",
    }, default_state="suggested")
