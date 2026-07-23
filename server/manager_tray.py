import os
import sys
import time
import atexit
import logging
import threading
import subprocess
import webbrowser
import tempfile
import winreg
from urllib.parse import quote
from pathlib import Path

from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw

from manager_utils import BASE_DIR, load_config, save_config, logger, kill_existing_processes, acquire_tray_single_instance
from manager_process import (
    is_flask_running, start_flask_service, stop_flask_service,
    get_service_status, PID_FILE,
)
from frp_service import is_frp_running, get_frp_status, start_frp_client
from network_utils import ADB_PATH, get_local_ip
import requests as _requests

# ============================================================
# 全局状态
# ============================================================

tray_icon = None

# 本机更新源；稳定后可切换为远程更新服务。
LOCAL_UPDATE_DIR = Path(os.environ.get("AIDELINK_UPDATE_DIR", r"Z:\共享\aidelink"))
REMOTE_UPDATE_URL = os.environ.get("AIDELINK_UPDATE_URL", "https://list.cciv.cc/aidelink")
REMOTE_OPENLIST_BASE = os.environ.get("AIDELINK_OPENLIST_BASE", "https://list.cciv.cc")

# ============================================================
# 系统托盘图标
# ============================================================

def create_tray_icon():
    candidates = [
        BASE_DIR / "brand_assets" / "tray-icon.png",
        BASE_DIR / "brand_assets" / "logo-application-primary-512.png",
    ]
    for p in candidates:
        if p.exists():
            img = Image.open(p).convert("RGBA")
            img.thumbnail((64, 64), Image.LANCZOS)
            return img

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = 28
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 217, 61, 255), outline=(244, 163, 0, 255), width=2)
    draw.ellipse([cx - 12, cy - 10, cx - 4, cy - 2], fill=(50, 50, 50, 255))
    draw.ellipse([cx + 4, cy - 10, cx + 12, cy - 2], fill=(50, 50, 50, 255))
    draw.ellipse([cx - 10, cy - 9, cx - 8, cy - 6], fill=(255, 255, 255, 220))
    draw.ellipse([cx + 6, cy - 9, cx + 8, cy - 6], fill=(255, 255, 255, 220))
    draw.arc([cx - 14, cy - 2, cx + 14, cy + 16], start=10, end=170, fill=(50, 50, 50, 255), width=2)
    draw.ellipse([cx - 20, cy + 6, cx - 12, cy + 13], fill=(255, 182, 193, 140))
    draw.ellipse([cx + 12, cy + 6, cx + 20, cy + 13], fill=(255, 182, 193, 140))
    return img


def refresh_tray_menu():
    global tray_icon
    if tray_icon:
        try:
            tray_icon.menu = build_tray_menu()
            status = get_service_status()
            tray_icon.title = f"AideLink 管理器 — {'运行中' if status['running'] else '已停止'}"
        except Exception:
            pass


def _tray_start_service():
    start_flask_service()
    refresh_tray_menu()


def _tray_stop_service():
    stop_flask_service()
    refresh_tray_menu()


def _tray_restart_service():
    # 彻底执行一键强杀，并重新拉起服务
    logger.info("正在执行强杀并重启服务...")
    try:
        python_exe = sys.executable
        start_script = BASE_DIR / "start_services.py"
        subprocess.Popen(
            [python_exe, str(start_script)],
            cwd=str(BASE_DIR),
            close_fds=True,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else 0
        )
        os._exit(0)
    except Exception as e:
        logger.error(f"合并强杀重启失败: {e}")
        # fallback: 仅重启 Flask
        stop_flask_service()
        time.sleep(0.5)
        start_flask_service()
        refresh_tray_menu()


def _find_local_update_package():
    try:
        if not LOCAL_UPDATE_DIR.is_dir():
            return None
        packages = [p for p in LOCAL_UPDATE_DIR.glob("AideLink-Setup*.exe") if p.is_file()]
        return max(packages, key=lambda p: p.stat().st_mtime) if packages else None
    except Exception:
        return None


def _find_remote_update():
    """Discover the newest installer in the OpenList ``aidelink`` folder."""
    try:
        def list_path(path):
            response = _requests.post(
                REMOTE_OPENLIST_BASE.rstrip("/") + "/api/fs/list",
                json={"path": path, "password": "", "page": 1, "per_page": 100,
                      "refresh": False},
                timeout=3,
            )
            response.raise_for_status()
            data = response.json().get("data", {})
            return data.get("content") or []

        root = list_path("/")
        folder = next((item for item in root if item.get("name", "").lower() == "aidelink" and item.get("is_dir")), None)
        if not folder:
            return None
        files = [item for item in list_path(folder.get("path", ""))
                 if not item.get("is_dir") and item.get("name", "").lower().startswith("aidelink-setup")
                 and item.get("name", "").lower().endswith(".exe")]
        if not files:
            return None
        item = max(files, key=lambda value: value.get("modified", ""))
        path = item.get("path", "").lstrip("/")
        return {"name": item.get("name"), "url": REMOTE_OPENLIST_BASE.rstrip("/") + "/d/" + quote(path)}
    except Exception:
        logger.debug("OpenList 更新源暂不可用", exc_info=True)
        return None


def _get_update_package():
    local = _find_local_update_package()
    if local:
        return local
    remote = _find_remote_update()
    if not remote:
        return None
    try:
        update_dir = Path(tempfile.gettempdir()) / "AideLink-update"
        update_dir.mkdir(parents=True, exist_ok=True)
        target = update_dir / remote["name"]
        response = _requests.get(remote["url"], timeout=10, stream=True)
        response.raise_for_status()
        with target.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
        return target
    except Exception:
        logger.exception("下载 OpenList 更新包失败")
        return None


def _tray_update_local():
    package = _get_update_package()
    if not package:
        logger.warning("本地映射盘和 OpenList 都未找到更新包")
        return
    try:
        subprocess.Popen(
            [str(package), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
            cwd=str(package.parent),
            creationflags=(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
            if os.name == "nt" else 0,
            close_fds=True,
        )
        # 安装器 PrepareToInstall 会先停止旧版服务，再覆盖文件。
        threading.Timer(1.0, on_tray_exit).start()
    except Exception:
        logger.exception("启动本机更新包失败: %s", package)


def show_main_window():
    webbrowser.open("http://127.0.0.1:5000")


def show_floating_window():
    try:
        from floating_window_app import open_floating_window
        open_floating_window()
    except Exception:
        logger.exception("打开桌面浮窗失败")


def toggle_floating_window():
    """Close the live float or start a fresh floating-window process."""
    try:
        from floating_window_app import close_floating_window
        if close_floating_window():
            return
        show_floating_window()
    except Exception:
        logger.exception("切换桌面浮窗失败")


def restart_floating_window():
    """Restart the floating window: close the old process, wait for it to exit, then start fresh."""
    try:
        from floating_window_app import close_floating_window, open_floating_window
        close_floating_window()
        # Wait for the old process to fully release the signal port (max ~3s)
        for _ in range(30):
            if not close_floating_window(timeout=0.1):
                break
            time.sleep(0.1)
        open_floating_window()
    except Exception:
        logger.exception("重启桌面浮窗失败")


def _get_target_projects():
    """Read the same target-project list shown by the Web manager."""
    try:
        response = _requests.get("http://127.0.0.1:5000/api/projects", timeout=2)
        response.raise_for_status()
        data = response.json()
        return data.get("projects", []), data.get("current_project", "")
    except Exception:
        logger.debug("读取目标项目列表失败", exc_info=True)
        return [], ""


def _discover_running_ide_projects():
    """Best-effort discovery from IDE process working directories/arguments."""
    try:
        import ide_scanner
        ide_paths = {
            os.path.normcase(os.path.abspath(item.get("path", "")))
            for item in ide_scanner.get_all_ides() if item.get("path")
        }
        candidates = {}
        from ide_project_bindings import load_bindings
        for path in load_bindings().values():
            if os.path.isdir(path) and _looks_like_project(path):
                candidates[os.path.normcase(path)] = path
        for process in __import__("psutil").process_iter(["exe", "cwd", "cmdline"]):
            try:
                exe = os.path.normcase(os.path.abspath(process.info.get("exe") or ""))
                if exe not in ide_paths:
                    continue
                values = [process.info.get("cwd") or ""]
                values.extend(process.info.get("cmdline") or [])
                for value in values:
                    value = value.strip().strip('"')
                    if os.path.isdir(value) and _looks_like_project(value):
                        candidates[os.path.normcase(value)] = value
            except (OSError, ValueError):
                continue
        return sorted(candidates.values(), key=lambda path: path.lower())
    except Exception:
        logger.debug("从运行中的 IDE 发现项目失败", exc_info=True)
        return []


def _looks_like_project(path):
    markers = (".git", "package.json", "settings.gradle", "settings.gradle.kts",
               "pom.xml", "Cargo.toml", "pyproject.toml")
    return any(os.path.exists(os.path.join(path, marker)) for marker in markers)


def _build_discovered_project_menu():
    items = []
    for path in _discover_running_ide_projects():
        items.append(MenuItem(
            os.path.basename(path) or path,
            _project_select_handler(path),
        ))
    if not items:
        items.append(MenuItem("未发现明确的项目目录", None, enabled=False))
    return Menu(*items)


def _select_target_project(path):
    """Select a configured target project through the normal Web API."""
    try:
        response = _requests.post(
            "http://127.0.0.1:5000/api/projects/select",
            json={"path": path},
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok", False):
            logger.warning("切换目标项目失败: %s", result.get("message", "未知错误"))
    except Exception:
        logger.exception("切换目标项目失败: %s", path)
    finally:
        refresh_tray_menu()


def _build_project_menu():
    projects, current = _get_target_projects()
    items = []
    for project in projects:
        path = project.get("path", "")
        if not path:
            continue
        name = project.get("name") or os.path.basename(path)
        marker = "✓ " if os.path.normcase(path) == os.path.normcase(current) else "   "
        items.append(MenuItem(
            f"{marker}{name}",
            _project_select_handler(path),
        ))
    if not items:
        items.append(MenuItem("暂无目标项目，请先在 Web 任务管理中添加", None, enabled=False))
    return Menu(*items)


def _project_select_handler(path):
    def handler(icon, item):
        threading.Thread(
            target=_select_target_project, args=(path,), daemon=True
        ).start()
    return handler


STARTUP_VALUE_NAME = "AideLink"


def _startup_command():
    """Return the command used by the per-user Windows startup entry."""
    start_script = BASE_DIR / "start_services.py"
    return f'"{sys.executable}" "{start_script}"'


def _is_auto_start_enabled(_item=None):
    if os.name != "nt":
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, STARTUP_VALUE_NAME)
            return bool(value)
    except (FileNotFoundError, OSError):
        return False


def _set_auto_start(enabled):
    if os.name != "nt":
        return
    try:
        subkey = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, STARTUP_VALUE_NAME, 0, winreg.REG_SZ, _startup_command())
            else:
                try:
                    winreg.DeleteValue(key, STARTUP_VALUE_NAME)
                except FileNotFoundError:
                    pass
        refresh_tray_menu()
    except Exception as e:
        logger.error(f"修改开机启动设置失败: {e}")


def _tray_toggle_auto_start():
    _set_auto_start(not _is_auto_start_enabled())


def get_adb_devices():
    """获取已连接的 ADB 设备列表"""
    import subprocess
    devices = []
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        result = subprocess.run(
            [ADB_PATH, "devices"], capture_output=True, text=True, timeout=5,
            startupinfo=si, creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in result.stdout.strip().split('\n')[1:]:
            if '\t' in line:
                parts = line.split('\t')
                if len(parts) >= 2 and parts[1] == 'device':
                    devices.append(parts[0])
    except Exception:
        pass
    return devices


def get_device_list():
    """从 AideLink 服务端获取设备列表（带在线状态和别名）"""
    import urllib.request, json
    try:
        req = urllib.request.Request("http://127.0.0.1:5000/api/devices", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                return data.get("devices", [])
    except Exception:
        pass

    # 兜底从本地配置文件读取，保证离线设备可见且可以点击连接
    try:
        aliases_path = BASE_DIR / "state" / "device_aliases.json"
        if aliases_path.exists():
            with open(aliases_path, "r", encoding="utf-8") as f:
                aliases = json.load(f)
                result = []
                for alias, info in aliases.items():
                    result.append({
                        "device_id": None,
                        "ip": info.get("ip"),
                        "online_ip": None,
                        "adb_port": info.get("port") or 5555,
                        "alias": alias,
                        "model": info.get("model", ""),
                        "is_adb_connected": False,
                        "is_online": False,
                        "ips": info.get("ips") or [],
                    })
                return result
    except Exception:
        pass
    return []


def _enable_adb_for_device(ip, port=5555):
    """通过 AideLink API 开启无线调试"""
    import urllib.request, json
    try:
        body = json.dumps({"ip": ip, "timeout": 30}).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:5000/api/adb/enable-wireless",
            data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=35) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                return True, data
            return False, data.get("error", "失败")
    except Exception as e:
        return False, str(e)


def connect_adb_and_copy(ip, port=5555):
    """尝试 ADB 连接设备，成功则复制到剪贴板"""
    import subprocess
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        target = f"{ip}:{port}"
        result = subprocess.run(
            [ADB_PATH, "connect", target], capture_output=True, text=True, timeout=10,
            startupinfo=si, creationflags=subprocess.CREATE_NO_WINDOW
        )
        output = result.stdout.strip()
        if "connected" in output.lower() or "already" in output.lower():
            copy_to_clipboard(f"adb connect {target}")
            return True, target
        return False, output
    except Exception as e:
        return False, str(e)


def copy_to_clipboard(text):
    """复制文本到剪贴板"""
    try:
        import pyperclip
        pyperclip.copy(text)
    except Exception:
        try:
            import subprocess
            subprocess.run(['clip'], input=text, text=True, check=True, timeout=3)
        except Exception:
            pass


def _try_adb_connect(ip, ips=None):
    """尝试 ADB 连接设备（优先同网段 IP，并发多线程，绝对静默），成功后自动拉起 AideLink"""
    import concurrent.futures
    import sys
    
    raw_candidates = list(dict.fromkeys(([ip] + (ips or []))))
    raw_candidates = [i for i in raw_candidates if i]

    server_subnet = _get_server_subnet()
    if server_subnet:
        raw_candidates.sort(key=lambda x: 0 if x.rsplit('.', 1)[0] == server_subnet else 1)

    known_port = None
    try:
        import json
        aliases_path = BASE_DIR / "state" / "device_aliases.json"
        if aliases_path.exists():
            with open(aliases_path, "r", encoding="utf-8") as f:
                aliases = json.load(f)
                for alias_name, info in aliases.items():
                    known_ips = [info.get("ip")] + (info.get("ips") or [])
                    if ip in known_ips and info.get("port"):
                        known_port = int(info.get("port"))
                        break
    except Exception:
        pass

    ports = [5555, 44233, 41157, 46325, 46075, 42829, 38131]
    if known_port and known_port not in ports:
        ports.insert(0, known_port)

    targets = []
    for dip in raw_candidates:
        for p in ports:
            targets.append(f"{dip}:{p}")

    connected_target = None
    lock = threading.Lock()

    def check_connect(target_addr):
        nonlocal connected_target
        if connected_target:
            return

        creationflags = 0
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NO_WINDOW
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
        except AttributeError:
            si = None

        try:
            res = subprocess.run(
                [ADB_PATH, "connect", target_addr],
                capture_output=True, text=True, timeout=4,
                startupinfo=si, creationflags=creationflags
            )
            out = res.stdout.lower()
            if "connected" in out or "already" in out:
                with lock:
                    if not connected_target:
                        connected_target = target_addr
        except Exception:
            pass

    # 最大 16 线程并发测试
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        executor.map(check_connect, targets)

    if connected_target:
        copy_to_clipboard(connected_target)
        creationflags = 0
        if sys.platform == 'win32':
            creationflags = subprocess.CREATE_NO_WINDOW
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
        except AttributeError:
            si = None

        try:
            subprocess.run(
                [ADB_PATH, "-s", connected_target, "shell", "am", "start", "-n",
                 "cc.aidelink.app/.MainActivity"],
                capture_output=True, timeout=5, startupinfo=si, creationflags=creationflags
            )
        except Exception:
            pass
    else:
        copy_to_clipboard(f"{ip}:5555")


def _get_server_subnet():
    """获取服务端所在子网前缀（如 192.168.1）"""
    import urllib.request, json
    try:
        req = urllib.request.Request("http://127.0.0.1:5000/api/settings", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            server_url = data.get("server_url", "")
            host = server_url.split("://")[-1].split(":")[0].split("/")[0]
            if host:
                return host.rsplit('.', 1)[0]
    except Exception:
        pass
    return None


def build_tray_menu():
    status = get_service_status()
    status_text = "✅ 运行中" if status["running"] else "⏹ 已停止"
    
    devices = get_device_list()
    adb_devices = get_adb_devices()

    def _copy_handler(t):
        def h(icon, item):
            threading.Thread(target=copy_to_clipboard, args=(t,), daemon=True).start()
        return h

    def _enable_handler(ip):
        def h(icon, item):
            def _do_enable():
                success, res_data = _enable_adb_for_device(ip)
                if success and isinstance(res_data, dict):
                    res_ip = res_data.get("ip") or ip
                    res_port = res_data.get("port") or 5555
                    copy_to_clipboard(f"{res_ip}:{res_port}")
                else:
                    copy_to_clipboard(f"{ip}:5555")
                refresh_tray_menu()
            threading.Thread(target=_do_enable, daemon=True).start()
        return h

    def _connect_handler(ip, ips):
        def h(icon, item):
            def _do_connect():
                # 1. 先通知 App 开启无线调试（SSE 命令 + adb connect fallback）
                #    覆盖 App 在线但 ADB 未开启的场景
                success, res_data = _enable_adb_for_device(ip)
                if success and isinstance(res_data, dict):
                    res_ip = res_data.get("ip") or ip
                    res_port = res_data.get("port") or 5555
                    copy_to_clipboard(f"{res_ip}:{res_port}")
                    refresh_tray_menu()
                    return
                # 2. 通知失败（App 离线/超时），回退到多端口探测
                #    覆盖 App 未启动但 ADB 已开启的场景，探测成功后自动拉起 App
                _try_adb_connect(ip, ips)
                refresh_tray_menu()
            threading.Thread(target=_do_connect, daemon=True).start()
        return h

    device_menu_items = []
    if devices:
        for d in devices:
            alias = d.get("alias", "未知")
            ip = d.get("online_ip") or d.get("ip") or ""
            model = d.get("model", "")
            online = d.get("is_online", False)
            is_adb = d.get("is_adb_connected", False)
            port = d.get("adb_port") or 5555
            display = f"📱 {alias}"
            if model:
                display += f" ({model})"
            if online:
                if is_adb:
                    display += f" [{ip}:{port}]  ✅ 在线+ADB"
                    target = d.get("device_id") or f"{ip}:{port}"
                    device_menu_items.append(MenuItem(display, _copy_handler(target)))
                else:
                    display += f" [{ip}]  🟢 在线"
                    device_menu_items.append(MenuItem(display, _enable_handler(ip)))
            else:
                display += f" [{ip}]  ⚪ 离线"
                all_ips = d.get("ips") or []
                device_menu_items.append(MenuItem(display, _connect_handler(ip, all_ips)))
    elif adb_devices:
        for dev in adb_devices:
            device_menu_items.append(
                MenuItem(f"📱 {dev}  ✅ ADB", _copy_handler(dev))
            )
    else:
        device_menu_items.append(MenuItem("  无已连接设备", None, enabled=False))

    frp_status = get_frp_status()

    return Menu(
        MenuItem(f"AideLink  ·  {status_text}", None, enabled=False),
        Menu.SEPARATOR,
        MenuItem("关闭 / 开启浮窗", lambda _icon, _item: toggle_floating_window(), default=True),
        MenuItem("重启浮窗", lambda _icon, _item: restart_floating_window()),
        MenuItem("打开管理面板", lambda: show_main_window()),
        MenuItem("开机启动 AideLink", _tray_toggle_auto_start, checked=_is_auto_start_enabled),
        Menu.SEPARATOR,
        MenuItem("设备连接", Menu(*device_menu_items)),
        MenuItem("发现运行中的 IDE 项目", _build_discovered_project_menu()),
        Menu.SEPARATOR,
        MenuItem("启动服务", _tray_start_service, enabled=not status["running"]),
        MenuItem("停止服务", _tray_stop_service, enabled=status["running"]),
        MenuItem("重启服务", _tray_restart_service),
        Menu.SEPARATOR,
        MenuItem(
            "FRP 随服务自动启动",
            _tray_toggle_frp_auto_start,
            checked=_is_frp_auto_start_enabled,
        ),
        MenuItem(
            f"立即启用 FRP 穿透{'  ·  已运行' if frp_status['running'] else ''}",
            _tray_start_frp_now,
            enabled=not frp_status["running"],
        ),
        Menu.SEPARATOR,
        MenuItem("选择目标项目", _build_project_menu()),
        Menu.SEPARATOR,
        MenuItem("退出 AideLink", lambda: on_tray_exit()),
    )


def _is_frp_auto_start_enabled(_item=None):
    config = load_config()
    return bool((config.get("frp") or {}).get("enabled", False))


def _tray_toggle_frp_auto_start(_icon=None, _item=None):
    config = load_config()
    frp_config = dict(config.get("frp") or {})
    frp_config["enabled"] = not bool(frp_config.get("enabled", False))
    config["frp"] = frp_config
    ok, message = save_config(config)
    if not ok:
        logger.error("保存 FRP 自动启动设置失败: %s", message)
    refresh_tray_menu()


def _tray_start_frp_now(_icon=None, _item=None):
    start_frp_client(force=True)
    refresh_tray_menu()


def _get_devspace_status():
    try:
        r = _requests.get("http://127.0.0.1:5000/api/devspace/status", timeout=3)
        j = r.json()
        return j.get("devspace", {}).get("running", False)
    except Exception:
        return None


def _tray_toggle_devspace():
    try:
        if _get_devspace_status():
            _requests.post("http://127.0.0.1:5000/api/devspace/stop", timeout=5)
        else:
            _requests.post("http://127.0.0.1:5000/api/devspace/start", timeout=10)
    except Exception as e:
        logger.error(f"DevSpace 切换失败: {e}")
    refresh_tray_menu()


def on_tray_exit():
    logger.info("正在退出 AideLink 管理器...")
    if is_flask_running():
        logger.info("正在停止 Flask 服务...")
        stop_flask_service()
    try:
        tray_icon.stop()
    except Exception:
        pass
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    os._exit(0)


# ============================================================
# PID 文件管理
# ============================================================

def write_pid_file():
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    logger.info(f"PID 文件已写入: {PID_FILE} (PID: {os.getpid()})")


def cleanup():
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# ============================================================
# 主入口
# ============================================================

def run_manager():
    if not acquire_tray_single_instance():
        logger.info("已有 AideLink 托盘实例运行，当前启动请求退出")
        return
    write_pid_file()
    atexit.register(cleanup)

    if not is_flask_running():
        logger.info("Flask 服务未运行，正在自动启动...")
        success, message = start_flask_service()
        logger.info(message)
    else:
        logger.info("Flask 服务已在运行中")

    # 是否打开网页由 Web 设置控制，默认关闭，避免开机启动打扰用户。
    config = load_config()
    if config.get("open_browser_on_start", False):
        threading.Timer(1.5, show_main_window).start()

    global tray_icon
    tray_icon = Icon(
        name="AideLinkManager",
        icon=create_tray_icon(),
        title="AideLink 管理器",
        menu=build_tray_menu(),
    )

    # pystray 的 Windows 后端在 WM_LBUTTONUP 时执行 default 菜单项，
    # 因此单击托盘会直接开启浮窗，右键仍显示完整管理菜单。

    # 定期刷新托盘菜单（更新设备列表）
    def _auto_refresh():
        import time
        time.sleep(30)
        while True:
            try:
                refresh_tray_menu()
            except Exception:
                pass
            time.sleep(30)
    threading.Thread(target=_auto_refresh, daemon=True).start()

    logger.info("系统托盘已启动，左键双击或右键菜单管理服务")
    tray_icon.run()


if __name__ == "__main__":
    run_manager()

