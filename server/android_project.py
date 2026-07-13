"""Android project and APK discovery helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


_ANDROID_PLUGIN_MARKERS = (
    "com.android.application",
    "com.android.library",
    "com.android.dynamic-feature",
)


def _windows_path(path: Path) -> str:
    return os.path.normpath(str(path)).replace("/", "\\")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _candidate_roots(project_path: Path) -> list[Path]:
    candidates = [project_path]
    try:
        candidates.extend(
            child for child in project_path.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        )
    except OSError:
        pass
    return candidates


def _is_android_root(path: Path) -> bool:
    settings = any((path / name).is_file() for name in ("settings.gradle.kts", "settings.gradle"))
    wrapper = (path / "gradlew").is_file() or (path / "gradlew.bat").is_file()
    if settings and wrapper:
        return True
    return any(
        marker in _read_text(path / name)
        for name in ("build.gradle.kts", "build.gradle")
        for marker in _ANDROID_PLUGIN_MARKERS
    )


def _application_modules(android_root: Path) -> list[tuple[str, Path, str]]:
    modules = []
    try:
        children = list(android_root.iterdir())
    except OSError:
        return modules
    for child in children:
        if not child.is_dir() or child.name.startswith("."):
            continue
        build_file = next((child / name for name in ("build.gradle.kts", "build.gradle") if (child / name).is_file()), None)
        if not build_file:
            continue
        text = _read_text(build_file)
        if "com.android.application" not in text:
            continue
        match = re.search(r"\bapplicationId\s*(?:=\s*)?[\"']([^\"']+)[\"']", text)
        modules.append((child.name, child, match.group(1) if match else ""))
    return modules


def inspect_android_project(project_path: str) -> dict[str, Any]:
    """Return JSON-safe Android metadata for a target project directory."""
    if not project_path or not os.path.isdir(project_path):
        return {"is_android": False, "android_roots": [], "modules": [], "apks": [], "primary_apk": ""}
    project_root = Path(project_path).resolve()
    android_roots = [path for path in _candidate_roots(project_root) if _is_android_root(path)]
    modules = []
    apks = []
    for android_root in android_roots:
        for module_name, module_path, application_id in _application_modules(android_root):
            module_rel = os.path.relpath(module_path, project_root).replace("\\", "/")
            modules.append({"name": module_name, "path": module_rel, "application_id": application_id})
            outputs_root = module_path / "build" / "outputs" / "apk"
            if not outputs_root.is_dir():
                continue
            try:
                for apk in outputs_root.rglob("*.apk"):
                    if "androidTest" in apk.parts or not apk.is_file():
                        continue
                    stat = apk.stat()
                    relative_parts = apk.relative_to(outputs_root).parts
                    apks.append({
                        "path": _windows_path(apk),
                        "name": apk.name,
                        "module": module_rel,
                        "variant": "/".join(relative_parts[:-1]) or apk.stem,
                        "application_id": application_id,
                        "modified_at": int(stat.st_mtime),
                        "size": stat.st_size,
                    })
            except OSError:
                continue
    apks.sort(key=lambda item: ("debug" not in item["variant"].lower(), -item["modified_at"]))
    return {
        "is_android": bool(android_roots),
        "android_roots": [os.path.relpath(path, project_root).replace("\\", "/") for path in android_roots],
        "modules": modules,
        "apks": apks,
        "primary_apk": apks[0]["path"] if apks else "",
    }


def resolve_project_apk(project_path: str, requested_apk: str = "") -> tuple[str, dict[str, Any]]:
    metadata = inspect_android_project(project_path)
    discovered = {os.path.normcase(os.path.abspath(item["path"])): item["path"] for item in metadata["apks"]}
    if requested_apk:
        return discovered.get(os.path.normcase(os.path.abspath(requested_apk)), ""), metadata
    return metadata["primary_apk"], metadata
