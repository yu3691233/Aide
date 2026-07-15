"""
UI 定位器 Blueprint
从 phone_chat_bridge.py 迁移的 /ui-locator/* 路由
"""
import os
from flask import Blueprint, request, jsonify, send_from_directory

from paths import BRIDGE_DIR

ui_locator_bp = Blueprint('ui_locator', __name__)

# 延迟导入避免循环依赖
def _get_ui_locator():
    import ui_locator
    return ui_locator

def _get_project_scanner():
    import project_scanner
    return project_scanner


@ui_locator_bp.route('/ui-locator/capture', methods=['POST'])
def ui_locator_capture():
    """触发手机截屏和 UI 树转储"""
    ui_locator = _get_ui_locator()
    data = request.get_json(silent=True) or {}
    target_ip = data.get("ip") or request.headers.get("X-Device-IP") or request.remote_addr
    res = ui_locator.capture_phone_ui(target_ip=target_ip)
    if res["ok"]:
        return jsonify({
            "ok": True,
            "device": res["device"],
            "screen_url": "/ui-locator/screen.png"
        })
    else:
        return jsonify({
            "ok": False,
            "error": res["error"]
        })


@ui_locator_bp.route('/ui-locator/screenshot', methods=['POST'])
def ui_locator_screenshot():
    """仅截取手机屏幕（不转储 UI 树），用于截图发送等轻量场景"""
    ui_locator = _get_ui_locator()
    data = request.get_json(silent=True) or {}
    target_ip = data.get("ip") or request.headers.get("X-Device-IP") or request.remote_addr
    res = ui_locator.capture_screenshot_only(target_ip=target_ip)
    if res["ok"]:
        return jsonify({
            "ok": True,
            "device": res["device"],
            "screen_url": "/ui-locator/screen.png"
        })
    else:
        return jsonify({
            "ok": False,
            "error": res["error"]
        })


@ui_locator_bp.route('/ui-locator/screen.png', methods=['GET'])
def ui_locator_screen():
    """获取手机截图图片"""
    ui_locator = _get_ui_locator()
    if os.path.exists(ui_locator.SCREEN_PNG_PATH):
        return send_from_directory(ui_locator.BRIDGE_DIR, "screen.png")
    return jsonify({"ok": False, "error": "No screenshot available"}), 404


@ui_locator_bp.route('/ui-locator/locate', methods=['POST'])
def ui_locator_locate():
    """根据点击坐标定位界面元素并匹配项目结构，返回代码位置"""
    ui_locator = _get_ui_locator()
    project_scanner = _get_project_scanner()
    
    data = request.json or {}
    x = data.get("x")
    y = data.get("y")
    width = data.get("width")
    height = data.get("height")
    
    if x is None or y is None:
        return jsonify({"ok": False, "error": "缺少参数: x, y"}), 400

    # 1. 缩放坐标
    if width and height and os.path.exists(ui_locator.SCREEN_PNG_PATH):
        try:
            from PIL import Image
            with Image.open(ui_locator.SCREEN_PNG_PATH) as img:
                img_w, img_h = img.size
            x = int(x * img_w / width)
            y = int(y * img_h / height)
            print(f"[INFO] 坐标映射: ({data['x']}, {data['y']}) -> ({x}, {y}) [显示: {width}x{height}, 实际: {img_w}x{img_h}]")
        except Exception as e:
            print(f"[WARN] 坐标缩放失败: {e}")

    # 2. 定位 XML 元素
    el_res = ui_locator.find_element_by_coords(x, y)
    if not el_res["ok"]:
        return jsonify(el_res), 404

    element = el_res["element"]
    text = element["text"]
    content_desc = element["content_desc"]

    # 3. 关联项目结构
    project_map = project_scanner.load_cached()
    if not project_map:
        project_map = project_scanner.scan_project()
        project_scanner.scan_and_save()

    matched_node = None
    
    def find_node(node):
        nonlocal matched_node
        if matched_node:
            return
        
        node_name = node.get("name", "")
        clean_node_name = node_name.split(":")[-1].strip() if ":" in node_name else node_name
        
        if text and text in clean_node_name:
            matched_node = node
            return
        if content_desc and content_desc in clean_node_name:
            matched_node = node
            return
            
        for child in node.get("children", []):
            find_node(child)

    for cat in project_map.get("categories", []):
        find_node(cat)

    response_data = {
        "ok": True,
        "element": element,
        "matched_code": None
    }

    if matched_node:
        response_data["matched_code"] = {
            "name": matched_node.get("name"),
            "file": matched_node.get("file"),
            "line_start": matched_node.get("line_start"),
            "line_end": matched_node.get("line_end"),
            "description": matched_node.get("description"),
            "composable": matched_node.get("composable"),
            "class": matched_node.get("class")
        }

    return jsonify(response_data)
