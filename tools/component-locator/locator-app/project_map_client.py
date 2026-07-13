import requests


def fetch_project_map(server: str = "http://localhost:5000") -> list[dict]:
    try:
        r = requests.get(f"{server}/api/project-map", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def match_element(element: dict, project_map: list[dict]) -> dict | None:
    tag = element.get("tag", "").lower()
    text = element.get("text", "").strip()
    aria = element.get("ariaLabel", "").strip()
    el_id = element.get("id", "").strip()

    candidates = [text, aria, el_id]

    for entry in project_map:
        label = entry.get("label", "")
        if not label:
            continue
        label_lower = label.lower()
        for c in candidates:
            if c and (label_lower in c.lower() or c.lower() in label_lower):
                return {
                    "file": entry.get("file", ""),
                    "line": entry.get("line", 0),
                    "label": label,
                    "description": entry.get("description", ""),
                }
    return None
