import os
from pathlib import Path

BRIDGE_DIR = Path(os.environ.get("BRIDGE_DIR", str(Path(__file__).parent)))
def get_project_root() -> Path:
    from config import load_settings
    try:
        settings = load_settings()
        custom_dir = settings.get("project_dir")
        if custom_dir and os.path.isdir(custom_dir):
            return Path(custom_dir)
    except Exception:
        pass
    return BRIDGE_DIR.parent

class DynamicProjectPath(object):
    def _get_path(self) -> Path:
        return get_project_root()

    def __fspath__(self):
        return str(self._get_path())

    def __str__(self):
        return str(self._get_path())

    def __repr__(self):
        return repr(self._get_path())

    def __truediv__(self, other):
        return self._get_path() / other

    def __rtruediv__(self, other):
        return other / self._get_path()

    def __getattr__(self, name):
        return getattr(self._get_path(), name)

PROJECT_ROOT = DynamicProjectPath()
STATE_DIR = BRIDGE_DIR / "state"
ASSETS_DIR = BRIDGE_DIR / "brand_assets"
DEFAULTS_DIR = BRIDGE_DIR / "defaults"

HISTORY_FILE = STATE_DIR / "chat_history.json"
CLIPBOARD_FILE = STATE_DIR / "clipboard_history.json"
IN_FILE = BRIDGE_DIR / "phone_in.txt"
UPLOAD_FOLDER = BRIDGE_DIR / "static" / "uploads"
SETTINGS_FILE = BRIDGE_DIR / "aidelink_settings.json"
CONFIG_FILE = BRIDGE_DIR / "config.json"
REGISTRY_FILE = STATE_DIR / "ide_registry.json"
DEFAULT_REGISTRY_FILE = DEFAULTS_DIR / "ide_registry.json"
MANUAL_IDES_FILE = BRIDGE_DIR / "manual_ides.json"
SCANNED_IDES_FILE = BRIDGE_DIR / "scanned_ides.json"
IDE_ROLES_FILE = STATE_DIR / "ide_roles.json"
IDE_ALIASES_FILE = STATE_DIR / "ide_aliases.json"
WINDOW_BINDINGS_FILE = STATE_DIR / "ide_window_bindings.json"
CROPS_FILE = STATE_DIR / "crops.json"
DEVICE_ALIASES_FILE = STATE_DIR / "device_aliases.json"
SCREEN_CONFIG_FILE = STATE_DIR / "screen_settings.json"
LOG_DIR = Path(os.environ.get("AIDELINK_LOG_DIR", str(BRIDGE_DIR)))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "flask_new.log"
PHONE_LOG_FILE = LOG_DIR / "phone_app.log"


def _migrate_state_files():
    """将旧位置的状态文件迁移到 state/ 目录（若目标不存在则复制）。"""
    _state_files = [
        ("chat_history.json", HISTORY_FILE),
        ("clipboard_history.json", CLIPBOARD_FILE),
        ("ide_registry.json", REGISTRY_FILE),
        ("device_aliases.json", DEVICE_ALIASES_FILE),
        ("screen_settings.json", SCREEN_CONFIG_FILE),
    ]
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    for name, target in _state_files:
        src = BRIDGE_DIR / name
        if src.exists() and not target.exists():
            try:
                import shutil
                shutil.copy2(str(src), str(target))
            except Exception:
                pass

_migrate_state_files()
def _get_app_name():
    from config import load_settings
    try:
        return load_settings().get("app_project_name", "")
    except Exception:
        return "AideLink-app"

class _DynamicAppPath:
    """延迟计算的 App 路径，每次访问都读取最新设置。"""
    def __init__(self, *parts):
        self._parts = parts
    def __fspath__(self):
        return str(self)
    def __str__(self):
        app = _get_app_name()
        return str(PROJECT_ROOT.joinpath(app, *self._parts))
    def __repr__(self):
        return repr(str(self))
    def __truediv__(self, other):
        return Path(str(self)) / other
    def __rtruediv__(self, other):
        return Path(other) / str(self)
    def __getattr__(self, name):
        return getattr(Path(str(self)), name)
    def exists(self):
        return Path(str(self)).exists()

APK_PATH = _DynamicAppPath("app", "build", "outputs", "apk", "debug", "app-debug.apk")
APK_GRADLE_PATH = _DynamicAppPath("app", "build.gradle.kts")
APK_METADATA_PATH = _DynamicAppPath("app", "build", "outputs", "apk", "debug", "output-metadata.json")
VERSION_JSON = BRIDGE_DIR / "version.json"
