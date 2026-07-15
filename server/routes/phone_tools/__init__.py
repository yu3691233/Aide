"""Aide 工具包：聚合所有工具定义与统一分发。

phone_routes.py 通过 ALL_TOOL_DEFS 和 dispatch_tool 使用本包。
每个子模块导出 TOOL_DEFS（OpenAI function 格式）和 handle(name, args) -> str|None。
"""
from . import tasks
from . import ide_device
from . import screenshot_logs

# 按模块顺序聚合工具定义
_MODULES = [tasks, ide_device, screenshot_logs]

ALL_TOOL_DEFS = []
for _m in _MODULES:
    ALL_TOOL_DEFS.extend(_m.TOOL_DEFS)


def dispatch_tool(name, args):
    """统一工具分发。返回工具结果字符串；返回 None 表示工具名未识别。"""
    if not isinstance(args, dict):
        args = {}
    for m in _MODULES:
        result = m.handle(name, args)
        if result is not None:
            return result
    return None
