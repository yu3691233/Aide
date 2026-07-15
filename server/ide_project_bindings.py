"""Small durable map of IDE keys to projects launched by AideLink."""

from pathlib import Path

from json_utils import safe_read_json, safe_write_json
from paths import STATE_DIR


BINDINGS_FILE = STATE_DIR / "ide_project_bindings.json"


def load_bindings():
    data = safe_read_json(BINDINGS_FILE, {})
    return data if isinstance(data, dict) else {}


def save_binding(ide_key, project_path):
    bindings = load_bindings()
    bindings[str(ide_key).strip().lower()] = str(Path(project_path))
    return safe_write_json(BINDINGS_FILE, bindings)
