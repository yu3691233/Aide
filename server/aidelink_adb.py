#!/usr/bin/env python3
"""Small CLI wrapper for IDEs that need a ready ADB device via AideLink."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _post_json(url: str, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"ok": False, "error": body or str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure an ADB device through AideLink")
    parser.add_argument("--server", default="http://127.0.0.1:5000", help="AideLink bridge URL")
    parser.add_argument("--alias", help="Device alias configured in AideLink")
    parser.add_argument("--ip", help="Known device IP")
    parser.add_argument("--port", type=int, help="Known ADB port")
    parser.add_argument("--timeout", type=int, default=45, help="Seconds to wait for wireless ADB")
    parser.add_argument("--no-auto-enable", action="store_true", help="Only connect existing ADB, do not ask the app to enable it")
    parser.add_argument("--json", action="store_true", help="Print the full JSON response")
    args = parser.parse_args()

    payload = {
        "timeout": args.timeout,
        "auto_enable": not args.no_auto_enable,
    }
    if args.alias:
        payload["alias"] = args.alias
    if args.ip:
        payload["ip"] = args.ip
    if args.port:
        payload["port"] = args.port

    result = _post_json(f"{args.server.rstrip('/')}/api/adb/ensure", payload, args.timeout)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result.get("ok"):
        print(result.get("device_id") or result.get("device") or f"{result.get('ip')}:{result.get('port')}")
    else:
        print(result.get("error", "ADB ensure failed"), file=sys.stderr)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
