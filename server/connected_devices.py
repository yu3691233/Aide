import time

_connected_devices = {}


def track_ip(ip):
    if ip and ip != "127.0.0.1" and ip != "::1":
        _connected_devices[ip] = time.time()


def get_connected():
    return _connected_devices


def get_active_ips(timeout=120):
    now = time.time()
    return [ip for ip, ts in _connected_devices.items() if ts > now - timeout]


def update_device_alias(device_ip, device_serial=None):
    if not device_ip:
        return
    _connected_devices[device_ip] = time.time()
    try:
        from device_manager import load_device_aliases, find_alias_by_ip, add_alias_ip
        aliases = load_device_aliases()
        # 1. 按 IP 匹配
        alias = find_alias_by_ip(aliases, device_ip)
        if alias:
            add_alias_ip(alias, device_ip)
            return
        # 2. 按 serial 精确匹配
        if device_serial:
            for a, info in aliases.items():
                if info.get("serial") == device_serial:
                    add_alias_ip(a, device_ip)
                    return
        # 3. 无 IP 的别名按 model 匹配（首次连接场景）
        for a, info in aliases.items():
            if info.get("model") and not info.get("ip"):
                add_alias_ip(a, device_ip)
                break
    except Exception:
        pass
