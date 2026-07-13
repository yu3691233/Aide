import os
import re
import json
import subprocess
import sys
from paths import DEVICE_ALIASES_FILE
from json_utils import safe_read_json, safe_write_json


def _run_adb(args, timeout=5):
    try:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        r = subprocess.run(
            ["adb"] + args,
            capture_output=True, text=True, timeout=timeout,
            creationflags=flags,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def get_device_serial(device_id):
    serial = _run_adb(["-s", device_id, "shell", "getprop", "ro.serialno"])
    if serial and serial != "unknown":
        return serial
    serial = _run_adb(["-s", device_id, "shell", "getprop", "ro.boot.serialno"])
    if serial and serial != "unknown":
        return serial
    return None


def get_device_brand(device_id):
    return _run_adb(["-s", device_id, "shell", "getprop", "ro.product.brand"])


def load_device_aliases():
    aliases = safe_read_json(DEVICE_ALIASES_FILE, {})
    migrated = False
    for alias, info in aliases.items():
        if "serial" not in info:
            info["serial"] = None
            migrated = True
        if "brand" not in info:
            info["brand"] = None
            migrated = True
        if "ips" not in info:
            info["ips"] = []
            if info.get("ip"):
                info["ips"] = [info["ip"]]
            migrated = True
    if migrated:
        safe_write_json(DEVICE_ALIASES_FILE, aliases)
    return aliases


def save_device_aliases(aliases):
    safe_write_json(DEVICE_ALIASES_FILE, aliases)


def find_alias_by_serial(aliases, serial):
    if not serial:
        return None
    for alias, info in aliases.items():
        if info.get("serial") == serial:
            return alias
    return None


def find_alias_by_ip(aliases, ip):
    if not ip:
        return None
    for alias, info in aliases.items():
        if info.get("ip") == ip:
            return alias
        if ip in (info.get("ips") or []):
            return alias
    return None


def add_alias_ip(alias, ip, port=None):
    if not ip:
        return
    aliases = load_device_aliases()
    if alias not in aliases:
        return
    entry = aliases[alias]
    ips = entry.get("ips") or []
    if ip not in ips:
        ips.append(ip)
        entry["ips"] = ips
    entry["ip"] = ip
    if port:
        entry["port"] = port
    entry["updated_at"] = __import__("time").time()
    save_device_aliases(aliases)


def update_alias_connection(alias, ip, port, serial=None, model=None, brand=None):
    aliases = load_device_aliases()
    if alias not in aliases:
        return
    entry = aliases[alias]
    entry["ip"] = ip
    entry["port"] = port
    if serial:
        entry["serial"] = serial
    if model:
        entry["model"] = model
    if brand:
        entry["brand"] = brand
    entry["updated_at"] = __import__("time").time()
    save_device_aliases(aliases)


def get_device_info(device_id):
    info = {
        "id": device_id, "ip": None, "port": None,
        "model": None, "serial": None, "brand": None,
        "connection_type": None
    }

    if ":" in device_id:
        info["connection_type"] = "wireless"
        parts = device_id.split(":")
        info["ip"] = parts[0]
        info["port"] = int(parts[1]) if len(parts) > 1 else None
    else:
        info["connection_type"] = "usb"

    info["model"] = _run_adb(["-s", device_id, "shell", "getprop", "ro.product.model"])
    info["serial"] = get_device_serial(device_id)
    info["brand"] = get_device_brand(device_id)

    if info["connection_type"] == "usb" and not info["ip"]:
        ip_out = _run_adb(["-s", device_id, "shell", "ip", "addr", "show", "wlan0"])
        if ip_out:
            match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', ip_out)
            if match:
                info["ip"] = match.group(1)

    if not info["port"]:
        port_str = _run_adb(["-s", device_id, "shell", "getprop", "service.adb.tcp.port"])
        if port_str:
            try:
                info["port"] = int(port_str)
            except ValueError:
                pass

    return info


def resolve_alias_for_device(aliases, device_id, ip=None, serial=None, model=None):
    if serial:
        alias = find_alias_by_serial(aliases, serial)
        if alias:
            return alias
    if ip:
        alias = find_alias_by_ip(aliases, ip)
        if alias:
            return alias
    if model:
        for alias, info in aliases.items():
            if info.get("model") and info["model"].lower() == model.lower():
                return alias
    return None


def get_active_adb_device():
    import ui_locator
    return ui_locator.select_best_device()
