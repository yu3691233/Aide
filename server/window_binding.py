"""Durable user bindings between stable IDE keys and changing desktop windows."""

import ctypes
import os
from ctypes import wintypes

import psutil

from json_utils import safe_read_json, safe_write_json
from paths import WINDOW_BINDINGS_FILE


def load_bindings():
    data = safe_read_json(WINDOW_BINDINGS_FILE, default={})
    return data if isinstance(data, dict) else {}


def get_binding(ide_key):
    value = load_bindings().get((ide_key or "").strip().lower())
    return value if isinstance(value, dict) else None


def _window_pid(hwnd):
    try:
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid))
        return int(pid.value)
    except Exception:
        return 0


def _window_class(hwnd):
    try:
        buffer = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(int(hwnd), buffer, len(buffer))
        return buffer.value
    except Exception:
        return ""


def describe_window(window):
    hwnd = int(getattr(window, "_hWnd", 0) or 0)
    pid = _window_pid(hwnd)
    process_name = ""
    exe_path = ""
    if pid:
        try:
            process = psutil.Process(pid)
            process_name = process.name() or ""
            exe_path = process.exe() or ""
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass
    return {
        "hwnd": hwnd,
        "title": (getattr(window, "title", "") or "").strip(),
        "process_name": process_name,
        "exe_path": exe_path,
        "exe_name": os.path.basename(exe_path).lower() if exe_path else process_name.lower(),
        "window_class": _window_class(hwnd),
        "left": int(getattr(window, "left", 0) or 0),
        "top": int(getattr(window, "top", 0) or 0),
        "width": int(getattr(window, "width", 0) or 0),
        "height": int(getattr(window, "height", 0) or 0),
    }


def list_window_candidates():
    import pygetwindow as gw

    candidates = []
    ignored_processes = {"explorer.exe", "textinputhost.exe", "shellexperiencehost.exe", "searchhost.exe"}
    ignored_titles = {"program manager", "windows input experience", "windows 输入体验"}
    for window in gw.getAllWindows():
        item = describe_window(window)
        if (
            item["title"]
            and item["width"] >= 120
            and item["height"] >= 80
            and _normalize(item["process_name"]) not in ignored_processes
            and _normalize(item["title"]) not in ignored_titles
        ):
            candidates.append(item)
    candidates.sort(key=lambda item: item["width"] * item["height"], reverse=True)
    return candidates[:100]


def _normalize(value):
    return (value or "").strip().lower()


def binding_match_score(binding, candidate):
    bound_exe = _normalize(binding.get("exe_name"))
    candidate_exe = _normalize(candidate.get("exe_name"))
    bound_process = _normalize(binding.get("process_name"))
    candidate_process = _normalize(candidate.get("process_name"))
    if bound_exe and candidate_exe and bound_exe != candidate_exe:
        return -1
    if not bound_exe and bound_process and candidate_process and bound_process != candidate_process:
        return -1

    score = 0
    if bound_exe and bound_exe == candidate_exe:
        score += 80
    elif bound_process and bound_process == candidate_process:
        score += 60
    if _normalize(binding.get("window_class")) == _normalize(candidate.get("window_class")) and binding.get("window_class"):
        score += 20

    bound_title = _normalize(binding.get("title"))
    candidate_title = _normalize(candidate.get("title"))
    if bound_title and bound_title == candidate_title:
        score += 30
    elif bound_title and (bound_title in candidate_title or candidate_title in bound_title):
        score += 10
    return score


def select_best_candidate(binding, candidates):
    scored = [(binding_match_score(binding, item), item) for item in candidates]
    scored = [item for item in scored if item[0] >= 40]
    if not scored:
        return None
    return max(scored, key=lambda item: (item[0], item[1].get("width", 0) * item[1].get("height", 0)))[1]


def save_binding(ide_key, candidate):
    key = (ide_key or "").strip().lower()
    if not key:
        return False
    bindings = load_bindings()
    bindings[key] = {
        "title": candidate.get("title", ""),
        "process_name": candidate.get("process_name", ""),
        "exe_name": candidate.get("exe_name", ""),
        "window_class": candidate.get("window_class", ""),
    }
    return safe_write_json(WINDOW_BINDINGS_FILE, bindings)


def delete_binding(ide_key):
    key = (ide_key or "").strip().lower()
    bindings = load_bindings()
    if key not in bindings:
        return True
    del bindings[key]
    return safe_write_json(WINDOW_BINDINGS_FILE, bindings)


def bind_window_by_hwnd(ide_key, hwnd):
    candidate = next((item for item in list_window_candidates() if item["hwnd"] == int(hwnd)), None)
    if not candidate:
        return None
    return candidate if save_binding(ide_key, candidate) else None


def find_bound_window(ide_key, windows=None):
    binding = get_binding(ide_key)
    if not binding:
        return None
    if windows is None:
        import pygetwindow as gw
        windows = gw.getAllWindows()
    described = [(window, describe_window(window)) for window in windows]
    best = select_best_candidate(binding, [item for _, item in described])
    if not best:
        return None
    return next((window for window, item in described if item["hwnd"] == best["hwnd"]), None)
