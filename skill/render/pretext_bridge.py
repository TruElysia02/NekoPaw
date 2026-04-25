from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .pipeline import RenderPipelineError


REPO_ROOT = Path(__file__).resolve().parents[2]
PRETEXT_PACKAGE = REPO_ROOT / "node_modules" / "@chenglou" / "pretext"
PRETEXT_ENTRY = PRETEXT_PACKAGE / "dist" / "layout.js"
PRETEXT_ROUTE_PREFIX = "/node_modules/@chenglou/pretext/"


@dataclass(frozen=True, slots=True)
class FlowTextLayoutInput:
    block_index: int
    block_id: str | None
    text: str
    font: str
    line_height: int
    content_x: int
    content_y: int
    content_width: int
    content_height: int
    screen_x: int
    screen_y: int
    align: str
    overflow: str
    avoid_rects: tuple[dict[str, Any], ...]


def _pretext_package_root() -> Path | None:
    return PRETEXT_PACKAGE if PRETEXT_ENTRY.exists() else None


def _require_pretext_package() -> Path:
    package_root = _pretext_package_root()
    if package_root is None:
        raise RenderPipelineError(
            "PRETEXT_DEPENDENCY_MISSING",
            "pretext layout requires @chenglou/pretext",
            {"package": "@chenglou/pretext", "install": "npm install"},
        )
    return package_root


def _pretext_bridge_html() -> str:
    return """
<!doctype html>
<html>
  <head><meta charset="utf-8"></head>
  <body>
    <script type="module">
      import {
        layoutNextLineRange,
        materializeLineRange,
        prepareWithSegments
      } from '/node_modules/@chenglou/pretext/dist/layout.js';

      function intersectRows(rect, rowTop, rowBottom) {
        return rect.y < rowBottom && (rect.y + rect.h) > rowTop;
      }

      function subtractSlot(slots, cutLeft, cutRight) {
        const next = [];
        for (const slot of slots) {
          const left = Math.max(slot.x, cutLeft);
          const right = Math.min(slot.x + slot.width, cutRight);
          if (right <= slot.x || left >= slot.x + slot.width) {
            next.push(slot);
            continue;
          }
          if (left > slot.x) {
            next.push({ x: slot.x, width: left - slot.x });
          }
          if (right < slot.x + slot.width) {
            next.push({ x: right, width: slot.x + slot.width - right });
          }
        }
        return next;
      }

      function slotsForRow(input, rowIndex) {
        const contentScreenX = input.screenX + input.contentX;
        const rowTop = input.screenY + input.contentY + rowIndex * input.lineHeight;
        const rowBottom = rowTop + input.lineHeight;
        let slots = [{ x: 0, width: input.contentWidth }];
        for (const rect of input.avoidRects) {
          if (!intersectRows(rect, rowTop, rowBottom)) {
            continue;
          }
          const cutLeft = Math.max(0, Math.floor(rect.x - contentScreenX));
          const cutRight = Math.min(input.contentWidth, Math.ceil(rect.x + rect.w - contentScreenX));
          if (cutRight > cutLeft) {
            slots = subtractSlot(slots, cutLeft, cutRight);
          }
        }
        slots.sort((a, b) => b.width - a.width || a.x - b.x);
        return slots;
      }

      function materializeBlock(input) {
        const prepared = prepareWithSegments(input.text, input.font, { whiteSpace: 'pre-wrap' });
        const maxRows = Math.max(0, Math.floor(input.contentHeight / Math.max(input.lineHeight, 1)));
        const guardLimit = Math.max(1024, input.text.length * 8 + 128);
        const allLines = [];
        let cursor = { segmentIndex: 0, graphemeIndex: 0 };
        let rowIndex = 0;
        let guard = 0;
        let guardOverflow = false;

        while (guard < guardLimit) {
          guard++;
          const slots = slotsForRow(input, rowIndex);
          const slot = slots.find((candidate) => candidate.width > 0);
          if (!slot) {
            rowIndex++;
            continue;
          }

          const range = layoutNextLineRange(prepared, cursor, slot.width);
          if (range === null) {
            break;
          }

          const line = materializeLineRange(prepared, range);
          let lineX = slot.x;
          if (input.align === 'center') {
            lineX = slot.x + Math.max(0, Math.floor((slot.width - line.width) / 2));
          } else if (input.align === 'right') {
            lineX = slot.x + Math.max(0, Math.floor(slot.width - line.width));
          }

          allLines.push({
            text: line.text,
            width: Math.max(0, Math.ceil(line.width)),
            x: lineX,
            y: rowIndex * input.lineHeight,
            rowIndex
          });
          cursor = range.end;
          rowIndex++;
        }

        if (guard >= guardLimit) {
          guardOverflow = true;
        }

        const visibleLines = allLines.filter((line) => line.rowIndex < maxRows);
        const overflow = guardOverflow || allLines.some((line) => line.rowIndex >= maxRows);
        if (overflow && input.overflow === 'ellipsis' && visibleLines.length > 0) {
          const last = visibleLines[visibleLines.length - 1];
          last.text = last.text.replace(/\\s+$/u, '') + '...';
        }

        const neededRows = allLines.length === 0 ? 0 : Math.max(...allLines.map((line) => line.rowIndex + 1));
        return {
          blockIndex: input.blockIndex,
          blockId: input.blockId,
          usedPretext: true,
          overflow,
          shownLineCount: visibleLines.length,
          totalLineCount: allLines.length,
          neededHeight: neededRows * input.lineHeight,
          contentHeight: input.contentHeight,
          avoidCount: input.avoidRects.length,
          lines: visibleLines.map(({ rowIndex, ...line }) => line)
        };
      }

      window.__layoutFlowTextBlocks = (inputs) => inputs.map(materializeBlock);
      window.__pretextReady = true;
    </script>
  </body>
</html>
"""


def _content_type(path: Path) -> str:
    if path.suffix == ".js":
        return "text/javascript"
    return "application/octet-stream"


def layout_flow_text_blocks(blocks: list[FlowTextLayoutInput], *, width: int, height: int) -> list[dict[str, Any]]:
    package_root = _require_pretext_package()
    if not blocks:
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RenderPipelineError(
            "DEPENDENCY_MISSING",
            "pretext layout requires Playwright",
            {"package": "playwright", "install": "pip install -r skill/render/requirements.txt"},
        ) from exc

    payload = [
        {
            "blockIndex": item.block_index,
            "blockId": item.block_id,
            "text": item.text,
            "font": item.font,
            "lineHeight": item.line_height,
            "contentX": item.content_x,
            "contentY": item.content_y,
            "contentWidth": item.content_width,
            "contentHeight": item.content_height,
            "screenX": item.screen_x,
            "screenY": item.screen_y,
            "align": item.align,
            "overflow": item.overflow,
            "avoidRects": list(item.avoid_rects),
        }
        for item in blocks
    ]

    def route_pretext_file(route: Any) -> None:
        url_path = urlparse(route.request.url).path
        relative = url_path.removeprefix(PRETEXT_ROUTE_PREFIX)
        file_path = (package_root / relative).resolve()
        if not str(file_path).startswith(str(package_root.resolve())) or not file_path.exists():
            route.abort()
            return
        route.fulfill(status=200, body=file_path.read_bytes(), content_type=_content_type(file_path))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/node_modules/@chenglou/pretext/**", route_pretext_file)
            page.route(
                "**/pretext-bridge.html",
                lambda route: route.fulfill(status=200, body=_pretext_bridge_html(), content_type="text/html"),
            )
            page.goto("http://nekopaw-render.local/pretext-bridge.html")
            page.wait_for_function("window.__pretextReady === true")
            result = page.evaluate("payload => window.__layoutFlowTextBlocks(payload)", payload)
        finally:
            browser.close()

    return json.loads(json.dumps(result))
