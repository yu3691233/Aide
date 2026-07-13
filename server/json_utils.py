import json
import os
import tempfile
import threading
from datetime import datetime

_locks = {}
_global_lock = threading.Lock()


def _get_lock(path):
    return _locks.setdefault(path, threading.Lock())


def safe_read_json(path, default=None):
    if default is None:
        default = []
    path = str(path)
    with _get_lock(path):
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default


def safe_write_json(path, data, indent=2):
    path = str(path)
    with _get_lock(path):
        dir_name = os.path.dirname(path)
        base_name = os.path.basename(path)
        tmp_path = os.path.join(dir_name, f".{base_name}.tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)
            os.replace(tmp_path, path)
            return True
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False


def atomic_write_json(path, data, indent=2):
    path = str(path)
    with _get_lock(path):
        try:
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)
            os.replace(tmp, path)
        except Exception:
            pass


def read_json_or_default(path, default=None):
    if default is None:
        default = {}
    path = str(path)
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def append_to_json_list(path, item, max_size=None):
    path = str(path)
    with _get_lock(path):
        data = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = []
        if not isinstance(data, list):
            data = []
        data.append(item)
        if max_size and len(data) > max_size:
            data = data[-max_size:]
        try:
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
            return True
        except Exception:
            return False


def read_history(path, limit=100):
    data = safe_read_json(path, default=[])
    if isinstance(data, list):
        return data[-limit:]
    return []


def write_history(path, history):
    return safe_write_json(path, history)
