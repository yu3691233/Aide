def generate_prompt(element: dict, match: dict | None = None) -> str:
    tag = element.get("tag", "?")
    text = element.get("text", "").strip()[:100]

    if match:
        return (
            f'组件: {tag} "{text}"\n'
            f'文件: {match["file"]}\n'
            f'行号: {match["line"]}\n'
            f'描述: {match.get("description", "")}'
        )
    return f'组件: {tag} "{text}"\n文件: (未匹配)\n行号: -\n描述: -'
