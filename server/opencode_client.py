"""Small OpenCode HTTP client used by AideLink task dispatch paths."""

from pathlib import Path

import requests

from config import load_settings, normalize_project_path


def _connection(settings=None):
    settings = settings or load_settings()
    port = int(settings.get("opencode_web_port", 4096))
    username = str(settings.get("opencode_web_username") or "")
    password = str(settings.get("opencode_web_password") or "")
    return f"http://127.0.0.1:{port}", ((username, password) if password else None)


def _session_updated_at(session):
    time_info = session.get("time") if isinstance(session, dict) else None
    if isinstance(time_info, dict):
        return time_info.get("updated") or time_info.get("created") or 0
    return 0


def send_prompt(message, task_id="", directory="", settings=None, http=requests):
    """Send text to the latest session in a project, creating one if needed."""
    base_url, auth = _connection(settings)
    normalized_directory = normalize_project_path(directory)
    headers = {"x-opencode-directory": normalized_directory} if normalized_directory else {}
    params = {"directory": normalized_directory} if normalized_directory else {}

    sessions_response = http.get(
        f"{base_url}/session",
        headers=headers,
        params={**params, "roots": "true"},
        auth=auth,
        timeout=10,
    )
    sessions_response.raise_for_status()
    sessions = sessions_response.json()
    if not isinstance(sessions, list):
        sessions = []

    if normalized_directory:
        requested_key = str(Path(normalized_directory)).replace("/", "\\").rstrip("\\").casefold()
        matching = []
        for session in sessions:
            session_dir = normalize_project_path(session.get("directory", "")) if isinstance(session, dict) else ""
            session_key = str(Path(session_dir)).replace("/", "\\").rstrip("\\").casefold() if session_dir else ""
            if not session_key or session_key == requested_key:
                matching.append(session)
        sessions = matching

    session = max(sessions, key=_session_updated_at) if sessions else None
    session_id = str(session.get("id") or "") if isinstance(session, dict) else ""
    if not session_id:
        create_response = http.post(
            f"{base_url}/session",
            headers=headers,
            params=params,
            auth=auth,
            json={"title": f"AideLink {task_id}" if task_id else "AideLink"},
            timeout=10,
        )
        create_response.raise_for_status()
        created = create_response.json()
        session_id = str(created.get("id") or "") if isinstance(created, dict) else ""
    if not session_id:
        raise RuntimeError("OpenCode 未返回有效会话 ID")

    text = str(message or "")
    if task_id:
        text = f"[AideLink task {task_id}]\n{text}"
    prompt_response = http.post(
        f"{base_url}/session/{session_id}/prompt_async",
        headers=headers,
        params=params,
        auth=auth,
        json={"parts": [{"type": "text", "text": text}]},
        timeout=15,
    )
    prompt_response.raise_for_status()
    return {"session_id": session_id, "directory": normalized_directory, "base_url": base_url}
