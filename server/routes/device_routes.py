import sys
from pathlib import Path
_server_dir = str(Path(__file__).parent.parent)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from flask import Blueprint, request, jsonify
import subprocess
import re
import os
import uuid

from paths import BRIDGE_DIR, APK_PATH
from device_manager import (
    load_device_aliases as _load_device_aliases,
    save_device_aliases as _save_device_aliases,
    get_device_info as _get_device_info,
    get_active_adb_device as _get_active_adb_device,
    get_device_serial,
    find_alias_by_serial,
    find_alias_by_ip,
    resolve_alias_for_device,
    update_alias_connection,
    add_alias_ip,
)
from network_utils import ADB_PATH
from connected_devices import get_connected, get_active_ips
from android_project import resolve_project_apk
from config import load_settings as _load_settings, normalize_project_path, project_path_key

device_bp = Blueprint('device', __name__)

import time as _time
from event_bus import bus

_wireless_result_pending = {}
_wireless_result_by_request = {}


def _run_adb(args, timeout=5):
    _flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    return subprocess.run(
        [ADB_PATH] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_flags,
    )


def _adb_devices():
    devices = {}
    try:
        res = _run_adb(["devices"], timeout=3)
        if res.returncode == 0:
            for line in res.stdout.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 2:
                    devices[parts[0]] = parts[1]
    except Exception:
        pass
    return devices


def _connected_adb_device_for(ip=None, port=None):
    devices = _adb_devices()
    if not ip:
        for device_id, state in devices.items():
            if state == "device":
                return device_id
        return None

    expected = f"{ip}:{port}" if port else None
    for device_id, state in devices.items():
        if state != "device":
            continue
        if expected and device_id == expected:
            return device_id
        if device_id == ip or device_id.startswith(f"{ip}:"):
            return device_id
    return None


def _connect_adb(ip, port, timeout=5):
    if not ip or not port:
        return None, ""
    device_id = f"{ip}:{port}"
    try:
        res = _run_adb(["connect", device_id], timeout=timeout)
        output = "\n".join(x for x in [res.stdout.strip(), res.stderr.strip()] if x)
        text = output.lower()
        if "connected" in text or "already connected" in text:
            try:
                _run_adb(["-s", device_id, "wait-for-device"], timeout=10)
            except Exception:
                pass
            connected = _connected_adb_device_for(ip, port) or device_id
            try:
                _run_adb(["-s", connected, "shell", "pm", "grant", "cc.aidelink.app", "android.permission.WRITE_SECURE_SETTINGS"], timeout=3)
            except Exception:
                pass
            return connected, output
        return None, output
    except Exception as e:
        return None, str(e)


def _remember_alias_connection(alias, device_id, ip, port):
    if not alias or not ip:
        return
    serial = None
    model = None
    brand = None
    try:
        info = _get_device_info(device_id)
        serial = info.get("serial")
        model = info.get("model")
        brand = info.get("brand")
    except Exception:
        pass
    try:
        update_alias_connection(alias, ip, port, serial=serial, model=model, brand=brand)
    except Exception:
        add_alias_ip(alias, ip, port)


def _active_ips_sorted():
    now = _time.time()
    conn = _get_connected_devices()
    return [
        ip for ip, ts in sorted(conn.items(), key=lambda item: item[1], reverse=True)
        if ip and ts > now - 300
    ]


def _resolve_adb_candidates(alias=None, ip=None, port=None):
    aliases = _load_device_aliases()
    candidates = []
    resolved_alias = alias
    default_port = port or 5555

    def add(candidate_ip, candidate_port=None):
        if candidate_ip and candidate_ip not in [item["ip"] for item in candidates]:
            candidates.append({"ip": candidate_ip, "port": candidate_port or default_port})

    if ip:
        add(ip, port)
        if not resolved_alias:
            resolved_alias = find_alias_by_ip(aliases, ip)

    if alias and alias in aliases:
        entry = aliases[alias]
        default_port = port or entry.get("port", 5555)
        known_ips = list(dict.fromkeys([entry.get("ip", "")] + (entry.get("ips") or [])))
        active = set(_active_ips_sorted())
        for candidate_ip in known_ips:
            if candidate_ip in active:
                add(candidate_ip, default_port)
        for candidate_ip in known_ips:
            add(candidate_ip, default_port)

    if not candidates:
        for active_ip in _active_ips_sorted():
            add(active_ip, default_port)

    return resolved_alias, candidates


def _publish_wireless_request(ip, alias=None):
    request_id = uuid.uuid4().hex
    payload = {
        "command": "enable_wireless_adb",
        "target_ip": ip or "",
        "target_alias": alias or "",
        "request_id": request_id,
    }
    bus.publish("app.command", payload)
    return request_id


def _find_wireless_result(request_id, started_at, target_ips):
    result = _wireless_result_by_request.get(request_id)
    if result:
        return result
    target_set = {ip for ip in target_ips if ip}
    for pending in sorted(_wireless_result_pending.values(), key=lambda item: item.get("time", 0), reverse=True):
        if pending.get("time", 0) < started_at:
            break
        pending_ip = pending.get("ip")
        if pending.get("request_id") == request_id:
            return pending
        if pending_ip in target_set:
            return pending
        # Backward compatibility for old app builds that report the fresh IP
        # but do not echo request_id/target_ip.
        if not target_set and pending_ip:
            return pending
        if pending.get("ok") and pending_ip and pending.get("method"):
            return pending
    return None


def _ensure_adb_device(alias=None, ip=None, port=None, auto_enable=True, timeout=30):
    resolved_alias, candidates = _resolve_adb_candidates(alias=alias, ip=ip, port=port)
    tried = []

    for item in candidates:
        candidate_ip = item["ip"]
        candidate_port = item.get("port") or port or 5555
        connected = _connected_adb_device_for(candidate_ip, candidate_port)
        if connected:
            _remember_alias_connection(resolved_alias, connected, candidate_ip, candidate_port)
            return {
                "ok": True,
                "device": connected,
                "ip": candidate_ip,
                "port": candidate_port,
                "method": "already_connected",
                "tried": tried,
            }
        device, output = _connect_adb(candidate_ip, candidate_port)
        tried.append({"ip": candidate_ip, "port": candidate_port, "output": output})
        if device:
            _remember_alias_connection(resolved_alias, device, candidate_ip, candidate_port)
            return {
                "ok": True,
                "device": device,
                "ip": candidate_ip,
                "port": candidate_port,
                "method": "adb_connect",
                "tried": tried,
            }

    if not auto_enable:
        return {"ok": False, "error": "ADB 未连接，且 auto_enable=false", "tried": tried}

    target_ip = candidates[0]["ip"] if candidates else (ip or "")
    target_port = candidates[0].get("port", port or 5555) if candidates else (port or 5555)
    started_at = _time.time()
    request_id = _publish_wireless_request(target_ip, alias=resolved_alias)
    deadline = started_at + timeout
    target_ips = [item["ip"] for item in candidates]

    while _time.time() < deadline:
        _time.sleep(0.3)
        pending = _find_wireless_result(request_id, started_at, target_ips)
        if pending:
            if pending.get("ok") is False:
                return {
                    "ok": False,
                    "error": f"App 开启失败: {pending.get('error', '未知错误')}",
                    "method": pending.get("method") or "app_command",
                    "request_id": request_id,
                    "tried": tried,
                }
            result_ip = pending.get("ip") or target_ip
            result_port = int(pending.get("port") or target_port or 5555)
            if pending.get("ok") and result_ip and result_port > 0:
                # App 回报成功，重试 connect（端口刚开可能需要几秒就绪）
                for attempt in range(5):
                    device, output = _connect_adb(result_ip, result_port)
                    tried.append({"ip": result_ip, "port": result_port, "output": output, "method": pending.get("method"), "attempt": attempt + 1})
                    if device:
                        _remember_alias_connection(resolved_alias, device, result_ip, result_port)
                        return {
                            "ok": True,
                            "device": device,
                            "ip": result_ip,
                            "port": result_port,
                            "method": pending.get("method") or "app_command",
                            "request_id": request_id,
                            "tried": tried,
                        }
                    _time.sleep(1)
                # connect 重试 5 次仍失败，返回错误
                return {
                    "ok": False,
                    "error": f"App 已开启无线调试(ip={result_ip}, port={result_port})，但 adb connect 失败",
                    "method": pending.get("method") or "app_command",
                    "request_id": request_id,
                    "tried": tried[-5:],
                }

    return {
        "ok": False,
        "error": f"等待超时({timeout}s)，App 未回报或连接失败",
        "request_id": request_id,
        "tried": tried[-5:],
    }


def _get_connected_devices():
    from connected_devices import get_connected
    return get_connected()


def _resolve_alias(ip=None, alias=None):
    if alias:
        aliases = _load_device_aliases()
        if alias in aliases:
            return alias, aliases[alias].get("ip")
    if ip:
        aliases = _load_device_aliases()
        found = find_alias_by_ip(aliases, ip)
        if found:
            return found, ip
    return alias, ip


@device_bp.route("/api/devices", methods=["GET"])
def api_get_devices():
    try:
        aliases = _load_device_aliases()
        now = _time.time()
        online_cutoff = now - 120

        conn = _get_connected_devices()

        adb_set = set()
        try:
            res = _run_adb(["devices"], timeout=3)
            if res.returncode == 0:
                for line in res.stdout.splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == "device":
                        adb_set.add(parts[0])
        except Exception:
            pass

        result = []
        matched_ips = set()

        for alias, info in aliases.items():
            ip = info.get("ip", "")
            ips = info.get("ips") or []
            port = info.get("port", 5555)
            device_id_ip = None
            is_adb = False
            for dip in [ip] + ips:
                matching_adb = next((x for x in adb_set if x == dip or x.startswith(f"{dip}:")), None)
                if matching_adb:
                    device_id_ip = matching_adb
                    is_adb = True
                    if ":" in matching_adb:
                        try:
                            port = int(matching_adb.split(":")[-1])
                        except Exception:
                            pass
                    break

            is_online = False
            online_ip = None
            for dip in [ip] + ips:
                ts = conn.get(dip, 0)
                if ts > online_cutoff:
                    is_online = True
                    online_ip = dip
                    matched_ips.add(dip)
                    break

            if is_online and online_ip and online_ip != ip:
                add_alias_ip(alias, online_ip)
                if online_ip not in ips:
                    ips.append(online_ip)

            result.append({
                "device_id": device_id_ip,
                "ip": info.get("ip"),
                "online_ip": online_ip,
                "adb_port": port,
                "alias": alias,
                "serial": info.get("serial"),
                "model": info.get("model"),
                "brand": info.get("brand"),
                "is_adb_connected": is_adb,
                "is_online": is_online,
                "is_active": is_online,
                "ip_changed": is_online and online_ip != ip,
                "ips": ips,
                "last_active": max(conn.get(d, 0) for d in [ip] + ips) if ips else conn.get(ip, 0),
            })

        # 补齐活跃但未配置 alias 的设备：App 在线但用户没在 device_aliases.json 配过别名
        # 这类设备也要在 web 端显示，否则会出现「设备管理页空」但 /api/debug/connected 有数据
        for active_ip, ts in conn.items():
            if ts <= online_cutoff:
                continue
            if active_ip in matched_ips:
                continue
            # 检查该 IP 是否已被任何 alias 的 ips 列表收过（避免重复）
            already = any(
                active_ip == info.get("ip") or active_ip in (info.get("ips") or [])
                for info in aliases.values()
            )
            if already:
                continue
            device_id_ip = None
            is_adb = False
            port = 5555
            matching_adb = next((x for x in adb_set if x == active_ip or x.startswith(f"{active_ip}:")), None)
            if matching_adb:
                device_id_ip = matching_adb
                is_adb = True
                if ":" in matching_adb:
                    try:
                        port = int(matching_adb.split(":")[-1])
                    except Exception:
                        pass
            result.append({
                "device_id": device_id_ip,
                "ip": active_ip,
                "online_ip": active_ip,
                "adb_port": port,
                "alias": None,
                "serial": None,
                "model": None,
                "brand": None,
                "is_adb_connected": is_adb,
                "is_online": True,
                "is_active": True,
                "ip_changed": False,
                "ips": [active_ip],
                "last_active": ts,
            })

        return jsonify({"ok": True, "devices": result, "aliases": aliases})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@device_bp.route("/api/devices/alias", methods=["POST"])
def api_set_device_alias():
    data = request.json or {}
    alias = data.get("alias")
    ip = data.get("ip")
    port = data.get("port", 5555)

    if not alias or not ip:
        return jsonify({"ok": False, "error": "Missing 'alias' or 'ip'"}), 400

    try:
        aliases = _load_device_aliases()

        serial = None
        model = None
        brand = None
        device_id = f"{ip}:{port}"
        try:
            model = _get_device_info(device_id).get("model")
            serial = get_device_serial(device_id)
            brand = _get_device_info(device_id).get("brand")
        except Exception:
            pass

        existing_alias = resolve_alias_for_device(aliases, device_id, ip=ip, serial=serial, model=model)
        if existing_alias and existing_alias != alias:
            if alias not in aliases:
                aliases[alias] = aliases.pop(existing_alias)
            else:
                old_entry = aliases.pop(existing_alias)
                for k, v in old_entry.items():
                    if k not in aliases[alias] or aliases[alias][k] is None:
                        aliases[alias][k] = v
                old_ips = old_entry.get("ips") or []
                if old_entry.get("ip") and old_entry["ip"] not in old_ips:
                    old_ips.append(old_entry["ip"])
                new_ips = aliases[alias].get("ips") or []
                for oip in old_ips:
                    if oip not in new_ips:
                        new_ips.append(oip)
                if ip and ip not in new_ips:
                    new_ips.append(ip)
                aliases[alias]["ips"] = new_ips

        entry = aliases.get(alias, {})
        entry["serial"] = serial or entry.get("serial")
        entry["model"] = model or entry.get("model")
        entry["brand"] = brand or entry.get("brand")
        entry["ip"] = ip
        entry["port"] = port
        ips = entry.get("ips") or []
        if ip and ip not in ips:
            ips.append(ip)
        entry["ips"] = ips
        entry["updated_at"] = _time.time()
        aliases[alias] = entry

        _save_device_aliases(aliases)
        return jsonify({"ok": True, "message": f"已设置别名 '{alias}' -> {ip}:{port}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@device_bp.route("/api/device/<alias>", methods=["GET"])
def api_get_device_by_alias(alias):
    try:
        aliases = _load_device_aliases()
        if alias not in aliases:
            return jsonify({"ok": False, "error": f"别名 '{alias}' 不存在"}), 404

        alias_info = aliases[alias]
        ip = alias_info["ip"]
        port = alias_info.get("port", 5555)

        now = _time.time()
        cutoff = now - 300
        is_connected = ip in _get_connected_devices() and _get_connected_devices()[ip] > cutoff

        if is_connected:
            alias_info["last_active"] = _get_connected_devices()[ip]

        return jsonify({
            "ok": True,
            "alias": alias,
            "ip": ip,
            "port": port,
            "serial": alias_info.get("serial"),
            "model": alias_info.get("model"),
            "brand": alias_info.get("brand"),
            "is_connected": is_connected,
            "adb_command": f"adb connect {ip}:{port}"
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@device_bp.route("/api/adb/disconnect", methods=["POST"])
def api_adb_disconnect():
    data = request.json or {}
    device_id = data.get("device_id")
    alias = data.get("alias")
    if not device_id and alias:
        aliases = _load_device_aliases()
        if alias in aliases:
            entry = aliases[alias]
            ip = entry.get("ip")
            port = entry.get("port", 5555)
            if ip:
                device_id = f"{ip}:{port}"
    if not device_id:
        return jsonify({"ok": False, "error": "缺少 device_id 或 alias"}), 400
    try:
        r = _run_adb(["disconnect", device_id], timeout=5)
        return jsonify({"ok": True, "message": f"已断开 {device_id}", "output": r.stdout.strip()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@device_bp.route("/api/devices/alias/<alias>", methods=["DELETE"])
def api_delete_device_alias(alias):
    try:
        aliases = _load_device_aliases()
        if alias not in aliases:
            return jsonify({"ok": False, "error": f"别名 '{alias}' 不存在"}), 404

        del aliases[alias]
        _save_device_aliases(aliases)
        return jsonify({"ok": True, "message": f"已删除别名 '{alias}'"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _adb_ensure_connected(ip, auto_enable=True, timeout=30):
    result = _ensure_adb_device(ip=ip, auto_enable=auto_enable, timeout=timeout)
    return result.get("device") if result.get("ok") else None


@device_bp.route("/api/adb/connect", methods=["POST"])
def api_adb_connect():
    data = request.json or {}
    alias = data.get("alias")
    ip = data.get("ip")
    port = data.get("port")
    timeout = min(data.get("timeout", 30), 60)
    if port is not None:
        port = int(port)

    if not ip and not alias:
        return jsonify({"ok": False, "error": "缺少 ip 或 alias 参数"}), 400

    result = _ensure_adb_device(alias=alias, ip=ip, port=port, auto_enable=True, timeout=timeout)
    if result.get("ok"):
        device = result["device"]
        method = result.get("method", "unknown")
        return jsonify({
            "ok": True,
            "device": device,
            "ip": result.get("ip"),
            "port": result.get("port"),
            "adb_command": f"{ADB_PATH} connect {result.get('ip')}:{result.get('port')}",
            "method": method,
            "message": f"ADB 已连接 {device} (method={method})",
        })

    status = 504 if "超时" in result.get("error", "") else 500
    return jsonify(result), status


@device_bp.route("/api/adb/ensure", methods=["POST"])
def api_adb_ensure():
    data = request.json or {}
    alias = data.get("alias")
    ip = data.get("ip")
    port = data.get("port")
    timeout = min(int(data.get("timeout", 30)), 60)
    auto_enable = data.get("auto_enable", True)
    if isinstance(auto_enable, str):
        auto_enable = auto_enable.lower() not in ("0", "false", "no")
    if port is not None:
        port = int(port)

    result = _ensure_adb_device(
        alias=alias,
        ip=ip,
        port=port,
        auto_enable=bool(auto_enable),
        timeout=timeout,
    )
    if result.get("ok"):
        result["adb_command"] = f"{ADB_PATH} connect {result.get('ip')}:{result.get('port')}"
        result["device_id"] = result.get("device")
        result["serial_arg"] = ["-s", result.get("device")]
        result["message"] = f"ADB ready: {result.get('device')}"
        return jsonify(result)
    status = 504 if "超时" in result.get("error", "") else 500
    return jsonify(result), status


@device_bp.route("/api/adb/grant-overlay", methods=["POST"])
def api_adb_grant_overlay():
    """Grant AideLink's overlay AppOp through the already connected ADB device."""
    data = request.json or {}
    device = data.get("device") or _connected_adb_device_for(data.get("ip"), data.get("port"))
    if not device:
        return jsonify({"ok": False, "error": "未找到已连接的 ADB 设备"}), 503
    result = _run_adb(["-s", device, "shell", "appops", "set", "cc.aidelink.app",
                       "android:system_alert_window", "allow"], timeout=8)
    if result.returncode != 0:
        return jsonify({"ok": False, "error": result.stderr.strip() or "ADB 授权悬浮窗失败"}), 500
    return jsonify({"ok": True, "device": device})


@device_bp.route("/api/adb/enable-wireless", methods=["POST"])
@device_bp.route("/adb/enable-wireless", methods=["POST"])
def api_adb_enable_wireless():
    data = request.json or {}
    alias = data.get("alias")
    ip = data.get("ip")
    timeout = min(data.get("timeout", 30), 60)

    if not ip and alias:
        aliases = _load_device_aliases()
        entry = aliases.get(alias)
        if entry:
            conn = _get_connected_devices()
            now = _time.time()
            known_ips = list(dict.fromkeys([entry.get("ip", "")] + (entry.get("ips") or [])))
            known_ips = [i for i in known_ips if i]
            for dip in known_ips:
                if conn.get(dip, 0) > now - 120:
                    ip = dip
                    break
            if not ip:
                ip = known_ips[0] if known_ips else None
        if not ip:
            _, ip = _resolve_alias(alias=alias)
    if not ip:
        return jsonify({"ok": False, "error": "缺少 ip 或 alias 参数"}), 400

    started_at = _time.time()
    request_id = _publish_wireless_request(ip, alias=alias)
    deadline = started_at + timeout
    while _time.time() < deadline:
        _time.sleep(1)
        pending = _find_wireless_result(request_id, started_at, [ip])
        if pending and pending.get("ok"):
            result_ip = pending.get("ip") or ip
            result_port = int(pending.get("port") or 5555)
            device, _ = _connect_adb(result_ip, result_port)
            if device:
                return jsonify({"ok": True, "ip": result_ip, "port": result_port, "device": device, "request_id": request_id, "message": "无线调试已开启，ADB 已连接"})
        if pending and pending.get("ok") is False:
            return jsonify({"ok": False, "request_id": request_id, "error": f"App 开启失败: {pending.get('error', '未知错误')}"}), 500
        try:
            _flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            res = subprocess.run(["adb", "connect", f"{ip}:5555"], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=5, creationflags=_flags)
            if res.returncode == 0 and "connected" in res.stdout.lower():
                subprocess.run(["adb", "-s", f"{ip}:5555", "wait-for-device"], capture_output=True, timeout=10, creationflags=_flags)
                return jsonify({"ok": True, "ip": ip, "port": 5555, "request_id": request_id, "message": "无线调试已开启，ADB 已连接"})
        except Exception:
            pass

    return jsonify({"ok": False, "error": f"等待超时({timeout}s)，App 未回报或连接失败"}), 504


@device_bp.route("/api/adb/screenshot-feedback", methods=["POST"])
@device_bp.route("/adb/screenshot-feedback", methods=["POST"])
def api_adb_screenshot_feedback():
    """通知目标设备弹出 App 端的截图反馈界面。

    通过 events/bus publish 一条 app.command 事件到 `app.command` topic，
    目标设备（App 通过 SSE 订阅）收到后启动 UiLocatorService 的截图反馈流程。

    入参：
        - ip: 目标设备 IP（必填）
        - alias: 设备别名（可选，用于 App 端日志/提示）
        - target_ide: 可选；指定截图反馈的目标 IDE key，App 默认走自动选择

    返回：{ok: True, request_id, message}；App 端异步处理，无回传。
    """
    data = request.json or {}
    ip = (data.get("ip") or "").strip()
    alias = (data.get("alias") or "").strip()
    target_ide = (data.get("target_ide") or "").strip()

    # alias 兜底解析 ip
    if not ip and alias:
        aliases = _load_device_aliases()
        entry = aliases.get(alias)
        if entry:
            ip = entry.get("ip") or (entry.get("ips") or [""])[0]
    if not ip:
        return jsonify({"ok": False, "error": "缺少 ip 或 alias 参数"}), 400

    # 校验设备是否在线（120s 内有心跳）；离线直接拒绝
    conn = _get_connected_devices()
    now = _time.time()
    if conn.get(ip, 0) <= now - 120:
        return jsonify({
            "ok": False,
            "error": f"设备 {ip} 不在线（120s 内无心跳），请先在手机上打开 AideLink App",
        }), 409

    request_id = uuid.uuid4().hex
    payload = {
        "command": "screenshot_feedback",
        "target_ip": ip,
        "target_alias": alias,
        "target_ide": target_ide,
        "request_id": request_id,
    }
    bus.publish("app.command", payload)
    return jsonify({
        "ok": True,
        "request_id": request_id,
        "ip": ip,
        "alias": alias,
        "message": f"已通知 {alias or ip} 弹出截图反馈界面",
    })


@device_bp.route("/api/adb/launch-app", methods=["POST"])
@device_bp.route("/adb/launch-app", methods=["POST"])
def api_adb_launch_app():
    """通过 ADB 拉起目标设备上的 AideLink ConnectionService（不切 App 到前台）。

    适用场景：手机端无线调试已开（ADB 能连上）但 AideLink App 不在线
    （SSE 心跳已断），此时无法通过 events/stream 推送命令。

    实现方式：`am start-foreground-service` 直接启动 ConnectionService。
    - ConnectionService 已设 exported=true，adb shell uid 可直接启动
    - 不启动 MainActivity，App 不会切到前台
    - 不依赖 BroadcastReceiver，不受 MIUI Greezer 进程冻结影响
    - 不依赖 Trampoline Activity，不受锁屏 Activity 启动拦截
    - ConnectionService 作为前台服务运行，通过 Notification 提示用户
    - SSE 心跳自动恢复，App 重新在线

    入参：
        - ip: 目标设备 IP（必填）
        - port: 默认 5555
        - alias: 设备别名（可选，仅用于提示消息）

    返回：{ok: True, device, message}
    """
    data = request.json or {}
    ip = (data.get("ip") or "").strip()
    alias = (data.get("alias") or "").strip()
    try:
        port = int(data.get("port") or 5555)
    except (TypeError, ValueError):
        port = 5555

    if not ip:
        return jsonify({"ok": False, "error": "缺少 ip 参数"}), 400

    device_id = f"{ip}:{port}"
    # 先 adb connect（若已连接会幂等返回）
    try:
        connect_res = _run_adb(["connect", device_id], timeout=10)
        connect_out = (connect_res.stdout + connect_res.stderr).lower()
        if "connected" not in connect_out and "already" not in connect_out:
            return jsonify({
                "ok": False,
                "error": f"adb connect {device_id} 失败：{connect_res.stdout.strip()}",
            }), 500
    except Exception as exc:
        return jsonify({"ok": False, "error": f"adb connect 异常：{exc}"}), 500

    # am start-foreground-service 直接启动 ConnectionService
    # App 不切到前台，仅通过 Notification 显示 ConnectionService 运行状态
    try:
        res = _run_adb(
            ["-s", device_id, "shell", "am", "start-foreground-service",
             "-n", "cc.aidelink.app/.service.ConnectionService"],
            timeout=10,
        )
        output = (res.stdout or "").strip()
        err = (res.stderr or "").strip()
        # 成功输出 "Starting service: Intent { ... }"，无 Error 行
        # 失败会输出 "Error: Requires permission ..." 或 "Error: ..."
        if res.returncode != 0 or "Error" in output or "Error" in err:
            return jsonify({
                "ok": False,
                "error": f"am start-foreground-service 失败：{err or output or '未知错误'}",
                "device": device_id,
            }), 500
        return jsonify({
            "ok": True,
            "device": device_id,
            "message": f"已通过 ADB 拉起 {alias or device_id} 上的 AideLink 服务",
            "output": output,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": f"am start-foreground-service 异常：{exc}"}), 500


@device_bp.route("/api/adb/wireless-result", methods=["POST"])
@device_bp.route("/adb/wireless-result", methods=["POST"])
def api_adb_wireless_result():
    data = request.json or {}
    ip = data.get("ip")
    port = data.get("port", 5555)
    ok = data.get("ok", False)
    error = data.get("error")
    method = data.get("method")
    request_id = data.get("request_id")
    target_ip = data.get("target_ip")
    result = {
        "ok": ok,
        "ip": ip,
        "port": port,
        "error": error,
        "method": method,
        "request_id": request_id,
        "target_ip": target_ip,
        "time": _time.time(),
    }
    if ip:
        _wireless_result_pending[ip] = result
    if target_ip:
        _wireless_result_pending[target_ip] = result
    if request_id:
        _wireless_result_by_request[request_id] = result
    return jsonify({"ok": True})


@device_bp.route("/api/adb/report", methods=["POST"])
def api_adb_report():
    import threading
    data = request.json or {}
    ip = data.get("ip")
    port = data.get("port")
    enabled = data.get("enabled", False)

    if not ip:
        return jsonify({"ok": False, "error": "Missing ip"}), 400

    if enabled and port:
        port = int(port)
        aliases = _load_device_aliases()
        changed = False
        for alias, entry in aliases.items():
            known_ips = [entry.get("ip")] + (entry.get("ips") or [])
            if ip in known_ips:
                entry["port"] = port
                entry["ip"] = ip
                entry["updated_at"] = _time.time()
                changed = True

        if changed:
            _save_device_aliases(aliases)

        def _bg_connect():
            connected, _ = _connect_adb(ip, port)
            if connected:
                try:
                    _run_adb(["-s", connected, "shell", "pm", "grant", "cc.aidelink.app", "android.permission.WRITE_SECURE_SETTINGS"], timeout=3)
                except Exception:
                    pass
        threading.Thread(target=_bg_connect, daemon=True).start()

        return jsonify({"ok": True, "message": f"Port reported and connecting: {ip}:{port}"})

    return jsonify({"ok": True, "message": "Status received"})


@device_bp.route("/api/adb/root/install", methods=["POST"])
def api_adb_root_install():
    data = request.json or {}
    apk_path = data.get("apk_path")
    alias = data.get("alias")
    target_ip = data.get("ip")
    auto_enable = data.get("auto_enable", True)

    if not apk_path:
        apk_path = str(APK_PATH)
    apk_path = os.path.abspath(apk_path)
    if not os.path.exists(apk_path):
        return jsonify({"ok": False, "error": f"APK 文件不存在: {apk_path}"}), 400

    if not target_ip and alias:
        _, target_ip = _resolve_alias(alias=alias)

    device = None
    if target_ip:
        device = _adb_ensure_connected(target_ip, auto_enable=auto_enable)
    if not device:
        device = _get_active_adb_device()
    if not device:
        return jsonify({"ok": False, "error": "无可用 ADB 设备，请确保手机已连接 AideLink 且已开启无线调试"}), 500

    try:
        temp_apk = "/data/local/tmp/temp_install.apk"
        _f = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        subprocess.run(["adb", "-s", device, "push", apk_path, temp_apk], check=True, capture_output=True, timeout=30, creationflags=_f)
        cmd = ["adb", "-s", device, "shell", "su", "-c", f"pm install -r -d -g {temp_apk}"]
        res = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=40, creationflags=_f)
        subprocess.run(["adb", "-s", device, "shell", "rm", temp_apk], check=True, capture_output=True, timeout=10, creationflags=_f)
        return jsonify({"ok": True, "message": "Root 静默安装完成", "output": res.stdout.strip()})
    except subprocess.CalledProcessError:
        try:
            res2 = subprocess.run(["adb", "-s", device, "install", "-r", "-d", apk_path], check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60, creationflags=_f)
            return jsonify({"ok": True, "message": "ADB 普通安装完成", "output": res2.stdout.strip()})
        except Exception as e2:
            return jsonify({"ok": False, "error": f"安装失败: {e2}"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@device_bp.route("/api/adb/self-install", methods=["POST"])
def api_adb_self_install():
    """局域网快速安装：通过 ADB 将 APK 推送到指定设备并静默安装。
    请求体: {"ip": "192.168.x.x", "port": 5555}
    """
    apk_path = str(APK_PATH)
    if not os.path.exists(apk_path):
        return jsonify({"ok": False, "error": f"APK 文件不存在: {apk_path}"}), 400

    data = request.json or {}
    target_ip = data.get("ip")
    target_port = data.get("port")
    if not target_ip:
        return jsonify({"ok": False, "error": "缺少 ip 参数"}), 400
    target_port = int(target_port) if target_port else 5555

    # 1) 先断开旧连接，再精确连接到目标设备 ip:port
    _f = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    device_id = f"{target_ip}:{target_port}"
    connected = False
    try:
        _run_adb(["disconnect", device_id], timeout=5)
    except Exception:
        pass
    try:
        res = _run_adb(["connect", device_id], timeout=10)
        text = (res.stdout + res.stderr).lower()
        if "connected" in text:
            connected = True
    except Exception:
        pass

    if not connected:
        return jsonify({"ok": False, "error": f"无法连接到 {device_id}，请确认无线调试已开启"}), 500

    # 2) 确认设备在线
    try:
        _run_adb(["-s", device_id, "wait-for-device"], timeout=10)
    except Exception:
        pass

    # 3) push + install
    temp_apk = "/data/local/tmp/aidelink_update.apk"
    try:
        subprocess.run(
            [ADB_PATH, "-s", device_id, "push", apk_path, temp_apk],
            check=True, capture_output=True, timeout=30, creationflags=_f
        )
        res = subprocess.run(
            [ADB_PATH, "-s", device_id, "shell", "su", "-c", f"pm install -r -d -g {temp_apk}"],
            check=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=40, creationflags=_f
        )
        subprocess.run(
            [ADB_PATH, "-s", device_id, "shell", "rm", temp_apk],
            check=True, capture_output=True, timeout=10, creationflags=_f
        )
        # 安装完成后自动启动 App
        subprocess.run(
            [ADB_PATH, "-s", device_id, "shell", "am", "start", "-n", "cc.aidelink.app/.MainActivity"],
            capture_output=True, timeout=5, creationflags=_f
        )
        return jsonify({"ok": True, "message": "ADB 静默安装完成", "device": device_id, "output": res.stdout.strip()})
    except subprocess.CalledProcessError:
        try:
            res2 = subprocess.run(
                [ADB_PATH, "-s", device_id, "install", "-r", "-d", apk_path],
                check=True, capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=60, creationflags=_f
            )
            # 安装完成后自动启动 App
            subprocess.run(
                [ADB_PATH, "-s", device_id, "shell", "am", "start", "-n", "cc.aidelink.app/.MainActivity"],
                capture_output=True, timeout=5, creationflags=_f
            )
            return jsonify({"ok": True, "message": "ADB 普通安装完成", "device": device_id, "output": res2.stdout.strip()})
        except Exception as e2:
            return jsonify({"ok": False, "error": f"安装失败: {e2}", "device": device_id}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "device": device_id}), 500


@device_bp.route("/api/adb/project-install", methods=["POST"])
def api_adb_project_install():
    """Install an APK discovered under a configured target Android project."""
    data = request.json or {}
    settings = _load_settings()
    project_path = normalize_project_path(data.get("project_path") or settings.get("current_project", ""))
    configured = settings.get("projects", [])
    if not project_path or not any(
        project_path_key(item.get("path", "")) == project_path_key(project_path)
        for item in configured
    ):
        return jsonify({"ok": False, "error": "目标项目未添加或未选中"}), 400

    apk_path, metadata = resolve_project_apk(project_path, data.get("apk_path", ""))
    if not metadata["is_android"]:
        return jsonify({"ok": False, "error": "目标项目中未识别到 Android 工程"}), 400
    if not apk_path:
        return jsonify({"ok": False, "error": "未发现可安装 APK，请先编译 Android 应用或重新扫描"}), 400

    target_ip = data.get("ip")
    target_port = int(data.get("port") or 5555)
    if not target_ip:
        return jsonify({"ok": False, "error": "缺少 ip 参数"}), 400
    device_id = f"{target_ip}:{target_port}"
    try:
        connect_result = _run_adb(["connect", device_id], timeout=10)
        if "connected" not in (connect_result.stdout + connect_result.stderr).lower():
            return jsonify({"ok": False, "error": f"无法连接到 {device_id}"}), 500

        _flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            [ADB_PATH, "-s", device_id, "install", "-r", "-d", apk_path],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            creationflags=_flags,
        )
        apk_info = next((item for item in metadata["apks"] if project_path_key(item["path"]) == project_path_key(apk_path)), {})
        application_id = apk_info.get("application_id", "")
        if application_id:
            # 不能用 monkey 启动：monkey 在 MIUI 上会注入系统事件，导致方向锁定被关闭。
            # 改用 cmd package resolve-activity 解析 launcher activity，再用 am start 启动。
            resolve_result = subprocess.run(
                [ADB_PATH, "-s", device_id, "shell", "cmd", "package", "resolve-activity", "--brief", application_id],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=10, creationflags=_flags,
            )
            component = next((line.strip() for line in (resolve_result.stdout or "").splitlines()
                              if line.strip() and "/" in line), "")
            if component:
                subprocess.run(
                    [ADB_PATH, "-s", device_id, "shell", "am", "start", "-n", component],
                    capture_output=True, timeout=10, creationflags=_flags,
                )
            else:
                # 极端情况下回退到 am start 直接传包名（Android 12+ 支持）
                subprocess.run(
                    [ADB_PATH, "-s", device_id, "shell", "am", "start", application_id],
                    capture_output=True, timeout=10, creationflags=_flags,
                )
        return jsonify({
            "ok": True,
            "message": "目标项目 APK 安装完成",
            "device": device_id,
            "apk_path": apk_path,
            "application_id": application_id,
            "output": result.stdout.strip(),
        })
    except subprocess.CalledProcessError as exc:
        error = (exc.stderr or exc.stdout or str(exc)).strip()
        return jsonify({"ok": False, "error": f"安装失败: {error}", "device": device_id}), 500
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "device": device_id}), 500


@device_bp.route("/api/adb/usb_tcpip", methods=["POST"])
def api_adb_usb_tcpip():
    try:
        import ui_locator
        devices = ui_locator.get_adb_devices()

        usb_devices = [d for d in devices if ":" not in d]

        if not usb_devices:
            return jsonify({"ok": False, "error": "未检测到通过 USB 连接的设备，请插好数据线并允许 USB 调试。"})

        success_list = []
        fail_list = []
        for dev in usb_devices:
            res = _run_adb(["-s", dev, "tcpip", "5555"], timeout=10)
            if res.returncode == 0:
                success_list.append(dev)
            else:
                fail_list.append(f"{dev} ({res.stderr.strip()})")

        if success_list:
            msg = f"成功对 USB 设备开启 5555 端口: {', '.join(success_list)}"
            if fail_list:
                msg += f"；失败: {', '.join(fail_list)}"
            return jsonify({"ok": True, "message": msg})
        else:
            return jsonify({"ok": False, "error": f"开启失败: {', '.join(fail_list)}"})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@device_bp.route("/api/adb/root/file", methods=["POST"])
def api_adb_root_file():
    data = request.json or {}
    action = data.get("action")
    path = data.get("path")
    if not action or not path:
        return jsonify({"ok": False, "error": "Missing 'action' or 'path'"}), 400

    device = _get_active_adb_device()
    if not device:
        return jsonify({"ok": False, "error": "No ADB device connected"}), 500

    try:
        if action == "read":
            import base64
            cmd = ["adb", "-s", device, "shell", "su", "-c", f"base64 {path}"]
            _f = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            res = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15, creationflags=_f)
            decoded = base64.b64decode(res.stdout.strip())
            try:
                text_content = decoded.decode("utf-8")
                return jsonify({"ok": True, "type": "text", "content": text_content})
            except UnicodeDecodeError:
                return jsonify({"ok": True, "type": "base64", "content": res.stdout.strip()})

        elif action == "write":
            content = data.get("content", "")
            temp_local = os.path.join(BRIDGE_DIR, "state", "temp_write.tmp")
            os.makedirs(os.path.dirname(temp_local), exist_ok=True)
            with open(temp_local, "w", encoding="utf-8") as f:
                f.write(content)

            temp_device = "/data/local/tmp/temp_write.tmp"
            _f = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            subprocess.run(["adb", "-s", device, "push", temp_local, temp_device], check=True, capture_output=True, timeout=15, creationflags=_f)

            cmd = ["adb", "-s", device, "shell", "su", "-c", f"cp {temp_device} {path} && chmod 660 {path}"]
            subprocess.run(cmd, check=True, capture_output=True, timeout=15, creationflags=_f)

            subprocess.run(["adb", "-s", device, "shell", "rm", temp_device], check=True, capture_output=True, timeout=10, creationflags=_f)
            if os.path.exists(temp_local):
                os.remove(temp_local)

            return jsonify({"ok": True, "message": f"成功使用 Root 权限写入沙盒文件: {path}"})
        else:
            return jsonify({"ok": False, "error": f"Unsupported action: {action}"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# 从 phone_chat_bridge.py 迁移的路由（Step 1.4）
# ============================================================

@device_bp.route("/api/adb/logcat", methods=["GET"])
def api_adb_logcat():
    """获取 Logcat 日志，支持按包名或关键字过滤"""
    from device_manager import get_active_adb_device
    package = request.args.get("package")
    lines = int(request.args.get("lines", 100))
    level = request.args.get("level")
    
    device = get_active_adb_device()
    if not device:
        return jsonify({"ok": False, "error": "No ADB device connected"}), 500

    try:
        _f = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        cmd = ["adb", "-s", device, "logcat", "-d", "-t", str(lines)]
        if level:
            cmd += ["*:" + level]
        res = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, creationflags=_f)
        log_lines = res.stdout.splitlines()
        
        if package:
            pid_res = _run_adb(["-s", device, "shell", "pidof", package], timeout=5)
            pid = pid_res.stdout.strip()
            if pid:
                pid_pattern = f" {pid} "
                log_lines = [l for l in log_lines if pid_pattern in l or f"({pid})" in l]
                
        return jsonify({"ok": True, "logs": log_lines})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
