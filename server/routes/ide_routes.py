import sys
import os
import subprocess
import shutil
import threading
import time
import ctypes

import psutil
import requests
from flask import Blueprint, request, jsonify, send_from_directory
from pathlib import Path

from manager_utils import logger
from paths import BRIDGE_DIR as BASE_DIR

ide_bp = Blueprint('ides', __name__)


def _install_aidelink_skill(key, home_dir=None, source_dir=None):
    """Install the bundled manager/worker skill for IDEs that discover SKILL.md folders."""
    source = Path(source_dir) if source_dir else BASE_DIR.parent / "skills" / "aidelink-manager-worker"
    if not (source / "SKILL.md").is_file():
        return 0
    home = Path(home_dir) if home_dir else Path.home()
    roots = []
    if key in {"codex", "openai-codex", "openaicodex"}:
        # Current Codex releases discover user skills from ~/.agents/skills.
        # Keep the former ~/.codex/skills target for installed older clients.
        roots.append(home / ".agents" / "skills")
        roots.append(home / ".codex" / "skills")
    if key in {"trae", "trae_cn", "trae_solo", "trae_solo_cn"}:
        roots.append(home / ".trae" / "skills")
    installed = 0
    for root in roots:
        target = root / source.name
        root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, dirs_exist_ok=True)
        installed += 1
    return installed


# ============================================================
# IDE 管理 API
# ============================================================

@ide_bp.route("/api/ide-window-bindings/candidates", methods=["GET"])
def api_window_binding_candidates():
    key = request.args.get("key", "").strip().lower()
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"}), 400
    try:
        from window_binding import get_binding, list_window_candidates, recommend_candidate
        windows = list_window_candidates()
        return jsonify({
            "success": True,
            "key": key,
            "binding": get_binding(key),
            "windows": windows,
            "recommendation": recommend_candidate(key, windows),
        })
    except Exception as exc:
        return jsonify({"success": False, "message": f"读取窗口列表失败: {exc}"}), 500


@ide_bp.route("/api/ide-window-bindings", methods=["POST", "DELETE"])
def api_window_binding():
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip().lower()
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"}), 400
    from window_binding import bind_window_by_hwnd, delete_binding
    if request.method == "DELETE":
        ok = delete_binding(key)
        return jsonify({"success": ok, "message": "已恢复默认窗口识别规则" if ok else "重置窗口绑定失败"})
    hwnd = data.get("hwnd")
    if not isinstance(hwnd, int) and not str(hwnd or "").isdigit():
        return jsonify({"success": False, "message": "请选择有效窗口"}), 400
    candidate = bind_window_by_hwnd(key, int(hwnd))
    if not candidate:
        return jsonify({"success": False, "message": "窗口已关闭或绑定保存失败，请刷新后重试"}), 409
    return jsonify({"success": True, "message": f"已将 {key} 绑定到 {candidate['title']}", "binding": candidate})


@ide_bp.route("/api/ide-window-bindings/auto", methods=["POST"])
def api_auto_window_binding():
    """将已激活/最大化的目标 IDE 前台窗口直接绑定。"""
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip().lower()
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"}), 400
    from window_binding import auto_bind_foreground_window
    candidate, message = auto_bind_foreground_window(key)
    if not candidate:
        return jsonify({"success": False, "message": message}), 409
    return jsonify({"success": True, "message": message, "binding": candidate})


@ide_bp.route("/api/ide-window-bindings/test", methods=["POST"])
def api_test_window_binding():
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip().lower()
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"}), 400
    import screenshot_engine as se
    from window_binding import describe_window, get_binding
    window = se._find_target_window(key)
    if not window:
        return jsonify({
            "success": False,
            "message": "仍未找到对应窗口，请重新选择当前打开的 IDE 窗口",
            "binding": get_binding(key),
        }), 404
    return jsonify({
        "success": True,
        "message": f"匹配成功: {window.title}",
        "window": describe_window(window),
        "binding": get_binding(key),
    })


@ide_bp.route("/api/ide-profiles/<key>", methods=["GET"])
def api_get_ide_profile(key):
    try:
        from ide_profiles import load_profile
        return jsonify({"ok": True, "profile": load_profile(key)})
    except Exception as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400


@ide_bp.route("/api/ide-profiles/<key>/update", methods=["POST"])
def api_update_ide_profile(key):
    data = request.get_json(silent=True) or {}
    try:
        from ide_profiles import update_profile
        updated, profile, message = update_profile(key, force=bool(data.get("force", False)))
        return jsonify({"ok": True, "updated": updated, "message": message, "profile": profile})
    except Exception as exc:
        return jsonify({"ok": False, "message": f"IDE 适配配置更新失败: {exc}"}), 502

@ide_bp.route("/api/launch-ide", methods=["POST"])
def api_launch_ide():
    """启动指定 IDE"""
    data = request.json or {}
    key = data.get("key", "").strip().lower()
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"}), 400

    import ide_scanner
    ides = ide_scanner.get_all_ides()
    ide_info = next((i for i in ides if i["key"] == key), None)
    if not ide_info:
        return jsonify({"success": False, "message": f"未知的 IDE: {key}"})

    ide_path = ide_info.get("path", "")
    if not ide_path:
        return jsonify({"success": False, "message": f"未找到 {key} 的安装路径"})

    import subprocess as _sp
    try:
        from paths import get_project_root
        project_root = get_project_root()
        cmd = [ide_path]
        if project_root and project_root.exists() and project_root.is_dir():
            cmd.append(str(project_root))
            from ide_project_bindings import save_binding
            save_binding(key, project_root)

        flags = _sp.CREATE_NEW_PROCESS_GROUP | _sp.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        _sp.Popen(cmd, creationflags=flags, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
        return jsonify({"success": True, "message": f"{ide_info['name']} 启动中..."})
    except Exception as e:
        return jsonify({"success": False, "message": f"启动失败: {e}"}), 500


@ide_bp.route("/api/stop-ide", methods=["POST"])
def api_stop_ide():
    """关闭指定 IDE，释放资源"""
    data = request.json or {}
    key = data.get("key", "").strip().lower()
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"}), 400

    import ide_scanner
    ides = ide_scanner.get_all_ides()
    ide_info = next((i for i in ides if i["key"] == key), None)
    if not ide_info:
        return jsonify({"success": False, "message": f"未知的 IDE: {key}"})

    ide_name = ide_info.get("name", key)
    ide_path = (ide_info.get("path") or "").lower()
    killed = 0
    try:
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                pname = (proc.info.get('name') or '').lower()
                if key == "oc":
                    proc_exe = (proc.info.get('exe') or '').lower()
                    cmdline = ' '.join(proc.cmdline() or []).lower()
                    if "serve" in cmdline:
                        continue
                    if ide_path and ide_path in proc_exe:
                        proc.kill()
                        killed += 1
                    elif "opencode" in proc_exe:
                        proc.kill()
                        killed += 1
                elif ide_name.lower() in pname or key in pname:
                    proc.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if killed > 0:
            return jsonify({"success": True, "message": f"已关闭 {ide_name}，释放了 {killed} 个进程"})
        else:
            return jsonify({"success": True, "message": f"{ide_name} 未在运行"})
    except Exception as e:
        return jsonify({"success": False, "message": f"关闭失败: {e}"}), 500


@ide_bp.route("/api/launch-ide-status")
def api_launch_ide_status():
    """返回正在运行的 IDE 列表"""
    import ide_scanner
    ides = ide_scanner.get_all_ides()
    running = []
    for ide in ides:
        key = ide.get("key", "")
        name = ide.get("name", "")
        # 检查进程是否存在
        try:
            for proc in psutil.process_iter(['name', 'cmdline']):
                pname = (proc.info.get('name') or '').lower()
                cmdline = ' '.join(proc.info.get('cmdline') or []).lower()
                if key in pname or key in cmdline or name.lower() in pname:
                    running.append(key)
                    break
        except Exception:
            pass
    return jsonify({"success": True, "running": list(set(running))})


@ide_bp.route("/api/ide/active_status", methods=["GET"])
def get_active_ide_status():
    """获取所有 IDE 当前的活动状态（是否启动、是否正忙等）"""
    import ide_scanner
    from shared_runtime import runtime
    
    all_ides = ide_scanner.get_all_ides()
    result = []
    
    for ide_info in all_ides:
        ide_key = ide_info["key"]
        ide_name = ide_info.get("name", ide_key)
        
        # 检查是否在运行
        running = False
        try:
            # 兼容 python_chat_bridge 的 _is_ide_running 实现
            if ide_key == "oc" and _is_port_in_use_local(4096):
                running = True
            else:
                exe_filename = os.path.basename(ide_info.get("path", "")).lower() if ide_info.get("path") else ""
                for proc in psutil.process_iter(['name', 'exe']):
                    try:
                        proc_info = proc.info
                        pname = (proc_info.get('name') or '').lower()
                        pexe = (proc_info.get('exe') or '').lower()
                        if len(ide_key) <= 2:
                            if (ide_name.lower() in pname or exe_filename and exe_filename in pexe):
                                running = True
                                break
                        else:
                            if (ide_key in pname or ide_name.lower() in pname or exe_filename and exe_filename in pexe):
                                running = True
                                break
                    except Exception:
                        continue
        except Exception:
            pass
            
        busy_status = "idle"
        current_task_id = None
        try:
            current = runtime.get_ide_status(ide_key)
            if current:
                busy_status = current.get("status", "idle")
                current_task_id = current.get("current_task_id")
        except Exception:
            pass
            
        result.append({
            "key": ide_key,
            "name": ide_name,
            "running": running,
            "status": busy_status,
            "current_task_id": current_task_id
        })
    
    return jsonify({"ides": result})


# ============================================================
# OC Web Service Management
# ============================================================

_oc_web_process = None


def _find_oc_web_listener_pid(port):
    """Return the process listening on the OC Web port, if any."""
    for conn in psutil.net_connections(kind="inet"):
        if not conn.laddr or conn.laddr.port != port:
            continue
        if conn.status == psutil.CONN_LISTEN and conn.pid:
            return conn.pid
    return None


def _terminate_process_tree(pid):
    if sys.platform == "win32":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0

    try:
        process = psutil.Process(pid)
    except psutil.Error:
        return False

    procs = process.children(recursive=True) + [process]
    for proc in procs:
        try:
            proc.terminate()
        except psutil.Error:
            pass

    try:
        gone, alive = psutil.wait_procs(procs, timeout=5)
    except psutil.Error:
        alive = procs
        gone = []
    for proc in alive:
        try:
            proc.kill()
        except psutil.Error:
            pass
    return bool(gone or alive)


@ide_bp.route('/api/oc-web/status', methods=['GET'])
def api_oc_web_status():
    global _oc_web_process
    running = False
    pid = None
    port = 4096

    settings = _load_settings_local()
    port = settings.get("opencode_web_port", 4096)

    if _oc_web_process is not None:
        if _oc_web_process.poll() is None:
            running = True
            pid = _oc_web_process.pid
        else:
            _oc_web_process = None

    if not running:
        running = _is_port_in_use_local(port)
        if running:
            pid = _find_oc_web_listener_pid(port)

    return jsonify({"ok": True, "running": running, "port": port, "pid": pid})


@ide_bp.route('/api/oc-web/start', methods=['POST'])
def api_oc_web_start():
    global _oc_web_process
    settings = _load_settings_local()
    port = settings.get("opencode_web_port", 4096)
    project_dir = settings.get("project_dir", "").strip()

    if _oc_web_process is not None and _oc_web_process.poll() is None:
        return jsonify({"ok": True, "message": "OC Web 已在运行", "pid": _oc_web_process.pid, "port": port})

    if _is_port_in_use_local(port):
        return jsonify({"ok": True, "message": f"端口 {port} 已被占用，OC Web 可能已在运行", "port": port})

    try:
        env = os.environ.copy()
        if settings.get("opencode_web_username"):
            env["OPENCODE_SERVER_USERNAME"] = settings["opencode_web_username"]
        if settings.get("opencode_web_password"):
            env["OPENCODE_SERVER_PASSWORD"] = settings["opencode_web_password"]
        if sys.platform == 'win32':
            _oc_web_process = subprocess.Popen(
                f"opencode serve --port {port} --hostname 0.0.0.0",
                cwd=project_dir if project_dir else None,
                env=env,
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            _oc_web_process = subprocess.Popen(
                ["opencode", "serve", "--port", str(port), "--hostname", "0.0.0.0"],
                cwd=project_dir if project_dir else None,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        for _ in range(30):
            time.sleep(0.5)
            if _is_port_in_use_local(port):
                return jsonify({"ok": True, "message": "OpenCode 服务启动成功", "pid": _oc_web_process.pid, "port": port})
        return jsonify({"ok": False, "error": "OpenCode 服务启动超时"}), 500
    except FileNotFoundError:
        _oc_web_process = None
        return jsonify({"ok": False, "error": "未找到 opencode 命令，请确认已安装"}), 404
    except Exception as e:
        _oc_web_process = None
        return jsonify({"ok": False, "error": f"启动失败: {e}"}), 500


@ide_bp.route('/api/oc-web/stop', methods=['POST'])
def api_oc_web_stop():
    global _oc_web_process
    settings = _load_settings_local()
    port = settings.get("opencode_web_port", 4096)
    killed = False

    if _oc_web_process is not None:
        killed = _terminate_process_tree(_oc_web_process.pid) or killed
        _oc_web_process = None

    listener_pid = _find_oc_web_listener_pid(port)
    if listener_pid:
        killed = _terminate_process_tree(listener_pid) or killed

    if killed:
        return jsonify({"ok": True, "message": "OC Web 已停止"})
    return jsonify({"ok": True, "message": "OC Web 未在运行"})


@ide_bp.route('/api/oc-web/latest-reply', methods=['GET'])
def api_oc_web_latest_reply():
    settings = _load_settings_local()
    port = settings.get("opencode_web_port", 4096)
    oc_base = f"http://127.0.0.1:{port}"

    try:
        sessions_resp = requests.get(f"{oc_base}/session", timeout=3)
        if sessions_resp.status_code != 200:
            return jsonify({"ok": False, "error": "OC Web 未运行或无法连接"}), 502

        sessions = sessions_resp.json()
        if not sessions:
            return jsonify({"ok": True, "reply": None})

        session_id = sessions[-1].get("id", "")
        title = sessions[-1].get("title", "")

        msg_resp = requests.get(f"{oc_base}/session/{session_id}/message", timeout=5)
        if msg_resp.status_code != 200:
            return jsonify({"ok": True, "reply": None})

        messages = msg_resp.json()
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
        if not assistant_msgs:
            return jsonify({"ok": True, "reply": None})

        last = assistant_msgs[-1]
        parts = last.get("parts", [])
        text = ""
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                text += part.get("text", "")
            elif isinstance(part, str):
                text += part

        return jsonify({
            "ok": True,
            "reply": {
                "session_id": session_id,
                "session_title": title,
                "text": text,
                "length": len(text),
            }
        })

    except requests.ConnectionError:
        return jsonify({"ok": False, "error": "OC Web 未运行"}), 502
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500



@ide_bp.route("/api/ide-screenshot", methods=["POST"])
def api_ide_screenshot():
    """获取 IDE 窗口信息和显示器信息（不自动截图）"""
    data = request.json or {}
    key = data.get("key", "").strip().lower()
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"})

    import pygetwindow as gw
    import ide_scanner
    import screenshot_engine as se

    ides = ide_scanner.get_all_ides()
    ide_info = next((i for i in ides if i["key"] == key), None)
    if not ide_info:
        return jsonify({"success": False, "message": f"未知 IDE: {key}"})

    ide_name = ide_info.get("name", key)
    win = None

    # 按标题找 GUI 窗口
    for w in gw.getAllWindows():
        if w.title.strip() and ide_name.lower() in w.title.lower():
            win = w
            break

    # 兜底：用 screenshot_engine 的窗口查找（有固定映射表）
    if not win:
        win = se._find_target_window(key)

    # 找不到则通过进程树找终端窗口
    if not win:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                pname = (proc.info.get('name') or '').lower()
                cmdline = ' '.join(proc.info.get('cmdline') or []).lower()
                if key in pname or key in cmdline or ide_name.lower() in pname:
                    ancestor = proc
                    for _ in range(6):
                        parent = ancestor.parent()
                        if not parent:
                            break
                        ppname = parent.name().lower()
                        if 'windowsterminal' in ppname or 'conhost' in ppname:
                            for w in gw.getAllWindows():
                                if w.title.strip():
                                    pid = ctypes.c_ulong()
                                    ctypes.windll.user32.GetWindowThreadProcessId(w._hWnd, ctypes.byref(pid))
                                    if pid.value == parent.pid:
                                        win = w
                                        break
                            break
                        ancestor = parent
                    if win:
                        break
            except Exception:
                pass

    monitor_info = {}
    monitors = se.get_all_monitors()
    crop = {"left": 0, "right": 0, "top": 0, "bottom": 0}
    window_info = {}

    if win:
        hwnd = win._hWnd
        monitor_name = se.get_monitor_for_window(hwnd)
        monitor_info = next((m for m in monitors if m["name"] == monitor_name), monitors[0] if monitors else {})
        crop = se.get_crop_config(key, monitor_name)
        window_info = {"left": win.left, "top": win.top, "width": win.width, "height": win.height}
    else:
        # 窗口未找到 → 使用主显示器信息 + 默认裁剪
        monitor_info = next((m for m in monitors if m.get("primary")), monitors[0] if monitors else {})
        crop = se.get_crop_config(key, "primary")
        window_info = {"left": 0, "top": 0, "width": monitor_info.get("width", 0), "height": monitor_info.get("height", 0)}

    return jsonify({
        "success": True,
        "monitor": monitor_info,
        "crop": crop,
        "all_monitors": monitors,
        "window": window_info,
    })


@ide_bp.route("/api/focus-ide", methods=["POST"])
def api_focus_ide():
    """激活指定 IDE 到最前"""
    data = request.json or {}
    key = data.get("key", "").strip().lower()
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"}), 400
    import screenshot_engine as se
    ok = se._activate_target_window(key, focus_input=False)
    return jsonify({"success": ok})


@ide_bp.route("/api/trigger-screenshot", methods=["POST"])
def api_trigger_screenshot():
    """触发系统截图工具 Win+Shift+S"""
    try:
        import pyautogui
        pyautogui.hotkey('win', 'shift', 's')
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": f"触发截图失败: {e}"})


@ide_bp.route("/api/read-clipboard-screenshot", methods=["POST"])
def api_read_clipboard_screenshot():
    """从系统剪贴板读取截图并保存（按显示器分文件）"""
    data = request.json or {}
    key = data.get("key", "").strip().lower()
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"})

    try:
        from PIL import ImageGrab
        import screenshot_engine as se

        img = ImageGrab.grabclipboard()
        if img is None:
            return jsonify({"success": False, "message": "剪贴板中没有图片"})

        monitors = se.get_all_monitors()
        w, h = img.size
        matched_monitor = "primary"
        for mon in monitors:
            if mon["width"] == w and mon["height"] == h:
                matched_monitor = mon["name"]
                break

        screenshot_path = BASE_DIR / "static" / f"screenshot_{key}_{matched_monitor}.png"
        img.save(str(screenshot_path), "PNG")
        return jsonify({"success": True, "path": str(screenshot_path), "monitor": matched_monitor})
    except Exception as e:
        return jsonify({"success": False, "message": f"读取剪贴板失败: {e}"})


@ide_bp.route("/api/ide-screenshot-image")
def api_ide_screenshot_image():
    """返回 IDE 截图图片，支持 ?key=&monitor=""，自动应用裁剪配置"""
    key = request.args.get("key", "").strip().lower()
    monitor = request.args.get("monitor", "").strip()
    raw = request.args.get("raw", "").strip() == "1"

    # 1. 优先自动探测当前 IDE 所在的显示器
    detected_monitor = "primary"
    try:
        import screenshot_engine as se
        target_win = se._find_target_window(key)
        if target_win:
            detected_monitor = se.get_monitor_for_window(target_win._hWnd)
    except Exception:
        pass

    # 确定要使用的 monitor 名称（如果请求传了就用传的，没传就用探测出来的）
    crop_monitor = monitor if monitor else detected_monitor
    if not crop_monitor or crop_monitor == '_default':
        crop_monitor = "default"

    # 2. 查找截图文件
    screenshot_path = None
    if crop_monitor and crop_monitor != 'default':
        p = BASE_DIR / "static" / f"screenshot_{key}_{crop_monitor}.png"
        if p.exists():
            screenshot_path = p

    if not screenshot_path:
        for suffix in ("", "_primary", "_default"):
            p = BASE_DIR / "static" / f"screenshot_{key}{suffix}.png"
            if p.exists():
                screenshot_path = p

    if not screenshot_path:
        return "", 404

    # raw=1 直接返回原图（校准等场景用）
    if raw:
        return send_from_directory(str(screenshot_path.parent), screenshot_path.name)

    # 加载图片并应用裁剪配置
    try:
        import screenshot_engine as se
        from PIL import Image
        img = Image.open(str(screenshot_path))
        crop = se.get_crop_config(key, crop_monitor)
        left_m = crop.get("left", 0)
        right_m = crop.get("right", 0)
        top_m = crop.get("top", 0)
        bottom_m = crop.get("bottom", 0)
        # 裁剪：从四边各去掉 margin 像素
        new_left = max(0, left_m)
        new_top = max(0, top_m)
        new_right = max(0, img.width - right_m)
        new_bottom = max(0, img.height - bottom_m)
        if new_right > new_left and new_bottom > new_top:
            img = img.crop((new_left, new_top, new_right, new_bottom))
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        from flask import Response
        resp = Response(buf.getvalue(), mimetype="image/png")
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp
    except Exception:
        resp = send_from_directory(str(screenshot_path.parent), screenshot_path.name)
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return resp


@ide_bp.route("/api/capture-all-monitors", methods=["POST"])
def api_capture_all_monitors():
    """按显示器截取全屏，保存为 screenshot_{key}_{monitor}.png"""
    data = request.json or {}
    key = data.get("key", "").strip().lower()
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"})
    try:
        import screenshot_engine as se
        from PIL import ImageGrab

        monitors = se.get_all_monitors()
        saved = []
        for mon in monitors:
            name = mon["name"]
            bbox = (mon["left"], mon["top"], mon["right"], mon["bottom"])
            img = ImageGrab.grab(bbox=bbox, all_screens=True)
            path = BASE_DIR / "static" / f"screenshot_{key}_{name}.png"
            img.save(str(path), "PNG")
            saved.append({"monitor": name, "path": str(path)})
        return jsonify({"success": True, "count": len(saved), "screenshots": saved})
    except Exception as e:
        return jsonify({"success": False, "message": f"截取失败: {e}"})


@ide_bp.route("/api/list-screenshots")
def api_list_screenshots():
    """列出所有已保存的 IDE 截图，按 key 和 monitor 分组"""
    static_dir = BASE_DIR / "static"
    result = {}
    for f in static_dir.glob("screenshot_*.png"):
        stem = f.stem  # screenshot_{key} or screenshot_{key}_{monitor}
        parts = stem.split("_", 1)
        if len(parts) < 2:
            continue
        rest = parts[1]
        # 尝试匹配 screenshot_{key}_{monitor}.png
        # monitor 名称格式: primary, ext_1920_0 等
        found = False
        for mon_prefix in ("primary", "ext_"):
            idx = rest.find(mon_prefix)
            if idx > 0:
                ide_key = rest[:idx].rstrip("_")
                monitor = rest[idx:]
                result.setdefault(ide_key, []).append(monitor)
                found = True
                break
        if not found:
            result.setdefault(rest, []).append("_default")
    return jsonify({"success": True, "screenshots": result})


@ide_bp.route("/api/calibrate", methods=["POST"])
def api_calibrate():
    """校准截图：截取 IDE 客户区，返回 base64 图片 + 窗口信息"""
    data = request.json or {}
    key = data.get("key", "").strip().lower()
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"})
    try:
        import screenshot_engine as se
        import capture_window
        import base64
        import io

        win = se._find_target_window(key)
        monitors = se.get_all_monitors()
        monitor_info = {}
        monitor_name = "primary"
        img = None
        client_w, client_h = 0, 0

        if win:
            hwnd = win._hWnd
            # 若窗口最小化，先恢复并最大化，避免截图失败
            import ctypes as _ct
            try:
                if _ct.windll.user32.IsIconic(hwnd):
                    _ct.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    import time as _t
                    _t.sleep(0.2)
                    _ct.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
                    _t.sleep(0.5)
            except Exception:
                pass
            monitor_name = se.get_monitor_for_window(hwnd)
            monitor_info = next((m for m in monitors if m["name"] == monitor_name), monitors[0] if monitors else {})

            # 优先：WinRT 截取客户区
            img = capture_window.capture_window_winrt(hwnd, client_only=True)
            if img is None:
                img = capture_window.capture_window_client(hwnd)
            if img is not None:
                client_w, client_h = img.size

        if img is None:
            # 窗口未找到 → 截显示器
            if monitor_info:
                from PIL import ImageGrab
                img = ImageGrab.grab(bbox=(monitor_info["left"], monitor_info["top"],
                                           monitor_info["right"], monitor_info["bottom"]),
                                     all_screens=True)
            else:
                monitor_info = next((m for m in monitors if m.get("primary")), monitors[0] if monitors else {})
                from PIL import ImageGrab
                img = ImageGrab.grab(bbox=(monitor_info["left"], monitor_info["top"],
                                           monitor_info["right"], monitor_info["bottom"]),
                                     all_screens=True)
            client_w, client_h = img.size if img else (0, 0)

        # 缩放
        max_w = 1920
        if img.width > max_w:
            from PIL import Image
            ratio = max_w / img.width
            img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        b64 = base64.b64encode(buf.getvalue()).decode()

        crop = se.get_crop_config(key, monitor_name) if win else {
            "left": 0, "right": 0, "top": 0, "bottom": 0,
            "dialog_position": "center", "calib_width": 0, "calib_height": 0,
            "focus_input_enabled": False, "input_region": None,
        }

        return jsonify({
            "success": True,
            "image": b64,
            "width": img.width,
            "height": img.height,
            "client_width": client_w,
            "client_height": client_h,
            "monitor": monitor_info,
            "monitor_name": monitor_name,
            "all_monitors": [m["name"] for m in monitors],
            "crop": crop,
            "window": {"left": win.left, "top": win.top, "width": win.width, "height": win.height} if win else {},
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"校准失败: {e}"})


@ide_bp.route("/api/calibrate-maximize", methods=["POST"])
def api_calibrate_maximize():
    """将 IDE 窗口移动到指定显示器并最大化后截图，用于校准流程。

    请求体:
        key: IDE 标识
        monitor_name: (可选) 目标显示器名称，如 "primary" 或 "ext_2880_0"。
                      不传则用窗口当前所在显示器。
    返回与 /api/calibrate 相同的结构，额外包含 all_monitors 列表。
    """
    data = request.json or {}
    key = data.get("key", "").strip().lower()
    monitor_name_req = (data.get("monitor_name") or "").strip()
    prepare_only = bool(data.get("prepare_only", False))
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"})
    try:
        import screenshot_engine as se
        import capture_window
        import base64
        import io
        import ctypes
        import time

        win = se._find_target_window(key)
        # 首次校准可能尚未有持久化绑定：使用窗口候选推荐自动建立绑定，
        # 否则手机端切换显示器时只能无声失败。
        if not win:
            try:
                from window_binding import list_window_candidates, recommend_candidate, bind_window_by_hwnd
                candidates = list_window_candidates()
                recommendation = recommend_candidate(key, candidates)
                if recommendation and recommendation.get("hwnd"):
                    bind_window_by_hwnd(key, int(recommendation["hwnd"]))
                    win = se._find_target_window(key)
            except Exception:
                pass
        if not win:
            return jsonify({"success": False, "message": "找不到 IDE 窗口，请先打开该 IDE 并绑定窗口"})

        hwnd = win._hWnd
        monitors = se.get_all_monitors()
        all_monitor_names = [m["name"] for m in monitors]

        # 确定目标显示器
        if monitor_name_req:
            target_mon = next((m for m in monitors if m["name"] == monitor_name_req), None)
            if not target_mon:
                return jsonify({"success": False, "message": f"找不到显示器 {monitor_name_req}，可用: {all_monitor_names}"})
        else:
            current = se.get_monitor_for_window(hwnd)
            target_mon = next((m for m in monitors if m["name"] == current), monitors[0] if monitors else None)

        if not target_mon:
            return jsonify({"success": False, "message": "无法确定目标显示器"})

        # 1. 先恢复窗口(避免最大化状态影响移动)
        try:
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            time.sleep(0.2)
        except Exception:
            pass

        # 2. 移动窗口到目标显示器，先放到左上角带尺寸
        mx, my = target_mon["left"], target_mon["top"]
        mw, mh = target_mon["width"], target_mon["height"]
        try:
            # 用 SWP_NOZORDER | SWP_SHOWWINDOW
            ctypes.windll.user32.SetWindowPos(hwnd, 0, mx, my, mw, mh, 0x0040 | 0x0004)
            time.sleep(0.2)
        except Exception:
            pass

        # 3. 最大化
        try:
            ctypes.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
            time.sleep(0.8)  # 等待窗口最大化动画 + DWM 合成稳定
        except Exception:
            pass

        # 4. 重新查找窗口（移动/最大化可能使旧 hwnd 失效），然后截图
        win2 = se._find_target_window(key)
        hwnd2 = win2._hWnd if win2 else hwnd
        if prepare_only:
            prepared_monitor = se.get_monitor_for_window(hwnd2)
            return jsonify({
                "success": True,
                "prepared": True,
                "monitor_name": prepared_monitor,
                "monitor": target_mon,
                "window": {"left": win2.left, "top": win2.top, "width": win2.width, "height": win2.height} if win2 else {},
            })
        img = capture_window.capture_window_winrt(hwnd2, client_only=True)
        if img is None:
            img = capture_window.capture_window_client(hwnd2)
        if img is None:
            # 回退：截取目标显示器整个区域（窗口已最大化，应覆盖整个显示器）
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=(target_mon["left"], target_mon["top"],
                                       target_mon["right"], target_mon["bottom"]),
                                 all_screens=True)
        if img is None:
            return jsonify({"success": False, "message": "截图失败"})
        client_w, client_h = img.size

        # 缩放
        max_w = 1920
        if img.width > max_w:
            from PIL import Image
            ratio = max_w / img.width
            img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        b64 = base64.b64encode(buf.getvalue()).decode()

        monitor_name = se.get_monitor_for_window(hwnd)
        crop = se.get_crop_config(key, monitor_name)

        return jsonify({
            "success": True,
            "image": b64,
            "width": img.width,
            "height": img.height,
            "client_width": client_w,
            "client_height": client_h,
            "monitor": target_mon,
            "monitor_name": monitor_name,
            "all_monitors": all_monitor_names,
            "crop": crop,
            "window": {"left": win.left, "top": win.top, "width": win.width, "height": win.height},
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"最大化校准失败: {e}"})


@ide_bp.route("/api/save-calibration", methods=["POST"])
def api_save_calibration():
    """保存校准裁剪配置"""
    data = request.json or {}
    key = data.get("key", "").strip().lower()
    monitor_name = data.get("monitor", "").strip()
    left = int(data.get("left", 0))
    right = int(data.get("right", 0))
    top = int(data.get("top", 0))
    bottom = int(data.get("bottom", 0))
    dialog_position = data.get("dialog_position")
    calib_w = data.get("calib_width")
    calib_h = data.get("calib_height")
    focus_input_enabled = data.get("focus_input_enabled")
    input_region = data.get("input_region")
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"})
    if focus_input_enabled is not None and not isinstance(focus_input_enabled, bool):
        return jsonify({"success": False, "message": "聚焦输入框开关格式无效"}), 400
    try:
        import screenshot_engine as se
        result = se.set_crop_config(key, left, right, top, bottom, monitor_name or "primary",
                                     dialog_position=dialog_position,
                                     calib_width=calib_w,
                                     calib_height=calib_h,
                                     focus_input_enabled=focus_input_enabled,
                                     input_region=input_region)
        pos_label = {"right": "靠右", "left": "靠左", "center": "居中"}.get(dialog_position, "居中")
        focus_label = "，派发前聚焦已开启" if result.get("focus_input_enabled") else ""
        return jsonify({"success": True, "message": f"已保存 {key} 校准 ({pos_label}{focus_label})"})
    except Exception as e:
        return jsonify({"success": False, "message": f"保存失败: {e}"})


@ide_bp.route("/api/ide/toggle-test-role", methods=["POST"])
def api_toggle_ide_test_role():
    """切换 IDE 是否可接受测试任务角色"""
    data = request.json or {}
    key = data.get("key", "").strip().lower()
    enabled = bool(data.get("enabled", False))
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"}), 400

    import ide_scanner
    roles = ide_scanner.load_ide_roles()
    if key not in roles:
        roles[key] = {}
    roles[key]["accept_test_tasks"] = enabled
    if ide_scanner.save_ide_roles(roles):
        return jsonify({"success": True, "message": f"已将 {key} 的测试任务角色设置为 {enabled}"})
    return jsonify({"success": False, "message": "保存配置失败"}), 500


@ide_bp.route("/api/ide/set-primary-role", methods=["POST"])
def api_set_ide_primary_role():
    """设置或取消唯一主 IDE。"""
    data = request.json or {}
    key = data.get("key", "").strip().lower()
    enabled = bool(data.get("enabled", False))
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"}), 400

    import ide_scanner
    desktop_keys = {
        item.get("key")
        for item in ide_scanner.get_all_ides()
        if item.get("type", "desktop") != "web"
    }
    if key not in desktop_keys:
        return jsonify({"success": False, "message": f"未知的桌面 IDE: {key}"}), 404

    if ide_scanner.set_primary_ide(key, enabled):
        message = f"已将 {key} 设为主 IDE" if enabled else f"已取消 {key} 的主 IDE"
        return jsonify({"success": True, "message": message, "primary_ide": key if enabled else ""})
    return jsonify({"success": False, "message": "保存配置失败"}), 500


# ============================================================
# IDE Start/Stop/Ports/Processes
# ============================================================

def _is_ide_running_local(ide, ide_info=None):
    from dispatch_utils import get_ide_running_statuses, is_ide_running
    if ide_info is not None:
        return get_ide_running_statuses([ide_info]).get(ide, False)
    return is_ide_running(ide)

def _is_port_in_use_local(port):
    from dispatch_utils import is_port_in_use
    return is_port_in_use(port)

def _load_settings_local():
    from config import load_settings
    return load_settings()


@ide_bp.route('/ide/<ide>/start', methods=['POST'])
def start_ide_server(ide):
    ide = ide.strip().lower()
    import ide_scanner
    all_ides = ide_scanner.get_all_ides()
    ide_info = next((i for i in all_ides if i["key"] == ide), None)

    # The scanned cache can be stale when a packaged app was updated while it
    # was closed. Refresh once before declaring a configured IDE unknown.
    if not ide_info:
        refreshed = ide_scanner.scan_installed_ides()
        ide_info = next((i for i in refreshed if i.get("key") == ide), None)

    from ide_profiles import load_profile
    profile = load_profile(ide)
    registry_config = ide_scanner.load_registry().get(ide, {})
    profile_aumid = str(profile.get("launch", {}).get("aumid") or "")

    # ChatGPT is an MSIX app. WindowsApps may not be enumerable while the app
    # is fully stopped, but its stable AppUserModelId can still launch it.
    if not ide_info and profile_aumid:
        ide_info = {
            "key": ide,
            "name": registry_config.get("name", profile.get("display_name", ide)),
            "path": "",
            "type": "desktop",
        }

    if not ide_info:
        return jsonify({"ok": False, "error": f"未知的 IDE: {ide}"}), 400

    ide_path = ide_info.get("path", "")
    if not ide_path and not profile_aumid:
        return jsonify({"ok": False, "error": f"未找到 {ide} 的安装路径"}), 400
    
    already_running = _is_ide_running_local(ide, ide_info)
    if already_running:
        try:
            import screenshot_engine as se
            se._activate_target_window(ide, focus_input=False)
        except Exception:
            pass
        return jsonify({"ok": True, "message": f"{ide_info['name']} 已在运行，已尝试激活窗口"})
    
    if ide in ("mimo", "oc"):
        try:
            exe_filename = os.path.basename(ide_path).lower() if ide_path else ""
            for proc in psutil.process_iter(['name', 'exe', 'cmdline']):
                try:
                    proc_info = proc.info
                    proc_name = (proc_info.get('name') or '').lower()
                    proc_exe = (proc_info.get('exe') or '').lower()
                    cmdline = " ".join(proc_info.get("cmdline") or []).lower()
                    if ide == "oc" and "serve" in cmdline:
                        continue
                    if (exe_filename and exe_filename in proc_exe) or (ide != "oc" and ide in proc_name):
                        proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            print(f"[WARN] Failed to clean up residual processes: {e}")
            
    try:
        if ide == "mimo":
            subprocess.Popen(
                ["cmd.exe", "/c", "start", "pwsh.exe", "-NoExit", "-Command", f'& "{ide_path}"']
            )
        else:
            from ide_profiles import launch_ide
            launched_target = launch_ide(profile, ide_info)
            logger.info("启动 IDE %s: %s", ide, launched_target)
        
        for _ in range(20):
            time.sleep(0.5)
            if _is_ide_running_local(ide, ide_info):
                if ide == "codex":
                    try:
                        ide_scanner.scan_installed_ides()
                    except Exception:
                        pass
                return jsonify({"ok": True, "message": f"{ide_info['name']} 启动成功"})
        
        return jsonify({"ok": False, "error": f"{ide_info['name']} 启动超时"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": f"启动失败: {e}"}), 500


@ide_bp.route('/ide/<ide>/open-project', methods=['POST'])
def open_ide_project(ide):
    ide = ide.strip().lower()
    data = request.get_json(silent=True) or {}
    requested_path = str(data.get("path") or "").strip()
    if not requested_path:
        return jsonify({"ok": False, "error": "缺少目标项目路径"}), 400

    import ide_scanner
    all_ides = ide_scanner.get_all_ides()
    ide_info = next((item for item in all_ides if item.get("key") == ide), None)
    if not ide_info and ide == "codex":
        refreshed = ide_scanner.scan_installed_ides()
        ide_info = next((item for item in refreshed if item.get("key") == ide), None)

    from config import load_settings, normalize_project_path, project_path_key
    normalized_requested = normalize_project_path(requested_path)
    settings = load_settings()
    configured_paths = [
        normalize_project_path(item.get("path", ""))
        for item in settings.get("projects", [])
        if isinstance(item, dict)
    ]
    current_path = normalize_project_path(settings.get("current_project", ""))
    if current_path:
        configured_paths.append(current_path)
    project_path = next(
        (path for path in configured_paths if project_path_key(path) == project_path_key(normalized_requested)),
        "",
    )
    if not project_path or not os.path.isdir(project_path):
        return jsonify({"ok": False, "error": "目标项目未在 AideLink 项目列表中或路径不存在"}), 400

    from ide_profiles import load_profile, open_project
    profile = load_profile(ide)
    if "open_project" not in profile.get("capabilities", []):
        return jsonify({"ok": False, "error": f"{ide} 当前适配配置不支持切换项目"}), 409

    if not ide_info:
        profile_aumid = str(profile.get("launch", {}).get("aumid") or "")
        if not profile_aumid:
            return jsonify({"ok": False, "error": f"未找到 {ide} 的安装信息"}), 404
        ide_info = {"key": ide, "name": profile.get("display_name", ide), "path": ""}

    try:
        target = open_project(profile, ide_info, project_path)
        from ide_project_bindings import save_binding
        save_binding(ide, project_path)
        logger.info("IDE %s 切换项目: %s", ide, target)
        return jsonify({
            "ok": True,
            "message": f"已请求 {ide_info.get('name', ide)} 打开目标项目 {project_path}",
            "project": project_path,
            "profile_version": profile.get("version", ""),
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"切换项目失败: {exc}"}), 500


@ide_bp.route('/ide/<ide>/sessions', methods=['GET'])
def get_ide_sessions(ide):
    try:
        from ide_profiles import list_history, load_profile
        profile = load_profile(ide)
        if "history" not in profile.get("capabilities", []):
            return jsonify({"ok": False, "error": f"{ide} 当前适配配置不支持历史会话"}), 409
        limit = request.args.get("limit", 30, type=int)
        return jsonify({"ok": True, "sessions": list_history(profile, limit=limit)})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"读取历史会话失败: {exc}"}), 500


@ide_bp.route('/ide/<ide>/sessions/<thread_id>/open', methods=['POST'])
def open_ide_session(ide, thread_id):
    try:
        from ide_profiles import load_profile, open_history
        profile = load_profile(ide)
        if "history" not in profile.get("capabilities", []):
            return jsonify({"ok": False, "error": f"{ide} 当前适配配置不支持历史会话"}), 409
        target = open_history(profile, thread_id)
        return jsonify({"ok": True, "message": "已请求 IDE 打开历史会话", "target": target})
    except Exception as exc:
        return jsonify({"ok": False, "error": f"打开历史会话失败: {exc}"}), 500


@ide_bp.route('/ide/ports', methods=['GET'])
def get_ide_ports():
    return jsonify({
        "ports": {
            "opencode": 4096,
            "mimo": 4097,
            "mimocode": 4097,
            "happy": 3005,
        }
    })


@ide_bp.route('/ide/<ide>/stop', methods=['POST'])
def stop_ide_server(ide):
    ide = ide.strip().lower()
    
    import ide_scanner
    all_ides = ide_scanner.get_all_ides()
    ide_info = next((i for i in all_ides if i["key"] == ide), None)
    
    if not ide_info:
        return jsonify({"ok": False, "error": f"未知的 IDE: {ide}"}), 400
    
    ide_name = ide_info.get("name", ide)
    
    closed_count = 0
    try:
        exe_filename = os.path.basename(ide_info.get("path", "")).lower() if ide_info.get("path") else ""
        main_pids = []
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
            try:
                proc_info = proc.info
                proc_name = (proc_info.get('name') or '').lower()
                proc_exe = (proc_info.get('exe') or '').lower()
                cmdline = " ".join(proc_info.get("cmdline") or []).lower()
                if ide == "oc" and "serve" in cmdline:
                    continue
                # Electron IDE 有大量 renderer/utility 子进程，只定位主窗口所属进程。
                is_electron_child = " --type=" in f" {cmdline}"
                proc_exe_filename = os.path.basename(proc_exe)
                matches_exe = bool(exe_filename and proc_exe_filename == exe_filename and not is_electron_child)
                matches_name = ide != "oc" and not is_electron_child and (ide_name.lower() in proc_name or ide in proc_name)
                if matches_exe or matches_name:
                    main_pids.append(proc.pid)
            except Exception:
                continue

        # 不使用 taskkill /F：WM_CLOSE 会让 IDE 自己保存并退出。若目标
        # 进程完整性更高，则只把固定的 close 操作交给管理员 helper。
        if main_pids:
            from ide_process_control import close_windows_for_pids
            from windows_privilege import process_requires_elevation, run_elevated
            elevated_pids = [pid for pid in main_pids if process_requires_elevation(pid)]
            normal_pids = [pid for pid in main_pids if pid not in elevated_pids]
            closed_count += close_windows_for_pids(normal_pids)
            if elevated_pids:
                helper = os.path.join(BASE_DIR, "ide_process_control.py")
                result = run_elevated(
                    sys.executable,
                    [helper, "close", *[str(pid) for pid in elevated_pids]],
                    BASE_DIR,
                    timeout_ms=15_000,
                )
                if result == 0:
                    closed_count += len(elevated_pids)
                else:
                    return jsonify({
                        "ok": False,
                        "error": f"{ide_name} 以管理员身份运行，但提权关闭操作失败（exit={result}）",
                    }), 409

        # ChatGPT Desktop keeps a tray process after its window receives
        # WM_CLOSE.  In the normal app-level close action, also exit that
        # ChatGPT process after giving the window a moment to save.  This is
        # deliberately limited to the configured ChatGPT.exe main process and
        # never uses taskkill /T, so AideLink and unrelated child processes are
        # not touched.
        if ide == "codex" and main_pids:
            time.sleep(1.0)
            for pid in main_pids:
                try:
                    proc = psutil.Process(pid)
                    if proc.is_running():
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except psutil.TimeoutExpired:
                            proc.kill()
                        closed_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        if closed_count > 0:
            return jsonify({"ok": True, "message": f"已请求 {ide_name} 保存并关闭"})
        if main_pids:
            return jsonify({"ok": True, "message": f"已请求 {ide_name} 关闭，请等待其完成保存"})
        else:
            return jsonify({"ok": True, "message": f"{ide_name} 未在运行"})
    except Exception as e:
        return jsonify({"ok": False, "error": f"强杀失败: {e}"}), 500


@ide_bp.route('/ide/processes', methods=['GET'])
def get_ide_process_status():
    import ide_scanner
    from dispatch_utils import get_ide_running_statuses

    all_ides = ide_scanner.get_all_ides()
    running_statuses = get_ide_running_statuses(all_ides)
    result = []
    
    for ide_info in all_ides:
        ide_key = ide_info["key"]
        ide_name = ide_info.get("name", ide_key)
        result.append({
            "key": ide_key,
            "name": ide_name,
            "path": ide_info.get("path", ""),
            "running": running_statuses.get(ide_key, False),
            "is_primary": bool(ide_info.get("is_primary", False)),
        })
    
    return jsonify({"ides": result})


# ============================================================
# 从 phone_chat_bridge.py 迁移的路由（Step 1.4）
# ============================================================

@ide_bp.route('/ide/<ide>/heartbeat', methods=['POST'])
def ide_heartbeat(ide):
    from shared_runtime import runtime
    from task_runtime import SUPPORTED_IDES
    ide = ide.strip().lower()
    if ide not in SUPPORTED_IDES:
        return jsonify({"ok": False, "error": "Unsupported IDE"}), 400
    data = request.json or {}
    state = runtime.heartbeat_ide(
        ide,
        status=data.get("status"),
        current_task_id=data.get("current_task_id"),
        error=data.get("error"),
    )
    return jsonify({"ok": True, "status": state})


@ide_bp.route('/ide/<ide>/release', methods=['POST'])
def ide_release(ide):
    from shared_runtime import runtime
    from task_runtime import SUPPORTED_IDES
    ide = ide.strip().lower()
    if ide not in SUPPORTED_IDES:
        return jsonify({"ok": False, "error": "Unsupported IDE"}), 400
    data = request.json or {}
    task_id = data.get("task_id")
    if task_id:
        runtime.release_leases(task_id)
    state = runtime.release_ide(ide, error=data.get("error"))
    # IDE 释放后自动派发队列中的下一个任务
    threading.Thread(
        target=runtime._try_dispatch_next_queued,
        args=(ide,),
        daemon=True,
    ).start()
    return jsonify({"ok": True, "status": state})


@ide_bp.route("/api/ide/install-mcp", methods=["POST"])
def api_ide_install_mcp():
    """一键为指定 IDE 注入 AideLink MCP 配置"""
    data = request.json or {}
    key = data.get("key", "").strip().lower()
    if not key:
        return jsonify({"success": False, "message": "缺少 IDE 标识符"}), 400

    mcp_script_path = str(BASE_DIR / "mcp_server.py").replace("\\", "/")
    success = False
    message = ""
    try:
        import json as _json

        def _inject_mcp_json(user_dir):
            """向 VSCode 内核 IDE 的 User/mcp.json 合并写入 aidelink MCP 配置。

            遵循 Trae 官方格式：顶层 mcpServers，每个 server 仅 command/args/env。
            保留已有的其他 MCP server 配置，仅新增/更新 aidelink。
            """
            mcp_file = Path(user_dir) / "User" / "mcp.json"
            try:
                if mcp_file.exists():
                    with open(mcp_file, "r", encoding="utf-8") as f:
                        mcp_data = _json.load(f)
                else:
                    mcp_data = {}
                if not isinstance(mcp_data.get("mcpServers"), dict):
                    mcp_data["mcpServers"] = {}
                mcp_data["mcpServers"]["aidelink"] = {
                    "command": "python",
                    "args": [mcp_script_path],
                }
                mcp_file.parent.mkdir(parents=True, exist_ok=True)
                with open(mcp_file, "w", encoding="utf-8") as f:
                    _json.dump(mcp_data, f, ensure_ascii=False, indent=2)
                return True
            except Exception as e:
                logger.error(f"Failed to write mcp.json at {mcp_file}: {e}")
                return False

        def _cleanup_storage_mcp(storage_path):
            """清理旧版本误写入 storage.json 顶层 mcp 键的错误配置。"""
            try:
                p = Path(storage_path)
                if not p.exists():
                    return
                with open(p, "r", encoding="utf-8") as f:
                    sdata = _json.load(f)
                if "mcp" in sdata:
                    del sdata["mcp"]
                    with open(p, "w", encoding="utf-8") as f:
                        _json.dump(sdata, f, ensure_ascii=False, indent=4)
            except Exception:
                pass

        if key in ("trae", "trae_cn", "trae_solo", "trae_solo_cn"):
            appdata_names = ["TRAE SOLO"] if key in {"trae", "trae_solo"} else ["TRAE SOLO CN"]
            appdata = os.environ.get("APPDATA", "")
            injected = 0
            for dn in appdata_names:
                user_dir = Path(appdata) / dn
                if user_dir.exists() and _inject_mcp_json(user_dir):
                    # 清理旧版本误写入 storage.json 的 mcp 键
                    _cleanup_storage_mcp(user_dir / "User" / "globalStorage" / "storage.json")
                    injected += 1
            if injected > 0:
                success, message = True, f"已将 MCP 配置写入 {injected} 个 Trae 实例的 mcp.json（重启 Trae 后生效）"
            else:
                message = "未找到已初始化的 Trae 配置目录"

        elif key in ("claude", "claude-code", "claude_code"):
            p = Path(os.path.expanduser("~")) / ".claude" / "mcp.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                _json.dump({"mcpServers": {"aidelink": {"command": "python", "args": [mcp_script_path]}}}, f, ensure_ascii=False, indent=2)
            success, message = True, "已成功写入 Claude Code MCP 配置"

        elif key in ("codex", "openai-codex", "openaicodex"):
            p = Path(os.path.expanduser("~")) / ".codex" / "config.toml"
            if p.exists():
                content = p.read_text(encoding="utf-8")
                if "[mcp_servers.aidelink]" not in content:
                    block = (
                        "\n[mcp_servers.aidelink]\n"
                        "command = 'python'\n"
                        f"args = ['{mcp_script_path}']\n"
                        "startup_timeout_sec = 120\n"
                    )
                    lines = content.splitlines()
                    insert_idx = next((i for i, l in enumerate(lines) if l.strip() == "[features]"), -1)
                    if insert_idx != -1:
                        lines[insert_idx:insert_idx] = block.splitlines()
                    else:
                        lines += block.splitlines()
                    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    success, message = True, "已成功将 MCP 配置注入 OpenAI Codex config.toml"
                else:
                    success, message = True, "OpenAI Codex 已配置过该 MCP"
            else:
                message = "未找到 OpenAI Codex 的 config.toml"

        elif key in ("antigravity_ide", "mimo", "minimax"):
            # VSCode 内核系 IDE：统一写入 User/mcp.json（Trae 官方格式）
            key_to_appdata_name = {
                "antigravity_ide":        ["Antigravity IDE", "Antigravity"],
                "trae_solo":  ["TRAE SOLO"],
                "mimo":       ["MiMo Code", "MiMoCode"],
                "minimax":    ["MiniMax Code"],
            }
            dir_names = key_to_appdata_name.get(key, [])
            appdata = os.environ.get("APPDATA", "")
            injected = 0
            for dn in dir_names:
                user_dir = Path(appdata) / dn
                if user_dir.exists() and _inject_mcp_json(user_dir):
                    _cleanup_storage_mcp(user_dir / "User" / "globalStorage" / "storage.json")
                    injected += 1
            if injected > 0:
                success, message = True, f"已将 MCP 配置写入 {key} 的 mcp.json（共 {injected} 个实例，重启后生效）"
            else:
                message = f"未找到 {key} 的已初始化配置目录"

        else:
            message = f"暂不支持自动配置 {key} 的 MCP，请手动配置"
    except Exception as e:
        success, message = False, f"配置 MCP 失败: {e}"

    if success:
        installed_skills = _install_aidelink_skill(key)
        if installed_skills:
            message += f"；已安装 AideLink 经理/员工技能（{installed_skills} 个目录）"

    return jsonify({"success": success, "message": message})
