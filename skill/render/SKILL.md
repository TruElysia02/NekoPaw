---
name: nekopaw-render
description: Render Markdown or scene JSON into NekoPaw preview PNG and 1bpp bitmap artifacts.
---

# NekoPaw Render

Use this skill when the user wants to turn content into display-ready bitmap files for a NekoPaw device.

Environment and setup:

- Install runtime packages with `pip install -r skill/render/requirements.txt`
- Install the browser binary with `python -m playwright install chromium`

Agent workflow:

1. Decide whether the input is `Markdown` or `scene json`.
2. Render a preview PNG first so the layout can be inspected.
3. Convert that preview into a raw `1bpp bitmap` file.
4. If the user wants to show it on a device, hand the bitmap file to `python skill/bridge_cli.py display bitmap --input ...`

Examples:

```bash
python skill/render_cli.py markdown --input note.md --preview out/note.png --bitmap out/note.bin

python skill/render_cli.py scene --input scene.json --preview out/scene.png --bitmap out/scene.bin

python skill/render_cli.py scene --input skill/render/examples/scene_news_card.json --preview out/news_card.png --bitmap out/news_card.bin

python skill/render_cli.py scene --input skill/render/examples/scene_poster_card.json --preview out/poster_card.png --bitmap out/poster_card.bin

python skill/render_cli.py bitmap --input out/scene.png --output out/scene.bin --dither floyd-steinberg

python skill/render_cli.py confirm-assets \
  --title "Smart Home" \
  --body "Turn on the fan?" \
  --output-dir out/confirm
```

Notes:

- `markdown` supports regular text flow and the first image block as a figure sidebar.
- `scene` is the free-layout path for absolute-positioned text and image blocks.
- `scene` now supports stable `z` stacking within each visual layer, plus image `anchor` placement for `cover` / `contain` / `fill`.
- On the current `296x128` low-res black-and-white target, `scene` text blocks now render into the final bitmap on the target pixel grid instead of only relying on browser text downscaling.
- On that same low-res target, text blocks are rasterized in their own block canvas before being composited back, so block clipping, centering, and invert badges stay more stable than the old whole-page white overlay path.
- The low-res text path still accepts `NEKOPAW_RENDER_FONT_REGULAR` and `NEKOPAW_RENDER_FONT_BOLD` as font overrides; without them, ASCII-heavy blocks prefer `Verdana` / `Tahoma`, while blocks with Chinese or other non-ASCII text prefer `Microsoft YaHei` / `Yu Gothic`.
- See `docs/SCENE_JSON.md` for the current scene schema and `skill/render/examples/` for ready-to-render examples.
- `confirm-assets` emits `pending` / `confirmed` / `cancelled` / `timeout` preview and bitmap files together.
- Those `confirm-assets` outputs can be sent to the device with `python skill/bridge_cli.py display confirm create --assets-dir out/confirm`.
- Successful commands print JSON to stdout and exit `0`. Local validation, dependency, file, or rendering errors print local JSON and exit `2`.
