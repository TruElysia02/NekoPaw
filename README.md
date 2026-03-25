# NekoPaw 🐾

NekoPaw is an ESP32 Arduino library that exposes a small HTTP API for AI agents to interact with a device (display/sensors/inputs/outputs).

Build (PlatformIO example):

```bash
cd examples/BasicDisplay
pio run
```

`examples/BasicDisplay` uses a local `platformio_override.ini` for board-specific settings such as WiFi credentials and panel driver selection. On boot, the example now shows a welcome/status page on the e-ink display so you can confirm whether it is waiting for WiFi, failed to connect, or is ready with an IP address.

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
python skill/bridge_cli.py device set-description --description "Living room e-ink ticker"
python skill/bridge_cli.py display text --body "Hello NekoPaw"
python skill/bridge_cli.py display state
```

P3 confirm/output requests are currently exercised with raw HTTP during hardware bring-up, for example:

```bash
curl -X POST http://<IP>/api/bridge/display/confirm \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"Smart Home\",\"body\":\"Turn on the fan?\",\"timeout\":30}"

curl "http://<IP>/api/bridge/display/confirm?id=cfm_000001"
curl -X POST "http://<IP>/api/bridge/outputs?id=led_rgb" \
  -H "Content-Type: application/json" \
  -d "{\"action\":\"set\",\"color\":\"green\",\"duration\":1500}"
```
