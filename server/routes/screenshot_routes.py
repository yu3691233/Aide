import sys
from pathlib import Path
_server_dir = str(Path(__file__).parent.parent)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from flask import Blueprint, request, jsonify
import json
import os
import time
import ctypes

from paths import BRIDGE_DIR, CROPS_FILE
from json_utils import safe_read_json, safe_write_json

screenshot_bp = Blueprint('screenshot', __name__)
# 保留旧白名单用于快速路径,但实际判断走 _is_window_target 动态查找
_WINDOW_TARGETS = ('trae', 'trae_cn', 'antigravity_ide', 'mimo', 'mimocode', 'oc', 'codex')


def _is_window_target(target):
    """动态判断 target 是否为窗口目标 — 通过 binding 或标题匹配能找到窗口即为 True。
    替代硬编码的 _WINDOW_TARGETS 白名单,支持自定义 IDE(如 WorkBuddy)。"""
    target = (target or "").strip().lower()
    if not target:
        return False
    # 快速路径:内置 IDE 直接返回 True,避免频繁找窗口
    if target in _WINDOW_TARGETS:
        return True
    try:
        pcb = _get_screenshot_utils()
        return pcb._find_target_window(target) is not None
    except Exception:
        return False


def _get_screenshot_utils():
    import screenshot_engine
    return screenshot_engine


def _target_window_payload(target):
    target = (target or "").strip().lower()
    if not _is_window_target(target):
        return None
    pcb = _get_screenshot_utils()
    target_win = pcb._find_target_window(target)
    if not target_win:
        return None
    hwnd = target_win._hWnd
    try:
        if ctypes.windll.user32.IsIconic(hwnd) != 0:
            return None
    except Exception:
        pass

    rect = pcb._get_window_rect(hwnd)
    if rect:
        left, top, right, bottom = [int(v) for v in rect]
    else:
        left = int(getattr(target_win, "left", 0))
        top = int(getattr(target_win, "top", 0))
        width = int(getattr(target_win, "width", 0))
        height = int(getattr(target_win, "height", 0))
        right = left + width
        bottom = top + height
    if right <= left or bottom <= top or left <= -10000 or top <= -10000:
        return None
    return {
        "target": target,
        "title": getattr(target_win, "title", ""),
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": right - left,
        "height": bottom - top,
    }


def _monitor_name_for_target(target):
    payload = _target_window_payload(target)
    if not payload:
        return ""
    center_x = (payload["left"] + payload["right"]) // 2
    center_y = (payload["top"] + payload["bottom"]) // 2
    pcb = _get_screenshot_utils()
    for mon in pcb.get_all_monitors():
        if mon["left"] <= center_x < mon["right"] and mon["top"] <= center_y < mon["bottom"]:
            return mon["name"]
    return ""


def _preferred_monitor_for_target(target, pcb):
    monitor_name = _monitor_name_for_target(target)
    if monitor_name:
        return monitor_name
    crops = pcb.read_crops()
    primary_crops = crops.get("monitors", {}).get("primary", {})
    if target in primary_crops:
        return "primary"
    return "default"


# ============================================================
# /screenshot/full
# ============================================================

@screenshot_bp.route('/screenshot/full')
def screenshot_full():
    _imgs = []
    try:
        print(f"[DEBUG] screenshot_full: UA={request.headers.get('User-Agent')}, Remote={request.remote_addr}, XFF={request.headers.get('X-Forwarded-For')}", flush=True)
        target = request.args.get('target', default='').strip().lower()
        monitor_name = request.args.get('monitor', default='').strip()
        full_monitor = request.args.get('full_monitor', default='').strip().lower() in ('true', '1')

        window_found = False
        data = None

        # Prioritize window capture if target is a window target
        if _is_window_target(target):
            try:
                pcb = _get_screenshot_utils()
                target_win = pcb._find_target_window(target)
                if target_win:
                    hwnd = target_win._hWnd
                    user32 = ctypes.windll.user32
                    is_minimized = False
                    try:
                        is_minimized = user32.IsIconic(hwnd) != 0
                    except Exception:
                        pass

                    if not is_minimized:
                        window_found = True

                        import capture_window
                        winrt_img = capture_window.capture_window_winrt(hwnd, client_only=True)
                        if winrt_img is not None:
                            _imgs.append(winrt_img)
                            winrt_img = pcb._scale_for_phone(winrt_img)
                            _imgs.append(winrt_img)
                            data = pcb._encode_jpeg(winrt_img)
                        else:
                            pw_img = capture_window.capture_window_client(hwnd)
                            if pw_img is not None:
                                _imgs.append(pw_img)
                                pw_img = pcb._scale_for_phone(pw_img)
                                _imgs.append(pw_img)
                                data = pcb._encode_jpeg(pw_img)
            except Exception as win_err:
                print(f"[WARN] Failed to grab window for {target}: {win_err}", flush=True)

        # Fallback to monitor_name if target window was not captured
        if data is None and monitor_name:
            try:
                pcb = _get_screenshot_utils()
                monitors = pcb.get_all_monitors()
                sel = next((m for m in monitors if m["name"] == monitor_name), None)
                if sel:
                    img = pcb.safe_grab_screen(bbox=(sel["left"], sel["top"], sel["right"], sel["bottom"]))
                    _imgs.append(img)
                    img = pcb._scale_for_phone(img)
                    _imgs.append(img)
                    data = pcb._encode_jpeg(img)
            except Exception as mon_err:
                print(f"[WARN] Failed to grab specified monitor {monitor_name}: {mon_err}", flush=True)

        # Fallback to window's monitor if target window was not captured but exists
        if data is None and _is_window_target(target):
            try:
                pcb = _get_screenshot_utils()
                target_win = pcb._find_target_window(target)
                if target_win:
                    hwnd = target_win._hWnd
                    rect = pcb._get_window_rect(hwnd)
                    if rect and rect[0] > -10000 and rect[1] > -10000:
                        win_mon = pcb.get_monitor_for_window(hwnd)
                        monitors = pcb.get_all_monitors()
                        sel = next((m for m in monitors if m["name"] == win_mon), None)
                        if sel:
                            img = pcb.safe_grab_screen(bbox=(sel["left"], sel["top"], sel["right"], sel["bottom"]))
                            _imgs.append(img)
                            img = pcb._scale_for_phone(img)
                            _imgs.append(img)
                            data = pcb._encode_jpeg(img)
            except Exception:
                pass

        if data is None:
            pcb = _get_screenshot_utils()
            try:
                primary = pcb._get_primary_monitor_bbox()
                if primary:
                    img = pcb.safe_grab_screen(bbox=primary)
                else:
                    img = pcb.safe_grab_screen()
            except Exception as grab_err:
                print(f"[WARN] Failed to grab primary screen: {grab_err}", flush=True)
                msg = "AideLink PC Offline / Locked\n\n(Screen grab not available)"
                img = pcb._make_placeholder(msg)

            _imgs.append(img)
            img = pcb._scale_for_phone(img)
            _imgs.append(img)
            data = pcb._encode_jpeg(img)

        if _is_window_target(target) and not window_found:
            window_found = _target_window_payload(target) is not None

        from flask import Response
        resp = Response(data, mimetype='image/jpeg')
        resp.headers['X-Window-Found'] = 'true' if window_found else 'false'
        return resp
    except Exception as e:
        print(f"[ERROR] screenshot_full fatal error: {e}", flush=True)
        try:
            pcb = _get_screenshot_utils()
            placeholder = pcb._make_placeholder(f"AideLink Fatal Error\n\n{e}")
            _imgs.append(placeholder)
            from flask import Response
            resp = Response(pcb._encode_jpeg(placeholder), mimetype='image/jpeg')
            resp.headers['X-Window-Found'] = 'false'
            return resp
        except Exception:
            return jsonify({"error": str(e)}), 500
    finally:
        try:
            pcb = _get_screenshot_utils()
            pcb._free_gdi_resources(*_imgs)
        except Exception:
            pass


# ============================================================
# /screenshot/crop
# ============================================================

@screenshot_bp.route('/screenshot/crop', methods=['GET', 'POST'])
def screenshot_crop():
    if request.method == 'POST':
        try:
            data = request.json or {}
            target = data.get('target', '').strip().lower()
            if not target:
                return jsonify({"ok": False, "error": "Missing target"}), 400

            pcb = _get_screenshot_utils()
            if _is_window_target(target):
                monitor_name = _preferred_monitor_for_target(target, pcb) or "default"
            else:
                monitor_val = data.get('monitor')
                monitor_name = str(monitor_val).strip() if monitor_val is not None else ""
                if not monitor_name or monitor_name == "default":
                    monitor_name = "default"

            dialog_pos = data.get("dialog_position")
            config = pcb.set_crop_config(
                target,
                int(data.get("left", 0)),
                int(data.get("right", 0)),
                int(data.get("top", 0)),
                int(data.get("bottom", 0)),
                monitor_name,
                dialog_position=dialog_pos,
                calib_width=data.get("calib_width"),
                calib_height=data.get("calib_height"),
                focus_input_enabled=data.get("focus_input_enabled"),
                input_region=data.get("input_region")
            )
            return jsonify({"ok": True, "config": config, "monitor": monitor_name})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    _imgs = []
    try:
        print(f"[DEBUG] screenshot_crop: UA={request.headers.get('User-Agent')}, Remote={request.remote_addr}, XFF={request.headers.get('X-Forwarded-For')}", flush=True)
        target = request.args.get('target', default='').strip().lower()

        pcb = _get_screenshot_utils()
        requested_monitor = request.args.get('monitor', default='').strip()

        if request.args.get('action', default='').strip().lower() == 'monitors':
            monitors = pcb.get_all_monitors()
            return jsonify({"ok": True, "monitors": monitors})

        if request.args.get('action', default='').strip().lower() == 'config':
            return jsonify(pcb.read_crops())

        if request.args.get('action', default='').strip().lower() == 'active_config':
            if not target:
                return jsonify({"ok": False, "error": "Missing target"}), 400
            if _is_window_target(target):
                monitor_name = _preferred_monitor_for_target(target, pcb) or "default"
            else:
                monitor_name = request.args.get('monitor', default='').strip()
                if not monitor_name:
                    monitor_name = "default"
            cfg = pcb.get_scaled_crop_config(target, monitor_name)
            return jsonify({
                "ok": True,
                "target": target,
                "monitor": monitor_name,
                "config": cfg
            })

        if 'x' in request.args or 'y' in request.args or 'w' in request.args or 'h' in request.args:
            img = pcb.safe_grab_screen()
            _imgs.append(img)
            x = request.args.get('x', default=0, type=int)
            y = request.args.get('y', default=0, type=int)
            w = request.args.get('w', default=1000, type=int)
            h = request.args.get('h', default=800, type=int)
            x = max(0, min(x, img.width - 1))
            y = max(0, min(y, img.height - 1))
            w = max(1, min(w, img.width - x))
            h = max(1, min(h, img.height - y))
            data = pcb._crop_to_bytes(img, x, y, x + w, y + h)
            if data:
                from flask import Response
                return Response(data, mimetype='image/jpeg')
            return jsonify({"error": "Crop region invalid"}), 400

        if target:
            base_img = None
            monitor_name = "default"
            cfg = None
            cur_w, cur_h = 0, 0

            # Prioritize window capture if target is a window target
            if _is_window_target(target):
                try:
                    target_win = pcb._find_target_window(target)
                    if target_win:
                        hwnd = target_win._hWnd
                        user32 = ctypes.windll.user32
                        is_minimized = False
                        try:
                            is_minimized = user32.IsIconic(hwnd) != 0
                        except Exception:
                            pass

                        if not is_minimized:
                            monitor_name = pcb.get_monitor_for_window(hwnd)
                            cfg = pcb.get_crop_config(target, monitor_name)

                            import capture_window
                            winrt_img = capture_window.capture_window_winrt(hwnd, client_only=True)
                            if winrt_img is not None:
                                base_img = winrt_img
                                _imgs.append(base_img)
                            else:
                                pw_img = capture_window.capture_window_client(hwnd)
                                if pw_img is not None:
                                    base_img = pw_img
                                    _imgs.append(base_img)

                            if base_img is not None:
                                cur_w, cur_h = base_img.size
                except Exception as win_err:
                    print(f"[WARN] Failed to grab crop window for {target}: {win_err}", flush=True)

            # Fallback to monitor if window was not captured
            if base_img is None:
                if requested_monitor and requested_monitor != "default":
                    monitor_name = requested_monitor
                    cfg = pcb.get_crop_config(target, monitor_name)
                    monitors = pcb.get_all_monitors()
                    sel = next((m for m in monitors if m["name"] == monitor_name), None)
                    if sel:
                        base_img = pcb.safe_grab_screen(bbox=(sel["left"], sel["top"], sel["right"], sel["bottom"]))
                        _imgs.append(base_img)
                        cur_w, cur_h = base_img.size

            if base_img is None:
                try:
                    primary = pcb._get_primary_monitor_bbox()
                    if primary:
                        base_img = pcb.safe_grab_screen(bbox=primary)
                    else:
                        base_img = pcb.safe_grab_screen()
                    _imgs.append(base_img)
                    cur_w, cur_h = base_img.size
                except Exception as grab_err:
                    print(f"[WARN] Failed to grab base screen for crop: {grab_err}", flush=True)
                    msg = "AideLink PC Offline / Locked\n\n(Screen grab not available)"
                    base_img = pcb._make_placeholder(msg)
                    _imgs.append(base_img)

            if cfg is None:
                cfg = pcb.get_crop_config(target, monitor_name)
            adj_l, adj_r, adj_t, adj_b = pcb._adjust_crop_margins(cfg, cur_w, cur_h)

            if base_img is not None:
                try:
                    adj_l = max(0, min(adj_l, base_img.width - 10))
                    adj_r = max(0, min(adj_r, base_img.width - adj_l - 10))
                    adj_t = max(0, min(adj_t, base_img.height - 10))
                    adj_b = max(0, min(adj_b, base_img.height - adj_t - 10))

                    cropped_img = base_img.crop((adj_l, adj_t, base_img.width - adj_r, base_img.height - adj_b))
                    cropped_img = pcb._scale_for_phone(cropped_img)
                    
                    result_bytes = pcb._encode_jpeg(cropped_img)
                    if result_bytes:
                        from flask import Response
                        return Response(result_bytes, mimetype='image/jpeg')
                except Exception as crop_err:
                    print(f"[WARN] Failed to crop and scale physical image: {crop_err}", flush=True)

            try:
                import io
                img_io = io.BytesIO()
                base_img.save(img_io, 'JPEG', quality=85)
                img_io.seek(0)
                from flask import Response
                return Response(img_io.getvalue(), mimetype='image/jpeg')
            except Exception:
                pass

        try:
            primary = pcb._get_primary_monitor_bbox()
            if primary:
                img = pcb.safe_grab_screen(bbox=primary)
            else:
                img = pcb.safe_grab_screen()
            _imgs.append(img)
        except Exception as grab_err:
            msg = "AideLink PC Offline / Locked\n\n(Screen grab not available)"
            img = pcb._make_placeholder(msg)
            _imgs.append(img)

        import io
        img_io = io.BytesIO()
        img.save(img_io, 'JPEG', quality=85)
        img_io.seek(0)
        from flask import Response
        return Response(img_io.getvalue(), mimetype='image/jpeg')
    except Exception as e:
        print(f"[ERROR] screenshot_crop fatal error: {e}", flush=True)
        try:
            pcb = _get_screenshot_utils()
            img = pcb._make_placeholder(f"AideLink Crop Fatal Error\n\n{e}")
            _imgs.append(img)
            import io
            img_io = io.BytesIO()
            img.save(img_io, 'JPEG', quality=85)
            img_io.seek(0)
            from flask import Response
            return Response(img_io.getvalue(), mimetype='image/jpeg')
        except Exception:
            return jsonify({"error": str(e)}), 500
    finally:
        try:
            pcb = _get_screenshot_utils()
            pcb._free_gdi_resources(*_imgs)
        except Exception:
            pass


# ============================================================
# App compatibility endpoints
# ============================================================

@screenshot_bp.route('/screenshot/monitors')
def screenshot_monitors():
    try:
        pcb = _get_screenshot_utils()
        return jsonify({"ok": True, "monitors": pcb.get_all_monitors()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "monitors": []}), 500


@screenshot_bp.route('/screenshot/window-info')
def screenshot_window_info():
    target = request.args.get('target', default='').strip().lower()
    try:
        payload = _target_window_payload(target)
        if not payload:
            return jsonify({"ok": False, "error": f"Window not found for {target}", "window": None}), 404
        return jsonify({"ok": True, "window": payload})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "window": None}), 500


@screenshot_bp.route('/screenshot/crops')
def screenshot_crops():
    try:
        pcb = _get_screenshot_utils()
        return jsonify(pcb.read_crops())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@screenshot_bp.route('/screenshot/crop-config', methods=['GET', 'POST'])
def screenshot_crop_config():
    try:
        pcb = _get_screenshot_utils()
        if request.method == 'POST':
            data = request.json or {}
            target = data.get('target', '').strip().lower()
            if not target:
                return jsonify({"ok": False, "error": "Missing target"}), 400
            if _is_window_target(target):
                monitor_name = _preferred_monitor_for_target(target, pcb) or "default"
            else:
                monitor_name = str(data.get('monitor') or "default").strip() or "default"
            config = pcb.set_crop_config(
                target,
                int(data.get("left", 0)),
                int(data.get("right", 0)),
                int(data.get("top", 0)),
                int(data.get("bottom", 0)),
                monitor_name,
                dialog_position=data.get("dialog_position"),
                calib_width=data.get("calib_width"),
                calib_height=data.get("calib_height"),
                focus_input_enabled=data.get("focus_input_enabled"),
                input_region=data.get("input_region")
            )
            return jsonify({"ok": True, "target": target, "monitor": monitor_name, "config": config})

        target = request.args.get('target', default='').strip().lower()
        if not target:
            return jsonify({"ok": False, "error": "Missing target"}), 400
        if _is_window_target(target):
            monitor_name = _preferred_monitor_for_target(target, pcb) or "default"
        else:
            monitor_name = request.args.get('monitor', default='').strip() or "default"
        config = pcb.get_scaled_crop_config(target, monitor_name)
        return jsonify({"ok": True, "target": target, "monitor": monitor_name, "config": config})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# /screenshot/dialog
# ============================================================

@screenshot_bp.route('/screenshot/dialog', methods=['GET'])
def screenshot_dialog():
    import dialog_detector as dd
    target = request.args.get('target', default='').strip().lower()
    mode = request.args.get('mode', default='auto').strip().lower()

    if not target:
        return jsonify({"ok": False, "error": "Missing target"}), 400

    _imgs = []
    try:
        pcb = _get_screenshot_utils()
        target_win = pcb._find_target_window(target)
        if not target_win or target_win.width <= 0 or target_win.height <= 0:
            print(f"[INFO] screenshot_dialog: window not found for {target}, falling back", flush=True)
            mode = "manual"

        base_img = None
        if mode == "auto" and target_win:
            hwnd = target_win._hWnd
            import capture_window
            winrt_img = capture_window.capture_window_winrt(hwnd, client_only=True)
            if winrt_img is not None:
                base_img = winrt_img
                _imgs.append(base_img)
            else:
                pw_img = capture_window.capture_window_client(hwnd)
                if pw_img is not None:
                    base_img = pw_img
                    _imgs.append(base_img)
            if base_img is None:
                rect = pcb._get_window_rect(hwnd)
                if rect and rect[0] > -10000 and rect[1] > -10000:
                    base_img = pcb.safe_grab_screen(bbox=(int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])))
                    _imgs.append(base_img)
                else:
                    base_img = pcb.safe_grab_screen()
                    _imgs.append(base_img)

        if mode == "auto" and base_img is not None:
            cropped = dd.detect_and_crop(base_img, target)
            if cropped is not None and cropped.width > 50 and cropped.height > 50:
                _imgs.append(cropped)
                cropped_scaled = pcb._scale_for_phone(cropped)
                _imgs.append(cropped_scaled)
                import io
                img_io = io.BytesIO()
                cropped_scaled.save(img_io, 'JPEG', quality=85)
                img_io.seek(0)
                print(f"[INFO] screenshot_dialog: auto-crop success for {target}", flush=True)
                from flask import Response
                return Response(img_io.getvalue(), mimetype='image/jpeg')
            else:
                print(f"[INFO] screenshot_dialog: auto-detect failed for {target}, using manual crop", flush=True)

        # 直接调用同蓝图中的路由处理函数即可，无需包裹在 test_request_context 中
        return screenshot_crop()

    except Exception as e:
        print(f"[ERROR] screenshot_dialog fatal error: {e}", flush=True)
        try:
            pcb = _get_screenshot_utils()
            img = pcb._make_placeholder(f"AideLink Dialog Error\n\n{e}")
            _imgs.append(img)
            import io
            img_io = io.BytesIO()
            img.save(img_io, 'JPEG', quality=85)
            img_io.seek(0)
            from flask import Response
            return Response(img_io.getvalue(), mimetype='image/jpeg')
        except Exception:
            return jsonify({"error": str(e)}), 500
    finally:
        try:
            pcb = _get_screenshot_utils()
            pcb._free_gdi_resources(*_imgs)
        except Exception:
            pass


# ============================================================
# /window/focus-input
# ============================================================

@screenshot_bp.route('/window/focus-input', methods=['POST'])
def focus_window_input():
    try:
        data = request.json or {}
        target = data.get("target", "").strip().lower()
        if not _is_window_target(target):
            return jsonify({"ok": False, "error": "Unsupported target"}), 400
        pcb = _get_screenshot_utils()
        ok = pcb._activate_target_window(target, focus_input=True)
        return jsonify({"ok": ok})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# /window/focus
# ============================================================

@screenshot_bp.route('/window/focus', methods=['POST'])
def focus_window():
    try:
        data = request.json or {}
        target = data.get("target", "").strip().lower()
        if not _is_window_target(target):
            return jsonify({"ok": False, "error": "Unsupported target"}), 400
        pcb = _get_screenshot_utils()
        ok = pcb._activate_target_window(target, focus_input=False)
        return jsonify({"ok": ok})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# /window/maximize
# ============================================================

@screenshot_bp.route('/window/maximize', methods=['POST'])
def maximize_window():
    """最大化目标窗口（用于进入边距调整对话框前，确保校准基准为最大化状态）"""
    try:
        data = request.json or {}
        target = data.get("target", "").strip().lower()
        if not _is_window_target(target):
            return jsonify({"ok": False, "error": "Unsupported target"}), 400
        pcb = _get_screenshot_utils()
        ok = pcb._maximize_target_window(target)
        return jsonify({"ok": ok})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# /window/info
# ============================================================

@screenshot_bp.route('/window/info')
def get_window_info():
    try:
        target = request.args.get("target", default="").strip().lower()
        if not _is_window_target(target):
            return jsonify({"ok": False, "error": "Unsupported target"}), 400
        pcb = _get_screenshot_utils()
        info = pcb._get_window_info(target)
        if not info:
            return jsonify({"ok": False, "error": "Window not found"}), 404
        return jsonify({"ok": True, "window": info})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
