import sys
from pathlib import Path
from flask import Blueprint, request, jsonify

log_bp = Blueprint('logs', __name__)

BASE_DIR = Path(__file__).parent.parent


@log_bp.route("/api/logs")
def api_logs():
    """返回最近的日志行"""
    from manager_utils import read_log_lines, LOG_FILE
    lines = request.args.get("lines", 200, type=int)
    return jsonify({"logs": read_log_lines(LOG_FILE, lines)})


@log_bp.route("/api/logs/phone")
def api_phone_logs():
    """返回最近上报的手机端日志行"""
    from manager_utils import read_phone_log_lines
    lines = request.args.get("lines", 200, type=int)
    return jsonify({"logs": read_phone_log_lines(lines)})


@log_bp.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    """清空日志文件"""
    from manager_utils import LOG_FILE
    data = request.get_json(force=True) if request.data else {}
    log_type = data.get("type", "desktop")
    file_to_clear = BASE_DIR / "phone_app.log" if log_type == "phone" else LOG_FILE

    try:
        with open(file_to_clear, "w", encoding="utf-8") as f:
            f.truncate(0)
        return jsonify({"success": True, "message": f"{'手机端' if log_type == 'phone' else '电脑端'}日志已清空"})
    except Exception as e:
        return jsonify({"success": False, "message": f"清空失败: {e}"})


@log_bp.route("/api/logs/analyze", methods=["POST"])
def api_logs_analyze():
    """使用 Aide 分析日志"""
    from manager_utils import read_log_lines, read_phone_log_lines
    try:
        data = request.get_json(force=True) if request.data else {}
        log_type = data.get("type", "desktop")

        if log_type == "phone":
            logs = read_phone_log_lines(100)
        else:
            logs = read_log_lines(LOG_FILE, 100)

        error_logs = [l for l in logs if "ERROR" in l or "Exception" in l or "Traceback" in l or "Error" in l or "E/" in l or "FATAL" in l]

        content_to_analyze = "\n".join(error_logs if error_logs else logs[-50:])
        if not content_to_analyze.strip():
            return jsonify({"success": False, "message": "日志内容为空，无需分析。"})

        from call_assistant import ask_assistant
        prompt = f"请翻译并深度解析以下系统日志中的错误与异常情况，用通俗易懂的中文说明发生了什么问题，并给出具体的修复步骤与建议：\n\n```\n{content_to_analyze}\n```"
        sys_prompt = "你是一个专业的系统运维与代码调试专家。擅长分析各种报错日志并提供清晰准确的中文翻译、原理解释和解决方案。"

        result = ask_assistant(prompt, sys_prompt)
        return jsonify({"success": True, "analysis": result})
    except Exception as e:
        return jsonify({"success": False, "message": f"解析失败: {e}"})


@log_bp.route("/api/logs/stream")
def api_logs_stream():
    """SSE 实时日志流"""
    from manager_utils import log_stream_generator, LOG_FILE
    from flask import Response, stream_with_context
    return Response(
        stream_with_context(log_stream_generator(LOG_FILE)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
