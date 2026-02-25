#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests


def _default_url() -> str:
    return os.getenv("NEKOPAW_URL", "http://localhost")


def _default_device_id() -> str | None:
    v = os.getenv("NEKOPAW_DEVICE_ID")
    return v if v else None


def _default_api_key() -> str | None:
    v = os.getenv("NEKOPAW_API_KEY")
    return v if v else None


def _headers(api_key: str | None) -> dict[str, str]:
    if not api_key:
        return {}
    return {"X-API-Key": api_key}


def _get_json(base_url: str, path: str, *, params: dict[str, str] | None = None) -> dict:
    url = base_url.rstrip("/") + path
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()


def _post_json(
    base_url: str, path: str, *, params: dict[str, str] | None, payload: dict, api_key: str | None
) -> dict:
    url = base_url.rstrip("/") + path
    r = requests.post(url, params=params, json=payload, headers=_headers(api_key), timeout=10)
    r.raise_for_status()
    return r.json()


def _post_bytes(
    base_url: str, path: str, *, params: dict[str, str] | None, data: bytes, api_key: str | None
) -> dict:
    url = base_url.rstrip("/") + path
    headers = {"Content-Type": "application/octet-stream", **_headers(api_key)}
    r = requests.post(url, params=params, data=data, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()


def _maybe_device_params(device_id: str | None) -> dict[str, str] | None:
    if not device_id:
        return None
    return {"device": device_id}


def cmd_device_info(args: argparse.Namespace) -> int:
    resp = _get_json(args.url, "/api/bridge/device", params=_maybe_device_params(args.device))
    print(json.dumps(resp, ensure_ascii=False, indent=2))
    return 0


def cmd_display_text(args: argparse.Namespace) -> int:
    body = args.body
    if body == "-":
        body = sys.stdin.read()

    payload = {
        "title": args.title,
        "body": body,
        "footer": args.footer,
        "style": args.style,
        "refresh": args.refresh,
        "ttl": args.ttl,
    }
    resp = _post_json(
        args.url,
        "/api/bridge/display/text",
        params=_maybe_device_params(args.device),
        payload=payload,
        api_key=args.api_key,
    )
    print(json.dumps(resp, ensure_ascii=False, indent=2))
    return 0


def cmd_display_bitmap(args: argparse.Namespace) -> int:
    data = Path(args.input).read_bytes()
    params = _maybe_device_params(args.device) or {}
    if args.refresh:
        params["refresh"] = args.refresh
    if args.ttl is not None:
        params["ttl"] = str(args.ttl)

    resp = _post_bytes(args.url, "/api/bridge/display/bitmap", params=params, data=data, api_key=args.api_key)
    print(json.dumps(resp, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bridge_cli.py", description="NekoPaw Bridge API helper")
    p.add_argument("--url", default=_default_url())
    p.add_argument("--device", default=_default_device_id())
    p.add_argument("--api-key", default=_default_api_key())

    sub = p.add_subparsers(dest="cmd", required=True)

    p_device = sub.add_parser("device", help="Device endpoints")
    sub_device = p_device.add_subparsers(dest="device_cmd", required=True)
    p_device_info = sub_device.add_parser("info", help="GET /api/bridge/device")
    p_device_info.set_defaults(func=cmd_device_info)

    p_display = sub.add_parser("display", help="Display endpoints")
    sub_display = p_display.add_subparsers(dest="display_cmd", required=True)

    p_text = sub_display.add_parser("text", help="POST /api/bridge/display/text")
    p_text.add_argument("--title", default=None)
    p_text.add_argument("--body", required=True, help="Text body, or '-' to read stdin")
    p_text.add_argument("--footer", default=None)
    p_text.add_argument("--style", default="default", choices=["default", "alert", "success", "compact"])
    p_text.add_argument("--refresh", default="partial", choices=["partial", "full"])
    p_text.add_argument("--ttl", type=int, default=None)
    p_text.set_defaults(func=cmd_display_text)

    p_bitmap = sub_display.add_parser("bitmap", help="POST /api/bridge/display/bitmap (raw bytes)")
    p_bitmap.add_argument("--input", required=True, help="Path to bitmap bytes")
    p_bitmap.add_argument("--refresh", default=None, choices=["partial", "full"])
    p_bitmap.add_argument("--ttl", type=int, default=None)
    p_bitmap.set_defaults(func=cmd_display_bitmap)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except requests.RequestException as e:
        print(f"request failed: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
