import os
import re
import subprocess
from json_utils import safe_read_json


def detect_app_version():
    from paths import APK_GRADLE_PATH, APK_METADATA_PATH, VERSION_JSON

    if APK_GRADLE_PATH.exists():
        try:
            content = APK_GRADLE_PATH.read_text(encoding="utf-8")
            match = re.search(r'versionName\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1)
        except Exception:
            pass

    if APK_METADATA_PATH.exists():
        data = safe_read_json(APK_METADATA_PATH, {})
        if isinstance(data, dict) and "elements" in data and len(data["elements"]) > 0:
            v = data["elements"][0].get("versionName")
            if v:
                return v

    if VERSION_JSON.exists():
        data = safe_read_json(VERSION_JSON, {})
        if isinstance(data, dict):
            v = data.get("version")
            if v:
                return v

    return "0.0.0"


def detect_git_version():
    from paths import PROJECT_ROOT
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=3
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT), timeout=3
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None
