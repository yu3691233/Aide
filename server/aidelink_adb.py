#!/usr/bin/env python3
"""AideLink CLI —— 让不支持 MCP 的 IDE/agent 也能通过 shell 调用 AideLink。

与 mcp_server.py 共用同一套 HTTP 路由，零逻辑重复。
子命令：devices / connect / install / screenshot / launch-app / tasks / ide-status
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def _request(url: str, method: str = "GET", payload: dict | None = None, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"ok": True, "raw": body}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"ok": False, "error": body or str(exc)}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "error": f"连接失败: {exc}"}


def _print_result(result: dict, as_json: bool, success_keys: tuple = ("device", "ip", "port", "method", "message", "alias")):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not result.get("ok", result.get("success", True)):
        print(result.get("error") or result.get("message") or "操作失败", file=sys.stderr)
        return
    # 紧凑输出关键字段
    parts = []
    for key in success_keys:
        if key in result and result[key] not in (None, "", False):
            parts.append(f"{key}={result[key]}")
    if parts:
        print(" ".join(parts))
    else:
        print(result.get("message") or "OK")


def _add_device_args(p: argparse.ArgumentParser):
    p.add_argument("--alias", help="设备别名（与 --ip 二选一）")
    p.add_argument("--ip", help="设备 IP")
    p.add_argument("--port", type=int, help="ADB 端口")


def _build_device_payload(args) -> dict:
    payload: dict = {}
    if getattr(args, "alias", None):
        payload["alias"] = args.alias
    if getattr(args, "ip", None):
        payload["ip"] = args.ip
    if getattr(args, "port", None):
        payload["port"] = args.port
    return payload


# ── 子命令实现 ──────────────────────────────────────────────

def cmd_devices(args) -> int:
    result = _request(f"{args.server.rstrip('/')}/api/devices", timeout=10)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("devices") else 1
    devices = result.get("devices") or []
    if not devices:
        print("暂无设备")
        return 1
    for d in devices:
        alias = d.get("alias") or d.get("ip") or "未知"
        ip = d.get("online_ip") or d.get("ip") or "-"
        port = d.get("adb_port") or 5555
        adb = "🟢" if d.get("is_adb_connected") else "⚪"
        online = "🟢" if d.get("is_online") else "⚪"
        print(f"{adb}ADB {online}网  {alias}  {ip}:{port}")
    return 0


def cmd_connect(args) -> int:
    payload = _build_device_payload(args)
    payload["timeout"] = args.timeout
    payload["auto_enable"] = not args.no_auto_enable
    result = _request(f"{args.server.rstrip('/')}/api/adb/ensure", method="POST", payload=payload, timeout=args.timeout)
    _print_result(result, args.json, success_keys=("device", "ip", "port", "method", "alias"))
    return 0 if result.get("ok") else 1


def cmd_install(args) -> int:
    server = args.server.rstrip("/")
    # 第一步：确保设备（如需自动开启无线调试）
    if not args.adb_only:
        ensure_payload = _build_device_payload(args)
        ensure_payload["timeout"] = args.timeout
        ensure_payload["auto_enable"] = True
        ensure_res = _request(f"{server}/api/adb/ensure", method="POST", payload=ensure_payload, timeout=args.timeout)
        if not ensure_res.get("ok"):
            _print_result(ensure_res, args.json)
            return 1
        device = ensure_res.get("device") or f"{ensure_res.get('ip')}:{ensure_res.get('port')}"
    else:
        # adb-only 模式：设备必须已连接
        devices_res = _request(f"{server}/api/devices", timeout=10)
        device = None
        for d in (devices_res.get("devices") or []):
            if d.get("is_adb_connected"):
                device = d.get("device_id")
                break
        if not device:
            print("错误：无已连接的 ADB 设备（--adb-only 需要设备已连接）", file=sys.stderr)
            return 1

    # 第二步：安装
    install_payload = {"device_id": device}
    if args.project:
        install_payload["project_path"] = args.project
    if args.alias:
        install_payload["alias"] = args.alias
    install_res = _request(f"{server}/api/adb/project-install", method="POST", payload=install_payload, timeout=120)
    _print_result(install_res, args.json, success_keys=("device", "apk_path", "install_output", "message"))
    return 0 if install_res.get("ok") else 1


def cmd_screenshot(args) -> int:
    payload = _build_device_payload(args)
    result = _request(f"{args.server.rstrip('/')}/api/adb/screenshot-feedback", method="POST", payload=payload, timeout=30)
    _print_result(result, args.json, success_keys=("message", "summary"))
    return 0 if result.get("ok") else 1


def cmd_launch_app(args) -> int:
    payload = _build_device_payload(args)
    result = _request(f"{args.server.rstrip('/')}/api/adb/launch-app", method="POST", payload=payload, timeout=15)
    _print_result(result, args.json, success_keys=("message",))
    return 0 if result.get("ok") else 1


def cmd_tasks(args) -> int:
    server = args.server.rstrip("/")
    if args.action == "list":
        result = _request(f"{server}/api/tasks", timeout=10)
        tasks = result.get("tasks") or result if isinstance(result, list) else result.get("tasks", [])
        if args.json:
            print(json.dumps(tasks, ensure_ascii=False, indent=2))
            return 0
        if not tasks:
            print("暂无任务")
            return 0
        for t in tasks:
            tid = t.get("task_id", "")[:8]
            status = t.get("status", "?")
            title = t.get("title", "")[:40]
            target = t.get("target_ide") or "-"
            print(f"[{tid}] {status:10} {target:12} {title}")
        return 0
    elif args.action == "dispatch":
        payload = {"text": args.text, "target_ide": args.target_ide}
        if args.title:
            payload["title"] = args.title
        result = _request(f"{server}/api/tasks/dispatch", method="POST", payload=payload, timeout=15)
        _print_result(result, args.json, success_keys=("task_id", "status", "target_ide", "message"))
        return 0 if result.get("ok", result.get("success")) else 1
    elif args.action == "done":
        payload = {"task_id": args.task_id, "summary": args.summary or ""}
        if args.result_ref:
            payload["result_ref"] = args.result_ref
        result = _request(f"{server}/api/tasks/complete", method="POST", payload=payload, timeout=15)
        _print_result(result, args.json, success_keys=("task_id", "status", "message"))
        return 0 if result.get("ok", result.get("success")) else 1
    return 1


def cmd_ide_status(args) -> int:
    result = _request(f"{args.server.rstrip('/')}/api/ide/active_status", timeout=10)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    ides = result.get("ides") or result if isinstance(result, list) else []
    if not ides and isinstance(result, dict):
        ides = result.get("ides", [])
    for ide in ides:
        key = ide.get("key", "?")
        name = ide.get("name", key)
        running = "🟢运行" if ide.get("running") else "⚪停止"
        status = ide.get("status", "idle")
        print(f"{running}  {key:16} {status:10} {name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AideLink CLI —— 不支持 MCP 的 IDE/agent 通过 shell 调用 AideLink",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例：
  aidelink devices
  aidelink install --alias 平板
  aidelink connect --alias 平板 --timeout 10
  aidelink screenshot --alias 平板
  aidelink launch-app --alias 平板
  aidelink tasks list
  aidelink tasks dispatch --text "修复登录bug" --target_ide trae_solo_cn
  aidelink ide-status
""",
    )
    parser.add_argument("--server", default=os.environ.get("AIDELINK_BRIDGE_URL", "http://127.0.0.1:5000"), help="AideLink bridge URL（默认 http://127.0.0.1:5000）")
    parser.add_argument("--json", action="store_true", help="输出完整 JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    # devices
    sub.add_parser("devices", help="列出所有设备及在线状态")

    # connect (原 adb ensure)
    p_connect = sub.add_parser("connect", help="确保 ADB 连接（必要时自动开启无线调试）")
    _add_device_args(p_connect)
    p_connect.add_argument("--timeout", type=int, default=45, help="等待无线调试开启的超时（秒）")
    p_connect.add_argument("--no-auto-enable", action="store_true", help="只连接已有 ADB，不触发开启无线调试")

    # install
    p_install = sub.add_parser("install", help="安装项目 APK 到设备")
    _add_device_args(p_install)
    p_install.add_argument("--timeout", type=int, default=45, help="等待无线调试开启的超时（秒）")
    p_install.add_argument("--project", help="项目路径（默认自动识别）")
    p_install.add_argument("--adb-only", action="store_true", help="跳过 ensure，直接用已连接的 ADB 安装")

    # screenshot
    p_shot = sub.add_parser("screenshot", help="触发设备截图反馈（推送到 IDE）")
    _add_device_args(p_shot)

    # launch-app
    p_launch = sub.add_parser("launch-app", help="拉起设备上的 AideLink App 服务")
    _add_device_args(p_launch)

    # tasks
    p_tasks = sub.add_parser("tasks", help="任务管理")
    task_sub = p_tasks.add_subparsers(dest="action", required=True)
    task_sub.add_parser("list", help="列出任务")
    p_dispatch = task_sub.add_parser("dispatch", help="派发任务到 IDE")
    p_dispatch.add_argument("--text", required=True, help="任务内容")
    p_dispatch.add_argument("--target-ide", required=True, help="目标 IDE key")
    p_dispatch.add_argument("--title", help="任务标题")
    p_done = task_sub.add_parser("done", help="标记任务完成")
    p_done.add_argument("--task-id", required=True, help="任务 ID")
    p_done.add_argument("--summary", help="完成摘要")
    p_done.add_argument("--result-ref", help="结果引用（commit:sha / file:path / test:cmd）")

    # ide-status
    sub.add_parser("ide-status", help="查看 IDE 运行状态")

    args = parser.parse_args()

    handlers = {
        "devices": cmd_devices,
        "connect": cmd_connect,
        "install": cmd_install,
        "screenshot": cmd_screenshot,
        "launch-app": cmd_launch_app,
        "tasks": cmd_tasks,
        "ide-status": cmd_ide_status,
    }
    handler = handlers.get(args.command)
    if not handler:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
