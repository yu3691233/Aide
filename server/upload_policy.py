"""Shared upload limits for the Flask bridge and upload routes."""

from pathlib import Path

from flask import jsonify
from werkzeug.exceptions import RequestEntityTooLarge


ALLOWED_UPLOAD_EXTENSIONS = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
        ".txt", ".md", ".json", ".csv", ".log", ".xml", ".yaml", ".yml",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".7z", ".tar", ".gz",
        ".kt", ".kts", ".java", ".py", ".js", ".ts", ".tsx", ".jsx",
        ".html", ".css", ".c", ".h", ".cpp", ".hpp", ".cs", ".go", ".rs",
        ".gradle", ".properties", ".toml", ".sql", ".sh", ".ps1",
    }
)
MAX_UPLOAD_SIZE = 50 * 1024 * 1024
MAX_UPLOAD_REQUEST_SIZE = MAX_UPLOAD_SIZE + 1024 * 1024


def is_allowed_upload(filename: str) -> bool:
    if not isinstance(filename, str) or not filename.strip():
        return False
    return Path(filename).suffix.lower() in ALLOWED_UPLOAD_EXTENSIONS


def configure_upload_limits(app) -> None:
    """Reject oversized requests before Flask stores the uploaded body."""
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_REQUEST_SIZE

    def handle_oversized_upload(_error: RequestEntityTooLarge):
        return jsonify({"ok": False, "raw": "Upload request too large"}), 413

    app.register_error_handler(RequestEntityTooLarge, handle_oversized_upload)
