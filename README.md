# NekoPaw 🐾

NekoPaw is an ESP32 Arduino library that exposes a small HTTP API for AI agents to interact with a device (display/sensors/inputs/outputs).

Build (PlatformIO example):

```bash
cd examples/BasicDisplay
pio run
```

`examples/BasicDisplay` uses a local `platformio_override.ini` for board-specific settings such as WiFi credentials and panel driver selection. On boot, the example now shows a welcome/status page on the e-ink display so you can confirm whether it is waiting for WiFi, failed to connect, or is ready with an IP address.

## Status

- Device-side phases through the current `bridge_cli.py` flow are complete as of 2026-03-25.
- The separate `render skill` is now in the repository and can render `Markdown` or `scene json` into preview PNGs and device-ready `1bpp bitmap` files.
- `scene json v2` docs and ready-to-render examples now live in `docs/SCENE_JSON.md` and `skill/render/examples/`.
- Live planning now stays in GitHub Issues instead of duplicated local TODO checklists.
- Current epic: `#1` https://github.com/TruElysia02/NekoPaw/issues/1
- Current priority path: `#9` low-res clarity optimization, then `#5` confirm bitmap state wiring.
- Follow-up layout work: `#10` scene json v2, then `#7` pretext.
- Hardware blocker tracked separately: `#8` buzzer reset issue.

Current device endpoints:

- `GET /api/bridge/device`
- `POST /api/bridge/display/text`
- `POST /api/bridge/display/bitmap`
- `GET /api/bridge/display/state`
- `POST /api/bridge/display/confirm`
- `GET /api/bridge/display/confirm`
- `DELETE /api/bridge/display/confirm`
- `PATCH /api/bridge/device/description`
- `GET /api/bridge/sensors`
- `POST /api/bridge/events/watch`
- `DELETE /api/bridge/events/watch`
- `GET /api/bridge/events`
- `POST /api/bridge/outputs`

`examples/BasicDisplay` now registers one battery voltage sensor (`battery`), two buttons (`button1`, `button2`), one RGB LED output (`led_rgb`), and one buzzer output (`buzzer`). During a pending confirm request, BTN1 confirms, BTN2 cancels, and the same button clicks still continue into the events queue for watch-based automation.

CLI examples:

```bash
python skill/bridge_cli.py device info
python skill/bridge_cli.py sensors list
python skill/bridge_cli.py device set-description --description "Living room e-ink ticker"
python skill/bridge_cli.py display text --title "Greeting" --body "Hello NekoPaw"
python skill/bridge_cli.py display state
python skill/bridge_cli.py display confirm create --title "Smart Home" --body "Turn on the fan?"
python skill/render_cli.py confirm-assets --title "Smart Home" --body "Turn on the fan?" --output-dir out/confirm
python skill/bridge_cli.py display confirm create --assets-dir out/confirm
python skill/bridge_cli.py display confirm wait --id cfm_000001
python skill/bridge_cli.py events watch input --id button1_click --input button1 --trigger click
python skill/bridge_cli.py outputs led set --color green --duration 1500
python skill/bridge_cli.py outputs buzzer beep --frequency 1000 --duration 200 --count 2
```

`display bitmap` now performs a local preflight by calling `/api/bridge/device` first and checking that the input byte size matches the reported display dimensions before uploading.
`display confirm create --assets-dir ...` uses the same preflight idea, then uploads `pending` / `confirmed` / `cancelled` / `timeout` four-page bitmap packs through the existing confirm route while keeping the old text JSON flow available.

CLI tests:

```bash
python -m unittest discover -s skill/tests -p "test_*.py"
```
