import os
import socket
import subprocess
import signal
from flask import Blueprint, jsonify

from paths import BRIDGE_DIR

# 合并用户 PATH 和系统 PATH，确保子进程能找到 npm 全局命令
_USER_PATH = None
def _get_user_path():
    global _USER_PATH
    if _USER_PATH is None:
        user_path = os.environ.get("PATH", "")
        try:
            user_path = subprocess.check_output(
                ["cmd", "/c", "echo", "%PATH%"],
                shell=False, timeout=5, text=True
            ).strip()
        except Exception:
            pass
        _USER_PATH = user_path
    return _USER_PATH

devspace_bp = Blueprint('devspace_mcp', __name__)

_devspace_proc = None
_frpc_sg_proc = None
SG_FRPS_HOST = os.environ.get("AIDELINK_FRPS_HOST", "")
SG_FRPS_PORT = 7000
DEVSPACE_PORT = 7676


def _find_devspace_cmd():
    possible = ["devspace", "npx"]
    for cmd in possible:
        try:
            r = subprocess.run(["where", cmd] if os.name == 'nt' else ["which", cmd],
                              capture_output=True, text=True, shell=False, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                paths = [p.strip() for p in r.stdout.strip().split("\n")]
                # Windows: prefer .cmd over extensionless shell script
                if os.name == 'nt':
                    cmd_path = next((p for p in paths if p.lower().endswith(".cmd")), paths[0])
                else:
                    cmd_path = paths[0]
                if cmd == "npx":
                    return [cmd_path, "@waishnav/devspace", "serve"]
                return [cmd_path, "serve"]
        except Exception:
            pass
    return None


def _is_port_listening(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


def _netstat_lines():
    """Return TCP netstat output without invoking a shell pipeline."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return result.stdout.splitlines()
    except Exception:
        return []


def _netstat_pids_for_port(port):
    endpoint = f":{port}"
    pids = []
    for line in _netstat_lines():
        parts = line.split()
        if len(parts) >= 5 and parts[1].endswith(endpoint) and parts[-2].upper() == "LISTENING":
            pid = parts[-1]
            if pid.isdigit() and pid not in pids:
                pids.append(pid)
    return pids


def _find_orphan_devspace():
    if _is_port_listening(DEVSPACE_PORT):
        return bool(_netstat_pids_for_port(DEVSPACE_PORT))
    return False


def _find_orphan_frpc_sg():
    if not SG_FRPS_HOST:
        return False
    try:
        target = f"{SG_FRPS_HOST}:{SG_FRPS_PORT}"
        if any(target in line for line in _netstat_lines()):
            return True
    except Exception:
        pass
    return False


@devspace_bp.route("/api/devspace/start", methods=["POST"])
def devspace_start():
    global _devspace_proc, _frpc_sg_proc

    msgs = []
    # 如果端口被占但跟踪丢失，先清理
    if _is_port_listening(DEVSPACE_PORT) and (_devspace_proc is None or _devspace_proc.poll() is not None):
        return jsonify({
            "success": False,
            "message": f"端口 {DEVSPACE_PORT} 已被其他进程占用，请关闭占用它的项目或修改 DevSpace 配置",
        }), 409

    # 1. 启动 DevSpace
    if _devspace_proc and _devspace_proc.poll() is None:
        msgs.append("DevSpace MCP 已在运行中")
    else:
        cmd = _find_devspace_cmd()
        if not cmd:
            return jsonify({"success": False, "message": "未找到 devspace 命令，请安装: npm install -g @waishnav/devspace"}), 400
        try:
            _devspace_proc = subprocess.Popen(
                cmd,
                cwd=BRIDGE_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                env={**os.environ, "PATH": _get_user_path()},
            )
            msgs.append(f"DevSpace MCP 已启动 (PID: {_devspace_proc.pid})")
        except Exception as e:
            return jsonify({"success": False, "message": f"DevSpace 启动失败: {e}"}), 500

    # 2. 启动新加坡 frpc
    frpc_cfg = os.path.join(BRIDGE_DIR, "frpc_sg.toml")
    frpc_bin = os.path.join(BRIDGE_DIR, "frpc.exe")
    if os.path.exists(frpc_bin) and os.path.exists(frpc_cfg):
        if _frpc_sg_proc is None or _frpc_sg_proc.poll() is not None:
            _frpc_sg_proc = subprocess.Popen(
                [frpc_bin, "-c", frpc_cfg],
                cwd=BRIDGE_DIR,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                env={**os.environ, "PATH": _get_user_path()},
            )
            msgs.append(f"新加坡 FRPC 已启动 (PID: {_frpc_sg_proc.pid})")
        else:
            msgs.append("新加坡 FRPC 已在运行中")

    return jsonify({"success": True, "message": " | ".join(msgs)})


@devspace_bp.route("/api/devspace/stop", methods=["POST"])
def devspace_stop():
    global _devspace_proc, _frpc_sg_proc

    if _devspace_proc and _devspace_proc.poll() is None:
        try:
            subprocess.call(["taskkill", "/F", "/T", "/PID", str(_devspace_proc.pid)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
    _devspace_proc = None

    if _frpc_sg_proc and _frpc_sg_proc.poll() is None:
        try:
            _frpc_sg_proc.terminate()
        except Exception:
            pass
    _frpc_sg_proc = None

    return jsonify({"success": True, "message": "DevSpace MCP 和新加坡 FRPC 已停止"})


@devspace_bp.route("/api/devspace/status", methods=["GET"])
def devspace_status():
    global _devspace_proc, _frpc_sg_proc

    # 侦查：端口是否在监听
    port_listening = _is_port_listening(DEVSPACE_PORT)

    # 侦查：frpc 是否与新加坡有连接
    sg_connected = _find_orphan_frpc_sg()

    # 修补进程跟踪
    if port_listening and (_devspace_proc is None or _devspace_proc.poll() is not None):
        pass
    devspace_running = (_devspace_proc is not None and _devspace_proc.poll() is None) or port_listening
    frpc_running = (_frpc_sg_proc is not None and _frpc_sg_proc.poll() is None) or sg_connected

    return jsonify({
        "devspace": {"running": devspace_running, "pid": _devspace_proc.pid if devspace_running and _devspace_proc else None},
        "frpc_sg": {"running": frpc_running, "pid": _frpc_sg_proc.pid if frpc_running and _frpc_sg_proc else None},
    })
