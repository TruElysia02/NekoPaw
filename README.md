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
python skill/bridge_cli.py sensors list
python skill/bridge_cli.py device set-description --description "Living room e-ink ticker"
python skill/bridge_cli.py display text --title "Greeting" --body "Hello NekoPaw"
python skill/bridge_cli.py display state
python skill/bridge_cli.py display confirm create --title "Smart Home" --body "Turn on the fan?"
python skill/bridge_cli.py display confirm wait --id cfm_000001
python skill/bridge_cli.py events watch input --id button1_click --input button1 --trigger click
python skill/bridge_cli.py outputs led set --color green --duration 1500
python skill/bridge_cli.py outputs buzzer beep --frequency 1000 --duration 200 --count 2
```

`display bitmap` now performs a local preflight by calling `/api/bridge/device` first and checking that the input byte size matches the reported display dimensions before uploading.

CLI tests:

```bash
python -m unittest discover -s skill/tests -p "test_*.py"
```
