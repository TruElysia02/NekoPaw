from __future__ import annotations

from dataclasses import dataclass
import base64
from io import BytesIO
from html import escape
import mimetypes
import re
from pathlib import Path
from typing import Any, Iterable

from .templates import build_markdown_document, build_scene_document


DEFAULT_WIDTH = 296
DEFAULT_HEIGHT = 128
DEFAULT_SCALE = 4
DEFAULT_THRESHOLD = 160
DEFAULT_FIT = "contain"
DEFAULT_DITHER = "none"
DEFAULT_PROFILE_NAME = "default"
EPD_PROFILE_NAME = "epd_296x128_bw"
COMPOSITION_SINGLE_LAYER_PREVIEW = "single-layer-preview"
COMPOSITION_SINGLE_LAYER_IMAGE = "single-layer-image"
COMPOSITION_LAYERED_FOREGROUND = "layered-foreground-overlay"

VALID_FIT = ("contain", "cover", "stretch")
VALID_DITHER = ("none", "floyd-steinberg")
VALID_TEXT_ROLES = ("title", "subtitle", "body", "caption", "badge")
VALID_ALIGN = ("left", "center", "right")
VALID_VALIGN = ("top", "middle", "bottom")

_IMG_SRC_RE = re.compile(r"(<img\b[^>]*\bsrc=)(['\"])([^'\"]+)(\2)", re.IGNORECASE)


class RenderPipelineError(Exception):
    def __init__(self, code: str, message: str, details: Any | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(slots=True)
class RenderSettings:
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    scale: int = DEFAULT_SCALE
    threshold: int = DEFAULT_THRESHOLD
    dither: str = DEFAULT_DITHER
    fit: str = DEFAULT_FIT

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise RenderPipelineError("INVALID_ARGUMENT", "width and height must be > 0")
        if self.scale <= 0:
            raise RenderPipelineError("INVALID_ARGUMENT", "scale must be > 0")
        if self.fit not in VALID_FIT:
            raise RenderPipelineError("INVALID_ARGUMENT", "fit must be contain, cover, or stretch", {"fit": self.fit})
        if self.dither not in VALID_DITHER:
            raise RenderPipelineError(
                "INVALID_ARGUMENT",
                "dither must be none or floyd-steinberg",
                {"dither": self.dither},
            )
        if not 0 <= self.threshold <= 255:
            raise RenderPipelineError("INVALID_ARGUMENT", "threshold must be between 0 and 255")


@dataclass(slots=True)
class BitmapArtifact:
    width: int
    height: int
    bitmap_bytes: bytes
    bitmap_byte_count: int


@dataclass(frozen=True, slots=True)
class RenderProfile:
    name: str
    composition: str
    css_vars: dict[str, str]
    foreground_threshold: int | None = None


DEFAULT_RENDER_PROFILE = RenderProfile(
    name=DEFAULT_PROFILE_NAME,
    composition=COMPOSITION_SINGLE_LAYER_PREVIEW,
    css_vars={},
)

EPD_RENDER_PROFILE = RenderProfile(
    name=EPD_PROFILE_NAME,
    composition=COMPOSITION_LAYERED_FOREGROUND,
    foreground_threshold=208,
    css_vars={
        "--muted": "#111111",
        "--frame-stroke": "2px",
        "--md-kicker-size": "7px",
        "--md-kicker-letter": "0.06em",
        "--md-kicker-transform": "none",
        "--md-title-size": "18px",
        "--md-subtitle-size": "12px",
        "--md-heading-size": "10px",
        "--md-heading-letter": "0.03em",
        "--md-heading-transform": "none",
        "--md-body-size": "10px",
        "--md-body-line": "1.2",
        "--md-footer-size": "8px",
        "--md-footer-letter": "0.02em",
        "--md-chip-size": "10px",
        "--scene-title-size": "18px",
        "--scene-subtitle-size": "12px",
        "--scene-body-size": "10px",
        "--scene-body-line": "1.18",
        "--scene-caption-size": "9px",
        "--scene-caption-letter": "0.03em",
        "--scene-caption-transform": "none",
        "--scene-badge-size": "10px",
        "--scene-badge-letter": "0em",
        "--scene-badge-transform": "none",
    },
)


def resolve_render_profile(settings: RenderSettings) -> RenderProfile:
    if settings.width == DEFAULT_WIDTH and settings.height == DEFAULT_HEIGHT:
        return EPD_RENDER_PROFILE
    return DEFAULT_RENDER_PROFILE


def _require_markdown():
    try:
        import markdown as markdown_lib
    except ModuleNotFoundError as exc:
        raise RenderPipelineError(
            "MISSING_DEPENDENCY",
            "markdown rendering requires the markdown package",
            {"package": "markdown", "install": "pip install -r skill/render/requirements.txt"},
        ) from exc

    return markdown_lib


def _require_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RenderPipelineError(
            "MISSING_DEPENDENCY",
            "preview rendering requires Playwright",
            {
                "package": "playwright",
                "install": [
                    "pip install -r skill/render/requirements.txt",
                    "python -m playwright install chromium",
                ],
            },
        ) from exc

    return sync_playwright


def _require_pillow():
    try:
        from PIL import Image, ImageOps
    except ModuleNotFoundError as exc:
        raise RenderPipelineError(
            "MISSING_DEPENDENCY",
            "bitmap conversion requires Pillow",
            {"package": "Pillow", "install": "pip install -r skill/render/requirements.txt"},
        ) from exc

    return Image, ImageOps


def _normalize_output_path(path: str | Path) -> Path:
    resolved = Path(path)
    if resolved.suffix == "":
        raise RenderPipelineError("INVALID_ARGUMENT", "output path must include a file extension", {"path": str(path)})
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise RenderPipelineError("FILE_READ_FAILED", f"failed to read {path}", {"reason": str(exc)}) from exc


def _resolve_asset_path(src: str, base_dir: Path | None) -> Path | None:
    if not src or re.match(r"^(?:[a-z]+:|//)", src, re.IGNORECASE):
        return None

    candidate = Path(src)
    if candidate.is_absolute():
        return candidate
    if base_dir is None:
        return candidate.resolve()
    return (base_dir / candidate).resolve()


def _path_to_data_uri(path: Path) -> str:
    raw = _read_bytes(path)
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _rewrite_image_sources(html_text: str, base_dir: Path | None) -> str:
    def replacer(match: re.Match[str]) -> str:
        prefix, quote, src, suffix = match.groups()
        asset_path = _resolve_asset_path(src, base_dir)
        if asset_path is None:
            return match.group(0)
        if not asset_path.exists():
            raise RenderPipelineError(
                "FILE_NOT_FOUND",
                "image asset does not exist",
                {"src": src, "resolvedPath": str(asset_path)},
            )
        return f"{prefix}{quote}{_path_to_data_uri(asset_path)}{suffix}"

    return _IMG_SRC_RE.sub(replacer, html_text)


def _extract_first_figure(html_text: str) -> tuple[str | None, str]:
    match = re.search(r"<p>\s*(<img\b.*?/?>)\s*</p>", html_text, re.IGNORECASE | re.DOTALL)
    if match is None:
        return None, html_text
    figure_html = match.group(1)
    body_html = (html_text[: match.start()] + html_text[match.end() :]).strip()
    return figure_html, body_html


def markdown_to_html(markdown_text: str, base_dir: Path | None = None, *, width: int, height: int) -> tuple[str, bool]:
    markdown_lib = _require_markdown()
    rendered = markdown_lib.markdown(markdown_text, extensions=["extra", "sane_lists"])
    rendered = _rewrite_image_sources(rendered, base_dir)
    figure_html, body_html = _extract_first_figure(rendered)

    article_parts = [
        '<section class="md-copy" data-np-layer="foreground">',
        '<div class="md-kicker" data-np-layer="foreground">NekoPaw render preview</div>',
        body_html or "<p>(empty)</p>",
        (
            f'<footer class="md-footer" data-np-layer="foreground">'
            f"<span>{width}x{height} preview</span>"
            '<span class="md-chip" data-np-layer="foreground">markdown</span>'
            "</footer>"
        ),
        "</section>",
    ]
    if figure_html is not None:
        article_parts.append(
            '<aside class="md-figure">'
            f'<div class="md-figure-frame" data-np-layer="image">{figure_html}</div>'
            '<span class="md-figure-label" data-np-layer="foreground">image</span>'
            "</aside>"
        )
    return "".join(article_parts), figure_html is not None


def _coerce_scene(scene: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = scene.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise RenderPipelineError("INVALID_JSON", "scene JSON must contain a non-empty blocks array")

    coerced: list[dict[str, Any]] = []
    for index, item in enumerate(blocks):
        if not isinstance(item, dict):
            raise RenderPipelineError("INVALID_JSON", "scene blocks must be objects", {"index": index})
        coerced.append(item)
    return coerced


def _scene_text_block(block: dict[str, Any], index: int) -> str:
    text = block.get("text")
    if not isinstance(text, str) or text == "":
        raise RenderPipelineError("INVALID_JSON", "text block requires a non-empty text field", {"index": index})

    role = block.get("role", "body")
    align = block.get("align", "left")
    valign = block.get("valign", "top")
    if role not in VALID_TEXT_ROLES:
        raise RenderPipelineError("INVALID_JSON", "text block role is invalid", {"index": index, "role": role})
    if align not in VALID_ALIGN:
        raise RenderPipelineError("INVALID_JSON", "text block align is invalid", {"index": index, "align": align})
    if valign not in VALID_VALIGN:
        raise RenderPipelineError("INVALID_JSON", "text block valign is invalid", {"index": index, "valign": valign})

    classes = [
        "scene-block",
        "scene-block--text",
        f"scene-role-{role}",
        f"scene-align-{align}",
        f"scene-valign-{valign}",
    ]
    if block.get("frame"):
        classes.append("scene-frame")
    if block.get("invert"):
        classes.append("scene-invert")

    style = _scene_position_style(block, index)
    return f'<div class="{" ".join(classes)}" data-np-layer="foreground" style="{style}">{escape(text)}</div>'


def _scene_image_block(block: dict[str, Any], index: int, base_dir: Path | None) -> str:
    src = block.get("src")
    if not isinstance(src, str) or src == "":
        raise RenderPipelineError("INVALID_JSON", "image block requires a src field", {"index": index})

    resolved_path = _resolve_asset_path(src, base_dir)
    if resolved_path is not None:
        if not resolved_path.exists():
            raise RenderPipelineError(
                "FILE_NOT_FOUND",
                "image asset does not exist",
                {"index": index, "src": src, "resolvedPath": str(resolved_path)},
            )
        src_value = _path_to_data_uri(resolved_path)
    else:
        src_value = src

    fit = block.get("fit", "cover")
    if fit not in ("cover", "contain", "fill"):
        raise RenderPipelineError("INVALID_JSON", "image block fit is invalid", {"index": index, "fit": fit})

    image_style = f"object-fit:{fit};"
    frame_overlay = '<span class="scene-frame-overlay" data-np-layer="foreground"></span>' if block.get("frame") else ""
    return (
        f'<figure class="scene-block scene-block--image" data-np-layer="image" style="{_scene_position_style(block, index)}">'
        f'<img alt="{escape(str(block.get("alt", "")))}" src="{src_value}" style="{image_style}">'
        f"{frame_overlay}"
        "</figure>"
    )


def _scene_position_style(block: dict[str, Any], index: int) -> str:
    try:
        x = int(block["x"])
        y = int(block["y"])
        width = int(block["w"])
        height = int(block["h"])
    except KeyError as exc:
        raise RenderPipelineError("INVALID_JSON", "scene block is missing a required position field", {"index": index}) from exc
    except (TypeError, ValueError) as exc:
        raise RenderPipelineError("INVALID_JSON", "scene block position fields must be integers", {"index": index}) from exc

    if width <= 0 or height <= 0:
        raise RenderPipelineError(
            "INVALID_JSON",
            "scene block width and height must be > 0",
            {"index": index, "width": width, "height": height},
        )

    style_parts = [
        f"left:{x}px",
        f"top:{y}px",
        f"width:{width}px",
        f"height:{height}px",
    ]
    if "padding" in block:
        style_parts.append(f"padding:{int(block['padding'])}px")
    return ";".join(style_parts) + ";"


def scene_to_html(scene: dict[str, Any], base_dir: Path | None = None) -> str:
    html_blocks: list[str] = []
    for index, block in enumerate(_coerce_scene(scene)):
        block_type = block.get("type")
        if block_type == "text":
            html_blocks.append(_scene_text_block(block, index))
        elif block_type == "image":
            html_blocks.append(_scene_image_block(block, index, base_dir))
        else:
            raise RenderPipelineError(
                "INVALID_JSON",
                "scene block type must be text or image",
                {"index": index, "type": block_type},
            )

    return "".join(html_blocks)


def _wait_for_render_ready(page: Any) -> None:
    page.evaluate(
        """
        async () => {
          const images = Array.from(document.images);
          await Promise.all(images.map((img) => {
            if (img.complete) {
              return null;
            }
            return new Promise((resolve) => {
              const done = () => resolve(null);
              img.addEventListener("load", done, { once: true });
              img.addEventListener("error", done, { once: true });
            });
          }));
          await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        }
        """
    )


def _set_capture_mode(page: Any, capture_mode: str | None) -> None:
    page.evaluate(
        """
        (mode) => {
          if (mode) {
            document.body.dataset.npCapture = mode;
          } else {
            delete document.body.dataset.npCapture;
          }
        }
        """,
        capture_mode,
    )
    page.evaluate("() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


def render_html_captures(
    html_document: str,
    preview_path: str | Path,
    *,
    width: int,
    height: int,
    scale: int,
) -> tuple[tuple[int, int], dict[str, bytes]]:
    return render_html_capture_set(html_document, preview_path, width=width, height=height, scale=scale, capture_modes=())


def render_html_capture_set(
    html_document: str,
    preview_path: str | Path,
    *,
    width: int,
    height: int,
    scale: int,
    capture_modes: Iterable[str],
) -> tuple[tuple[int, int], dict[str, bytes]]:
    sync_playwright = _require_playwright()
    preview_file = _normalize_output_path(preview_path)
    captures: dict[str, bytes] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=scale)
            page.set_content(html_document, wait_until="load")
            _wait_for_render_ready(page)
            page.locator(".np-page").screenshot(path=str(preview_file))
            for capture_mode in capture_modes:
                _set_capture_mode(page, capture_mode)
                captures[capture_mode] = page.locator(".np-page").screenshot()
            _set_capture_mode(page, None)
        finally:
            browser.close()

    return (width * scale, height * scale), captures


def render_html_preview(
    html_document: str,
    preview_path: str | Path,
    *,
    width: int,
    height: int,
    scale: int,
) -> tuple[int, int]:
    preview_size, _ = render_html_captures(html_document, preview_path, width=width, height=height, scale=scale)
    return preview_size


def render_markdown_preview(
    markdown_text: str,
    preview_path: str | Path,
    settings: RenderSettings,
    *,
    base_dir: Path | None = None,
    title: str = "NekoPaw Markdown Preview",
) -> tuple[int, int]:
    settings.validate()
    profile = resolve_render_profile(settings)
    content_html, has_figure = markdown_to_html(markdown_text, base_dir, width=settings.width, height=settings.height)
    document = build_markdown_document(
        title,
        content_html,
        has_figure,
        settings.width,
        settings.height,
        theme=profile.css_vars,
    )
    return render_html_preview(
        document,
        preview_path,
        width=settings.width,
        height=settings.height,
        scale=settings.scale,
    )


def render_scene_preview(
    scene: dict[str, Any],
    preview_path: str | Path,
    settings: RenderSettings,
    *,
    base_dir: Path | None = None,
    title: str = "NekoPaw Scene Preview",
) -> tuple[int, int]:
    settings.validate()
    profile = resolve_render_profile(settings)
    document = build_scene_document(
        title,
        scene_to_html(scene, base_dir),
        settings.width,
        settings.height,
        theme=profile.css_vars,
    )
    return render_html_preview(
        document,
        preview_path,
        width=settings.width,
        height=settings.height,
        scale=settings.scale,
    )


def _resize_image(image, settings: RenderSettings, image_module, image_ops):
    target_size = (settings.width, settings.height)
    if settings.fit == "stretch":
        return image.resize(target_size)
    if settings.fit == "cover":
        return image_ops.fit(image, target_size)
    contained = image_ops.contain(image, target_size)
    if contained.size == target_size:
        return contained
    canvas = image_module.new("L", target_size, 255)
    x = (settings.width - contained.width) // 2
    y = (settings.height - contained.height) // 2
    canvas.paste(contained, (x, y))
    return canvas


def _threshold_pixels(values: Iterable[int], threshold: int) -> list[int]:
    return [0 if value <= threshold else 255 for value in values]


def _floyd_steinberg(values: list[int], width: int, height: int, threshold: int) -> list[int]:
    working = [float(value) for value in values]
    output = [255] * len(values)

    for y in range(height):
        for x in range(width):
            index = y * width + x
            old_value = working[index]
            new_value = 0.0 if old_value <= threshold else 255.0
            output[index] = int(new_value)
            error = old_value - new_value

            if x + 1 < width:
                working[index + 1] += error * (7.0 / 16.0)
            if y + 1 < height:
                if x > 0:
                    working[index + width - 1] += error * (3.0 / 16.0)
                working[index + width] += error * (5.0 / 16.0)
                if x + 1 < width:
                    working[index + width + 1] += error * (1.0 / 16.0)

    return output


def reduce_oversampled_binary(
    values: list[int],
    *,
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
) -> list[int]:
    reduced: list[int] = []
    for y in range(target_height):
        start_y = (y * source_height) // target_height
        end_y = max(start_y + 1, ((y + 1) * source_height) // target_height)
        for x in range(target_width):
            start_x = (x * source_width) // target_width
            end_x = max(start_x + 1, ((x + 1) * source_width) // target_width)
            has_black = False
            for source_y in range(start_y, end_y):
                row_offset = source_y * source_width
                for source_x in range(start_x, end_x):
                    if values[row_offset + source_x] == 0:
                        has_black = True
                        break
                if has_black:
                    break
            reduced.append(0 if has_black else 255)
    return reduced


def overlay_mono_layers(image_values: list[int], foreground_values: list[int]) -> list[int]:
    if len(image_values) != len(foreground_values):
        raise RenderPipelineError(
            "INVALID_ARGUMENT",
            "image and foreground layers must have the same pixel count",
            {"image": len(image_values), "foreground": len(foreground_values)},
        )
    return [0 if foreground == 0 else image for image, foreground in zip(image_values, foreground_values)]


def pack_bitmap_bytes(values: list[int], width: int, height: int) -> bytes:
    stride = (width + 7) // 8
    output = bytearray(stride * height)

    for y in range(height):
        for x in range(width):
            value = values[y * width + x]
            if value == 0:
                byte_index = y * stride + (x // 8)
                bit_index = 7 - (x % 8)
                output[byte_index] |= 1 << bit_index

    return bytes(output)


def _mono_image_from_values(image_module: Any, values: list[int], width: int, height: int) -> Any:
    mono_image = image_module.new("L", (width, height))
    mono_image.putdata(values)
    return mono_image


def _save_mono_preview(image_module: Any, values: list[int], width: int, height: int, path: Path) -> None:
    mono_image = _mono_image_from_values(image_module, values, width, height)
    mono_image.save(path)


def _load_grayscale_bytes(image_bytes: bytes, image_module: Any) -> Any:
    try:
        with image_module.open(BytesIO(image_bytes)) as raw_image:
            return raw_image.convert("L")
    except OSError as exc:
        raise RenderPipelineError(
            "FILE_READ_FAILED",
            "failed to decode rendered image bytes",
            {"reason": str(exc)},
        ) from exc


def _mono_values_from_grayscale(values: list[int], *, width: int, height: int, threshold: int, dither: str) -> list[int]:
    if dither == "floyd-steinberg":
        return _floyd_steinberg(values, width, height, threshold)
    return _threshold_pixels(values, threshold)


def _bitmap_artifact_from_values(
    image_module: Any,
    values: list[int],
    *,
    width: int,
    height: int,
    bitmap_path: str | Path,
    bw_preview_path: str | Path | None = None,
) -> BitmapArtifact:
    bitmap_file = _normalize_output_path(bitmap_path)
    bw_preview_file = _normalize_output_path(bw_preview_path) if bw_preview_path is not None else None
    bitmap_bytes = pack_bitmap_bytes(values, width, height)
    bitmap_file.write_bytes(bitmap_bytes)

    if bw_preview_file is not None:
        _save_mono_preview(image_module, values, width, height, bw_preview_file)

    return BitmapArtifact(
        width=width,
        height=height,
        bitmap_bytes=bitmap_bytes,
        bitmap_byte_count=len(bitmap_bytes),
    )


def convert_image_to_bitmap(
    image_path: str | Path,
    settings: RenderSettings,
    *,
    bitmap_path: str | Path,
    bw_preview_path: str | Path | None = None,
) -> BitmapArtifact:
    settings.validate()
    Image, ImageOps = _require_pillow()

    try:
        with Image.open(image_path) as raw_image:
            grayscale = raw_image.convert("L")
            grayscale = _resize_image(grayscale, settings, Image, ImageOps)
    except OSError as exc:
        raise RenderPipelineError(
            "FILE_READ_FAILED",
            f"failed to open image {image_path}",
            {"reason": str(exc)},
        ) from exc

    pixels = list(grayscale.getdata())
    mono_values = _mono_values_from_grayscale(
        pixels,
        width=settings.width,
        height=settings.height,
        threshold=settings.threshold,
        dither=settings.dither,
    )

    return _bitmap_artifact_from_values(
        Image,
        mono_values,
        width=settings.width,
        height=settings.height,
        bitmap_path=bitmap_path,
        bw_preview_path=bw_preview_path,
    )


def convert_layer_captures_to_bitmap(
    image_capture: bytes,
    foreground_capture: bytes,
    settings: RenderSettings,
    *,
    bitmap_path: str | Path,
    bw_preview_path: str | Path | None = None,
    foreground_threshold: int,
) -> BitmapArtifact:
    settings.validate()
    Image, ImageOps = _require_pillow()

    image_layer = _load_grayscale_bytes(image_capture, Image)
    image_layer = _resize_image(image_layer, settings, Image, ImageOps)
    image_values = _mono_values_from_grayscale(
        list(image_layer.getdata()),
        width=settings.width,
        height=settings.height,
        threshold=settings.threshold,
        dither=settings.dither,
    )

    foreground_layer = _load_grayscale_bytes(foreground_capture, Image)
    foreground_high_res = _threshold_pixels(list(foreground_layer.getdata()), foreground_threshold)
    foreground_values = reduce_oversampled_binary(
        foreground_high_res,
        source_width=foreground_layer.width,
        source_height=foreground_layer.height,
        target_width=settings.width,
        target_height=settings.height,
    )

    composed_values = overlay_mono_layers(image_values, foreground_values)
    return _bitmap_artifact_from_values(
        Image,
        composed_values,
        width=settings.width,
        height=settings.height,
        bitmap_path=bitmap_path,
        bw_preview_path=bw_preview_path,
    )


def _artifact_metadata(preview_path: str | Path, settings: RenderSettings, profile: RenderProfile) -> dict[str, Any]:
    return {
        "previewPath": str(Path(preview_path)),
        "width": settings.width,
        "height": settings.height,
        "dither": settings.dither,
        "threshold": settings.threshold,
        "fit": settings.fit,
        "profile": profile.name,
        "composition": profile.composition,
    }


def _render_document_to_artifacts(
    document: str,
    *,
    preview_path: str | Path,
    settings: RenderSettings,
    profile: RenderProfile,
    bitmap_path: str | Path | None = None,
    bw_preview_path: str | Path | None = None,
) -> dict[str, Any]:
    capture_modes: tuple[str, ...] = ()
    if bitmap_path is not None and profile.composition == COMPOSITION_LAYERED_FOREGROUND:
        capture_modes = ("image", "foreground")

    preview_size, captures = render_html_capture_set(
        document,
        preview_path,
        width=settings.width,
        height=settings.height,
        scale=settings.scale,
        capture_modes=capture_modes,
    )

    result: dict[str, Any] = {
        "previewSize": {"width": preview_size[0], "height": preview_size[1]},
        **_artifact_metadata(preview_path, settings, profile),
    }

    if bitmap_path is not None:
        if capture_modes:
            bitmap_artifact = convert_layer_captures_to_bitmap(
                captures["image"],
                captures["foreground"],
                settings,
                bitmap_path=bitmap_path,
                bw_preview_path=bw_preview_path,
                foreground_threshold=profile.foreground_threshold or settings.threshold,
            )
        else:
            bitmap_artifact = convert_image_to_bitmap(
                preview_path,
                settings,
                bitmap_path=bitmap_path,
                bw_preview_path=bw_preview_path,
            )
        result["bitmapPath"] = str(Path(bitmap_path))
        result["bitmapBytes"] = bitmap_artifact.bitmap_byte_count
        if bw_preview_path is not None:
            result["bwPreviewPath"] = str(Path(bw_preview_path))

    return result


def render_markdown_to_artifacts(
    markdown_text: str,
    *,
    preview_path: str | Path,
    settings: RenderSettings,
    bitmap_path: str | Path | None = None,
    bw_preview_path: str | Path | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    settings.validate()
    profile = resolve_render_profile(settings)
    content_html, has_figure = markdown_to_html(markdown_text, base_dir, width=settings.width, height=settings.height)
    document = build_markdown_document(
        "NekoPaw Markdown Preview",
        content_html,
        has_figure,
        settings.width,
        settings.height,
        theme=profile.css_vars,
    )
    return _render_document_to_artifacts(
        document,
        preview_path=preview_path,
        settings=settings,
        profile=profile,
        bitmap_path=bitmap_path,
        bw_preview_path=bw_preview_path,
    )


def render_scene_to_artifacts(
    scene: dict[str, Any],
    *,
    preview_path: str | Path,
    settings: RenderSettings,
    bitmap_path: str | Path | None = None,
    bw_preview_path: str | Path | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    settings.validate()
    profile = resolve_render_profile(settings)
    document = build_scene_document(
        "NekoPaw Scene Preview",
        scene_to_html(scene, base_dir),
        settings.width,
        settings.height,
        theme=profile.css_vars,
    )
    return _render_document_to_artifacts(
        document,
        preview_path=preview_path,
        settings=settings,
        profile=profile,
        bitmap_path=bitmap_path,
        bw_preview_path=bw_preview_path,
    )


def build_confirm_scenes(
    *,
    title: str | None,
    body: str,
    confirm_label: str,
    cancel_label: str,
    confirmed_text: str,
    cancelled_text: str,
    timeout_text: str,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
) -> dict[str, dict[str, Any]]:
    header_title = title or "Confirmation"
    button_width = max((width - 34) // 2, 64)
    button_y = height - 28

    pending_scene = {
        "blocks": [
            {"type": "text", "x": 12, "y": 10, "w": width - 24, "h": 12, "text": "confirm", "role": "caption"},
            {"type": "text", "x": 12, "y": 24, "w": width - 24, "h": 22, "text": header_title, "role": "title"},
            {"type": "text", "x": 12, "y": 48, "w": width - 24, "h": 42, "text": body, "role": "body"},
            {
                "type": "text",
                "x": 12,
                "y": button_y,
                "w": button_width,
                "h": 16,
                "text": confirm_label,
                "role": "badge",
                "align": "center",
                "valign": "middle",
                "frame": True,
                "invert": True,
            },
            {
                "type": "text",
                "x": width - 12 - button_width,
                "y": button_y,
                "w": button_width,
                "h": 16,
                "text": cancel_label,
                "role": "badge",
                "align": "center",
                "valign": "middle",
                "frame": True,
            },
        ]
    }

    def status_scene(label: str, message: str, invert: bool) -> dict[str, Any]:
        return {
            "blocks": [
                {
                    "type": "text",
                    "x": 16,
                    "y": 16,
                    "w": 92,
                    "h": 18,
                    "text": label,
                    "role": "badge",
                    "align": "center",
                    "valign": "middle",
                    "frame": True,
                    "invert": invert,
                },
                {"type": "text", "x": 16, "y": 42, "w": width - 32, "h": 26, "text": header_title, "role": "subtitle"},
                {"type": "text", "x": 16, "y": 74, "w": width - 32, "h": 30, "text": message, "role": "title"},
            ]
        }

    return {
        "pending": pending_scene,
        "confirmed": status_scene("confirmed", confirmed_text, True),
        "cancelled": status_scene("cancelled", cancelled_text, False),
        "timeout": status_scene("timeout", timeout_text, False),
    }
