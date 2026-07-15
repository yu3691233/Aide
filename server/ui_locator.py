#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AideLink ADB UI Locator
========================
用于连通 ADB，对手机进行截图并转储 UI 树，解析用户点击坐标对应的界面元素。
"""

import os
import re
import subprocess
import sys
import json
import xml.etree.ElementTree as ET
from json_utils import safe_read_json

# 本地保存路径
BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
SCREEN_PNG_PATH = os.path.join(BRIDGE_DIR, "screen.png")
WINDOW_XML_PATH = os.path.join(BRIDGE_DIR, "window_dump.xml")

from network_utils import ADB_PATH

# subprocess 统一参数（隐藏窗口）
_POPEN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def _run(cmd, **kwargs):
    """运行 subprocess.run，在 Windows 上自动隐藏终端窗口。"""
    merged = {**_POPEN_FLAGS, **kwargs}
    return subprocess.run(cmd, **merged)


# ─── 设备发现 ─────────────────────────────────────────────


def get_target_device_ip():
    """获取目标手机 IP，优先读取 adb_status.json，其次环境变量，最后返回 None。"""
    status_file = os.path.join(BRIDGE_DIR, "adb_status.json")
    if os.path.exists(status_file):
        data = safe_read_json(status_file, {})
        if isinstance(data, dict):
            ip = data.get("ip")
            if ip and ip != "127.0.0.1":
                return ip

    env_ip = os.environ.get("TARGET_DEVICE_IP")
    if env_ip:
        return env_ip

    return None  # 不再回退到旧 IP，避免跨网段连接报错


def is_ip_in_local_subnets(ip):
    """检查 IP 是否处于 PC 的任一本地局域网网段内（/24 匹配）。"""
    if not ip:
        return False
    import socket
    try:
        import psutil
        for _iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    local_ip = addr.address
                    if local_ip.split(".")[:3] == ip.split(".")[:3]:
                        return True
    except Exception:
        # psutil 不可用时降级
        try:
            hostname = socket.gethostname()
            local_ips = socket.gethostbyname_ex(hostname)[2]
            for local_ip in local_ips:
                if local_ip.split(".")[:3] == ip.split(".")[:3]:
                    return True
        except Exception:
            pass
    return False


def get_adb_devices():
    """获取所有已连接且状态为 device 的 ADB 设备列表。"""
    devices = []
    try:
        result = _run([ADB_PATH, "devices"], stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE, text=True, timeout=3)
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

    if devices:
        return devices

    # 尝试从 adb_status.json 读取上报的 IP:port 并重连
    target_ip = get_target_device_ip()
    status_file = os.path.join(BRIDGE_DIR, "adb_status.json")
    connect_target = None
    if os.path.exists(status_file):
        data = safe_read_json(status_file, {})
        if isinstance(data, dict) and data.get("ip") and data.get("port"):
            connect_target = f"{data['ip']}:{data['port']}"
    if connect_target and target_ip and is_ip_in_local_subnets(target_ip):
        try:
            _run([ADB_PATH, "connect", connect_target],
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        except Exception:
            pass
        # 再次获取
        try:
            result = _run([ADB_PATH, "devices"], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, timeout=3)
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


def select_best_device(devices, target_ip=None):
    """从设备列表中选择最佳设备（优先匹配 adb_status.json 上报 IP）。"""
    if not devices:
        return None
    target_ip = target_ip or get_target_device_ip()
    if target_ip:
        for d in devices:
            if target_ip in d:
                return d
    return devices[0]


# ─── 截图 & UI 树 ─────────────────────────────────────────


def capture_screenshot_only(target_ip=None):
    """仅截图，不 dump UI 树。"""
    devices = get_adb_devices()
    device = select_best_device(devices, target_ip=target_ip)
    if not device:
        return {"ok": False, "error": "未检测到已连接的 ADB 设备。"}
    cmd_prefix = [ADB_PATH, "-s", device]
    try:
        _run(cmd_prefix + ["shell", "screencap", "-p", "/sdcard/screen.png"],
             check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        _run(cmd_prefix + ["pull", "/sdcard/screen.png", SCREEN_PNG_PATH],
             check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        return {"ok": True, "device": device, "screen_path": SCREEN_PNG_PATH}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": f"ADB 截图失败: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"截图异常: {e}"}


def capture_phone_ui(target_ip=None):
    """截图 + dump UI 树，全部拉取到本地。"""
    devices = get_adb_devices()
    device = select_best_device(devices, target_ip=target_ip)
    if not device:
        return {"ok": False, "error": "未检测到已连接的 ADB 设备，请确保手机已开启无线 ADB 并连接到电脑。"}

    print(f"[INFO] 正在使用设备: {device}", flush=True)
    cmd_prefix = [ADB_PATH, "-s", device]

    try:
        _run(cmd_prefix + ["shell", "screencap", "-p", "/sdcard/screen.png"],
             check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        _run(cmd_prefix + ["pull", "/sdcard/screen.png", SCREEN_PNG_PATH],
             check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        _run(cmd_prefix + ["shell", "uiautomator", "dump", "/sdcard/window_dump.xml"],
             check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        _run(cmd_prefix + ["pull", "/sdcard/window_dump.xml", WINDOW_XML_PATH],
             check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        return {"ok": True, "device": device,
                "screen_path": SCREEN_PNG_PATH, "xml_path": WINDOW_XML_PATH}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": f"ADB 命令执行失败: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"截图与转储过程发生异常: {e}"}


# ─── XML 解析工具 ─────────────────────────────────────────


def parse_bounds(bounds_str):
    """解析 bounds 属性 [x1,y1][x2,y2]，返回 (x1, y1, x2, y2)。"""
    m = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
    if m:
        return tuple(map(int, m.groups()))
    return None


def _parse_element(node):
    """将 XML node 转换为统一的 dict 格式。"""
    bounds_str = node.get("bounds", "")
    coords = parse_bounds(bounds_str)
    if not coords:
        return None
    x1, y1, x2, y2 = coords
    if (x2 - x1) <= 0 or (y2 - y1) <= 0:
        return None
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    return {
        "text": node.get("text", "").strip(),
        "resource_id": node.get("resource-id", "").strip(),
        "content_desc": node.get("content-desc", "").strip(),
        "class_name": node.get("class", "").strip(),
        "clickable": node.get("clickable", "").lower() == "true",
        "focusable": node.get("focusable", "").lower() == "true",
        "scrollable": node.get("scrollable", "").lower() == "true",
        "enabled": node.get("enabled", "true").lower() == "true",
        "bounds": [x1, y1, x2, y2],
        "center": [cx, cy],
        "area": (x2 - x1) * (y2 - y1),
    }


def _walk_tree(root):
    """遍历整个 UI 树，返回所有节点的元素列表。"""
    elements = []
    def _walk(node):
        e = _parse_element(node)
        if e:
            elements.append(e)
        for child in node:
            _walk(child)
    _walk(root)
    return elements


def _load_xml(xml_path=WINDOW_XML_PATH):
    """加载并解析 UI XML 树。"""
    if not os.path.exists(xml_path):
        return None, "UI XML 树文件不存在，请先调用 capture_phone_ui()"
    try:
        tree = ET.parse(xml_path)
        return tree.getroot(), None
    except Exception as e:
        return None, f"解析 XML 失败: {e}"


# ─── 公开接口 ──────────────────────────────────────────────


def get_interactive_elements():
    """
    获取当前屏幕上所有可交互/有信息的元素列表。
    先截图 + dump UI 树，再解析返回。
    """
    res = capture_phone_ui()
    if not res["ok"]:
        return {"ok": False, "error": res["error"]}

    root, err = _load_xml()
    if err:
        return {"ok": False, "error": err}

    all_elems = _walk_tree(root)
    # 过滤：只保留有内容或可交互的
    visible = [e for e in all_elems if
               e["clickable"] or e["focusable"] or e["scrollable"]
               or e["text"] or e["resource_id"] or e["content_desc"]]

    return {"ok": True, "device": res["device"], "elements": visible}


def find_element_by_attr(text=None, resource_id=None, content_desc=None,
                         class_name=None, refresh=True):
    """
    按属性查找元素，支持模糊匹配（包含）。
    - refresh=True 时先重新截图/dump UI 树，False 时直接复用上一次的 XML。
    返回匹配元素列表（按面积升序，即越精准的越靠前）。
    """
    if refresh:
        res = capture_phone_ui()
        if not res["ok"]:
            return {"ok": False, "error": res["error"]}
        device = res["device"]
    else:
        devices = get_adb_devices()
        device = select_best_device(devices) or "unknown"

    root, err = _load_xml()
    if err:
        return {"ok": False, "error": err}

    all_elems = _walk_tree(root)
    matched = []
    for e in all_elems:
        if text and text not in e["text"]:
            continue
        if resource_id and resource_id not in e["resource_id"]:
            continue
        if content_desc and content_desc not in e["content_desc"]:
            continue
        if class_name and class_name not in e["class_name"]:
            continue
        matched.append(e)

    matched.sort(key=lambda x: x["area"])

    return {
        "ok": True,
        "device": device,
        "count": len(matched),
        "elements": matched,
    }


def tap_element_by_attr(text=None, resource_id=None, content_desc=None,
                         class_name=None, index=0, refresh=True):
    """
    按属性查找元素，然后自动点击第 index 个匹配结果的中心点。
    返回操作结果。
    """
    res = find_element_by_attr(
        text=text, resource_id=resource_id,
        content_desc=content_desc, class_name=class_name,
        refresh=refresh
    )
    if not res["ok"]:
        return res
    if not res["elements"]:
        return {"ok": False, "error": "未找到符合条件的元素", "query": {
            "text": text, "resource_id": resource_id,
            "content_desc": content_desc, "class_name": class_name
        }}

    elems = res["elements"]
    if index >= len(elems):
        index = 0
    target = elems[index]
    cx, cy = target["center"]

    devices = get_adb_devices()
    device = select_best_device(devices)
    if not device:
        return {"ok": False, "error": "未检测到已连接的 ADB 设备。"}

    try:
        _run([ADB_PATH, "-s", device, "shell", "input", "tap", str(cx), str(cy)],
             check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        return {
            "ok": True,
            "device": device,
            "tapped": target,
            "message": f"已点击元素 text='{target['text']}' resource_id='{target['resource_id']}' 中心点 ({cx}, {cy})"
        }
    except Exception as e:
        return {"ok": False, "error": f"ADB tap 失败: {e}"}


def find_element_by_coords(x, y, xml_path=WINDOW_XML_PATH):
    """在 XML 文件中寻找包含坐标 (x, y) 且最精确的节点。"""
    if not os.path.exists(xml_path):
        return {"ok": False, "error": f"找不到 UI 树文件: {xml_path}"}

    root, err = _load_xml(xml_path)
    if err:
        return {"ok": False, "error": err}

    all_elems = _walk_tree(root)
    matched = [e for e in all_elems
               if e["bounds"][0] <= x <= e["bounds"][2]
               and e["bounds"][1] <= y <= e["bounds"][3]]

    if not matched:
        return {"ok": False, "error": f"在坐标 ({x}, {y}) 处未找到任何 UI 元素。"}

    def rank(n):
        has_text = 0 if (n["text"] or n["content_desc"]) else 1
        return (has_text, n["area"])

    matched.sort(key=rank)
    best = matched[0]
    return {"ok": True, "element": best}


if __name__ == "__main__":
    print("正在进行 ADB UI Locator 自测...")
    res = capture_phone_ui()
    if res["ok"]:
        print(f"截图成功，设备: {res['device']}")
        el_res = find_element_by_coords(300, 300)
        print("坐标(300,300)对应元素:", el_res)
    else:
        print("测试失败:", res["error"])
