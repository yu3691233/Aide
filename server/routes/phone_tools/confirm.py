"""二段式确认机制：高风险操作先返回确认 token，用户在手机端确认后才执行。

机制:
1. Aide 调用高风险工具（如 stop_service/restart_ide）时，工具 handler 不直接执行，
   而是生成一个 confirm_token，把"待执行操作描述"存入内存待确认表。
2. 工具返回给 Aide："操作 X 需要用户确认，已生成确认请求，请在手机端点击确认"。
3. 手机 App 拉取待确认列表，用户点击确认后，调用 /phone/tools/confirm 接口，
   传入 confirm_token，触发真正执行。
4. 确认 token 5 分钟过期。

当前首批只读工具不需要确认，此模块为后续高风险工具预留。
"""
import time
import uuid
import threading

_PENDING_CONFIRMS = {}
_LOCK = threading.Lock()
_EXPIRE_SECONDS = 300  # 5 分钟


def request_confirm(action_desc, execute_callback):
    """登记一个待确认的高风险操作。

    参数:
        action_desc: 人类可读的操作描述，如"停止 Trae IDE"
        execute_callback: 无参数可调用对象，确认后执行

    返回:
        confirm_token (str)，用于返回给 Aide 和手机端确认。
    """
    token = uuid.uuid4().hex[:12]
    with _LOCK:
        _expire_old_locked()
        _PENDING_CONFIRMS[token] = {
            "desc": action_desc,
            "callback": execute_callback,
            "created_at": time.time(),
        }
    return token


def execute_confirmed(token):
    """用户确认后调用，执行挂起的操作。

    返回:
        (ok, result_or_error)
    """
    with _LOCK:
        _expire_old_locked()
        entry = _PENDING_CONFIRMS.pop(token, None)
    if not entry:
        return False, "确认 token 不存在或已过期"
    try:
        result = entry["callback"]()
        return True, result
    except Exception as e:
        return False, f"执行失败: {e}"


def list_pending():
    """列出所有待确认操作（供手机 App 拉取）。"""
    with _LOCK:
        _expire_old_locked()
        return [
            {"token": t, "desc": e["desc"], "created_at": e["created_at"]}
            for t, e in _PENDING_CONFIRMS.items()
        ]


def cancel_confirm(token):
    """取消一个待确认操作。"""
    with _LOCK:
        _PENDING_CONFIRMS.pop(token, None)


def _expire_old_locked():
    """清理过期条目（调用方需持锁）。"""
    now = time.time()
    expired = [t for t, e in _PENDING_CONFIRMS.items() if now - e["created_at"] > _EXPIRE_SECONDS]
    for t in expired:
        _PENDING_CONFIRMS.pop(t, None)
