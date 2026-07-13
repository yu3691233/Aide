"""
OC Web 代理 Blueprint
从 phone_chat_bridge.py 迁移的 /oc-web/* 路由
"""
import os
import requests
from flask import Blueprint, request, Response

from paths import BRIDGE_DIR
from json_utils import safe_read_json

oc_web_bp = Blueprint('oc_web', __name__)


@oc_web_bp.route('/oc-web/')
@oc_web_bp.route('/oc-web/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def oc_web_proxy(subpath=''):
    """OC Web 反向代理（供 FRP 模式访问本地 4096 端口）"""
    settings_file = os.path.join(BRIDGE_DIR, "aidelink_settings.json")
    settings = safe_read_json(settings_file, {})
    port = settings.get("opencode_web_port", 4096)
    target = f"http://127.0.0.1:{port}/{subpath}"
    if request.query_string:
        target += f"?{request.query_string.decode()}"
    try:
        headers = {k: v for k, v in request.headers if k.lower() not in ('host', 'transfer-encoding')}
        body = request.get_data()
        resp = requests.request(
            method=request.method, url=target, headers=headers, data=body, timeout=30,
            allow_redirects=False,
        )
        excluded_headers = {'content-encoding', 'content-length', 'transfer-encoding', 'connection'}
        resp_headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded_headers]
        return Response(resp.content, status=resp.status_code, headers=resp_headers)
    except requests.ConnectionError:
        return Response("OC Web 未运行", status=502)
    except Exception as e:
        return Response(f"代理错误: {e}", status=502)
