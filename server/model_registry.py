"""
AideLink 模型注册中心 —— 全局动态模型池

设计目标：
  1. 用户在 manager.py 管理面板里能增删改模型条目；
  2. 任何消费者（Aide、phone_chat_bridge、call_co_workers、call_assistant）
     都不再硬编码 model_id / api_key，全部从本模块读；
  3. api_key 用本地 JSON 明文存储（用户主动录入，非仓库硬编码），
     文件不进 git（.gitignore 已覆盖），读写都加权限提示；
  4. 运行时支持热加载（修改后消费者下次调用自动取到）。

架构：
  PRESETS  =  硬编码的"系统预设"，不可删除，只能补 api_key 才能用
  USER_FILE = 用户自定义模型 + 用户填的 api_key，原子写 JSON
  读取优先级：USER_FILE 中显式启用的预设 > PRESETS > USER_FILE 中禁用的预设

消费者接口：
  get_active_models()         ->  dict[model_key, ModelEntry]   # 全部当前可用模型
  get_model(key)              ->  ModelEntry | None
  call_model(key, messages)   ->  dict                          # 统一调用入口，自动选 provider
"""

import json
import os
import threading
import time
from datetime import datetime
from typing import Optional


MODEL_ALIAS_KEYS = {"auto", "free", "default"}


# ═══════════════════════════════════════════════════════════════
# 预设模型（系统内置，不可删除）
# 设计原则：列齐市面主流模型，用户填 api_key 即可用
# ═══════════════════════════════════════════════════════════════

PRESETS = {
    # ── 国际厂商（OpenAI 协议兼容） ────────────────────────────
    "gpt-4o": {
        "provider": "openai",
        "model_id": "gpt-4o",
        "api_url": "https://api.openai.com/v1/chat/completions",
        "caps": ["chat", "code", "qa", "summary", "translate", "complex_code", "architecture"],
        "description": "OpenAI GPT-4o（多模态旗舰）",
        "needs_api_key": True,
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "model_id": "gpt-4o-mini",
        "api_url": "https://api.openai.com/v1/chat/completions",
        "caps": ["chat", "code", "qa", "summary", "translate", "simple_code"],
        "description": "OpenAI GPT-4o Mini（性价比）",
        "needs_api_key": True,
    },
    "claude-sonnet-4": {
        "provider": "anthropic",
        "model_id": "claude-sonnet-4-20250514",
        "api_url": "https://api.anthropic.com/v1/messages",
        "caps": ["chat", "code", "qa", "summary", "complex_code", "architecture", "debug_hard"],
        "description": "Anthropic Claude Sonnet 4（编程强项）",
        "needs_api_key": True,
    },
    "claude-haiku-3.5": {
        "provider": "anthropic",
        "model_id": "claude-3-5-haiku-20241022",
        "api_url": "https://api.anthropic.com/v1/messages",
        "caps": ["chat", "code", "qa", "summary", "translate", "simple_code"],
        "description": "Anthropic Claude Haiku 3.5（快速）",
        "needs_api_key": True,
    },
    "gemini-2.5-pro": {
        "provider": "google",
        "model_id": "gemini-2.5-pro",
        "api_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent",
        "caps": ["chat", "code", "qa", "summary", "complex_code", "architecture", "full_stack"],
        "description": "Google Gemini 2.5 Pro（超长上下文）",
        "needs_api_key": True,
    },
    "gemini-2.0-flash": {
        "provider": "google",
        "model_id": "gemini-2.0-flash",
        "api_url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "caps": ["chat", "code", "qa", "summary", "translate", "simple_code"],
        "description": "Google Gemini 2.0 Flash（快速免费）",
        "needs_api_key": True,
    },

    # ── 国产厂商 ───────────────────────────────────────────────
    "deepseek-chat": {
        "provider": "deepseek",
        "model_id": "deepseek-chat",
        "api_url": "https://api.deepseek.com/v1/chat/completions",
        "caps": ["chat", "code", "qa", "summary", "translate", "complex_code", "debug_hard"],
        "description": "DeepSeek Chat（V3，国产代码强）",
        "needs_api_key": True,
    },
    "deepseek-coder": {
        "provider": "deepseek",
        "model_id": "deepseek-coder",
        "api_url": "https://api.deepseek.com/v1/chat/completions",
        "caps": ["code", "file_op", "debug", "refactor", "complex_code"],
        "description": "DeepSeek Coder（编程专用）",
        "needs_api_key": True,
    },
    "qwen-max": {
        "provider": "qwen",
        "model_id": "qwen-max",
        "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "caps": ["chat", "code", "qa", "summary", "translate", "complex_code"],
        "description": "阿里通义千问 Qwen Max",
        "needs_api_key": True,
    },
    "qwen-coder-plus": {
        "provider": "qwen",
        "model_id": "qwen-coder-plus",
        "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "caps": ["code", "file_op", "debug", "refactor", "complex_code", "full_stack"],
        "description": "阿里通义千问 Coder Plus（编程专用）",
        "needs_api_key": True,
    },
    "glm-4-plus": {
        "provider": "zhipu",
        "model_id": "glm-4-plus",
        "api_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "caps": ["chat", "code", "qa", "summary", "translate", "complex_code"],
        "description": "智谱 GLM-4 Plus",
        "needs_api_key": True,
    },
    "doubao-pro": {
        "provider": "doubao",
        "model_id": "doubao-pro-256k",
        "api_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "caps": ["chat", "code", "qa", "summary", "complex_code", "full_stack"],
        "description": "字节豆包 Pro 256K",
        "needs_api_key": True,
    },
    "hunyuan-pro": {
        "provider": "tencent",
        "model_id": "hunyuan-pro",
        "api_url": "https://api.hunyuan.tencent.com/v1/chat/completions",
        "caps": ["chat", "code", "qa", "summary", "complex_code"],
        "description": "腾讯混元 Pro",
        "needs_api_key": True,
    },
    "minimax-m3": {
        "provider": "minimax",
        "model_id": "minimax-m3",
        "api_url": "https://api.minimax.chat/v1/chat/completions",
        "caps": ["chat", "qa", "summary", "simple_code", "translate"],
        "description": "MiniMax-M3（Aide 默认）",
        "needs_api_key": True,
    },

    # ── 本地/自托管 ────────────────────────────────────────────
    "ollama-local": {
        "provider": "ollama",
        "model_id": "qwen2.5:3b",
        "api_url": "http://localhost:11434/v1/chat/completions",
        "caps": ["chat", "code", "qa", "summary", "simple_code"],
        "description": "Ollama 本地千问 Qwen 2.5 3B",
        "needs_api_key": False,
    },
}


# ═══════════════════════════════════════════════════════════════
# 文件 I/O
# ═══════════════════════════════════════════════════════════════

BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_FILE = os.path.join(BRIDGE_DIR, "aidelink_models.json")

_lock = threading.Lock()


from json_utils import safe_read_json, safe_write_json


def _load_user_file() -> dict:
    """
    读取用户层模型文件。
    结构：
      {
        "<model_key>": {
          "enabled": bool,         # 是否启用（缺失视为启用）
          "api_key": "...",        # 用户填的 key（缺失或 None 表示没填）
          "extra": {...},          # 自定义模型专有字段（model_id/api_url/provider/caps/description）
        },
        ...
      }
    """
    if not os.path.exists(USER_FILE):
        return {}
    with _lock:
        data = safe_read_json(USER_FILE, {})
    if not isinstance(data, dict):
        return {}
    return data


def _save_user_file(data: dict) -> bool:
    """原子写用户层。"""
    with _lock:
        return safe_write_json(USER_FILE, data)


# ═══════════════════════════════════════════════════════════════
# 公开 API
# ═══════════════════════════════════════════════════════════════

def get_active_models() -> dict:
    """
    返回当前所有可用模型（合并 PRESETS + 用户层）。
    预设：用户没禁用且填了 api_key → 启用
    自定义：enabled=true → 启用
    """
    user = _load_user_file()
    out = {}

    # 1) 预设
    for key, meta in PRESETS.items():
        u = user.get(key, {})
        if u.get("enabled") is False:
            continue  # 用户显式禁用
        if meta["needs_api_key"] and not u.get("api_key"):
            continue  # 需要 key 但没填
        out[key] = {
            **meta,
            "key": key,
            "source": "preset",
            "api_key": u.get("api_key"),
        }

    # 2) 用户自定义
    for key, u in user.items():
        if key in PRESETS:
            continue  # 已在上面处理
        if key.startswith("__"):
            continue
        if not u.get("enabled", True):
            continue
        extra = u.get("extra", {})
        if not extra.get("model_id") or not extra.get("api_url"):
            continue  # 自定义必须填 model_id + api_url
        out[key] = {
            "provider": extra.get("provider", "custom"),
            "model_id": extra["model_id"],
            "api_url": extra["api_url"],
            "caps": extra.get("caps", ["chat", "code"]),
            "description": extra.get("description", key),
            "needs_api_key": bool(extra.get("needs_api_key", True)),
            "key": key,
            "source": "custom",
            "api_key": u.get("api_key"),
        }

    return out


def get_model(key: str) -> Optional[dict]:
    """单查一个模型（含 api_key 等敏感信息）。"""
    return get_active_models().get(key)


def list_all_keys() -> list:
    """返回所有预设 + 自定义 key（用于管理面板展示）。"""
    user = _load_user_file()
    out = []
    for key, meta in PRESETS.items():
        u = user.get(key, {})
        out.append({
            "key": key,
            "provider": meta["provider"],
            "model_id": meta["model_id"],
            "caps": meta["caps"],
            "description": meta["description"],
            "source": "preset",
            "needs_api_key": meta["needs_api_key"],
            "has_api_key": bool(u.get("api_key")),
            "enabled": u.get("enabled", True),
        })
    for key, u in user.items():
        if key in PRESETS:
            continue
        if key.startswith("__"):
            continue
        extra = u.get("extra", {})
        out.append({
            "key": key,
            "provider": extra.get("provider", "custom"),
            "model_id": extra.get("model_id", ""),
            "caps": extra.get("caps", []),
            "description": extra.get("description", ""),
            "source": "custom",
            "needs_api_key": bool(extra.get("needs_api_key", True)),
            "has_api_key": bool(u.get("api_key")),
            "enabled": u.get("enabled", True),
        })
    return out


def get_default_model() -> str:
    """获取当前默认模型。如果未设置或不可用，回退到 minimax-m3 或其他可用模型。"""
    user = _load_user_file()
    default_key = user.get("__default_model__", "minimax-m3")
    active = get_active_models()
    if default_key in active and default_key not in MODEL_ALIAS_KEYS:
        return default_key
    if "minimax-m3" in active:
        return "minimax-m3"
    real_models = [key for key in active if key not in MODEL_ALIAS_KEYS]
    if real_models:
        return real_models[0]
    return "minimax-m3"


def set_default_model(key: str) -> tuple:
    """设置默认模型。"""
    active = get_active_models()
    if key not in active:
        return False, f"模型 {key} 未激活或不存在，无法设为默认"
    user = _load_user_file()
    user["__default_model__"] = key
    if _save_user_file(user):
        return True, "设置默认模型成功"
    return False, "保存失败"


def upsert_model(key: str, payload: dict) -> tuple:
    """
    新增或更新一个模型。
    payload 字段：
      - enabled: bool (可选，默认 True)
      - api_key: str (可选，preset 需要填才能用)
      - extra: {provider, model_id, api_url, caps, description, needs_api_key} (仅自定义模型需要)
    返回 (ok: bool, message: str)
    """
    if key.startswith("__"):
        return False, "非法的模型 Key 命名"
    user = _load_user_file()
    is_preset = key in PRESETS

    if is_preset:
        # 预设只能改 enabled + api_key
        cur = user.get(key, {})
        cur["enabled"] = payload.get("enabled", cur.get("enabled", True))
        if "api_key" in payload:
            cur["api_key"] = payload["api_key"]
        user[key] = cur
    else:
        # 自定义模型必填字段
        extra = payload.get("extra", {})
        if not extra.get("model_id") or not extra.get("api_url"):
            return False, "自定义模型必须填写 model_id 和 api_url"
        user[key] = {
            "enabled": payload.get("enabled", True),
            "api_key": payload.get("api_key"),
            "extra": extra,
        }

    if _save_user_file(user):
        return True, "保存成功"
    return False, "保存失败"


def delete_model(key: str) -> tuple:
    """删除一个模型。预设不可删（返回 False）。"""
    if key.startswith("__") or key in PRESETS:
        return False, "预设或系统内置条目不可删除"
    user = _load_user_file()
    if key not in user:
        return False, f"模型 {key} 不存在"
    del user[key]
    if _save_user_file(user):
        return True, "删除成功"
    return False, "删除失败"


def set_enabled(key: str, enabled: bool) -> tuple:
    """启用/禁用一个模型。"""
    if key.startswith("__"):
        return False, "非法的模型 Key 命名"
    user = _load_user_file()
    cur = user.get(key, {})
    cur["enabled"] = enabled
    user[key] = cur
    if _save_user_file(user):
        return True, f"{'启用' if enabled else '禁用'}成功"
    return False, "保存失败"


# ═══════════════════════════════════════════════════════════════
# 文本工具调用解析（兼容不返回标准 tool_calls 的代理服务）
# ═══════════════════════════════════════════════════════════════

import re as _re

# 匹配 <]minimax[><tool_call>...<]minimax[><invoke name="xxx">...<]minimax[><param>value</param>...
_MINIMAX_INVOKE_RE = _re.compile(
    r'<invoke\s+name=["\']([\w_]+)["\']>(.*?)</invoke>',
    _re.DOTALL,
)
_MINIMAX_PARAM_RE = _re.compile(r'<(\w+)>(.*?)</\w*>', _re.DOTALL)
# 匹配 [Tool Call: xxx] 后跟 JSON 块
_BRACKET_CALL_RE = _re.compile(
    r'\[Tool\s*Call[:\s]*([\w_]+)\]\s*\n?\s*(\{[^{}]*\})',
    _re.IGNORECASE,
)


def _parse_text_tool_calls(content: str) -> list:
    """从模型文本输出中解析非标准的工具调用，返回标准 tool_calls 列表。

    兼容格式：
    1. <]minimax[> 标签格式（aicncn 代理透传的 MiniMax 原生格式）
    2. [Tool Call: name] + JSON 参数
    """
    if not content:
        return []
    calls = []

    # 1. MiniMax 原生标签格式：先清除 <]minimax[> 包装标签，再解析 invoke
    cleaned = content.replace('<]minimax[>', '')
    for m in _MINIMAX_INVOKE_RE.finditer(cleaned):
        name = m.group(1).strip()
        body = m.group(2)
        args = {}
        for pm in _MINIMAX_PARAM_RE.finditer(body):
            # rstrip('[' 去除 <]minimax[> 闭合标记残留
            args[pm.group(1).strip()] = pm.group(2).strip().rstrip('[').strip()
        calls.append({
            "id": f"textcall-{len(calls)}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args, ensure_ascii=False),
            },
        })

    if calls:
        return calls

    # 2. [Tool Call: name] 格式（排除 [Tool Call Result] 等非调用块）
    for m in _BRACKET_CALL_RE.finditer(content):
        name = m.group(1).strip()
        if name.lower() in ("result", "results", "output", "response"):
            continue
        try:
            args = json.loads(m.group(2))
        except Exception:
            args = {}
        calls.append({
            "id": f"textcall-{len(calls)}",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps(args, ensure_ascii=False),
            },
        })

    return calls


def _strip_tool_call_text(content: str) -> str:
    """从 content 中移除已解析的工具调用标签，保留正常文本。"""
    if not content:
        return content
    # 移除 <]minimax[> 标签及其包裹的内容
    cleaned = _re.sub(r'<\]minimax\[>.*?(?=<\]minimax\[>|$)', '', content, flags=_re.DOTALL)
    # 移除残留的 <]minimax[> 标记
    cleaned = cleaned.replace('<]minimax[>', '')
    # 移除 [Tool Call: ...] 块
    cleaned = _BRACKET_CALL_RE.sub('', cleaned)
    return cleaned.strip()


# ═══════════════════════════════════════════════════════════════
# 统一调用入口
# ═══════════════════════════════════════════════════════════════

def call_model(key: str, messages: list, **kwargs) -> dict:
    """
    统一调用入口，根据 model 元信息自动选 provider 协议。
    返回 {"ok": bool, "content": str, "raw": str, "error": str | None,
           "tool_calls": list | None, "finish_reason": str | None}
    kwargs 支持: timeout, max_tokens, temperature, tools
    """
    import requests

    m = get_model(key)
    if not m:
        return {"ok": False, "content": "", "raw": "", "error": f"模型 {key} 不可用（未启用或缺 api_key）", "tool_calls": None, "finish_reason": None}

    provider = m["provider"]
    api_url = m["api_url"]
    api_key = m.get("api_key")
    model_id = m["model_id"]
    timeout = kwargs.get("timeout", 60)
    tools = kwargs.get("tools")

    try:
        if provider == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            system = None
            chat_msgs = []
            for msg in messages:
                if msg.get("role") == "system":
                    system = msg["content"]
                else:
                    chat_msgs.append(msg)
            body = {
                "model": model_id,
                "max_tokens": kwargs.get("max_tokens", 4096),
                "messages": chat_msgs,
            }
            if system:
                body["system"] = system
            if tools:
                anthropic_tools = []
                for t in tools:
                    fn = t.get("function", {})
                    anthropic_tools.append({
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {}),
                    })
                body["tools"] = anthropic_tools
            r = requests.post(api_url, headers=headers, json=body, timeout=timeout)
            if r.status_code != 200:
                return {"ok": False, "content": "", "raw": r.text, "error": f"HTTP {r.status_code}", "tool_calls": None, "finish_reason": None}
            data = r.json()
            stop_reason = data.get("stop_reason", "")
            content_blocks = data.get("content", [])
            text_parts = []
            tool_calls = []
            for block in content_blocks:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block.get("id", ""),
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    })
            content = "".join(text_parts)
            return {
                "ok": True, "content": content, "raw": r.text, "error": None,
                "tool_calls": tool_calls if tool_calls else None,
                "finish_reason": stop_reason,
            }

        elif provider == "google":
            user_text = "\n".join(
                m["content"] for m in messages if m.get("role") in ("user", "system")
            )
            url = f"{api_url}?key={api_key}"
            body = {"contents": [{"parts": [{"text": user_text}]}]}
            r = requests.post(url, json=body, timeout=timeout)
            if r.status_code != 200:
                return {"ok": False, "content": "", "raw": r.text, "error": f"HTTP {r.status_code}", "tool_calls": None, "finish_reason": None}
            data = r.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            return {"ok": True, "content": content, "raw": r.text, "error": None, "tool_calls": None, "finish_reason": "stop"}

        else:
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            body = {
                "model": model_id,
                "messages": messages,
                "temperature": kwargs.get("temperature", 0.7),
            }
            if "max_tokens" in kwargs:
                body["max_tokens"] = kwargs["max_tokens"]
            if "response_format" in kwargs:
                body["response_format"] = kwargs["response_format"]
            if tools:
                body["tools"] = tools
                body["tool_choice"] = "auto"
            r = requests.post(api_url, headers=headers, json=body, timeout=timeout)
            if r.status_code != 200:
                return {"ok": False, "content": "", "raw": r.text, "error": f"HTTP {r.status_code}", "tool_calls": None, "finish_reason": None}
            data = r.json()
            choice = data["choices"][0]
            msg = choice.get("message", {})
            content = msg.get("content", "") or ""
            tc = msg.get("tool_calls")
            finish = choice.get("finish_reason", "stop")
            # 某些代理服务（如 aicncn）不返回标准 tool_calls，而是把工具调用
            # 用自定义标签（<]minimax[>、[Tool Call:]）塞进 content，尝试解析
            if not tc and tools:
                parsed = _parse_text_tool_calls(content)
                if parsed:
                    tc = parsed
                    content = _strip_tool_call_text(content)
                    finish = "tool_calls"
            return {
                "ok": True, "content": content, "raw": r.text, "error": None,
                "tool_calls": tc, "finish_reason": finish,
            }

    except Exception as e:
        return {"ok": False, "content": "", "raw": "", "error": str(e)}


def call_model_stream(key: str, messages: list, **kwargs):
    """
    流式调用入口，yield {"type": "delta", "content": str} 或 {"type": "thinking", "content": str} 或 {"type": "done", "content": full_reply} 或 {"type": "error", "error": str}
    支持 OpenAI 兼容和 Anthropic provider 的流式输出。
    """
    import requests
    import json as _json

    m = get_model(key)
    if not m:
        yield {"type": "error", "error": f"模型 {key} 不可用"}
        return

    provider = m["provider"]
    api_url = m["api_url"]
    api_key = m.get("api_key")
    model_id = m["model_id"]
    timeout = kwargs.get("timeout", 90)

    try:
        if provider == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            system = None
            chat_msgs = []
            for msg in messages:
                if msg.get("role") == "system":
                    system = msg["content"]
                else:
                    chat_msgs.append(msg)
            body = {
                "model": model_id,
                "max_tokens": kwargs.get("max_tokens", 4096),
                "messages": chat_msgs,
                "stream": True,
            }
            if system:
                body["system"] = system
            with requests.post(api_url, headers=headers, json=body, timeout=timeout, stream=True) as r:
                if r.status_code != 200:
                    yield {"type": "error", "error": f"HTTP {r.status_code}: {r.text}"}
                    return
                full_reply = ""
                for line in r.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8", errors="replace")
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = _json.loads(data_str)
                            event_type = data.get("type", "")
                            if event_type == "content_block_delta":
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    text = delta.get("text", "")
                                    full_reply += text
                                    yield {"type": "delta", "content": text}
                                elif delta.get("type") == "thinking_delta":
                                    text = delta.get("thinking", "")
                                    yield {"type": "thinking", "content": text}
                            elif event_type == "message_stop":
                                break
                        except _json.JSONDecodeError:
                            pass
                yield {"type": "done", "content": full_reply}

        else:
            # OpenAI 兼容
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            body = {
                "model": model_id,
                "messages": messages,
                "temperature": kwargs.get("temperature", 0.7),
                "stream": True,
            }
            if "max_tokens" in kwargs:
                body["max_tokens"] = kwargs["max_tokens"]
            tools = kwargs.get("tools")
            if tools:
                body["tools"] = tools
                body["tool_choice"] = "auto"

            with requests.post(api_url, headers=headers, json=body, timeout=timeout, stream=True) as r:
                if r.status_code != 200:
                    yield {"type": "error", "error": f"HTTP {r.status_code}: {r.text}"}
                    return
                full_reply = ""
                for line in r.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8", errors="replace")
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = _json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                # 思考部分（部分模型如 deepseek-r1 返回 reasoning_content）
                                thinking = delta.get("reasoning_content") or delta.get("reasoning")
                                if thinking:
                                    yield {"type": "thinking", "content": thinking}
                                text = delta.get("content", "")
                                if text:
                                    full_reply += text
                                    yield {"type": "delta", "content": text}
                        except _json.JSONDecodeError:
                            pass
                yield {"type": "done", "content": full_reply}

    except Exception as e:
        yield {"type": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# CLI 自检（python model_registry.py）
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"[MODEL_REGISTRY] 已注册预设 {len(PRESETS)} 个模型")
    print(f"[MODEL_REGISTRY] 用户文件: {USER_FILE} {'存在' if os.path.exists(USER_FILE) else '不存在'}")
    active = get_active_models()
    print(f"[MODEL_REGISTRY] 当前可用 {len(active)} 个模型:")
    for k, v in active.items():
        print(f"  - {k}: {v['description']} ({v['provider']}/{v['model_id']})")
