"""Collect currently rendered Android and Windows interfaces for project maps."""

import ctypes
import hashlib
import os
import re
import subprocess
import sys
from ctypes import wintypes

import psutil

_UIA_CONTROL_TYPES = {
    50000: "Button", 50001: "Calendar", 50002: "CheckBox", 50003: "ComboBox",
    50004: "Edit", 50005: "Hyperlink", 50006: "Image", 50007: "ListItem",
    50008: "List", 50009: "Menu", 50010: "MenuBar", 50011: "MenuItem",
    50012: "ProgressBar", 50013: "RadioButton", 50014: "ScrollBar",
    50015: "Slider", 50016: "Spinner", 50017: "StatusBar", 50018: "Tab",
    50019: "TabItem", 50020: "Text", 50021: "ToolBar", 50022: "ToolTip",
    50023: "Tree", 50024: "TreeItem", 50025: "Custom", 50026: "Group",
    50027: "Thumb", 50028: "DataGrid", 50029: "DataItem", 50030: "Document",
    50031: "SplitButton", 50032: "Window", 50033: "Pane", 50034: "Header",
    50035: "HeaderItem", 50036: "Table", 50037: "TitleBar", 50038: "Separator",
    50039: "SemanticZoom", 50040: "AppBar",
}
_UIA_INTERACTIVE_TYPES = {
    "Button", "CheckBox", "ComboBox", "Edit", "Hyperlink", "ListItem", "List",
    "Menu", "MenuItem", "RadioButton", "ScrollBar", "Slider", "Spinner", "Tab",
    "TabItem", "Tree", "TreeItem", "DataGrid", "DataItem", "Document", "SplitButton",
}


def _stable_id(*parts):
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def scan_android_runtime():
    """Return the foreground Android UI hierarchy using the existing ADB locator."""
    try:
        import ui_locator

        result = ui_locator.get_interactive_elements()
    except Exception as exc:
        return [], {"available": False, "message": str(exc)}
    if not result.get("ok"):
        return [], {"available": False, "message": result.get("error", "Android 运行态不可用")}

    device = result.get("device", "")
    package_name = ""
    activity_name = ""
    try:
        completed = ui_locator._run(
            [ui_locator.ADB_PATH, "-s", device, "shell", "dumpsys", "window", "windows"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
        focus = re.search(
            r"mCurrentFocus=.*?\s([\w.]+)/([\w.$]+)",
            completed.stdout or "",
        )
        if focus:
            package_name, activity_name = focus.groups()
    except Exception:
        pass

    components = []
    seen = set()
    for element in result.get("elements") or []:
        resource_id = str(element.get("resource_id") or "")
        text = str(element.get("text") or "").strip()
        description = str(element.get("content_desc") or "").strip()
        class_name = str(element.get("class_name") or "")
        short_type = class_name.rsplit(".", 1)[-1] or "View"
        resource_name = resource_id.rsplit("/", 1)[-1] if resource_id else ""
        label = text or description or resource_name
        if not label:
            continue
        identity = (resource_id, text, description, tuple(element.get("bounds") or []))
        if identity in seen:
            continue
        seen.add(identity)
        interactive = bool(
            element.get("clickable")
            or element.get("focusable")
            or element.get("scrollable")
        )
        components.append({
            "id": f"android_runtime_{_stable_id(*identity)}",
            "name": f"[{short_type}] {label}",
            "description": description or (
                "当前屏幕可交互组件" if interactive else "当前屏幕可见内容"
            ),
            "category": "交互" if interactive else "展示",
            "source": "android_uiautomator",
            "confidence": 0.98 if resource_id else 0.9,
            "resource_id": resource_id,
            "class_name": class_name,
            "bounds": element.get("bounds"),
            "clickable": bool(element.get("clickable")),
            "focusable": bool(element.get("focusable")),
            "scrollable": bool(element.get("scrollable")),
        })

    page_label = activity_name.rsplit(".", 1)[-1] or package_name or "当前手机界面"
    pages = []
    if components:
        pages.append({
            "id": f"android_runtime_page_{_stable_id(device, package_name, activity_name)}",
            "name": f"📡 当前运行界面 · {page_label}",
            "description": f"通过 Android UiAutomator 采集 ({device})",
            "package": package_name,
            "activity": activity_name,
            "source": "android_uiautomator",
            "confidence": 0.98,
            "children": components,
        })
    return pages, {
        "available": bool(pages),
        "device": device,
        "package": package_name,
        "activity": activity_name,
        "component_count": len(components),
    }


def _project_process_ids(project_root):
    normalized_root = os.path.normcase(os.path.abspath(project_root))
    process_ids = set()
    for process in psutil.process_iter(["pid", "exe", "cmdline", "cwd"]):
        try:
            values = [
                process.info.get("exe") or "",
                process.info.get("cwd") or "",
                " ".join(process.info.get("cmdline") or []),
            ]
            if any(
                normalized_root in os.path.normcase(os.path.abspath(value))
                for value in values if value
            ):
                process_ids.add(int(process.info["pid"]))
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError, ValueError):
            continue
    return process_ids


def _collect_uia_controls(hwnd):
    """Use Windows UI Automation when comtypes/UIAutomationCore is available."""
    try:
        import comtypes.client
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA

        automation = comtypes.client.CreateObject(
            UIA.CUIAutomation, interface=UIA.IUIAutomation,
        )
        root = automation.ElementFromHandle(hwnd)
        elements = root.FindAll(UIA.TreeScope_Subtree, automation.CreateTrueCondition())
    except Exception:
        return []

    components = []
    seen = set()
    for index in range(min(int(elements.Length), 1200)):
        try:
            element = elements.GetElement(index)
            if bool(element.CurrentIsOffscreen):
                continue
            name = str(element.CurrentName or "").strip()
            automation_id = str(element.CurrentAutomationId or "").strip()
            control_type_id = int(element.CurrentControlType or 0)
            control_type = _UIA_CONTROL_TYPES.get(control_type_id, f"Control{control_type_id}")
            rect = element.CurrentBoundingRectangle
            bounds = [
                int(rect.left), int(rect.top), int(rect.right), int(rect.bottom),
            ]
            if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                continue
            if not name and not automation_id:
                continue
            identity = (automation_id, name, control_type, tuple(bounds))
            if identity in seen:
                continue
            seen.add(identity)
            label = name or automation_id
            interactive = control_type in _UIA_INTERACTIVE_TYPES
            components.append({
                "id": f"windows_uia_{_stable_id(hwnd, *identity)}",
                "name": f"[{control_type}] {label}",
                "description": "Windows UI Automation 可交互组件" if interactive else "Windows UI Automation 可见内容",
                "category": "交互" if interactive else "展示",
                "source": "windows_uia",
                "confidence": 0.98 if automation_id else 0.92,
                "automation_id": automation_id,
                "control_type": control_type,
                "class_name": str(element.CurrentClassName or ""),
                "bounds": bounds,
                "enabled": bool(element.CurrentIsEnabled),
            })
        except Exception:
            continue
    return components


def scan_windows_runtime(project_root):
    """Enumerate visible native controls owned by processes launched from the project."""
    if sys.platform != "win32":
        return [], {"available": False, "message": "Windows UI Automation 仅在 Windows 可用"}
    process_ids = _project_process_ids(project_root)
    if not process_ids:
        return [], {"available": False, "message": "当前项目没有运行中的桌面进程"}

    user32 = ctypes.windll.user32
    foreground_hwnd = int(user32.GetForegroundWindow() or 0)
    pages = []
    enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def window_text(hwnd):
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(max(1, length + 1))
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value.strip()

    def class_name(hwnd):
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buffer, len(buffer))
        return buffer.value.strip()

    def rect_for(hwnd):
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return [rect.left, rect.top, rect.right, rect.bottom]

    def pid_for(hwnd):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)

    def collect_children(parent_hwnd):
        components = []

        @enum_proc_type
        def visit(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            text = window_text(hwnd)
            control_class = class_name(hwnd)
            bounds = rect_for(hwnd)
            if not bounds or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                return True
            interactive = bool(re.search(
                r"(Button|Edit|ComboBox|ListBox|TreeView|TabControl|ScrollBar)",
                control_class,
                re.IGNORECASE,
            ))
            if text or interactive:
                label = text or control_class or "控件"
                components.append({
                    "id": f"windows_runtime_{_stable_id(parent_hwnd, hwnd, label, bounds)}",
                    "name": f"[{control_class or '控件'}] {label}",
                    "description": "当前桌面窗口可交互组件" if interactive else "当前桌面窗口可见内容",
                    "category": "交互" if interactive else "展示",
                    "source": "windows_native_runtime",
                    "confidence": 0.93 if text else 0.78,
                    "hwnd": int(hwnd),
                    "class_name": control_class,
                    "bounds": bounds,
                    "enabled": bool(user32.IsWindowEnabled(hwnd)),
                })
            return True

        user32.EnumChildWindows(parent_hwnd, visit, 0)
        return components

    @enum_proc_type
    def visit_top(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or pid_for(hwnd) not in process_ids:
            return True
        title = window_text(hwnd)
        bounds = rect_for(hwnd)
        if not title or not bounds or bounds[2] - bounds[0] < 120 or bounds[3] - bounds[1] < 80:
            return True
        uia_components = _collect_uia_controls(hwnd)
        native_components = collect_children(hwnd)
        if len(uia_components) >= len(native_components):
            components = uia_components
            collector = "Windows UI Automation"
        else:
            components = native_components
            collector = "Windows 原生窗口控件树"
        if components:
            pages.append({
                "id": f"windows_runtime_page_{_stable_id(hwnd, title)}",
                "name": f"📡 当前运行窗口 · {title}",
                "description": f"通过 {collector} 采集",
                "source": "windows_uia" if collector == "Windows UI Automation" else "windows_native_runtime",
                "confidence": 0.98 if collector == "Windows UI Automation" else 0.93,
                "hwnd": int(hwnd),
                "is_foreground": int(hwnd) == foreground_hwnd,
                "bounds": bounds,
                "children": components,
            })
        return True

    user32.EnumWindows(visit_top, 0)
    pages.sort(key=lambda page: (not page.get("is_foreground"), page.get("name", "")))
    return pages, {
        "available": bool(pages),
        "process_count": len(process_ids),
        "window_count": len(pages),
        "component_count": sum(len(page["children"]) for page in pages),
        "collector": pages[0].get("source") if pages else "",
        "foreground_hwnd": foreground_hwnd,
    }
