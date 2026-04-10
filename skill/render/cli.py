from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from .pipeline import (
    DEFAULT_DITHER,
    DEFAULT_FIT,
    DEFAULT_HEIGHT,
    DEFAULT_SCALE,
    DEFAULT_THRESHOLD,
    DEFAULT_WIDTH,
    VALID_DITHER,
    VALID_FIT,
    RenderPipelineError,
    RenderSettings,
    build_confirm_scenes,
    convert_image_to_bitmap,
    render_markdown_to_artifacts,
    render_scene_to_artifacts,
)


class LocalCliError(Exception):
    def __init__(self, code: str, message: str, details: Any | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def payload(self) -> dict[str, Any]:
        return {
            "ok": False,
            "data": None,
            "error": {"code": self.code, "message": self.message, "details": self.details},
            "ts": int(time.time()),
            "source": "render_cli",
        }


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return parsed


def _threshold_value(value: str) -> int:
    parsed = int(value)
    if parsed < 0 or parsed > 255:
        raise argparse.ArgumentTypeError("must be between 0 and 255")
    return parsed


def _read_text_input(value: str, label: str) -> str:
    if value == "-":
        text = sys.stdin.read()
    else:
        path = Path(value)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LocalCliError("FILE_READ_FAILED", f"failed to read {path}", {"reason": str(exc)}) from exc
    if not text.strip():
        raise LocalCliError("INVALID_ARGUMENT", f"{label} is required")
    return text


def _read_text_argument(value: str, label: str) -> str:
    text = sys.stdin.read() if value == "-" else value
    if not text.strip():
        raise LocalCliError("INVALID_ARGUMENT", f"{label} is required")
    return text


def _load_json_input(value: str) -> tuple[dict[str, Any], Path | None]:
    if value == "-":
        raw = sys.stdin.read()
        base_dir = None
    else:
        path = Path(value)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LocalCliError("FILE_READ_FAILED", f"failed to read {path}", {"reason": str(exc)}) from exc
        base_dir = path.parent.resolve()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LocalCliError(
            "INVALID_JSON",
            "scene JSON is invalid",
            {"line": exc.lineno, "column": exc.colno, "message": exc.msg},
        ) from exc

    if not isinstance(data, dict):
        raise LocalCliError("INVALID_JSON", "scene JSON must decode to an object")

    return data, base_dir


def _markdown_base_dir(input_value: str, assets_root: str | None) -> Path | None:
    if assets_root:
        return Path(assets_root).resolve()
    if input_value == "-":
        return None
    return Path(input_value).resolve().parent


def _settings_from_args(args: argparse.Namespace) -> RenderSettings:
    return RenderSettings(
        width=args.width,
        height=args.height,
        scale=args.scale,
        threshold=args.threshold,
        dither=args.dither,
        fit=args.fit,
    )


def _success_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "error": None,
        "ts": int(time.time()),
        "source": "render_cli",
    }


def cmd_markdown(args: argparse.Namespace) -> int:
    markdown_text = _read_text_input(args.input, "markdown input")
    base_dir = _markdown_base_dir(args.input, args.assets_root)
    result = render_markdown_to_artifacts(
        markdown_text,
        preview_path=args.preview,
        bitmap_path=args.bitmap,
        bw_preview_path=args.bw_preview,
        settings=_settings_from_args(args),
        base_dir=base_dir,
    )
    result["inputType"] = "markdown"
    _print_json(_success_payload(result))
    return 0


def cmd_scene(args: argparse.Namespace) -> int:
    scene, base_dir = _load_json_input(args.input)
    if args.assets_root:
        base_dir = Path(args.assets_root).resolve()
    result = render_scene_to_artifacts(
        scene,
        preview_path=args.preview,
        bitmap_path=args.bitmap,
        bw_preview_path=args.bw_preview,
        settings=_settings_from_args(args),
        base_dir=base_dir,
    )
    result["inputType"] = "scene"
    _print_json(_success_payload(result))
    return 0


def cmd_bitmap(args: argparse.Namespace) -> int:
    artifact = convert_image_to_bitmap(
        args.input,
        _settings_from_args(args),
        bitmap_path=args.output,
        bw_preview_path=args.bw_preview,
    )
    data: dict[str, Any] = {
        "inputType": "image",
        "imagePath": str(Path(args.input)),
        "bitmapPath": str(Path(args.output)),
        "bitmapBytes": artifact.bitmap_byte_count,
        "width": artifact.width,
        "height": artifact.height,
        "threshold": args.threshold,
        "dither": args.dither,
        "fit": args.fit,
    }
    if args.bw_preview:
        data["bwPreviewPath"] = str(Path(args.bw_preview))
    _print_json(_success_payload(data))
    return 0


def cmd_confirm_assets(args: argparse.Namespace) -> int:
    settings = _settings_from_args(args)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scenes = build_confirm_scenes(
        title=args.title,
        body=_read_text_argument(args.body, "confirm body"),
        confirm_label=args.confirm_label,
        cancel_label=args.cancel_label,
        confirmed_text=args.confirmed_text,
        cancelled_text=args.cancelled_text,
        timeout_text=args.timeout_text,
        width=settings.width,
        height=settings.height,
    )

    generated: dict[str, Any] = {}
    for state_name, scene in scenes.items():
        preview_path = output_dir / f"{state_name}.png"
        bitmap_path = output_dir / f"{state_name}.bin"
        bw_preview_path = output_dir / f"{state_name}_bw.png" if args.bw_preview else None
        generated[state_name] = render_scene_to_artifacts(
            scene,
            preview_path=preview_path,
            bitmap_path=bitmap_path,
            bw_preview_path=bw_preview_path,
            settings=settings,
            base_dir=Path(args.assets_root).resolve() if args.assets_root else None,
        )

    payload = {
        "inputType": "confirm",
        "outputDir": str(output_dir),
        "states": generated,
    }
    _print_json(_success_payload(payload))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="render_cli.py", description="NekoPaw rendering helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_common_render_args(target: argparse.ArgumentParser, *, include_bw_preview_path: bool = True) -> None:
        target.add_argument("--width", type=_positive_int, default=DEFAULT_WIDTH)
        target.add_argument("--height", type=_positive_int, default=DEFAULT_HEIGHT)
        target.add_argument("--scale", type=_positive_int, default=DEFAULT_SCALE, help="Preview device scale factor")
        target.add_argument("--threshold", type=_threshold_value, default=DEFAULT_THRESHOLD)
        target.add_argument("--dither", choices=VALID_DITHER, default=DEFAULT_DITHER)
        target.add_argument("--fit", choices=VALID_FIT, default=DEFAULT_FIT)
        if include_bw_preview_path:
            target.add_argument("--bw-preview", default=None, help="Optional thresholded preview PNG path")

    parser_markdown = sub.add_parser("markdown", help="Render Markdown into preview and optional bitmap artifacts")
    parser_markdown.add_argument("--input", required=True, help="Markdown file path, or '-' to read stdin")
    parser_markdown.add_argument("--preview", required=True, help="Preview PNG output path")
    parser_markdown.add_argument("--bitmap", default=None, help="Optional raw 1bpp bitmap output path")
    parser_markdown.add_argument("--assets-root", default=None, help="Optional base directory for relative images")
    add_common_render_args(parser_markdown)
    parser_markdown.set_defaults(func=cmd_markdown)

    parser_scene = sub.add_parser("scene", help="Render scene JSON into preview and optional bitmap artifacts")
    parser_scene.add_argument("--input", required=True, help="Scene JSON file path, or '-' to read stdin")
    parser_scene.add_argument("--preview", required=True, help="Preview PNG output path")
    parser_scene.add_argument("--bitmap", default=None, help="Optional raw 1bpp bitmap output path")
    parser_scene.add_argument("--assets-root", default=None, help="Optional base directory for relative images")
    add_common_render_args(parser_scene)
    parser_scene.set_defaults(func=cmd_scene)

    parser_bitmap = sub.add_parser("bitmap", help="Convert a preview PNG into a raw 1bpp bitmap")
    parser_bitmap.add_argument("--input", required=True, help="Input preview PNG path")
    parser_bitmap.add_argument("--output", required=True, help="Output bitmap path")
    add_common_render_args(parser_bitmap)
    parser_bitmap.set_defaults(func=cmd_bitmap)

    parser_confirm = sub.add_parser("confirm-assets", help="Generate pending and feedback bitmaps for confirm flows")
    parser_confirm.add_argument("--output-dir", required=True, help="Directory for generated PNG and BIN files")
    parser_confirm.add_argument("--title", default=None)
    parser_confirm.add_argument("--body", required=True, help="Confirm body text, or '-' to read stdin")
    parser_confirm.add_argument("--confirm-label", default="Confirm (BTN1)")
    parser_confirm.add_argument("--cancel-label", default="Cancel (BTN2)")
    parser_confirm.add_argument("--confirmed-text", default="Confirmed")
    parser_confirm.add_argument("--cancelled-text", default="Cancelled")
    parser_confirm.add_argument("--timeout-text", default="Timed out")
    parser_confirm.add_argument("--assets-root", default=None, help="Optional base directory for image assets")
    add_common_render_args(parser_confirm, include_bw_preview_path=False)
    parser_confirm.add_argument(
        "--bw-preview",
        action="store_true",
        help="Also emit thresholded preview PNG files next to each bitmap",
    )
    parser_confirm.set_defaults(func=cmd_confirm_assets)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except RenderPipelineError as exc:
        _print_json(LocalCliError(exc.code, exc.message, exc.details).payload())
        return 2
    except LocalCliError as exc:
        _print_json(exc.payload())
        return 2


__all__ = ["main", "build_parser"]
