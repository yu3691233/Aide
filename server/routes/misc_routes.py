import sys
from pathlib import Path
_server_dir = str(Path(__file__).parent.parent)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from flask import Blueprint, request, jsonify, Response
import json
import time
from paths import CONFIG_FILE
from json_utils import safe_read_json, safe_write_json

misc_bp = Blueprint('misc', __name__)


def _refresh_connected_devices(remote_addr, device_ip=""):
    from connected_devices import track_ip, update_device_alias
    track_ip(remote_addr)
    if device_ip:
        update_device_alias(device_ip)


def _get_event_bus():
    from event_bus import bus
    return bus


def _get_watcher():
    from notification_watcher import get_watcher
    return get_watcher()


def _parse_event_types(raw):
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_event_types_from_args():
    raw_list = request.args.getlist("types")
    if not raw_list:
        return None
    result = []
    for raw in raw_list:
        result.extend(item.strip() for item in raw.split(",") if item.strip())
    return result if result else None


@misc_bp.route("/api/connected-devices")
def api_connected_devices():
    from connected_devices import get_connected
    conn = get_connected()
    now = time.time()
    cutoff = now - 300
    active = [ip for ip, ts in conn.items() if ts > cutoff]
    for ip in list(conn.keys()):
        if conn[ip] < cutoff:
            del conn[ip]
    return jsonify(active)


@misc_bp.route("/api/codex/quota")
def api_codex_quota():
    """返回 Codex 登账号的当前周额度。

    供手机 App 在顶栏展示。模块内部维护 5 分钟缓存，并在新完成任务≥3 个时
    提前刷新；本端点直接转发缓存结果，不阻塞请求。force=1 时强制刷新。
    """
    from codex_quota import get_current_codex_quota
    force = request.args.get("force", "0").strip() in {"1", "true", "yes"}
    # App 端没有任务执行基线概念，传空集合即可：缓存逻辑会按时间或 force 决定刷新。
    quota = get_current_codex_quota(force=force, executed_task_ids=None)
    return jsonify({"ok": True, "quota": quota})


@misc_bp.route('/events/stream')
def events_stream():
    bus = _get_event_bus()
    types = _parse_event_types_from_args()
    maxsize = max(10, min(2000, request.args.get("max_queue", type=int) or 200))
    idle_timeout = max(5, min(120, request.args.get("idle_timeout", type=int) or 20))
    client_info = {
        "remote_addr": request.remote_addr,
        "user_agent": request.headers.get("User-Agent", ""),
    }
    sub_id = bus.subscribe(filters=types, maxsize=maxsize, client_info=client_info)

    device_ip = request.headers.get("X-Device-IP", "").strip()
    remote_addr = request.remote_addr  # 在请求上下文中捕获，避免生成器中访问

    def generate():
        try:
            _refresh_connected_devices(remote_addr, device_ip)
            yield ": ping\n\n"
            while True:
                event = bus.get(sub_id, timeout=idle_timeout)
                if event is None:
                    _refresh_connected_devices(remote_addr, device_ip)
                    yield ": ping\n\n"
                    continue
                _refresh_connected_devices(remote_addr, device_ip)
                yield f"id: {event['id']}\n"
                yield f"event: {event['type']}\n"
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            pass
        finally:
            bus.unsubscribe(sub_id)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return Response(generate(), mimetype="text/event-stream", headers=headers)


@misc_bp.route('/events/recent')
def events_recent():
    bus = _get_event_bus()
    since_id = max(0, request.args.get("since_id", type=int) or 0)
    types = _parse_event_types_from_args()
    limit = max(1, min(500, request.args.get("limit", type=int) or 100))
    events = bus.recent(since_id=since_id, types=types, limit=limit)
    return jsonify({
        "ok": True,
        "events": events,
        "stats": bus.stats(),
    })


@misc_bp.route('/events/stats')
def events_stats():
    bus = _get_event_bus()
    return jsonify({"ok": True, **bus.stats()})


@misc_bp.route('/events/reset', methods=['POST'])
def events_reset():
    bus = _get_event_bus()
    bus.reset()
    return jsonify({"ok": True})


@misc_bp.route('/notifications/status')
def notifications_status():
    try:
        watcher = _get_watcher()
        if watcher:
            return jsonify({"ok": True, "status": watcher.get_status()})
        return jsonify({"ok": False, "error": "Watcher not initialized"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@misc_bp.route('/server/ips')
def server_ips():
    try:
        from network_utils import is_physical_lan
        import socket
        ips = []
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if is_physical_lan(ip) and ip not in ips:
                ips.append(ip)
        return jsonify({"ok": True, "ips": ips, "hostname": hostname})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@misc_bp.route('/notifications/aumids')
def notifications_aumids():
    try:
        watcher = _get_watcher()
        if watcher:
            return jsonify({"ok": True, "handlers": watcher.list_known_aumids()})
        return jsonify({"ok": False, "error": "Watcher not initialized"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@misc_bp.route('/notifications/aumid', methods=['POST'])
def notifications_update_aumid():
    try:
        data = request.json or {}
        aumid = data.get("aumid", "").strip()
        ide_key = data.get("ide", "").strip()
        if not aumid or not ide_key:
            return jsonify({"ok": False, "error": "Missing aumid or ide"}), 400
        watcher = _get_watcher()
        if watcher:
            watcher.update_aumid_map(aumid, ide_key)
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Watcher not initialized"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@misc_bp.route('/api/frp/status', methods=['GET'])
def api_frp_status():
    try:
        from frp_service import get_frp_status
        return jsonify({"ok": True, **get_frp_status()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@misc_bp.route('/api/frp/start', methods=['POST'])
def api_frp_start():
    try:
        from frp_service import start_frp_client, get_frp_status
        ok = start_frp_client(force=True)
        return jsonify({"ok": ok, **get_frp_status()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@misc_bp.route('/api/frp/stop', methods=['POST'])
def api_frp_stop():
    try:
        from frp_service import stop_frp_client, get_frp_status
        stop_frp_client()
        return jsonify({"ok": True, **get_frp_status()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@misc_bp.route('/api/frp/proxies', methods=['GET'])
def api_frp_get_proxies():
    try:
        cfg = safe_read_json(CONFIG_FILE, {})
        if not isinstance(cfg, dict):
            cfg = {}
        frp_cfg = cfg.get("frp", {})
        proxies = frp_cfg.get("proxies", [])
        if not proxies:
            proxies = [{
                "name": frp_cfg.get("name", "mengling-bridge"),
                "type": frp_cfg.get("type", "http"),
                "local_ip": "127.0.0.1",
                "local_port": cfg.get("flask_port", 5000),
                "custom_domains": frp_cfg.get("custom_domains", ""),
                "remote_port": frp_cfg.get("remote_port", 5000),
            }]
        return jsonify({"ok": True, "proxies": proxies})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@misc_bp.route('/api/frp/proxies', methods=['POST'])
def api_frp_add_proxy():
    try:
        data = request.json or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"ok": False, "error": "代理名称不能为空"})
        cfg = safe_read_json(CONFIG_FILE, {})
        if not isinstance(cfg, dict):
            cfg = {}
        frp_cfg = cfg.setdefault("frp", {})
        proxies = frp_cfg.get("proxies", [])
        if any(p.get("name") == name for p in proxies):
            return jsonify({"ok": False, "error": f"代理 '{name}' 已存在"})
        proxies.append({
            "name": name,
            "type": data.get("type", "tcp"),
            "local_ip": data.get("local_ip", "127.0.0.1"),
            "local_port": int(data.get("local_port", 5000)),
            "custom_domains": data.get("custom_domains", ""),
            "remote_port": int(data.get("remote_port", 5000)),
        })
        frp_cfg["proxies"] = proxies
        safe_write_json(CONFIG_FILE, cfg)
        return jsonify({"ok": True, "proxies": proxies})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@misc_bp.route('/api/frp/proxies/<name>', methods=['DELETE'])
def api_frp_delete_proxy(name):
    try:
        cfg = safe_read_json(CONFIG_FILE, {})
        if not isinstance(cfg, dict):
            cfg = {}
        frp_cfg = cfg.setdefault("frp", {})
        proxies = frp_cfg.get("proxies", [])
        new_proxies = [p for p in proxies if p.get("name") != name]
        if len(new_proxies) == len(proxies):
            return jsonify({"ok": False, "error": f"未找到代理 '{name}'"})
        frp_cfg["proxies"] = new_proxies
        safe_write_json(CONFIG_FILE, cfg)
        return jsonify({"ok": True, "proxies": new_proxies})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@misc_bp.route('/api/frp/proxies/save', methods=['POST'])
def api_frp_save_proxies():
    try:
        data = request.json or {}
        proxies = data.get("proxies", [])
        cfg = safe_read_json(CONFIG_FILE, {})
        if not isinstance(cfg, dict):
            cfg = {}
        cfg.setdefault("frp", {})["proxies"] = proxies
        safe_write_json(CONFIG_FILE, cfg)
        from frp_service import is_frp_running, stop_frp_client, start_frp_client
        was_running = is_frp_running()
        if was_running:
            stop_frp_client()
        ok = start_frp_client(force=True) if was_running else True
        return jsonify({"ok": True, "restarted": was_running, "frp_running": is_frp_running()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@misc_bp.route('/scheduler/stats')
def scheduler_stats():
    return jsonify({"status": "active", "scheduler": "free_model_scheduler"})


# ============================================================
# 从 phone_chat_bridge.py 迁移的路由（Step 1.4）
# ============================================================

@misc_bp.route('/api/debug/connected')
def debug_connected():
    import time
    import connected_devices as _cd
    now = time.time()
    return jsonify({ip: f"{now-ts:.0f}s ago" for ip, ts in _cd._connected_devices.items()})


@misc_bp.route('/debug/notify', methods=['POST'])
def debug_notify():
    """调试：直接发布 task.pending_test 事件"""
    from event_bus import bus
    bus.publish("task.pending_test", {
        "task_id": "debug-test",
        "target_ide": "mimo",
        "summary": "调试通知测试",
        "title": "🔔 调试通知",
    })
    return jsonify({"ok": True, "message": "Debug event published"})
