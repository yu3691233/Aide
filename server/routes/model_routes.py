import os
from pathlib import Path
from flask import Blueprint, request, jsonify
from paths import BRIDGE_DIR as BASE_DIR

model_bp = Blueprint('model', __name__)


# ============================================================
# Aide 模型管理 API
# ============================================================

@model_bp.route("/api/xiaomengling/models")
def api_xiaomengling_models():
    """获取所有模型列表"""
    import model_registry
    models = model_registry.list_all_keys()
    default_model = model_registry.get_default_model()
    return jsonify({"success": True, "models": models, "default_model": default_model})


@model_bp.route("/api/xiaomengling/models/default", methods=["POST"])
def api_xiaomengling_models_default():
    """设置默认模型"""
    import model_registry
    data = request.get_json(force=True)
    key = data.get("key")
    if not key:
        return jsonify({"success": False, "message": "缺少 key"})
    ok, msg = model_registry.set_default_model(key)
    return jsonify({"success": ok, "message": msg})


@model_bp.route("/api/xiaomengling/models/toggle", methods=["POST"])
def api_xiaomengling_models_toggle():
    """启用/禁用模型"""
    import model_registry
    data = request.get_json(force=True)
    key = data.get("key")
    enabled = data.get("enabled", True)
    if not key:
        return jsonify({"success": False, "message": "缺少 key"})
    ok, msg = model_registry.set_enabled(key, enabled)
    return jsonify({"success": ok, "message": msg})


@model_bp.route("/api/xiaomengling/models/apikey", methods=["POST"])
def api_xiaomengling_models_apikey():
    """设置模型 API Key"""
    import model_registry
    data = request.get_json(force=True)
    key = data.get("key")
    api_key = data.get("api_key")
    if not key:
        return jsonify({"success": False, "message": "缺少 key"})
    ok, msg = model_registry.upsert_model(key, {"api_key": api_key})
    return jsonify({"success": ok, "message": msg})


@model_bp.route("/api/xiaomengling/models/upsert", methods=["POST"])
def api_xiaomengling_models_upsert():
    """新增或更新模型"""
    import model_registry
    data = request.get_json(force=True)
    key = data.get("key")
    if not key:
        return jsonify({"success": False, "message": "缺少 key"})
    ok, msg = model_registry.upsert_model(key, data)
    return jsonify({"success": ok, "message": msg})


@model_bp.route("/api/xiaomengling/models/delete", methods=["POST"])
def api_xiaomengling_models_delete():
    """删除模型"""
    import model_registry
    data = request.get_json(force=True)
    key = data.get("key")
    if not key:
        return jsonify({"success": False, "message": "缺少 key"})
    ok, msg = model_registry.delete_model(key)
    return jsonify({"success": ok, "message": msg})
