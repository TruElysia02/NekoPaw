---
name: nekopaw
description: Control a NekoPaw ESP32 device or gateway through the HTTP bridge API using skill/bridge_cli.py. Use when Codex needs to inspect device info, display text or raw 1bpp bitmaps, create or wait for confirm flows, read sensors, poll input events, manage event watches, or drive outputs such as LED and buzzer.
---

# NekoPaw Control

Use this skill when the user wants to read sensors, display text or bitmaps, wait for a confirm result, manage watches, or drive outputs on a NekoPaw device.

For preview rendering, `1bpp bitmap` generation, `scene json`, or confirm bitmap asset generation, use the separate render skill at `skill/render/SKILL.md`.

Environment variables:

- `NEKOPAW_URL`: device or gateway base URL, for example `http://192.168.1.123`
- `NEKOPAW_DEVICE_ID`: optional, only needed in gateway mode
- `NEKOPAW_API_KEY`: optional, passed as `X-API-Key`

Agent workflow:

1. Run `python skill/bridge_cli.py device info` first.
2. Read `data.capabilities` from the response before choosing `display`, `sensors`, `events`, or `outputs` commands.
3. Prefer the CLI over handwritten HTTP so error handling and bitmap preflight stay consistent.
4. For confirm flows, use `display confirm create` and `display confirm wait` unless the task explicitly needs manual polling.

Examples:

```bash
python skill/bridge_cli.py device info
python skill/bridge_cli.py device set-description --description "Living room e-ink ticker"

python skill/bridge_cli.py display text --title "Greeting" --body "Hello NekoPaw"
python skill/bridge_cli.py display bitmap --input screen_296x128_1bpp.bin
python skill/bridge_cli.py display state

python skill/bridge_cli.py display confirm create --title "Smart Home" --body "Turn on the fan?"
python skill/render_cli.py confirm-assets --title "Smart Home" --body "Turn on the fan?" --output-dir out/confirm
python skill/bridge_cli.py display confirm create --assets-dir out/confirm
python skill/bridge_cli.py display confirm wait --id cfm_000001
python skill/bridge_cli.py display confirm cancel --id cfm_000001

python skill/bridge_cli.py sensors list
python skill/bridge_cli.py sensors get --id battery

python skill/bridge_cli.py events watch input --id button1_click --input button1 --trigger click
python skill/bridge_cli.py events watch sensor --id battery_low --sensor battery --op lt --value 3.6 --cooldown 60
python skill/bridge_cli.py events poll
python skill/bridge_cli.py events watch delete --id button1_click

python skill/bridge_cli.py outputs led set --color green --duration 1500
python skill/bridge_cli.py outputs led off
python skill/bridge_cli.py outputs buzzer beep --frequency 1000 --duration 200 --count 2
```

Notes:

- `display bitmap` uploads raw 1bpp bytes only. The CLI checks the byte size against `/api/bridge/device` before upload.
- `display confirm create --assets-dir ...` uploads one raw bitmap pack in `pending` -> `confirmed` -> `cancelled` -> `timeout` order and keeps `POST /api/bridge/display/confirm` text mode compatible.
- `events watch upsert --payload ...` and `outputs send --payload ...` are the raw protocol-mapping entry points when the typed helpers are not enough.
- Successful commands print JSON to stdout and exit `0`. Device JSON errors are printed as-is and exit `1`. Local validation or network failures print a local JSON error and exit `2`.
