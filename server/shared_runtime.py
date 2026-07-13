import os
from paths import BRIDGE_DIR, HISTORY_FILE, CLIPBOARD_FILE
from json_utils import safe_read_json, safe_write_json
from task_runtime import TaskRuntime

runtime = TaskRuntime(BRIDGE_DIR)

def init_files():
    if not os.path.exists(HISTORY_FILE):
        safe_write_json(HISTORY_FILE, [])
    if not os.path.exists(CLIPBOARD_FILE):
        safe_write_json(CLIPBOARD_FILE, [])
    runtime.ensure_storage()

def read_history():
    init_files()
    return safe_read_json(HISTORY_FILE, [])

def write_history(history):
    safe_write_json(HISTORY_FILE, history)

def read_clipboard():
    init_files()
    return safe_read_json(CLIPBOARD_FILE, [])

def write_clipboard(history):
    safe_write_json(CLIPBOARD_FILE, history)
