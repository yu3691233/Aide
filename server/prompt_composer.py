"""Small, shared prompt composer for the browser extension and Android overlay."""

from __future__ import annotations

import json
import re


TYPE_LABELS = {
    "bug_fix": "问题修复",
    "feature_change": "功能调整",
    "test_plan": "测试与计划",
}

DIFFICULTY_LABELS = {
    "simple": "简单",
    "medium": "中等",
    "complex": "复杂",
}


def _clean(value, limit=300):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def infer_task_type(text):
    lower = _clean(text, 1200).lower()
    if any(word in lower for word in ("报错", "错误", "异常", "失败", "崩溃", "闪退", "变红", "不工作", "无法", "bug")):
        return "bug_fix"
    if any(word in lower for word in ("测试", "验证", "检查", "分析", "计划", "方案", "评审", "审查")):
        return "test_plan"
    return "feature_change"


def infer_difficulty(text):
    lower = _clean(text, 1200).lower()
    if any(word in lower for word in ("跨端", "架构", "重构", "并发", "安全", "性能", "偶现", "内存泄漏")):
        return "complex"
    if any(word in lower for word in ("一段时间", "原因", "排查", "多个", "状态", "偶尔", "有时")):
        return "medium"
    return "simple"


def normalize_component(raw):
    raw = raw if isinstance(raw, dict) else {}
    platform = _clean(raw.get("platform"), 30) or "界面"
    name = _clean(raw.get("name") or raw.get("component_name"), 100)
    component_type = _clean(raw.get("type") or raw.get("component_type"), 50)
    location = _clean(raw.get("location"), 160)
    page = _clean(raw.get("page") or raw.get("page_title"), 100)
    technical = raw.get("technical") if isinstance(raw.get("technical"), dict) else {}
    return {
        "platform": platform,
        "name": name or component_type or "所选组件",
        "type": component_type,
        "location": location,
        "page": page,
        "technical": {str(k)[:50]: _clean(v, 240) for k, v in list(technical.items())[:10]},
    }


def _context_label(component):
    parts = [component["platform"], component["page"], component["location"], component["name"]]
    out = []
    for part in parts:
        if part and part not in out:
            out.append(part)
    return " · ".join(out)


def build_fallback(component, user_text, task_type, difficulty):
    type_label = TYPE_LABELS[task_type]
    context = _context_label(component)
    if "【用户未描述具体需求】" in user_text:
        return {
            "title": f"确认{component['name']}的反馈意图"[:40],
            "understanding": f"用户标注了 {context}，但尚未说明希望如何处理。",
            "prompt": (
                f"【界面定位】{context}\n"
                "用户已通过截图标注关注区域，但尚未明确具体问题或修改目标。\n"
                "请先向用户确认：1. 标注的是哪个页面和组件；2. 当前表现哪里不符合预期；"
                "3. 期望结果是什么。确认前不要新增、删除或修改组件行为。"
            ),
        }
    title_text = user_text.rstrip("。！？!? ") or "需要处理"
    title = f"{component['name']}：{title_text}"[:40]
    constraint_text = (
        "只检查并反馈结果，不修改代码、配置或项目文件。"
        if task_type == "test_plan"
        else "保留现有相关行为，不改无关内容。"
    )
    prompt = (
        f"目标：{user_text or '确认并处理用户反馈'}\n"
        f"定位：{context}\n"
        f"边界：{constraint_text}"
    )
    return {
        "title": title,
        "understanding": f"用户指的是 {context}，并补充了：{user_text or '暂无补充描述'}。",
        "prompt": prompt,
    }


def _extract_json(text):
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(cleaned[start:end + 1])
    except (TypeError, ValueError):
        return None


def _recover_partial_json(text):
    """Recover the first usable candidate when a vision model emits almost-JSON."""
    cleaned = str(text or "")
    def field(name, limit):
        match = re.search(rf'"{name}"\s*:\s*"((?:\\.|[^"\\])*)"', cleaned, flags=re.DOTALL)
        if not match:
            return ""
        try:
            return _clean(json.loads('"' + match.group(1) + '"'), limit)
        except (TypeError, ValueError):
            return _clean(match.group(1), limit)
    prompt = field("prompt", 4000)
    if not prompt:
        return None
    return {
        "difficulty": field("difficulty", 20),
        "component_name": field("component_name", 100),
        "component_location": field("component_location", 160),
        "candidates": [{
            "title": field("title", 50) or "截图识别结果",
            "understanding": field("understanding", 300),
            "prompt": prompt,
        }],
    }


def _ai_messages(component, user_text, task_type, difficulty, image_data_url=None):
    payload = {
        "component": component,
        "user_text": user_text,
        "selected_type": task_type,
        "initial_difficulty": difficulty,
    }
    system = (
        "你是低上下文、低额度消耗的开发任务提示词助手。提示词的作用是让开发IDE准确理解目标和边界，"
        "不是教开发IDE如何写代码。用户已经定位了界面组件，你不需要猜代码文件。"
        "根据组件上下文和短描述生成最多3个可能意图，候选之间是具体理解差异，不要强行对应不同任务类型。"
        "若提供截图，请结合截图识别用户所指的页面、组件类型、可见文字和位置，不要猜源码文件。"
        "每个prompt尽量控制在300个汉字以内，只保留：明确目标、已知定位、必须保留的边界、可验证结果。"
        "禁止输出实现教程、逐步操作、技术方案、示例代码、通用开发规范或背景铺陈；"
        "禁止让IDE先扫描整个项目、到处查找或自行猜测需求。已知文件或组件就直接写明，不知道则不要编造。"
        "截图和标注只能证明用户关注的位置，不能证明用户想如何修改。禁止仅凭截图臆造新增、删除、恢复、"
        "改样式或改交互等需求。若user_text包含【用户未描述具体需求】，只描述识别到的页面、组件和可见状态，"
        "prompt必须明确写出意图尚未确认，并列出需要用户确认的问题，不得给出具体修改指令。"
        "只输出JSON：{\"difficulty\":\"simple|medium|complex\","
        "\"component_name\":\"识别后的简短组件名\",\"component_location\":\"页面和位置\",\"candidates\":["
        "{\"title\":\"不超过24字\",\"understanding\":\"一句话\",\"prompt\":\"可直接交给开发IDE的提示词\"}]}。"
        "若类型是test_plan，所有提示词必须明确只检查、验证、输出计划，不修改任何项目文件。"
    )
    user_content = json.dumps(payload, ensure_ascii=False)
    if image_data_url:
        user_content = [
            {"type": "text", "text": user_content},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]


def compose_prompt(data, model_caller=None, image_data_url=None):
    data = data if isinstance(data, dict) else {}
    component = normalize_component(data.get("component"))
    user_text = _clean(data.get("user_text"), 1200)
    requested_type = _clean(data.get("task_type"), 30)
    task_type = requested_type if requested_type in TYPE_LABELS else infer_task_type(user_text)
    difficulty = infer_difficulty(user_text)
    fallback = build_fallback(component, user_text, task_type, difficulty)
    candidates = [fallback]
    used_ai = False
    message = None

    if model_caller is not None and user_text:
        try:
            result = model_caller(_ai_messages(component, user_text, task_type, difficulty, image_data_url))
            if result.get("ok"):
                parsed = _extract_json(result.get("content")) or _recover_partial_json(result.get("content")) or {}
                parsed_difficulty = parsed.get("difficulty")
                if parsed_difficulty in DIFFICULTY_LABELS:
                    difficulty = parsed_difficulty
                recognized_name = _clean(parsed.get("component_name"), 100)
                recognized_location = _clean(parsed.get("component_location"), 160)
                if recognized_name:
                    component["name"] = recognized_name
                if recognized_location:
                    component["location"] = recognized_location
                parsed_candidates = []
                for item in parsed.get("candidates", [])[:3]:
                    if not isinstance(item, dict):
                        continue
                    title = _clean(item.get("title"), 50)
                    prompt = str(item.get("prompt") or "").strip()[:900]
                    if title and prompt:
                        parsed_candidates.append({
                            "title": title,
                            "understanding": _clean(item.get("understanding"), 300),
                            "prompt": prompt,
                        })
                if parsed_candidates:
                    candidates = parsed_candidates
                    used_ai = True
            else:
                message = _clean(result.get("error"), 300) or "AI 暂不可用，已使用基础模板"
        except Exception as exc:
            message = _clean(exc, 300) or "AI 暂不可用，已使用基础模板"

    primary = candidates[0]
    return {
        "ok": True,
        "used_ai": used_ai,
        "task_type": task_type,
        "task_type_label": TYPE_LABELS[task_type],
        "difficulty": difficulty,
        "difficulty_label": DIFFICULTY_LABELS[difficulty],
        "component": component,
        "component_name": component["name"],
        "component_location": component["location"],
        "title": primary["title"],
        "prompt": primary["prompt"],
        "candidates": candidates,
        "message": message,
    }
