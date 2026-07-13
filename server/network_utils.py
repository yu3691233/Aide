import os
import subprocess
import sys

_ADB_DEFAULT_PATH = os.environ.get("AIDELINK_ADB_PATH", "")

ADB_PATH = _ADB_DEFAULT_PATH if _ADB_DEFAULT_PATH and os.path.exists(_ADB_DEFAULT_PATH) else "adb"

_POPEN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def get_local_ip():
    try:
        s = __import__("socket").socket(__import__("socket").AF_INET, __import__("socket").SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_all_local_ips():
    import psutil
    import socket
    ips = []
    try:
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    if not ip.startswith("127.") and ip not in ips:
                        ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = info[4][0]
                if not ip.startswith("127.") and ip not in ips:
                    ips.append(ip)
        except Exception:
            pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            ips.append("127.0.0.1")
    return ips


def is_physical_lan(ip):
    if ip.startswith("127."):
        return False
    if ip.startswith("172."):
        try:
            parts = ip.split(".")
            if len(parts) >= 2:
                second = int(parts[1])
                if 16 <= second <= 31:
                    return False
        except Exception:
            pass
    if ip.startswith("169.254."):
        return False
    if ip.startswith("10."):
        return False
    return True


def get_adb_devices():
    devices = []
    try:
        result = subprocess.run(
            [ADB_PATH, "devices"], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, timeout=3, **_POPEN_FLAGS
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line or line.startswith("List of devices"):
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    devices.append(parts[0])
    except Exception:
        pass
    return devices
