import re

from flask import jsonify

from json_utils import safe_read_json
from paths import BRIDGE_DIR as BASE_DIR, PROJECT_ROOT


def _to_int_list(val):
    """将值解析为 int 列表（支持逗号分隔或单个值）"""
    if val is None:
        return []
    if isinstance(val, int):
        return [val]
    s = str(val).strip()
    if not s:
        return []
    out = []
    for p in s.split(","):
        try:
            out.append(int(p.strip()))
        except ValueError:
            out.append(None)
    return out


def _build_code_snippet_section(file_path, line_start_param, line_end_param, logger):
    code_snippet_section = ""
    if not file_path:
        return code_snippet_section

    files = [f.strip() for f in str(file_path).split(",") if f.strip()]
    starts = _to_int_list(line_start_param)
    ends = _to_int_list(line_end_param)

    for idx, rel_path in enumerate(files):
        ls = starts[idx] if idx < len(starts) else (starts[0] if starts else None)
        le = ends[idx] if idx < len(ends) else (ends[0] if ends else None)
        if not ls or ls < 1:
            continue
        try:
            abs_path = PROJECT_ROOT / rel_path
            if not abs_path.exists():
                logger.warning(f"代码片段文件不存在: {abs_path}")
                continue
            actual_end = le if le and le > ls and (le - ls) <= 200 else ls + 200
            if not le or le <= ls:
                actual_end = ls + 200
            with open(abs_path, "r", encoding="utf-8", errors="replace") as cf:
                all_lines = cf.readlines()
            snippet = "".join(all_lines[max(0, ls - 1):actual_end]).rstrip()
            if snippet:
                code_snippet_section = (
                    f"\n--- 代码片段（{rel_path} 第 {ls}-{actual_end} 行）---\n"
                    f"{snippet}\n---\n"
                )
                break
        except Exception as e:
            logger.warning(f"读取代码片段失败 {rel_path}: {e}")
            continue
    return code_snippet_section


def _build_prediction_prompt(name, desc, file_path, type_cn, user_req, code_snippet_section):
    return f"""
    针对以下组件/文件，预测3个简短的开发需求提示词。提示词用于避免开发IDE误解和无目的搜索，
    不是用于教授IDE具体实现方式。

    组件名称: {name}

    组件描述: {desc}

    目标文件: {file_path}

    修改类型: {type_cn}

    用户附加想法: {user_req if user_req else '无'}

{code_snippet_section}

    请给出3个不同理解方向、可以直接交给AI开发助手的提示词。

    要求：

    1. 每条提示词尽量不超过300字，只写清目标、已知文件或组件、必要边界和验收结果。

    2. 不要写实现步骤、技术教程、示例代码或通用规范；不要要求IDE扫描整个项目或自行猜测需求。

    3. 需求应当贴合组件本身的作用，真实且合理，不编造未知文件和需求。

    4. 另外，请为每一个提示词提供以下两项：

       - 预期效果 (极其简短，通常15字以内)

       - 建议理由 (极其简短，通常15字以内)

    5. 严格采用以下格式输出这3个推荐，以便我使用 `---` 进行分割和正则解析：

    ---

    提示词: [具体提示词内容 1]

    效果: [预期效果 1]

    理由: [建议理由 1]

    ---

    提示词: [具体提示词内容 2]

    效果: [预期效果 2]

    理由: [建议理由 2]

    ---

    提示词: [具体提示词内容 3]

    效果: [预期效果 3]

    理由: [建议理由 3]
    """


def _parse_prompt_choices(res):
    choices = []
    parts = res.split("---")
    for part in parts:
        part = part.strip()
        if not part:
            continue

        prompt_match = re.search(r"(?:提示词|Prompt)\s*[:：]\s*(.+)", part, re.IGNORECASE)
        effect_match = re.search(r"(?:效果|Effect)\s*[:：]\s*(.+)", part, re.IGNORECASE)
        reason_match = re.search(r"(?:理由|Reason)\s*[:：]\s*(.+)", part, re.IGNORECASE)

        if prompt_match:
            p_text = prompt_match.group(1).strip()
            e_text = effect_match.group(1).strip() if effect_match else ""
            r_text = reason_match.group(1).strip() if reason_match else ""
            p_text = re.sub(r"^[\[【](.+?)[\]】]", r"\1", p_text).strip()
            e_text = re.sub(r"^[\[【](.+?)[\]】]", r"\1", e_text).strip()
            r_text = re.sub(r"^[\[【](.+?)[\]】]", r"\1", r_text).strip()
            choices.append({"prompt": p_text, "effect": e_text, "reason": r_text})
            continue

        lines = [l.strip() for l in part.split("\n") if l.strip()]
        p_text, e_text, r_text = "", "", ""
        for line in lines:
            if line.startswith("提示词:") or line.startswith("提示词：") or line.lower().startswith("prompt:"):
                p_text = re.sub(r"^(?:提示词|prompt)\s*[:：]\s*", "", line, flags=re.IGNORECASE).strip()
            elif line.startswith("效果:") or line.startswith("效果：") or line.lower().startswith("effect:"):
                e_text = re.sub(r"^(?:效果|effect)\s*[:：]\s*", "", line, flags=re.IGNORECASE).strip()
            elif line.startswith("理由:") or line.startswith("理由：") or line.lower().startswith("reason:"):
                r_text = re.sub(r"^(?:理由|reason)\s*[:：]\s*", "", line, flags=re.IGNORECASE).strip()
        if p_text:
            p_text = re.sub(r"^[\[【](.+?)[\]】]", r"\1", p_text).strip()
            e_text = re.sub(r"^[\[【](.+?)[\]】]", r"\1", e_text).strip()
            r_text = re.sub(r"^[\[【](.+?)[\]】]", r"\1", r_text).strip()
            choices.append({"prompt": p_text, "effect": e_text, "reason": r_text})

    if len(choices) == 0:
        raw_choices = [c.strip() for c in res.split("\n") if c.strip() and len(c) > 5][:3]
        for raw in raw_choices:
            choices.append({"prompt": raw, "effect": "修改并增强功能", "reason": "优化组件体验"})
    return choices


def build_prompt_candidates(file_path, name, desc, category, user_req, line_start_param, line_end_param, logger):
    type_cn = "新增功能"
    if category == "optimize":
        type_cn = "功能优化"
    elif category == "bug":
        type_cn = "修复bug"

    code_snippet_section = _build_code_snippet_section(file_path, line_start_param, line_end_param, logger)
    prompt = _build_prediction_prompt(name, desc, file_path, type_cn, user_req, code_snippet_section)

    from call_assistant import ask_assistant

    res = ask_assistant(prompt, "你是一个擅长写高质量开发提示词的专家。")
    choices = _parse_prompt_choices(res)
    nodes = [{"file": file_path, "name": name, "desc": desc}]
    return choices, nodes


def read_prompt_history():
    history_file = BASE_DIR / "state" / "prompt_history.json"
    data = safe_read_json(history_file, default={})
    return data.get("history", [])
