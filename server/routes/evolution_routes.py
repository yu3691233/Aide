import time
from flask import Blueprint, request, jsonify

import model_registry
from config import SYSTEM_PROMPT, load_settings

evolution_bp = Blueprint('evolution', __name__)


@evolution_bp.route('/evolution/submit', methods=['POST'])
def evolution_submit():
    data = request.json or {}
    msg = data.get("message", "")
    task_type = data.get("task_type", "chat")

    if not msg:
        return jsonify({"ok": False, "error": "缺少 message"}), 400

    task_id = f"task_{int(time.time())}"

    settings = load_settings()
    model_key = data.get("model") or settings.get("xiaomengling_model") or model_registry.get_default_model()
    if model_key in ("free", "auto", "default"):
        model_key = model_registry.get_default_model()

    if model_key not in model_registry.get_active_models():
        fallback = model_registry.get_default_model()
        if fallback == model_key or fallback not in model_registry.get_active_models():
            return jsonify({
                "ok": False,
                "task_id": task_id,
                "success": False,
                "error": f"模型 {model_key} 未激活或缺少 API Key",
            }), 400
        model_key = fallback

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": msg},
    ]
    result = model_registry.call_model(model_key, messages, timeout=120)
    if not result.get("ok"):
        return jsonify({
            "ok": False,
            "task_id": task_id,
            "success": False,
            "model_used": model_key,
            "error": result.get("error") or "模型调用失败",
        }), 502

    return jsonify({
        "ok": True,
        "task_id": task_id,
        "success": True,
        "model_used": model_key,
        "task_type": task_type,
        "response": result.get("content", ""),
        "finish_reason": result.get("finish_reason"),
    })


@evolution_bp.route('/evolution/task/<task_id>')
def evolution_task_status(task_id):
    return jsonify({"status": "completed", "result": "Execution succeeded"})
