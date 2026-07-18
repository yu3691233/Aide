import base64
import io
from pathlib import Path

from flask import Blueprint, jsonify, make_response, request
from PIL import Image

from prompt_composer import compose_prompt
from paths import BRIDGE_DIR, UPLOAD_FOLDER


prompt_bp = Blueprint("prompt_compose", __name__)


def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


def _prepare_image_data_url(image_ref):
    """Resolve only Bridge-owned images and compress them before model upload."""
    ref = str(image_ref or "").strip()
    if not ref:
        return None
    name = Path(ref.replace("\\", "/")).name
    candidates = [Path(UPLOAD_FOLDER) / name, Path(BRIDGE_DIR) / name]
    allowed_roots = [Path(UPLOAD_FOLDER).resolve(), Path(BRIDGE_DIR).resolve()]
    source = None
    for candidate in candidates:
        resolved = candidate.resolve()
        if any(resolved == root or root in resolved.parents for root in allowed_roots) and resolved.is_file():
            source = resolved
            break
    if source is None or source.stat().st_size > 20 * 1024 * 1024:
        return None
    try:
        with Image.open(source) as image:
            image = image.convert("RGB")
            image.thumbnail((1280, 1920))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=76, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except Exception:
        return None


@prompt_bp.route("/api/prompt/compose", methods=["POST", "OPTIONS"])
def api_prompt_compose():
    if request.method == "OPTIONS":
        return _cors(make_response("", 204))

    data = request.get_json(silent=True) or {}
    image_data_url = _prepare_image_data_url(data.get("image"))

    def call_default_model(messages):
        from model_registry import call_model, get_default_model, get_model
        model_key = "minimax-m3" if image_data_url and get_model("minimax-m3") else get_default_model()
        return call_model(
            model_key,
            messages,
            max_tokens=800,
            temperature=0.1,
            timeout=45,
            response_format={"type": "json_object"},
        )

    result = compose_prompt(data, model_caller=call_default_model, image_data_url=image_data_url)
    result["image_used"] = bool(image_data_url and result.get("used_ai"))
    return _cors(jsonify(result))
