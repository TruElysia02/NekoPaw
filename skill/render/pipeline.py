from __future__ import annotations

from dataclasses import dataclass
import base64
from io import BytesIO
from html import escape
import mimetypes
import os
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
COMPOSITION_LAYERED_DIRECT_TEXT = "layered-direct-text-overlay"

VALID_FIT = ("contain", "cover", "stretch")
VALID_DITHER = ("none", "floyd-steinberg")
VALID_TEXT_ROLES = ("title", "subtitle", "body", "caption", "badge")
VALID_ALIGN = ("left", "center", "right")
VALID_VALIGN = ("top", "middle", "bottom")
VALID_SCENE_IMAGE_FIT = ("contain", "cover", "fill")
VALID_IMAGE_ANCHOR = (
    "top-left",
    "top",
    "top-right",
    "left",
    "center",
    "right",
    "bottom-left",
    "bottom",
    "bottom-right",
)
IMAGE_ANCHOR_POSITIONS = {
    "top-left": "left top",
    "top": "center top",
    "top-right": "right top",
    "left": "left center",
    "center": "center center",
    "right": "right center",
    "bottom-left": "left bottom",
    "bottom": "center bottom",
    "bottom-right": "right bottom",
}
SCENE_IMAGE_Z_BASE = 0
SCENE_FOREGROUND_Z_BASE = 1000
DEFAULT_TEXT_PADDING = 4
DEFAULT_FRAME_STROKE = 2
LOW_RES_TEXT_SAFE_INSET = 1
LOW_RES_BADGE_MIN_HEIGHT = 20
LOW_RES_TEXT_THRESHOLD = 160
FONT_ENV_REGULAR = "NEKOPAW_RENDER_FONT_REGULAR"
FONT_ENV_BOLD = "NEKOPAW_RENDER_FONT_BOLD"

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
class SceneTextRoleSpec:
    font_size: int
    line_height_ratio: float
    bold: bool
    max_lines: int | None = None
    single_line: bool = False


@dataclass(frozen=True, slots=True)
class SceneBlockBox:
    x: int
    y: int
    w: int
    h: int
    z: int
    padding: int
    padding_explicit: bool


@dataclass(frozen=True, slots=True)
class NormalizedSceneTextBlock:
    index: int
    box: SceneBlockBox
    text: str
    role: str
    align: str
    valign: str
    frame: bool
    invert: bool
    role_spec: SceneTextRoleSpec


@dataclass(frozen=True, slots=True)
class NormalizedSceneImageBlock:
    index: int
    box: SceneBlockBox
    src_value: str
    alt: str
    fit: str
    anchor: str
    frame: bool


NormalizedSceneBlock = NormalizedSceneTextBlock | NormalizedSceneImageBlock


@dataclass(frozen=True, slots=True)
class NormalizedScene:
    blocks: tuple[NormalizedSceneBlock, ...]
    text_blocks: tuple[NormalizedSceneTextBlock, ...]
    image_blocks: tuple[NormalizedSceneImageBlock, ...]


@dataclass(frozen=True, slots=True)
class SceneTextLine:
    text: str
    width: int
    bbox_left: int
    bbox_top: int
    bbox_right: int
    bbox_bottom: int


@dataclass(frozen=True, slots=True)
class SceneTextLayout:
    block: NormalizedSceneTextBlock
    lines: tuple[SceneTextLine, ...]
    line_height: int
    content_x: int
    content_y: int
    content_width: int
    content_height: int


@dataclass(frozen=True, slots=True)
class DirectTextLayers:
    black_values: list[int]
    white_values: list[int]
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class RenderProfile:
    name: str
    composition: str
    css_vars: dict[str, str]
    foreground_threshold: int | None = None
    text_threshold: int | None = None


DEFAULT_RENDER_PROFILE = RenderProfile(
    name=DEFAULT_PROFILE_NAME,
    composition=COMPOSITION_SINGLE_LAYER_PREVIEW,
    css_vars={},
)

EPD_RENDER_PROFILE = RenderProfile(
    name=EPD_PROFILE_NAME,
    composition=COMPOSITION_LAYERED_FOREGROUND,
    foreground_threshold=208,
    text_threshold=LOW_RES_TEXT_THRESHOLD,
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

DEFAULT_SCENE_ROLE_SPECS = {
    "title": SceneTextRoleSpec(font_size=18, line_height_ratio=1.02, bold=True),
    "subtitle": SceneTextRoleSpec(font_size=12, line_height_ratio=1.08, bold=True),
    "body": SceneTextRoleSpec(font_size=10, line_height_ratio=1.22, bold=False),
    "caption": SceneTextRoleSpec(font_size=8, line_height_ratio=1.1, bold=False),
    "badge": SceneTextRoleSpec(font_size=9, line_height_ratio=1.05, bold=True),
}

EPD_SCENE_ROLE_SPECS = {
    "title": SceneTextRoleSpec(font_size=18, line_height_ratio=1.02, bold=True, max_lines=2),
    "subtitle": SceneTextRoleSpec(font_size=12, line_height_ratio=1.08, bold=True, max_lines=2),
    "body": SceneTextRoleSpec(font_size=10, line_height_ratio=1.18, bold=False),
    "caption": SceneTextRoleSpec(font_size=9, line_height_ratio=1.1, bold=False, max_lines=1, single_line=True),
    "badge": SceneTextRoleSpec(font_size=10, line_height_ratio=1.05, bold=True, max_lines=1, single_line=True),
}


def resolve_render_profile(settings: RenderSettings) -> RenderProfile:
    if settings.width == DEFAULT_WIDTH and settings.height == DEFAULT_HEIGHT:
        return EPD_RENDER_PROFILE
    return DEFAULT_RENDER_PROFILE


def _is_low_res_epd(settings: RenderSettings) -> bool:
    return settings.width == DEFAULT_WIDTH and settings.height == DEFAULT_HEIGHT


def _scene_role_specs_for_settings(settings: RenderSettings) -> dict[str, SceneTextRoleSpec]:
    if _is_low_res_epd(settings):
        return EPD_SCENE_ROLE_SPECS
    return DEFAULT_SCENE_ROLE_SPECS


def _resolve_scene_role_spec(settings: RenderSettings, role: str) -> SceneTextRoleSpec:
    return _scene_role_specs_for_settings(settings)[role]


def _resolve_scene_composition(settings: RenderSettings) -> str:
    if _is_low_res_epd(settings):
        return COMPOSITION_LAYERED_DIRECT_TEXT
    return resolve_render_profile(settings).composition


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


def _require_pillow_text():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ModuleNotFoundError as exc:
        raise RenderPipelineError(
            "MISSING_DEPENDENCY",
            "bitmap conversion requires Pillow",
            {"package": "Pillow", "install": "pip install -r skill/render/requirements.txt"},
        ) from exc

    return Image, ImageDraw, ImageFont


def _text_prefers_cjk_font(text: str) -> bool:
    return any(ord(char) > 0x7F and not char.isspace() for char in text)


def _scene_font_candidates(
    bold: bool,
    *,
    text: str = "",
    settings: RenderSettings | None = None,
) -> list[str]:
    env_value = os.getenv(FONT_ENV_BOLD if bold else FONT_ENV_REGULAR)
    if env_value:
        return [env_value]

    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    low_res_epd = settings is not None and _is_low_res_epd(settings)
    if low_res_epd and _text_prefers_cjk_font(text):
        windows_fonts = [
            windir / "Fonts" / ("msyhbd.ttc" if bold else "msyh.ttc"),
            windir / "Fonts" / ("YuGothB.ttc" if bold else "YuGothR.ttc"),
            windir / "Fonts" / ("segoeuib.ttf" if bold else "segoeui.ttf"),
        ]
        generic_fonts = [
            "NotoSansCJK-Bold.ttc" if bold else "NotoSansCJK-Regular.ttc",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        ]
    elif low_res_epd:
        windows_fonts = [
            windir / "Fonts" / ("verdanab.ttf" if bold else "verdana.ttf"),
            windir / "Fonts" / ("tahomabd.ttf" if bold else "tahoma.ttf"),
            windir / "Fonts" / ("segoeuib.ttf" if bold else "segoeui.ttf"),
        ]
        generic_fonts = [
            "Arial Bold.ttf" if bold else "Arial.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        ]
    else:
        windows_fonts = [
            windir / "Fonts" / ("msyhbd.ttc" if bold else "msyh.ttc"),
            windir / "Fonts" / ("segoeuib.ttf" if bold else "segoeui.ttf"),
        ]
        generic_fonts = [
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            "Arial Bold.ttf" if bold else "Arial.ttf",
        ]

    return [*(str(path) for path in windows_fonts), *generic_fonts]


def _load_scene_font(
    image_font_module: Any,
    font_size: int,
    *,
    bold: bool,
    text: str = "",
    settings: RenderSettings | None = None,
):
    for candidate in _scene_font_candidates(bold, text=text, settings=settings):
        try:
            return image_font_module.truetype(candidate, size=font_size)
        except OSError:
            continue
    return image_font_module.load_default()


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


def _coerce_scene_nonnegative_int(value: Any, field: str, index: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RenderPipelineError(
            "INVALID_JSON",
            f"scene block {field} must be an integer",
            {"index": index, field: value},
        ) from exc

    if parsed < 0:
        raise RenderPipelineError(
            "INVALID_JSON",
            f"scene block {field} must be >= 0",
            {"index": index, field: parsed},
        )
    return parsed


def _scene_position_box(
    block: dict[str, Any],
    index: int,
    *,
    default_padding: int = 0,
) -> SceneBlockBox:
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

    padding_explicit = "padding" in block
    padding_value = block.get("padding", default_padding)
    padding = _coerce_scene_nonnegative_int(padding_value, "padding", index)
    z_value = _coerce_scene_nonnegative_int(block.get("z", 0), "z", index)
    return SceneBlockBox(
        x=x,
        y=y,
        w=width,
        h=height,
        z=z_value,
        padding=padding,
        padding_explicit=padding_explicit,
    )


def _estimate_single_line_width(text: str, font_size: int) -> int:
    total = 0.0
    for char in text:
        if char.isspace():
            total += font_size * 0.35
        elif ord(char) >= 0x2E80:
            total += font_size * 1.0
        elif char.isupper():
            total += font_size * 0.72
        elif char.isdigit():
            total += font_size * 0.58
        elif char.isalpha():
            total += font_size * 0.56
        else:
            total += font_size * 0.44
    return int(total + 0.9999)


def _flatten_single_line_text(text: str) -> str:
    return " ".join(part for part in text.split())


def _normalize_scene_text_block(
    block: dict[str, Any],
    index: int,
    settings: RenderSettings,
) -> NormalizedSceneTextBlock:
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

    role_spec = _resolve_scene_role_spec(settings, role)
    box = _scene_position_box(block, index, default_padding=DEFAULT_TEXT_PADDING)
    frame = bool(block.get("frame"))
    invert = bool(block.get("invert"))

    if _is_low_res_epd(settings) and role == "badge" and invert:
        safe_inset = LOW_RES_TEXT_SAFE_INSET * 2
        content_width = max(
            1,
            box.w - (box.padding * 2) - (DEFAULT_FRAME_STROKE * 2 if frame else 0) - safe_inset,
        )
        estimated_text_width = _estimate_single_line_width(_flatten_single_line_text(text), role_spec.font_size)
        if box.h < LOW_RES_BADGE_MIN_HEIGHT or estimated_text_width > content_width:
            invert = False

    return NormalizedSceneTextBlock(
        index=index,
        box=box,
        text=text,
        role=role,
        align=align,
        valign=valign,
        frame=frame,
        invert=invert,
        role_spec=role_spec,
    )


def _normalize_scene_image_block(
    block: dict[str, Any],
    index: int,
    base_dir: Path | None,
) -> NormalizedSceneImageBlock:
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
    if fit not in VALID_SCENE_IMAGE_FIT:
        raise RenderPipelineError("INVALID_JSON", "image block fit is invalid", {"index": index, "fit": fit})
    anchor = block.get("anchor", "center")
    if anchor not in VALID_IMAGE_ANCHOR:
        raise RenderPipelineError("INVALID_JSON", "image block anchor is invalid", {"index": index, "anchor": anchor})

    return NormalizedSceneImageBlock(
        index=index,
        box=_scene_position_box(block, index),
        src_value=src_value,
        alt=str(block.get("alt", "")),
        fit=fit,
        anchor=anchor,
        frame=bool(block.get("frame")),
    )


def normalize_scene(
    scene: dict[str, Any],
    base_dir: Path | None = None,
    *,
    settings: RenderSettings | None = None,
) -> NormalizedScene:
    render_settings = settings or RenderSettings()
    blocks: list[NormalizedSceneBlock] = []
    text_blocks: list[NormalizedSceneTextBlock] = []
    image_blocks: list[NormalizedSceneImageBlock] = []

    for index, block in enumerate(_coerce_scene(scene)):
        block_type = block.get("type")
        if block_type == "text":
            normalized_text = _normalize_scene_text_block(block, index, render_settings)
            blocks.append(normalized_text)
            text_blocks.append(normalized_text)
        elif block_type == "image":
            normalized_image = _normalize_scene_image_block(block, index, base_dir)
            blocks.append(normalized_image)
            image_blocks.append(normalized_image)
        else:
            raise RenderPipelineError(
                "INVALID_JSON",
                "scene block type must be text or image",
                {"index": index, "type": block_type},
            )

    return NormalizedScene(
        blocks=tuple(blocks),
        text_blocks=tuple(text_blocks),
        image_blocks=tuple(image_blocks),
    )


def _scene_position_style(box: SceneBlockBox, *, z_base: int) -> str:
    style_parts = [
        f"left:{box.x}px",
        f"top:{box.y}px",
        f"width:{box.w}px",
        f"height:{box.h}px",
        f"z-index:{z_base + box.z}",
    ]
    if box.padding_explicit:
        style_parts.append(f"padding:{box.padding}px")
    return ";".join(style_parts) + ";"


def _normalized_text_block_to_html(block: NormalizedSceneTextBlock) -> str:
    classes = [
        "scene-block",
        "scene-block--text",
        f"scene-role-{block.role}",
        f"scene-align-{block.align}",
        f"scene-valign-{block.valign}",
    ]
    if block.frame:
        classes.append("scene-frame")
    if block.invert:
        classes.append("scene-invert")
    if block.role_spec.single_line:
        classes.append("scene-single-line")
    elif block.role_spec.max_lines is not None:
        classes.append(f"scene-max-lines-{block.role_spec.max_lines}")

    style = _scene_position_style(block.box, z_base=SCENE_FOREGROUND_Z_BASE)
    return (
        f'<div class="{" ".join(classes)}" data-np-layer="foreground" style="{style}">'
        f'<span class="scene-block__copy">{escape(block.text)}</span>'
        "</div>"
    )


def _normalized_image_block_to_html(block: NormalizedSceneImageBlock) -> str:
    image_style = f"object-fit:{block.fit};object-position:{IMAGE_ANCHOR_POSITIONS[block.anchor]};"
    image_block_style = _scene_position_style(block.box, z_base=SCENE_IMAGE_Z_BASE)
    parts = [
        f'<figure class="scene-block scene-block--image" data-np-layer="image" style="{image_block_style}">',
        f'<img alt="{escape(block.alt)}" src="{block.src_value}" style="{image_style}">',
        "</figure>",
    ]
    if block.frame:
        frame_style = _scene_position_style(block.box, z_base=SCENE_FOREGROUND_Z_BASE)
        parts.append(
            f'<span class="scene-block scene-block--image-frame" data-np-layer="decoration" style="{frame_style}"></span>'
        )
    return "".join(parts)


def normalized_scene_to_html(scene: NormalizedScene) -> str:
    html_blocks: list[str] = []
    for block in scene.blocks:
        if isinstance(block, NormalizedSceneTextBlock):
            html_blocks.append(_normalized_text_block_to_html(block))
        elif isinstance(block, NormalizedSceneImageBlock):
            html_blocks.append(_normalized_image_block_to_html(block))
        else:
            raise RenderPipelineError("INVALID_JSON", "unsupported normalized scene block")

    return "".join(html_blocks)


def scene_to_html(
    scene: dict[str, Any],
    base_dir: Path | None = None,
    settings: RenderSettings | None = None,
) -> str:
    return normalized_scene_to_html(normalize_scene(scene, base_dir, settings=settings))


def _scene_block_sort_key(block: NormalizedSceneTextBlock | NormalizedSceneImageBlock) -> tuple[int, int]:
    return (block.box.z, block.index)


def _text_bbox(draw: Any, text: str, font: Any) -> tuple[int, int, int, int]:
    if text == "":
        return (0, 0, 0, 0)
    bbox = draw.textbbox((0, 0), text, font=font)
    return (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))


def _text_width(draw: Any, text: str, font: Any) -> int:
    bbox = _text_bbox(draw, text, font)
    return max(0, int(bbox[2] - bbox[0]))


def _font_line_height(font: Any, *, role_spec: SceneTextRoleSpec) -> int:
    try:
        ascent, descent = font.getmetrics()
        metric_height = int(ascent + descent)
    except Exception:
        metric_height = role_spec.font_size
    scaled_height = int((role_spec.font_size * role_spec.line_height_ratio) + 0.9999)
    return max(metric_height, scaled_height)


def _wrap_scene_paragraph(draw: Any, text: str, font: Any, max_width: int) -> list[str]:
    if text == "":
        return [""]

    has_ws = bool(re.search(r"\s", text))
    tokens: Iterable[str] = text.split() if has_ws else list(text)
    lines: list[str] = []
    current = ""
    for token in tokens:
        candidate = token if current == "" else (current + (" " if has_ws else "") + token)
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = token
            continue

        if has_ws:
            fragment = ""
            for char in token:
                candidate_fragment = char if fragment == "" else fragment + char
                if _text_width(draw, candidate_fragment, font) <= max_width:
                    fragment = candidate_fragment
                else:
                    if fragment:
                        lines.append(fragment)
                    fragment = char
            current = fragment
        else:
            lines.append(token)
            current = ""

    if current:
        lines.append(current)
    return lines


def _wrap_scene_text(draw: Any, text: str, font: Any, max_width: int, *, single_line: bool) -> list[str]:
    if single_line:
        return [_flatten_single_line_text(text)]

    lines: list[str] = []
    for paragraph in text.splitlines():
        if paragraph.strip() == "":
            lines.append("")
            continue
        lines.extend(_wrap_scene_paragraph(draw, paragraph, font, max_width))
    return lines or [""]


def _ellipsize_text(draw: Any, text: str, font: Any, max_width: int) -> str:
    if _text_width(draw, text, font) <= max_width:
        return text

    ellipsis = "..."
    if _text_width(draw, ellipsis, font) > max_width:
        return ""

    trimmed = text
    while trimmed:
        candidate = trimmed.rstrip() + ellipsis
        if _text_width(draw, candidate, font) <= max_width:
            return candidate
        trimmed = trimmed[:-1]
    return ellipsis


def _truncate_scene_lines(
    draw: Any,
    lines: list[str],
    font: Any,
    max_width: int,
    max_lines: int | None,
) -> list[str]:
    truncated = list(lines)
    if truncated and max_lines is not None and len(truncated) > max_lines:
        truncated = truncated[:max_lines]
        truncated[-1] = _ellipsize_text(draw, truncated[-1], font, max_width)
    elif truncated and max_lines == 1:
        truncated[0] = _ellipsize_text(draw, truncated[0], font, max_width)
    elif truncated and _text_width(draw, truncated[-1], font) > max_width:
        truncated[-1] = _ellipsize_text(draw, truncated[-1], font, max_width)
    return truncated


def _layout_text_block(
    draw: Any,
    image_font_module: Any,
    block: NormalizedSceneTextBlock,
    settings: RenderSettings,
) -> SceneTextLayout:
    frame_padding = DEFAULT_FRAME_STROKE if block.frame else 0
    safe_inset = LOW_RES_TEXT_SAFE_INSET if _is_low_res_epd(settings) else 0
    content_x = block.box.padding + frame_padding + safe_inset
    content_y = block.box.padding + frame_padding + safe_inset
    content_width = max(1, block.box.w - (block.box.padding * 2) - (frame_padding * 2) - (safe_inset * 2))
    content_height = max(1, block.box.h - (block.box.padding * 2) - (frame_padding * 2) - (safe_inset * 2))

    font = _load_scene_font(
        image_font_module,
        block.role_spec.font_size,
        bold=block.role_spec.bold,
        text=block.text,
        settings=settings,
    )
    line_height = _font_line_height(font, role_spec=block.role_spec)

    requested_lines = _wrap_scene_text(
        draw,
        block.text,
        font,
        content_width,
        single_line=block.role_spec.single_line,
    )

    max_lines_from_height = max(1, content_height // max(line_height, 1))
    max_lines = max_lines_from_height
    if block.role_spec.max_lines is not None:
        max_lines = min(max_lines, block.role_spec.max_lines)

    visible_lines = _truncate_scene_lines(draw, requested_lines, font, content_width, max_lines)
    line_items_list: list[SceneTextLine] = []
    for line in visible_lines:
        bbox_left, bbox_top, bbox_right, bbox_bottom = _text_bbox(draw, line, font)
        line_items_list.append(
            SceneTextLine(
                text=line,
                width=max(0, bbox_right - bbox_left),
                bbox_left=bbox_left,
                bbox_top=bbox_top,
                bbox_right=bbox_right,
                bbox_bottom=bbox_bottom,
            )
        )
    line_items = tuple(line_items_list)
    ink_bounds = [
        (index * line_height + line.bbox_top, index * line_height + line.bbox_bottom)
        for index, line in enumerate(line_items)
        if line.text
    ]
    if ink_bounds:
        ink_top = min(top for top, _ in ink_bounds)
        ink_bottom = max(bottom for _, bottom in ink_bounds)
        ink_height = max(1, ink_bottom - ink_top)
    else:
        ink_top = 0
        ink_height = max(line_height, len(line_items) * line_height)
    if block.valign == "middle":
        start_y = content_y + max(0, (content_height - ink_height) // 2) - ink_top
    elif block.valign == "bottom":
        start_y = content_y + max(0, content_height - ink_height) - ink_top
    else:
        start_y = content_y - ink_top

    return SceneTextLayout(
        block=block,
        lines=line_items,
        line_height=line_height,
        content_x=content_x,
        content_y=start_y,
        content_width=content_width,
        content_height=content_height,
    )


def _draw_text_block_background(draw: Any, block: NormalizedSceneTextBlock) -> None:
    if block.invert:
        draw.rectangle(
            (
                0,
                0,
                block.box.w - 1,
                block.box.h - 1,
            ),
            fill=0,
        )
    if block.frame:
        draw.rectangle(
            (
                0,
                0,
                block.box.w - 1,
                block.box.h - 1,
            ),
            outline=0,
            width=DEFAULT_FRAME_STROKE,
        )


def _draw_text_layout(
    draw: Any,
    image_font_module: Any,
    layout: SceneTextLayout,
    settings: RenderSettings,
    *,
    white_text: bool,
) -> None:
    font = _load_scene_font(
        image_font_module,
        layout.block.role_spec.font_size,
        bold=layout.block.role_spec.bold,
        text=layout.block.text,
        settings=settings,
    )
    y = layout.content_y
    for line in layout.lines:
        if layout.block.align == "center":
            x = layout.content_x + max(0, (layout.content_width - line.width) // 2) - line.bbox_left
        elif layout.block.align == "right":
            x = layout.content_x + max(0, layout.content_width - line.width) - line.bbox_left
        else:
            x = layout.content_x - line.bbox_left
        draw.text((x, y), line.text, font=font, fill=0 if white_text else 0)
        y += layout.line_height


def _render_text_block_layers(
    block: NormalizedSceneTextBlock,
    settings: RenderSettings,
    *,
    text_threshold: int,
) -> DirectTextLayers:
    Image, ImageDraw, ImageFont = _require_pillow_text()
    black_canvas = Image.new("L", (block.box.w, block.box.h), 255)
    white_canvas = Image.new("L", (block.box.w, block.box.h), 255)
    black_draw = ImageDraw.Draw(black_canvas)
    white_draw = ImageDraw.Draw(white_canvas)
    measure_canvas = Image.new("L", (1, 1), 255)
    measure_draw = ImageDraw.Draw(measure_canvas)
    layout = _layout_text_block(measure_draw, ImageFont, block, settings)

    _draw_text_block_background(black_draw, layout.block)
    if layout.block.invert:
        _draw_text_layout(white_draw, ImageFont, layout, settings, white_text=True)
    else:
        _draw_text_layout(black_draw, ImageFont, layout, settings, white_text=False)

    return DirectTextLayers(
        black_values=_threshold_pixels(list(black_canvas.getdata()), text_threshold),
        white_values=_threshold_pixels(list(white_canvas.getdata()), text_threshold),
        width=block.box.w,
        height=block.box.h,
    )


def _overlay_black_region(
    image_values: list[int],
    overlay_values: list[int],
    *,
    image_width: int,
    image_height: int,
    overlay_width: int,
    overlay_height: int,
    dest_x: int,
    dest_y: int,
) -> None:
    for overlay_y in range(overlay_height):
        image_y = dest_y + overlay_y
        if image_y < 0 or image_y >= image_height:
            continue
        for overlay_x in range(overlay_width):
            image_x = dest_x + overlay_x
            if image_x < 0 or image_x >= image_width:
                continue
            overlay_index = (overlay_y * overlay_width) + overlay_x
            if overlay_values[overlay_index] == 0:
                image_values[(image_y * image_width) + image_x] = 0


def _overlay_white_region(
    image_values: list[int],
    overlay_values: list[int],
    *,
    image_width: int,
    image_height: int,
    overlay_width: int,
    overlay_height: int,
    dest_x: int,
    dest_y: int,
) -> None:
    for overlay_y in range(overlay_height):
        image_y = dest_y + overlay_y
        if image_y < 0 or image_y >= image_height:
            continue
        for overlay_x in range(overlay_width):
            image_x = dest_x + overlay_x
            if image_x < 0 or image_x >= image_width:
                continue
            overlay_index = (overlay_y * overlay_width) + overlay_x
            if overlay_values[overlay_index] == 0:
                image_values[(image_y * image_width) + image_x] = 255


def _compose_scene_text_blocks(
    base_values: list[int],
    scene: NormalizedScene,
    settings: RenderSettings,
    *,
    text_threshold: int,
) -> list[int]:
    composed_values = list(base_values)
    for block in sorted(scene.text_blocks, key=_scene_block_sort_key):
        block_layers = _render_text_block_layers(block, settings, text_threshold=text_threshold)
        _overlay_black_region(
            composed_values,
            block_layers.black_values,
            image_width=settings.width,
            image_height=settings.height,
            overlay_width=block_layers.width,
            overlay_height=block_layers.height,
            dest_x=block.box.x,
            dest_y=block.box.y,
        )
        _overlay_white_region(
            composed_values,
            block_layers.white_values,
            image_width=settings.width,
            image_height=settings.height,
            overlay_width=block_layers.width,
            overlay_height=block_layers.height,
            dest_x=block.box.x,
            dest_y=block.box.y,
        )

    return composed_values


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
    normalized_scene = normalize_scene(scene, base_dir, settings=settings)
    document = build_scene_document(
        title,
        normalized_scene_to_html(normalized_scene),
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


def overlay_white_pixels(image_values: list[int], white_values: list[int]) -> list[int]:
    if len(image_values) != len(white_values):
        raise RenderPipelineError(
            "INVALID_ARGUMENT",
            "image and white layers must have the same pixel count",
            {"image": len(image_values), "white": len(white_values)},
        )
    return [255 if white == 0 else image for image, white in zip(image_values, white_values)]


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


def convert_scene_captures_to_bitmap(
    image_capture: bytes,
    decoration_capture: bytes,
    scene: NormalizedScene,
    settings: RenderSettings,
    *,
    bitmap_path: str | Path,
    bw_preview_path: str | Path | None = None,
    foreground_threshold: int,
    text_threshold: int,
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

    decoration_layer = _load_grayscale_bytes(decoration_capture, Image)
    decoration_high_res = _threshold_pixels(list(decoration_layer.getdata()), foreground_threshold)
    decoration_values = reduce_oversampled_binary(
        decoration_high_res,
        source_width=decoration_layer.width,
        source_height=decoration_layer.height,
        target_width=settings.width,
        target_height=settings.height,
    )

    composed_values = overlay_mono_layers(image_values, decoration_values)
    composed_values = _compose_scene_text_blocks(
        composed_values,
        scene,
        settings,
        text_threshold=text_threshold,
    )
    return _bitmap_artifact_from_values(
        Image,
        composed_values,
        width=settings.width,
        height=settings.height,
        bitmap_path=bitmap_path,
        bw_preview_path=bw_preview_path,
    )


def _artifact_metadata(
    preview_path: str | Path,
    settings: RenderSettings,
    profile: RenderProfile,
    *,
    composition: str | None = None,
) -> dict[str, Any]:
    return {
        "previewPath": str(Path(preview_path)),
        "width": settings.width,
        "height": settings.height,
        "dither": settings.dither,
        "threshold": settings.threshold,
        "fit": settings.fit,
        "profile": profile.name,
        "composition": composition or profile.composition,
    }


def _render_document_to_artifacts(
    document: str,
    *,
    preview_path: str | Path,
    settings: RenderSettings,
    profile: RenderProfile,
    bitmap_path: str | Path | None = None,
    bw_preview_path: str | Path | None = None,
    composition: str | None = None,
) -> dict[str, Any]:
    capture_modes: tuple[str, ...] = ()
    selected_composition = composition or profile.composition
    if bitmap_path is not None and selected_composition == COMPOSITION_LAYERED_FOREGROUND:
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
        **_artifact_metadata(preview_path, settings, profile, composition=selected_composition),
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
    composition = _resolve_scene_composition(settings)
    normalized_scene = normalize_scene(scene, base_dir, settings=settings)
    document = build_scene_document(
        "NekoPaw Scene Preview",
        normalized_scene_to_html(normalized_scene),
        settings.width,
        settings.height,
        theme=profile.css_vars,
    )
    if composition != COMPOSITION_LAYERED_DIRECT_TEXT:
        return _render_document_to_artifacts(
            document,
            preview_path=preview_path,
            settings=settings,
            profile=profile,
            bitmap_path=bitmap_path,
            bw_preview_path=bw_preview_path,
            composition=composition,
        )

    capture_modes: tuple[str, ...] = ()
    if bitmap_path is not None:
        capture_modes = ("image", "decoration")

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
        **_artifact_metadata(preview_path, settings, profile, composition=composition),
    }

    if bitmap_path is not None:
        bitmap_artifact = convert_scene_captures_to_bitmap(
            captures["image"],
            captures["decoration"],
            normalized_scene,
            settings,
            bitmap_path=bitmap_path,
            bw_preview_path=bw_preview_path,
            foreground_threshold=profile.foreground_threshold or settings.threshold,
            text_threshold=profile.text_threshold or settings.threshold,
        )
        result["bitmapPath"] = str(Path(bitmap_path))
        result["bitmapBytes"] = bitmap_artifact.bitmap_byte_count
        if bw_preview_path is not None:
            result["bwPreviewPath"] = str(Path(bw_preview_path))

    return result


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
    button_height = 18
    button_y = height - 12 - button_height

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
                "h": button_height,
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
                "h": button_height,
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
                    "h": 20,
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
