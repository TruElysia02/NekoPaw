#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import requests


DISPLAY_STYLES = ("default", "alert", "success", "compact")
LED_COLORS = ("red", "green", "blue", "yellow", "cyan", "magenta", "white", "off")
INPUT_TRIGGERS = ("click", "double_click", "long_press", "release")
SENSOR_OPERATORS = ("gt", "lt", "gte", "lte", "eq", "change")
DEFAULT_REQUEST_TIMEOUT = 10.0
CONFIRM_BITMAP_STATES = ("pending", "confirmed", "cancelled", "timeout")


class LocalCliError(Exception):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def payload(self) -> dict[str, Any]:
        return {
            "ok": False,
            "data": None,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
            "ts": int(time.time()),
            "device": None,
            "source": "bridge_cli",
        }


class DeviceHttpJsonError(Exception):
    def __init__(self, status_code: int, payload: Any):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.payload = payload


def _default_url() -> str:
    return os.getenv("NEKOPAW_URL", "http://localhost")


def _default_device_id() -> str | None:
    value = os.getenv("NEKOPAW_DEVICE_ID")
    return value if value else None


def _default_api_key() -> str | None:
    value = os.getenv("NEKOPAW_API_KEY")
    return value if value else None


def _headers(api_key: str | None, *, content_type: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if api_key:
        headers["X-API-Key"] = api_key
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return parsed


def _merge_params(*parts: dict[str, str] | None) -> dict[str, str] | None:
    merged: dict[str, str] = {}
    for part in parts:
        if part:
            merged.update(part)
    return merged or None


def _maybe_device_params(device_id: str | None) -> dict[str, str] | None:
    if not device_id:
        return None
    return {"device": device_id}


def _read_text_argument(value: str, label: str) -> str:
    text = sys.stdin.read() if value == "-" else value
    if not text.strip():
        raise LocalCliError("INVALID_ARGUMENT", f"{label} is required")
    return text


def _load_json_argument(value: str, label: str) -> Any:
    raw = _read_text_argument(value, label)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LocalCliError(
            "INVALID_JSON",
            f"invalid {label} JSON",
            {"line": exc.lineno, "column": exc.colno, "message": exc.msg},
        ) from exc


def _load_json_object_argument(value: str, label: str) -> dict[str, Any]:
    payload = _load_json_argument(value, label)
    if not isinstance(payload, dict):
        raise LocalCliError("INVALID_JSON", f"{label} JSON must decode to an object", {"type": type(payload).__name__})
    return payload


def _read_bytes(path_text: str) -> bytes:
    path = Path(path_text)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise LocalCliError("FILE_READ_FAILED", f"failed to read {path}", {"reason": str(exc)}) from exc


def _bitmap_byte_length(width: int, height: int) -> int:
    return ((width + 7) // 8) * height


def _parse_response_json(response: requests.Response) -> tuple[bool, Any]:
    text = response.text or ""
    if not text.strip():
        return False, None

    try:
        return True, response.json()
    except ValueError:
        return False, None


def _request(
    method: str,
    base_url: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    data: bytes | None = None,
    api_key: str | None = None,
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
) -> Any:
    url = base_url.rstrip("/") + path
    headers = _headers(api_key, content_type="application/octet-stream" if data is not None else None)

    try:
        response = requests.request(
            method,
            url,
            params=params,
            json=payload,
            data=data,
            headers=headers,
            timeout=request_timeout,
        )
    except requests.Timeout as exc:
        raise LocalCliError(
            "REQUEST_TIMEOUT",
            f"request timed out after {request_timeout:g}s",
            {"method": method, "url": url},
        ) from exc
    except requests.RequestException as exc:
        raise LocalCliError("REQUEST_FAILED", str(exc), {"method": method, "url": url}) from exc

    has_json, body = _parse_response_json(response)
    if 200 <= response.status_code < 300:
        if has_json:
            return body
        raise LocalCliError(
            "INVALID_RESPONSE",
            "device returned a non-JSON success response",
            {"status": response.status_code, "body": response.text[:512]},
        )

    if has_json:
        raise DeviceHttpJsonError(response.status_code, body)

    raise LocalCliError(
        "HTTP_ERROR",
        f"device returned HTTP {response.status_code} without JSON body",
        {"status": response.status_code, "body": response.text[:512]},
    )


def _request_from_args(
    args: argparse.Namespace,
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    data: bytes | None = None,
) -> Any:
    return _request(
        method,
        args.url,
        path,
        params=params,
        payload=payload,
        data=data,
        api_key=args.api_key,
        request_timeout=args.request_timeout,
    )


def _request_and_print(
    args: argparse.Namespace,
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    data: bytes | None = None,
) -> int:
    response = _request_from_args(args, method, path, params=params, payload=payload, data=data)
    _print_json(response)
    return 0


def _device_display_dimensions(args: argparse.Namespace) -> tuple[int, int]:
    response = _request_from_args(args, "GET", "/api/bridge/device", params=_maybe_device_params(args.device))
    if not isinstance(response, dict):
        raise LocalCliError("INVALID_RESPONSE", "device info response must be a JSON object")

    data = response.get("data")
    if not isinstance(data, dict):
        raise LocalCliError("INVALID_RESPONSE", "device info response is missing data")

    capabilities = data.get("capabilities")
    if not isinstance(capabilities, dict):
        raise LocalCliError("INVALID_RESPONSE", "device info response is missing capabilities")

    display = capabilities.get("display")
    if not isinstance(display, dict):
        raise LocalCliError("DISPLAY_UNAVAILABLE", "device does not report a display capability")

    width = display.get("width")
    height = display.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise LocalCliError("INVALID_RESPONSE", "device display dimensions are invalid", {"display": display})

    return width, height


def _load_confirm_bitmap_pack(args: argparse.Namespace) -> bytes:
    if args.title is not None or args.body is not None or args.confirm_label is not None or args.cancel_label is not None:
        raise LocalCliError(
            "INVALID_ARGUMENT",
            "--assets-dir cannot be combined with text confirm fields",
            {
                "forbidden": ["title", "body", "confirmLabel", "cancelLabel"],
            },
        )
    if args.style is not None:
        raise LocalCliError(
            "INVALID_ARGUMENT",
            "--assets-dir cannot be combined with --style",
            {"forbidden": ["style"]},
        )

    assets_dir = Path(args.assets_dir)
    width, height = _device_display_dimensions(args)
    expected_bytes = _bitmap_byte_length(width, height)
    pack_parts: list[bytes] = []

    for state_name in CONFIRM_BITMAP_STATES:
        path = assets_dir / f"{state_name}.bin"
        data = _read_bytes(str(path))
        if len(data) != expected_bytes:
            raise LocalCliError(
                "BITMAP_SIZE_MISMATCH",
                f"{state_name} bitmap size does not match display {width}x{height}",
                {
                    "path": str(path),
                    "state": state_name,
                    "expectedBytes": expected_bytes,
                    "actualBytes": len(data),
                    "width": width,
                    "height": height,
                },
            )

        pack_parts.append(data)

    return b"".join(pack_parts)


def _expect_confirm_status(response: Any) -> str:
    if not isinstance(response, dict):
        raise LocalCliError("INVALID_RESPONSE", "confirm response must be a JSON object")

    data = response.get("data")
    if not isinstance(data, dict):
        raise LocalCliError("INVALID_RESPONSE", "confirm response is missing data")

    status = data.get("status")
    if not isinstance(status, str) or not status:
        raise LocalCliError("INVALID_RESPONSE", "confirm response is missing status", {"data": data})

    return status


def cmd_device_info(args: argparse.Namespace) -> int:
    return _request_and_print(args, "GET", "/api/bridge/device", params=_maybe_device_params(args.device))


def cmd_device_set_description(args: argparse.Namespace) -> int:
    description = _read_text_argument(args.description, "description")
    return _request_and_print(
        args,
        "PATCH",
        "/api/bridge/device/description",
        params=_maybe_device_params(args.device),
        payload={"description": description},
    )


def cmd_display_text(args: argparse.Namespace) -> int:
    payload = {
        "title": args.title,
        "body": _read_text_argument(args.body, "body"),
        "footer": args.footer,
        "style": args.style,
        "refresh": args.refresh,
        "ttl": args.ttl,
    }
    return _request_and_print(
        args,
        "POST",
        "/api/bridge/display/text",
        params=_maybe_device_params(args.device),
        payload=payload,
    )


def cmd_display_bitmap(args: argparse.Namespace) -> int:
    data = _read_bytes(args.input)
    width, height = _device_display_dimensions(args)
    expected_bytes = _bitmap_byte_length(width, height)
    if len(data) != expected_bytes:
        raise LocalCliError(
            "BITMAP_SIZE_MISMATCH",
            f"bitmap size does not match display {width}x{height}",
            {
                "path": str(Path(args.input)),
                "expectedBytes": expected_bytes,
                "actualBytes": len(data),
                "width": width,
                "height": height,
            },
        )

    params = _merge_params(
        _maybe_device_params(args.device),
        {"refresh": args.refresh} if args.refresh else None,
        {"ttl": str(args.ttl)} if args.ttl is not None else None,
    )
    return _request_and_print(args, "POST", "/api/bridge/display/bitmap", params=params, data=data)


def cmd_display_state(args: argparse.Namespace) -> int:
    return _request_and_print(args, "GET", "/api/bridge/display/state", params=_maybe_device_params(args.device))


def cmd_display_confirm_create(args: argparse.Namespace) -> int:
    if args.assets_dir is not None:
        data = _load_confirm_bitmap_pack(args)
        params = _merge_params(
            _maybe_device_params(args.device),
            {"format": "bitmap-pack"},
            {"timeout": str(args.timeout)} if args.timeout is not None else None,
        )
        return _request_and_print(
            args,
            "POST",
            "/api/bridge/display/confirm",
            params=params,
            data=data,
        )

    if args.body is None:
        raise LocalCliError("INVALID_ARGUMENT", "body is required unless --assets-dir is used")

    payload = {
        "title": args.title,
        "body": _read_text_argument(args.body, "body"),
        "confirmLabel": args.confirm_label,
        "cancelLabel": args.cancel_label,
        "timeout": args.timeout,
        "style": args.style,
    }
    return _request_and_print(
        args,
        "POST",
        "/api/bridge/display/confirm",
        params=_maybe_device_params(args.device),
        payload=payload,
    )


def cmd_display_confirm_get(args: argparse.Namespace) -> int:
    params = _merge_params(_maybe_device_params(args.device), {"id": args.id})
    return _request_and_print(args, "GET", "/api/bridge/display/confirm", params=params)


def cmd_display_confirm_cancel(args: argparse.Namespace) -> int:
    params = _merge_params(_maybe_device_params(args.device), {"id": args.id})
    return _request_and_print(args, "DELETE", "/api/bridge/display/confirm", params=params)


def cmd_display_confirm_wait(args: argparse.Namespace) -> int:
    started_at = time.monotonic()
    params = _merge_params(_maybe_device_params(args.device), {"id": args.id})

    while True:
        response = _request_from_args(args, "GET", "/api/bridge/display/confirm", params=params)
        if _expect_confirm_status(response) != "pending":
            _print_json(response)
            return 0

        if args.max_wait is not None and (time.monotonic() - started_at) >= args.max_wait:
            raise LocalCliError(
                "CONFIRM_WAIT_TIMEOUT",
                f"confirm remained pending after {args.max_wait:g}s",
                {"requestId": args.id, "maxWait": args.max_wait, "lastResponse": response},
            )

        time.sleep(args.interval)


def cmd_sensors_list(args: argparse.Namespace) -> int:
    return _request_and_print(args, "GET", "/api/bridge/sensors", params=_maybe_device_params(args.device))


def cmd_sensors_get(args: argparse.Namespace) -> int:
    params = _merge_params(_maybe_device_params(args.device), {"id": args.id})
    return _request_and_print(args, "GET", "/api/bridge/sensors", params=params)


def cmd_events_poll(args: argparse.Namespace) -> int:
    return _request_and_print(args, "GET", "/api/bridge/events", params=_maybe_device_params(args.device))


def cmd_events_watch_upsert(args: argparse.Namespace) -> int:
    payload = _load_json_object_argument(args.payload, "watch payload")
    return _request_and_print(
        args,
        "POST",
        "/api/bridge/events/watch",
        params=_maybe_device_params(args.device),
        payload=payload,
    )


def cmd_events_watch_sensor(args: argparse.Namespace) -> int:
    if args.op == "change" and args.value is not None and args.value < 0:
        raise LocalCliError("INVALID_ARGUMENT", "condition value must be >= 0 when op=change")

    watch: dict[str, Any] = {
        "id": args.id,
        "sensor": args.sensor,
        "condition": {"op": args.op},
        "message": args.message,
    }
    if args.value is not None:
        watch["condition"]["value"] = args.value
    elif args.op != "change":
        raise LocalCliError("INVALID_ARGUMENT", "condition value is required unless op=change")

    if args.cooldown is not None:
        watch["cooldown"] = args.cooldown

    return _request_and_print(
        args,
        "POST",
        "/api/bridge/events/watch",
        params=_maybe_device_params(args.device),
        payload={"watches": [watch]},
    )


def cmd_events_watch_input(args: argparse.Namespace) -> int:
    watch: dict[str, Any] = {
        "id": args.id,
        "input": args.input,
        "trigger": args.trigger,
        "message": args.message,
    }
    if args.cooldown is not None:
        watch["cooldown"] = args.cooldown

    return _request_and_print(
        args,
        "POST",
        "/api/bridge/events/watch",
        params=_maybe_device_params(args.device),
        payload={"watches": [watch]},
    )


def cmd_events_watch_delete(args: argparse.Namespace) -> int:
    params = _merge_params(_maybe_device_params(args.device), {"id": args.id})
    return _request_and_print(args, "DELETE", "/api/bridge/events/watch", params=params)


def cmd_outputs_send(args: argparse.Namespace) -> int:
    payload = _load_json_object_argument(args.payload, "output payload")
    params = _merge_params(_maybe_device_params(args.device), {"id": args.id})
    return _request_and_print(args, "POST", "/api/bridge/outputs", params=params, payload=payload)


def cmd_outputs_led_set(args: argparse.Namespace) -> int:
    payload: dict[str, Any] = {"action": "set", "color": args.color}
    if args.duration is not None:
        payload["duration"] = args.duration

    params = _merge_params(_maybe_device_params(args.device), {"id": args.id})
    return _request_and_print(args, "POST", "/api/bridge/outputs", params=params, payload=payload)


def cmd_outputs_led_off(args: argparse.Namespace) -> int:
    params = _merge_params(_maybe_device_params(args.device), {"id": args.id})
    return _request_and_print(args, "POST", "/api/bridge/outputs", params=params, payload={"action": "off"})


def cmd_outputs_buzzer_beep(args: argparse.Namespace) -> int:
    payload: dict[str, Any] = {"action": "beep"}
    if args.frequency is not None:
        payload["frequency"] = args.frequency
    if args.duration is not None:
        payload["duration"] = args.duration
    if args.count is not None:
        payload["count"] = args.count

    params = _merge_params(_maybe_device_params(args.device), {"id": args.id})
    return _request_and_print(args, "POST", "/api/bridge/outputs", params=params, payload=payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bridge_cli.py", description="NekoPaw Bridge API helper")
    parser.add_argument("--url", default=_default_url(), help="Device or gateway base URL")
    parser.add_argument("--device", default=_default_device_id(), help="Gateway device id (optional)")
    parser.add_argument("--api-key", default=_default_api_key(), help="X-API-Key value (optional)")
    parser.add_argument(
        "--request-timeout",
        default=DEFAULT_REQUEST_TIMEOUT,
        type=_positive_float,
        help="HTTP request timeout in seconds",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    parser_device = sub.add_parser("device", help="Device endpoints")
    sub_device = parser_device.add_subparsers(dest="device_cmd", required=True)
    parser_device_info = sub_device.add_parser("info", help="GET /api/bridge/device")
    parser_device_info.set_defaults(func=cmd_device_info)
    parser_device_set_description = sub_device.add_parser(
        "set-description",
        help="PATCH /api/bridge/device/description",
    )
    parser_device_set_description.add_argument("--description", required=True, help="Human-readable device description")
    parser_device_set_description.set_defaults(func=cmd_device_set_description)

    parser_display = sub.add_parser("display", help="Display endpoints")
    sub_display = parser_display.add_subparsers(dest="display_cmd", required=True)

    parser_text = sub_display.add_parser("text", help="POST /api/bridge/display/text")
    parser_text.add_argument("--title", default=None)
    parser_text.add_argument("--body", required=True, help="Text body, or '-' to read stdin")
    parser_text.add_argument("--footer", default=None)
    parser_text.add_argument("--style", default="default", choices=DISPLAY_STYLES)
    parser_text.add_argument("--refresh", default="partial", choices=["partial", "full"])
    parser_text.add_argument("--ttl", type=_nonnegative_int, default=None)
    parser_text.set_defaults(func=cmd_display_text)

    parser_bitmap = sub_display.add_parser("bitmap", help="POST /api/bridge/display/bitmap (raw bytes)")
    parser_bitmap.add_argument("--input", required=True, help="Path to a raw 1bpp bitmap")
    parser_bitmap.add_argument("--refresh", default=None, choices=["partial", "full"])
    parser_bitmap.add_argument("--ttl", type=_nonnegative_int, default=None)
    parser_bitmap.set_defaults(func=cmd_display_bitmap)

    parser_state = sub_display.add_parser("state", help="GET /api/bridge/display/state")
    parser_state.set_defaults(func=cmd_display_state)

    parser_confirm = sub_display.add_parser("confirm", help="Confirm endpoints")
    sub_confirm = parser_confirm.add_subparsers(dest="confirm_cmd", required=True)

    parser_confirm_create = sub_confirm.add_parser("create", help="POST /api/bridge/display/confirm")
    parser_confirm_create.add_argument("--title", default=None)
    parser_confirm_create.add_argument("--body", default=None, help="Confirm body, or '-' to read stdin")
    parser_confirm_create.add_argument("--assets-dir", default=None, help="Directory with pending/confirmed/cancelled/timeout bitmap files")
    parser_confirm_create.add_argument("--confirm-label", default=None)
    parser_confirm_create.add_argument("--cancel-label", default=None)
    parser_confirm_create.add_argument("--timeout", type=_positive_int, default=None)
    parser_confirm_create.add_argument("--style", default=None, choices=DISPLAY_STYLES)
    parser_confirm_create.set_defaults(func=cmd_display_confirm_create)

    parser_confirm_get = sub_confirm.add_parser("get", help="GET /api/bridge/display/confirm?id=...")
    parser_confirm_get.add_argument("--id", required=True, help="Confirm request id")
    parser_confirm_get.set_defaults(func=cmd_display_confirm_get)

    parser_confirm_cancel = sub_confirm.add_parser("cancel", help="DELETE /api/bridge/display/confirm?id=...")
    parser_confirm_cancel.add_argument("--id", required=True, help="Confirm request id")
    parser_confirm_cancel.set_defaults(func=cmd_display_confirm_cancel)

    parser_confirm_wait = sub_confirm.add_parser("wait", help="Poll confirm status until it leaves pending")
    parser_confirm_wait.add_argument("--id", required=True, help="Confirm request id")
    parser_confirm_wait.add_argument("--interval", type=_positive_float, default=1.0, help="Polling interval in seconds")
    parser_confirm_wait.add_argument("--max-wait", type=_positive_float, default=None, help="Client-side wait limit")
    parser_confirm_wait.set_defaults(func=cmd_display_confirm_wait)

    parser_sensors = sub.add_parser("sensors", help="Sensor endpoints")
    sub_sensors = parser_sensors.add_subparsers(dest="sensors_cmd", required=True)
    parser_sensors_list = sub_sensors.add_parser("list", help="GET /api/bridge/sensors")
    parser_sensors_list.set_defaults(func=cmd_sensors_list)
    parser_sensors_get = sub_sensors.add_parser("get", help="GET /api/bridge/sensors?id=...")
    parser_sensors_get.add_argument("--id", required=True, help="Sensor id")
    parser_sensors_get.set_defaults(func=cmd_sensors_get)

    parser_events = sub.add_parser("events", help="Event endpoints")
    sub_events = parser_events.add_subparsers(dest="events_cmd", required=True)
    parser_events_poll = sub_events.add_parser("poll", help="GET /api/bridge/events")
    parser_events_poll.set_defaults(func=cmd_events_poll)

    parser_watch = sub_events.add_parser("watch", help="Event watch endpoints")
    sub_watch = parser_watch.add_subparsers(dest="watch_cmd", required=True)

    parser_watch_upsert = sub_watch.add_parser("upsert", help="POST /api/bridge/events/watch with raw JSON payload")
    parser_watch_upsert.add_argument("--payload", required=True, help="JSON object, or '-' to read stdin")
    parser_watch_upsert.set_defaults(func=cmd_events_watch_upsert)

    parser_watch_sensor = sub_watch.add_parser("sensor", help="Create or update a single sensor watch")
    parser_watch_sensor.add_argument("--id", required=True, help="Watch id")
    parser_watch_sensor.add_argument("--sensor", required=True, help="Sensor id")
    parser_watch_sensor.add_argument("--op", required=True, choices=SENSOR_OPERATORS)
    parser_watch_sensor.add_argument("--value", type=float, default=None, help="Condition value or change threshold")
    parser_watch_sensor.add_argument("--cooldown", type=_nonnegative_int, default=None)
    parser_watch_sensor.add_argument("--message", default=None)
    parser_watch_sensor.set_defaults(func=cmd_events_watch_sensor)

    parser_watch_input = sub_watch.add_parser("input", help="Create or update a single input watch")
    parser_watch_input.add_argument("--id", required=True, help="Watch id")
    parser_watch_input.add_argument("--input", required=True, help="Input id")
    parser_watch_input.add_argument("--trigger", required=True, choices=INPUT_TRIGGERS)
    parser_watch_input.add_argument("--cooldown", type=_nonnegative_int, default=None)
    parser_watch_input.add_argument("--message", default=None)
    parser_watch_input.set_defaults(func=cmd_events_watch_input)

    parser_watch_delete = sub_watch.add_parser("delete", help="DELETE /api/bridge/events/watch?id=...")
    parser_watch_delete.add_argument("--id", required=True, help="Watch id")
    parser_watch_delete.set_defaults(func=cmd_events_watch_delete)

    parser_outputs = sub.add_parser("outputs", help="Output endpoints")
    sub_outputs = parser_outputs.add_subparsers(dest="outputs_cmd", required=True)

    parser_outputs_send = sub_outputs.add_parser("send", help="POST /api/bridge/outputs with raw JSON payload")
    parser_outputs_send.add_argument("--id", required=True, help="Output id")
    parser_outputs_send.add_argument("--payload", required=True, help="JSON object, or '-' to read stdin")
    parser_outputs_send.set_defaults(func=cmd_outputs_send)

    parser_outputs_led = sub_outputs.add_parser("led", help="Typed helpers for RGB LED outputs")
    sub_outputs_led = parser_outputs_led.add_subparsers(dest="outputs_led_cmd", required=True)
    parser_outputs_led_set = sub_outputs_led.add_parser("set", help="POST /api/bridge/outputs?action=set")
    parser_outputs_led_set.add_argument("--id", default="led_rgb", help="LED output id")
    parser_outputs_led_set.add_argument("--color", required=True, choices=LED_COLORS)
    parser_outputs_led_set.add_argument("--duration", type=_nonnegative_int, default=None)
    parser_outputs_led_set.set_defaults(func=cmd_outputs_led_set)

    parser_outputs_led_off = sub_outputs_led.add_parser("off", help="POST /api/bridge/outputs?action=off")
    parser_outputs_led_off.add_argument("--id", default="led_rgb", help="LED output id")
    parser_outputs_led_off.set_defaults(func=cmd_outputs_led_off)

    parser_outputs_buzzer = sub_outputs.add_parser("buzzer", help="Typed helpers for buzzer outputs")
    sub_outputs_buzzer = parser_outputs_buzzer.add_subparsers(dest="outputs_buzzer_cmd", required=True)
    parser_outputs_buzzer_beep = sub_outputs_buzzer.add_parser("beep", help="POST /api/bridge/outputs?action=beep")
    parser_outputs_buzzer_beep.add_argument("--id", default="buzzer", help="Buzzer output id")
    parser_outputs_buzzer_beep.add_argument("--frequency", type=_positive_int, default=None)
    parser_outputs_buzzer_beep.add_argument("--duration", type=_positive_int, default=None)
    parser_outputs_buzzer_beep.add_argument("--count", type=_positive_int, default=None)
    parser_outputs_buzzer_beep.set_defaults(func=cmd_outputs_buzzer_beep)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except DeviceHttpJsonError as exc:
        _print_json(exc.payload)
        return 1
    except LocalCliError as exc:
        _print_json(exc.payload())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
