import sys
from pathlib import Path
_server_dir = str(Path(__file__).parent.parent)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

from flask import Blueprint, request, jsonify, send_from_directory
import json
import os
import time
import threading
from datetime import datetime

from paths import BRIDGE_DIR, HISTORY_FILE, CLIPBOARD_FILE, IN_FILE, UPLOAD_FOLDER, LOG_FILE, PHONE_LOG_FILE
from json_utils import safe_read_json, safe_write_json
from device_manager import load_device_aliases, find_alias_by_ip
from upload_policy import MAX_UPLOAD_SIZE, is_allowed_upload

phone_bp = Blueprint('phone', __name__)


XIAOMENGLING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取项目中的文件内容。返回文件的文本内容，最多返回 3000 字符。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对于项目根目录的文件路径，如 src/main.py"},
                    "offset": {"type": "integer", "description": "从第几行开始读（默认 0）"},
                    "limit": {"type": "integer", "description": "读取多少行（默认 200）"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出项目目录下的文件和子目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对于项目根目录的目录路径，留空则列出根目录"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "在项目文件中搜索文本内容（grep），返回匹配的文件和行。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "要搜索的文本或正则表达式"},
                    "glob": {"type": "string", "description": "文件过滤模式，如 *.py、*.kt"},
                },
                "required": ["query"],
            },
        },
    },
]


def _execute_xiaomengling_tool(name: str, args: dict, project_dir: str) -> str:
    import subprocess

    if name == "read_file":
        rel = args.get("path", "")
        if not rel:
            return "错误：缺少 path 参数"
        abs_path = os.path.normpath(os.path.join(project_dir, rel))
        if not abs_path.startswith(os.path.normpath(project_dir)):
            return "错误：路径超出项目范围"
        if not os.path.isfile(abs_path):
            return f"错误：文件不存在 {rel}"
        try:
            offset = max(0, int(args.get("offset", 0)))
            limit = min(500, max(1, int(args.get("limit", 200))))
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            total = len(lines)
            selected = lines[offset:offset + limit]
            numbered = [f"{offset + i + 1}: {line.rstrip()}" for i, line in enumerate(selected)]
            result = "\n".join(numbered)
            if len(result) > 3000:
                result = result[:3000] + "\n...（内容截断）"
            return f"文件: {rel} ({total} 行，显示 {offset+1}-{offset+len(selected)})\n{result}"
        except Exception as e:
            return f"读取失败: {e}"

    elif name == "list_dir":
        rel = args.get("path", "")
        abs_path = os.path.normpath(os.path.join(project_dir, rel)) if rel else project_dir
        if not abs_path.startswith(os.path.normpath(project_dir)):
            return "错误：路径超出项目范围"
        if not os.path.isdir(abs_path):
            return f"错误：目录不存在 {rel or '.'}"
        try:
            entries = []
            for e in sorted(os.listdir(abs_path)):
                if e.startswith(".") and e not in (".gitignore", ".env"):
                    continue
                full = os.path.join(abs_path, e)
                prefix = "📁" if os.path.isdir(full) else "📄"
                size = ""
                if os.path.isfile(full):
                    s = os.path.getsize(full)
                    size = f" ({s}B)" if s < 1024 else f" ({s // 1024}KB)"
                entries.append(f"{prefix} {e}{size}")
                if len(entries) >= 80:
                    entries.append("...（更多文件省略）")
                    break
            dir_label = rel or "."
            return f"目录: {dir_label}\n" + "\n".join(entries)
        except Exception as e:
            return f"列出失败: {e}"

    elif name == "search_files":
        query = args.get("query", "")
        if not query:
            return "错误：缺少 query 参数"
        glob_filter = args.get("glob")
        try:
            cmd = ["rg", "-n", "--max-count", "5", "-l", query]
            if glob_filter:
                cmd.extend(["-g", glob_filter])
            cmd.append(".")
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
                cwd=project_dir,
            )
            output = r.stdout.strip()
            if not output:
                return f"未找到匹配 '{query}' 的文件"
            files = output.split("\n")[:20]
            result_parts = []
            for f in files:
                cmd2 = ["rg", "-n", "--max-count", "3", query, f]
                if glob_filter:
                    cmd2 = ["rg", "-n", "--max-count", "3", "-g", glob_filter, query, f]
                r2 = subprocess.run(
                    cmd2, capture_output=True, text=True, timeout=5,
                    cwd=project_dir,
                )
                result_parts.append(f"\n--- {f} ---\n{r2.stdout.strip()}")
            total_matches = len(files)
            header = f"搜索 '{query}'：找到 {total_matches} 个文件"
            if total_matches >= 20:
                header += "（仅显示前20个）"
            return header + "\n".join(result_parts)
        except FileNotFoundError:
            matches = []
            for root, dirs, fnames in os.walk(project_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__", "build", ".gradle")]
                for fn in fnames:
                    if glob_filter:
                        import fnmatch
                        if not fnmatch.fnmatch(fn, glob_filter):
                            continue
                    fp = os.path.join(root, fn)
                    try:
                        with open(fp, "r", encoding="utf-8", errors="ignore") as fobj:
                            for i, line in enumerate(fobj, 1):
                                if query.lower() in line.lower():
                                    rel_fp = os.path.relpath(fp, project_dir)
                                    matches.append(f"{rel_fp}:{i}: {line.rstrip()}")
                                    break
                    except Exception:
                        pass
                    if len(matches) >= 20:
                        break
                if len(matches) >= 20:
                    break
            if not matches:
                return f"未找到匹配 '{query}' 的文件"
            return f"搜索 '{query}'：\n" + "\n".join(matches[:20])
        except Exception as e:
            return f"搜索失败: {e}"

    return f"未知工具: {name}"


from shared_runtime import read_history, write_history, read_clipboard, write_clipboard, init_files


def _normalize_owned_paths(value):
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def set_image_to_clipboard(image_path):
    """通过 PowerShell 把图片本身写入 Windows 系统剪贴板"""
    if os.name != 'nt':
        return False
    try:
        import base64
        import subprocess
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            return False
        ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile(@'
{abs_path}
'@)
$bmp = New-Object System.Drawing.Bitmap $img
$img.Dispose()
[System.Windows.Forms.Clipboard]::SetImage($bmp)
Start-Sleep -Milliseconds 100
$bmp.Dispose()
"""
        encoded = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
        creationflags = 0x08000000
        result = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=10,
        )
        if result.returncode != 0:
            print(f"[ERROR] set_image_to_clipboard PowerShell failed: {result.stderr}", flush=True)
            return False
        return True
    except Exception as e:
        print(f"[ERROR] set_image_to_clipboard failed: {e}", flush=True)
        return False


def _get_phone_deps():
    from shared_runtime import runtime
    from dispatch_utils import dispatch_task, is_ide_reachable
    from task_runtime import SUPPORTED_IDES
    return runtime, dispatch_task, is_ide_reachable, SUPPORTED_IDES


def _get_screen_deps():
    from screen_control import is_screen_locked, wake_screen
    return is_screen_locked, wake_screen


def _get_settings_loader():
    from config import load_settings as _load_settings
    return _load_settings


@phone_bp.route('/ping')
def ping():
    return jsonify({"status": "ok", "message": "AideLink server is running"})


@phone_bp.route('/logs/server')
def server_logs():
    source = request.args.get("source", "flask")
    n = request.args.get("n", 100, type=int)
    if n > 500:
        n = 500
    log_path = LOG_FILE if source == "flask" else PHONE_LOG_FILE
    if not log_path.exists():
        return jsonify({"ok": False, "error": f"log file not found: {log_path}"}), 404
    try:
        with open(str(log_path), "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        tail = lines[-n:]
        return jsonify({"ok": True, "lines": tail, "total": len(lines), "showing": len(tail), "source": source, "path": str(log_path)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@phone_bp.route('/logs/report', methods=['POST'])
def report_logs():
    data = request.json or {}
    logs_str = data.get("logs", "")
    if logs_str:
        log_file_path = os.path.join(BRIDGE_DIR, "phone_app.log")
        try:
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(f"--- Reported at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                f.write(logs_str)
                if not logs_str.endswith("\n"):
                    f.write("\n")
            return jsonify({"ok": True, "message": "Logs reported successfully"})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": False, "error": "No logs provided"}), 400


@phone_bp.route('/inject-clipboard', methods=['POST'])
def inject_clipboard_to_ide():
    """将当前剪贴板内容粘贴到指定 IDE 窗口（用于截图先注入图片）"""
    data = request.json or {}
    ide = data.get("target", "").strip().lower()
    if not ide:
        return jsonify({"ok": False, "error": "缺少 target 参数"}), 400

    try:
        import inject_to_ide as inj
        import pygetwindow as gw
        import pyautogui

        win = None
        if ide in ("mimo", "mimocode"):
            win = inj.find_terminal_window_for_process("mimo")
        elif ide == "trae":
            wins = [w for w in gw.getAllWindows() if "trae" in w.title.lower()]
            win = wins[0] if wins else None
        elif ide == "antigravity_ide":
            wins = [w for w in gw.getAllWindows() if "antigravity" in w.title.lower()]
            win = wins[0] if wins else None
        elif ide == "oc":
            win = inj.find_terminal_window_for_process("opencode")

        if not win:
            return jsonify({"ok": False, "error": f"未找到 {ide.upper()} 窗口"})

        inj.activate_window(win)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(0.3)

        return jsonify({"ok": True, "message": f"已粘贴到 {ide.upper()}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@phone_bp.route('/history')
def get_history():
    history = read_history()
    limit = request.args.get('limit', type=int)
    if limit:
        history = history[-limit:]
    return jsonify(history)


@phone_bp.route('/send', methods=['POST'])
def send_message():
    data = request.json or {}
    msg = data.get("text", "").strip()
    target = data.get("target", "auto").strip()
    image = data.get("image")
    request_task_id = data.get("task_id")
    owned_paths = _normalize_owned_paths(data.get("owned_paths"))

    if not msg:
        return jsonify({"ok": False, "raw": "Empty message"})

    history = read_history()
    now_str = datetime.now().strftime("%H:%M:%S")
    user_history_entry = {
        "sender": "user",
        "text": msg,
        "time": now_str,
        "target": target,
        "image": image,
        "owned_paths": owned_paths
    }
    if request_task_id:
        user_history_entry["task_id"] = request_task_id
    history.append(user_history_entry)
    write_history(history)

    runtime, _dispatch_task, _is_ide_reachable, SUPPORTED_IDES = _get_phone_deps()
    is_screen_locked, wake_screen = _get_screen_deps()
    _load_settings = _get_settings_loader()

    effective_target = target
    if target == "auto":
        for ide in SUPPORTED_IDES:
            if _is_ide_reachable(ide):
                effective_target = ide
                break

    if effective_target in SUPPORTED_IDES:
        screen_woke = False
        if is_screen_locked():
            screen_woke = True
            threading.Thread(target=wake_screen, daemon=True).start()
            time.sleep(0.3)

        from routes.task_routes_injection import _inject_to_ide

        ok, reply = _inject_to_ide(effective_target, msg, "")
        user_history_entry["target"] = effective_target
        history.append({
            "sender": "agent",
            "text": reply,
            "time": datetime.now().strftime("%H:%M:%S"),
            "target": effective_target,
        })
        write_history(history)
        return jsonify({
            "ok": ok,
            "raw": reply,
            "routed_to": effective_target,
            "screen_woke": screen_woke
        })

    else:
        try:
            from model_registry import call_model, get_active_models

            settings = _load_settings()
            xiaomengling_model = settings.get("xiaomengling_model", "")

            if not xiaomengling_model:
                active = get_active_models()
                if active:
                    xiaomengling_model = next(iter(active))

            if not xiaomengling_model:
                reply = "Aide 未配置模型，请在设置→模型管理中添加并启用至少一个模型"
                history.append({"sender": "agent", "text": reply, "time": datetime.now().strftime("%H:%M:%S"), "target": "aide"})
                write_history(history)
                return jsonify({"ok": False, "raw": reply, "routed_to": "aide"})

            project_dir = settings.get("project_dir", "").strip()
            tools_enabled = bool(project_dir and os.path.isdir(project_dir))

            system_prompt = (
                "你是 Aide，AideLink 的 AI 助手。你运行在用户的手机/平板上，通过 AideLink 桥接服务与用户对话。"
                "请简洁、有帮助地回答用户的问题。"
            )
            if tools_enabled:
                system_prompt += (
                    f"\n\n你有文件操作能力，可以查看项目目录 '{project_dir}' 中的文件。"
                    "当用户问到项目代码、文件内容、代码结构相关的问题时，"
                    "请主动使用 read_file、list_dir、search_files 工具来查看文件后回答。"
                )

            messages = [{"role": "system", "content": system_prompt}]
            recent = [h for h in history if h.get("target") in ("xiaomengling", "aidelink", "aide", "auto", None, "")]
            for h in recent[-20:]:
                role = "assistant" if h.get("sender") == "agent" else "user"
                messages.append({"role": role, "content": h.get("text", "")})

            image_context = ""
            if image:
                image_context = f"\n[用户发送了一张图片: {image}]"
            messages.append({"role": "user", "content": msg + image_context})

            tools = XIAOMENGLING_TOOLS if tools_enabled else None

            reply = ""
            for _ in range(5):
                result = call_model(xiaomengling_model, messages, timeout=90, tools=tools)
                if not result.get("ok"):
                    reply = f"模型调用失败: {result.get('error', '未知错误')}"
                    break

                content = result.get("content", "").strip()
                tool_calls = result.get("tool_calls")

                if not tool_calls:
                    reply = content or "（模型返回了空回复）"
                    break

                messages.append({
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": tool_calls,
                })

                for tc in tool_calls:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    try:
                        fn_args = json.loads(fn.get("arguments", "{}"))
                    except Exception:
                        fn_args = {}
                    tool_result = _execute_xiaomengling_tool(fn_name, fn_args, project_dir)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": tool_result,
                    })
            else:
                if not reply:
                    reply = "（达到最大工具调用次数）"

        except Exception as e:
            reply = f"Aide 请求异常: {e}"

        history.append({
            "sender": "agent",
            "text": reply,
            "time": datetime.now().strftime("%H:%M:%S"),
            "target": "aide",
        })
        write_history(history)
        return jsonify({"ok": True, "raw": reply, "routed_to": "aide"})


@phone_bp.route('/send/stream', methods=['POST'])
def send_message_stream():
    """流式发送消息到 Aide，返回 SSE 流。仅支持 Aide（非 IDE 注入）路径。"""
    from flask import Response
    data = request.json or {}
    msg = data.get("text", "").strip()
    target = data.get("target", "auto").strip()

    if not msg:
        return jsonify({"ok": False, "raw": "Empty message"})

    history = read_history()
    now_str = datetime.now().strftime("%H:%M:%S")
    user_history_entry = {
        "sender": "user", "text": msg, "time": now_str,
        "target": target, "image": data.get("image"),
    }
    history.append(user_history_entry)
    write_history(history)

    runtime, _dispatch_task, _is_ide_reachable, SUPPORTED_IDES = _get_phone_deps()
    _load_settings = _get_settings_loader()

    effective_target = target
    if target == "auto":
        for ide in SUPPORTED_IDES:
            if _is_ide_reachable(ide):
                effective_target = ide
                break

    # 如果有可用 IDE，走非流式派发（IDE 注入不支持流式）
    if effective_target in SUPPORTED_IDES:
        from routes.task_routes_injection import _inject_to_ide

        ok, reply = _inject_to_ide(effective_target, msg, "")
        user_history_entry["target"] = effective_target
        history.append({
            "sender": "agent", "text": reply,
            "time": datetime.now().strftime("%H:%M:%S"),
            "target": effective_target
        })
        write_history(history)

        def gen_ide():
            yield f"data: {json.dumps({'type': 'delta', 'content': reply}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'content': reply}, ensure_ascii=False)}\n\n"
        return Response(gen_ide(), mimetype="text/event-stream")

    # 无可用 IDE，走流式模型调用
    from model_registry import call_model_stream, get_active_models

    settings = _load_settings()
    xiaomengling_model = settings.get("xiaomengling_model", "")
    if not xiaomengling_model:
        active = get_active_models()
        if active:
            xiaomengling_model = next(iter(active))

    if not xiaomengling_model:
        reply = "Aide 未配置模型，请在设置→模型管理中添加并启用至少一个模型"
        history.append({"sender": "agent", "text": reply, "time": datetime.now().strftime("%H:%M:%S"), "target": "aide"})
        write_history(history)

        def gen_err():
            yield f"data: {json.dumps({'type': 'error', 'error': reply}, ensure_ascii=False)}\n\n"
        return Response(gen_err(), mimetype="text/event-stream")

    project_dir = settings.get("project_dir", "").strip()
    system_prompt = (
        "你是 Aide，AideLink 的 AI 助手。你运行在用户的手机/平板上，通过 AideLink 桥接服务与用户对话。"
        "请简洁、有帮助地回答用户的问题。"
    )
    if project_dir and os.path.isdir(project_dir):
        system_prompt += (
            f"\n\n你有文件操作能力，可以查看项目目录 '{project_dir}' 中的文件。"
            "当用户问到项目代码、文件内容、代码结构相关的问题时，"
            "请主动使用 read_file、list_dir、search_files 工具来查看文件后回答。"
        )

    messages = [{"role": "system", "content": system_prompt}]
    recent = [h for h in history if h.get("target") in ("xiaomengling", "aidelink", "aide", "auto", None, "")]
    for h in recent[-20:]:
        role = "assistant" if h.get("sender") == "agent" else "user"
        messages.append({"role": role, "content": h.get("text", "")})

    image_context = ""
    if data.get("image"):
        image_context = f"\n[用户发送了一张图片: {data['image']}]"
    messages.append({"role": "user", "content": msg + image_context})

    # 流式调用不支持工具调用循环，直接单轮流式
    stream = call_model_stream(xiaomengling_model, messages, timeout=90)

    def generate():
        full_reply = ""
        try:
            for chunk in stream:
                chunk_type = chunk.get("type")
                if chunk_type == "delta":
                    full_reply += chunk.get("content", "")
                elif chunk_type == "thinking":
                    pass  # 思考部分也推送
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                if chunk_type == "error":
                    return
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"
            return

        # 流式完成后写入历史
        if full_reply:
            history.append({
                "sender": "agent", "text": full_reply,
                "time": datetime.now().strftime("%H:%M:%S"),
                "target": "aide",
            })
            write_history(history)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}
    return Response(generate(), mimetype="text/event-stream", headers=headers)


@phone_bp.route('/clipboard')
def get_clipboard():
    return jsonify(read_clipboard())


@phone_bp.route('/clipboard/append', methods=['POST'])
def append_clipboard():
    data = request.json or {}
    text = data.get("text", "").strip()
    if text:
        import pyperclip
        pyperclip.copy(text)
        history = read_clipboard()
        history.append({
            "text": text,
            "time": datetime.now().strftime("%H:%M:%S"),
            "source": "phone"
        })
        write_clipboard(history)
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Empty text"})


@phone_bp.route('/clipboard/clear', methods=['POST'])
def clear_clipboard():
    write_clipboard([])
    return jsonify({"status": "success"})


@phone_bp.route('/upload', methods=['POST'])
def upload_file():
    from werkzeug.utils import secure_filename

    if 'file' not in request.files:
        return jsonify({"ok": False, "raw": "No file part"})
    file = request.files['file']
    if file.filename == '':
        return jsonify({"ok": False, "raw": "No selected file"})

    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({"ok": False, "raw": "Invalid filename"}), 400

    ext = os.path.splitext(filename)[1].lower()
    if not is_allowed_upload(filename):
        return jsonify({"ok": False, "raw": f"File type '{ext}' not allowed"}), 400

    unique_filename = f"{int(time.time())}_{filename}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)

    file.save(file_path)

    file_size = os.path.getsize(file_path)
    if file_size > MAX_UPLOAD_SIZE:
        os.remove(file_path)
        return jsonify({"ok": False, "raw": f"File too large ({file_size} > {MAX_UPLOAD_SIZE})"}), 413

    to_clipboard = request.form.get('to_clipboard', 'false').lower() == 'true'
    clipboard_ok = None
    if to_clipboard and ext in ('.png', '.jpg', '.jpeg', '.bmp'):
        clipboard_ok = set_image_to_clipboard(file_path)

    file_url = f"/uploads/{unique_filename}"
    return jsonify({"ok": True, "path": file_path, "url": file_url, "clipboard_ok": clipboard_ok})


@phone_bp.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)
