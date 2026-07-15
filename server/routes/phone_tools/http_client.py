"""Aide 工具内部调用的 HTTP 客户端。

所有 Aide 工具通过本模块调用 AideLink 自身的 HTTP endpoint，统一走 Flask 路由层，
复用现有鉴权/日志/错误处理，避免直接读文件系统或绕过路由。
"""
import json
import urllib.request
import urllib.error

# AideLink Flask 服务本地地址。端口与 manager_app 启动端口一致。
_DEFAULT_BASE = "http://127.0.0.1:5000"
_DEFAULT_TIMEOUT = 15


def _base_url():
    """允许通过环境变量覆盖基址，默认 127.0.0.1:5000。"""
    import os
    return os.environ.get("AIDELINK_LOCAL_BASE", _DEFAULT_BASE).rstrip("/")


def call(method, path, query=None, body=None, timeout=_DEFAULT_TIMEOUT, raw_bytes=False):
    """调用 AideLink HTTP endpoint。

    参数:
        method: "GET" / "POST" 等
        path:   "/api/tasks" 等，开头必须有 /
        query:  dict 查询参数
        body:   dict 请求体（POST/PUT），JSON 序列化
        timeout: 超时秒数
        raw_bytes: True 时返回 (status, bytes, headers)，False 时返回 (status, parsed_json_or_text, headers)

    返回:
        (status_code, data, headers_dict)
        data 在 raw_bytes=False 时：JSON 响应返回解析后的 dict/list；非 JSON 返回字符串
    """
    url = _base_url() + path
    if query:
        from urllib.parse import urlencode
        url += "?" + urlencode(query)

    data_bytes = None
    headers = {}
    if body is not None:
        data_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data_bytes, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read()
            resp_headers = dict(resp.headers)
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read() or b""
        resp_headers = dict(e.headers) if e.headers else {}
    except urllib.error.URLError as e:
        return 0, {"error": f"无法连接 AideLink 服务: {e.reason}"}, {}
    except Exception as e:
        return 0, {"error": f"调用失败: {e}"}, {}

    if raw_bytes:
        return status, raw, resp_headers

    # 尝试 JSON 解析
    try:
        return status, json.loads(raw.decode("utf-8")), resp_headers
    except Exception:
        return status, raw.decode("utf-8", errors="replace"), resp_headers


def get(path, query=None, timeout=_DEFAULT_TIMEOUT):
    """GET 请求，返回 (status, json_or_text)。"""
    status, data, _ = call("GET", path, query=query, timeout=timeout)
    return status, data


def get_bytes(path, query=None, timeout=_DEFAULT_TIMEOUT):
    """GET 请求，返回 (status, bytes, headers)。用于截图等二进制响应。"""
    return call("GET", path, query=query, timeout=timeout, raw_bytes=True)


def post(path, body=None, timeout=_DEFAULT_TIMEOUT):
    """POST 请求，返回 (status, json_or_text)。"""
    status, data, _ = call("POST", path, body=body, timeout=timeout)
    return status, data


def summarize_status(status, data, ok_codes=(200,)):
    """统一的状态判断，返回 (ok_bool, summary_string)。

    summary 适合直接塞给 Aide 模型作为工具结果。
    """
    if status not in ok_codes:
        return False, f"HTTP {status}: {data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)[:500]}"
    if isinstance(data, dict) and data.get("error"):
        return False, f"错误: {data['error']}"
    return True, data
