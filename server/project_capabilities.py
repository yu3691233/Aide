import os
from pathlib import Path

from android_project import inspect_android_project


_CACHE = {}
_WEB_MARKERS = {
    "package.json",
    "vite.config.js",
    "vite.config.ts",
    "next.config.js",
    "next.config.mjs",
    "next.config.ts",
    "nuxt.config.js",
    "nuxt.config.ts",
    "svelte.config.js",
    "astro.config.mjs",
    "angular.json",
}
_WEB_DIR_MARKERS = {"src", "pages", "app", "public"}
_SKIP_DIRS = {
    ".git",
    ".gradle",
    ".idea",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "out",
    "__pycache__",
}


def clear_project_capability_cache():
    _CACHE.clear()


def _dir_mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def _is_web_root(path):
    marker_hits = []
    try:
        names = {item.name for item in Path(path).iterdir()}
    except OSError:
        return {"is_web": False, "markers": []}

    for marker in sorted(_WEB_MARKERS):
        if marker in names:
            marker_hits.append(marker)

    if "package.json" in names and names.intersection(_WEB_DIR_MARKERS):
        marker_hits.append("package.json+web_dirs")

    return {
        "is_web": bool(marker_hits),
        "markers": list(dict.fromkeys(marker_hits)),
    }


def inspect_web_project(path):
    path = str(path or "").strip()
    if not path or not os.path.isdir(path):
        return {"is_web": False, "roots": [], "markers": []}

    roots = []
    markers = []
    candidates = [Path(path)]
    try:
        for child in Path(path).iterdir():
            if child.is_dir() and child.name not in _SKIP_DIRS:
                candidates.append(child)
    except OSError:
        pass

    for candidate in candidates:
        result = _is_web_root(candidate)
        if not result["is_web"]:
            continue
        rel = os.path.relpath(candidate, path)
        root_name = "." if rel == "." else rel.replace(os.sep, "/")
        roots.append(root_name)
        for marker in result["markers"]:
            markers.append(marker if root_name == "." else f"{root_name}/{marker}")

    return {
        "is_web": bool(roots),
        "roots": roots,
        "markers": list(dict.fromkeys(markers)),
    }


def inspect_project_capabilities(path):
    path = str(path or "").strip()
    cache_key = os.path.normcase(os.path.abspath(path)) if path else ""
    signature = _dir_mtime(path) if path else 0
    cached = _CACHE.get(cache_key)
    if cached and cached.get("signature") == signature:
        return dict(cached["value"])

    android = inspect_android_project(path)
    web = inspect_web_project(path)
    capabilities = []
    if web.get("is_web"):
        capabilities.append("web")
    if android.get("is_android"):
        capabilities.append("android")
    if not capabilities:
        capabilities.append("general")

    preferred_surface = "general"
    if "android" in capabilities:
        preferred_surface = "android"
    if capabilities == ["web"]:
        preferred_surface = "web"

    value = {
        "capabilities": capabilities,
        "preferred_surface": preferred_surface,
        "android": android,
        "web": web,
    }
    _CACHE[cache_key] = {"signature": signature, "value": value}
    return dict(value)


def enrich_project(project):
    enriched = dict(project or {})
    enriched.update(inspect_project_capabilities(enriched.get("path", "")))
    return enriched
