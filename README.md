# NekoPaw 🐾

NekoPaw is an ESP32 Arduino library that exposes a small HTTP API for AI agents to interact with a device (display/sensors/inputs/outputs).

Build (PlatformIO example):

```bash
cd examples/BasicDisplay
pio run
```

`examples/BasicDisplay` uses a local `platformio_override.ini` for board-specific settings such as WiFi credentials and panel driver selection. On boot, the example now shows a welcome/status page on the e-ink display so you can confirm whether it is waiting for WiFi, failed to connect, or is ready with an IP address.

Phase 1 endpoints:

- `GET /api/bridge/device`
- `POST /api/bridge/display/text`
- `POST /api/bridge/display/bitmap`
- `GET /api/bridge/display/state`
- `PATCH /api/bridge/device/description`

CLI examples:

```bash
python skill/bridge_cli.py device info
python skill/bridge_cli.py device set-description --description "Living room e-ink ticker"
python skill/bridge_cli.py display text --body "Hello NekoPaw"
python skill/bridge_cli.py display state
```
