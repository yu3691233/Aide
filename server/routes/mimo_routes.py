import os
import sys
import time
import subprocess
from pathlib import Path
from types import SimpleNamespace

import requests
from flask import Blueprint, request, jsonify

mimo_bp = Blueprint('mimo', __name__)

_server_dir = str(Path(__file__).parent.parent)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


def _get_bridge_deps():
    from dispatch_utils import is_ide_running
    import ide_scanner
    # 使用命名空间对象避免类体作用域引用局部名时触发 NameError
    return SimpleNamespace(
        _is_ide_running=is_ide_running,
        ide_scanner=ide_scanner,
    )


def _get_config_deps():
    from config import load_settings, save_settings
    return load_settings, save_settings


def _get_paths():
    from paths import BRIDGE_DIR
    return BRIDGE_DIR


@mimo_bp.route('/xiaomengling/mimo/status')
def xiaomengling_mimo_status():
    bridge = _get_bridge_deps()
    mimo_running = bridge._is_ide_running("mimo")
    mimo_pid = None
    if mimo_running:
        try:
            import psutil
            all_ides = bridge.ide_scanner.get_all_ides()
            ide_info = next((i for i in all_ides if i["key"] == "mimo"), None)
            if ide_info:
                ide_path = ide_info.get("path", "")
                exe_filename = os.path.basename(ide_path).lower() if ide_path else "mimo.exe"
                for proc in psutil.process_iter(attrs=["pid", "name"]):
                    try:
                        if proc.info.get("name", "").lower() == exe_filename:
                            mimo_pid = proc.info["pid"]
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
        except Exception:
            pass
    return jsonify({
        "ok": True,
        "running": mimo_running,
        "pid": mimo_pid,
        "port": 0,
    })


@mimo_bp.route('/xiaomengling/mimo/start', methods=['POST'])
def xiaomengling_mimo_start():
    bridge = _get_bridge_deps()
    if bridge._is_ide_running("mimo"):
        return jsonify({"ok": True, "message": "MiMoCode 已在运行"})

    all_ides = bridge.ide_scanner.get_all_ides()
    ide_info = next((i for i in all_ides if i["key"] == "mimo"), None)
    if not ide_info:
        return jsonify({"ok": False, "message": "未找到 mimo 的安装路径"}), 400

    ide_path = ide_info.get("path", "")
    if not ide_path:
        return jsonify({"ok": False, "message": "未找到 mimo 的安装路径"}), 400

    try:
        import psutil
        exe_filename = os.path.basename(ide_path).lower() if ide_path else "mimo.exe"
        for proc in psutil.process_iter(['name', 'exe']):
            try:
                proc_info = proc.info
                proc_name = (proc_info.get('name') or '').lower()
                proc_exe = (proc_info.get('exe') or '').lower()
                if (exe_filename and exe_filename in proc_exe) or ("mimo" in proc_name):
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception as e:
        print(f"[WARN] Failed to clean up residual processes: {e}")

    try:
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "pwsh.exe", "-NoExit", "-Command", f'& "{ide_path}"']
        )

        for _ in range(10):
            time.sleep(0.5)
            if bridge._is_ide_running("mimo"):
                return jsonify({"ok": True, "message": "MiMoCode 已启动"})

        return jsonify({"ok": False, "message": "MiMoCode 启动超时"})
    except Exception as e:
        return jsonify({"ok": False, "message": f"启动失败: {e}"})


@mimo_bp.route('/xiaomengling/mimo/stop', methods=['POST'])
def xiaomengling_mimo_stop():
    bridge = _get_bridge_deps()
    all_ides = bridge.ide_scanner.get_all_ides()
    ide_info = next((i for i in all_ides if i["key"] == "mimo"), None)
    ide_path = ide_info.get("path", "") if ide_info else ""
    exe_filename = os.path.basename(ide_path).lower() if ide_path else "mimo.exe"

    try:
        import psutil
        stopped = False
        for proc in psutil.process_iter(attrs=["pid", "name", "exe"]):
            try:
                proc_info = proc.info
                proc_name = (proc_info.get('name') or '').lower()
                proc_exe = (proc_info.get('exe') or '').lower()
                if (exe_filename and exe_filename in proc_exe) or ("mimo" in proc_name):
                    proc.terminate()
                    proc.wait(timeout=5)
                    stopped = True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                try:
                    proc.kill()
                    stopped = True
                except Exception:
                    pass
        if stopped:
            return jsonify({"ok": True, "message": "MiMoCode 已停止"})
        else:
            return jsonify({"ok": False, "message": "未找到运行中的 MiMoCode 进程"})
    except Exception as e:
        return jsonify({"ok": False, "message": f"停止失败: {e}"})


@mimo_bp.route('/xiaomengling/models')
def xiaomengling_models():
    _load_settings, _ = _get_config_deps()
    oc_port = 4096
    try:
        resp = requests.get(f"http://127.0.0.1:{oc_port}/provider", timeout=5)
        if resp.status_code != 200:
            return jsonify({"ok": False, "models": [], "message": "OpenCode 不可达"})

        data = resp.json()
        providers = data.get("all", [])
        defaults = data.get("default", {})
        models = []
        for provider in providers:
            provider_id = provider.get("id", "")
            provider_name = provider.get("name", "")
            provider_models = provider.get("models", {})
            default_model = defaults.get(provider_id, "")
            for model_id, model_info in provider_models.items():
                models.append({
                    "id": model_id,
                    "name": model_info.get("name", model_id),
                    "provider": provider_name,
                    "providerId": provider_id,
                    "isDefault": model_id == default_model,
                    "status": model_info.get("status", "unknown"),
                    "cost": model_info.get("cost", {}),
                    "capabilities": model_info.get("capabilities", {}),
                })
        settings = _load_settings()
        current_model = settings.get("xiaomengling_model", "")
        current_provider = settings.get("xiaomengling_provider", "")
        return jsonify({"ok": True, "models": models, "current_model": current_model, "current_provider": current_provider})
    except Exception as e:
        return jsonify({"ok": False, "models": [], "message": f"获取模型列表失败: {e}"})


@mimo_bp.route('/xiaomengling/models/set', methods=['POST'])
def xiaomengling_models_set():
    _load_settings, _save_settings = _get_config_deps()
    data = request.get_json(force=True)
    model_id = data.get("model_id")
    provider_id = data.get("provider_id", "")
    if not model_id:
        return jsonify({"ok": False, "message": "缺少 model_id"})

    settings = _load_settings()
    settings["xiaomengling_model"] = model_id
    if provider_id:
        settings["xiaomengling_provider"] = provider_id
    _save_settings(settings)

    return jsonify({"ok": True, "message": f"已设置模型: {model_id} (provider: {provider_id})"})


@mimo_bp.route('/xiaomengling/mimo/weburl')
def xiaomengling_mimo_weburl():
    BRIDGE_DIR = _get_paths()
    import base64
    oc_port = 4096
    try:
        sessions_resp = requests.get(f"http://127.0.0.1:{oc_port}/session", timeout=5, headers={"x-opencode-directory": str(BRIDGE_DIR)})
        if sessions_resp.status_code != 200:
            return jsonify({"ok": False, "url": "", "message": "OpenCode 不可达"})

        xml_session_id = None
        for s in sessions_resp.json():
            title = s.get("title", "")
            if "Aide" in title or "小梦灵" in title or "xiaomengling" in title.lower() or "aide" in title.lower():
                xml_session_id = s["id"]
                break

        if not xml_session_id:
            return jsonify({"ok": False, "url": "", "message": "未找到 Aide 会话"})

        project_b64 = base64.b64encode(str(BRIDGE_DIR).encode()).decode().rstrip("=")
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            lan_ip = s.getsockname()[0]
            s.close()
        except Exception:
            lan_ip = request.host.split(":")[0] if request.host else "127.0.0.1"
        url = f"http://{lan_ip}:{oc_port}/{project_b64}/session/{xml_session_id}"
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        return jsonify({"ok": False, "url": "", "message": f"获取失败: {e}"})


@mimo_bp.route('/xiaomengling/session/new', methods=['POST'])
def xiaomengling_session_new():
    BRIDGE_DIR = _get_paths()
    import base64
    oc_port = 4096
    try:
        create_resp = requests.post(
            f"http://127.0.0.1:{oc_port}/session",
            json={"title": "Aide"},
            headers={"x-opencode-directory": str(BRIDGE_DIR)},
            timeout=10,
        )
        if create_resp.status_code not in (200, 201):
            return jsonify({"ok": False, "session_id": "", "message": f"创建失败: HTTP {create_resp.status_code}"})

        new_session = create_resp.json()
        session_id = new_session.get("id", "")
        if not session_id:
            return jsonify({"ok": False, "session_id": "", "message": "创建失败: 无 session_id"})

        project_b64 = base64.b64encode(str(BRIDGE_DIR).encode()).decode().rstrip("=")
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            lan_ip = s.getsockname()[0]
            s.close()
        except Exception:
            lan_ip = request.host.split(":")[0] if request.host else "127.0.0.1"
        url = f"http://{lan_ip}:{oc_port}/{project_b64}/session/{session_id}"
        return jsonify({"ok": True, "session_id": session_id, "url": url})
    except Exception as e:
        return jsonify({"ok": False, "session_id": "", "message": f"创建失败: {e}"})
