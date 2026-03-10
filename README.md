# NekoPaw 🐾

NekoPaw is an ESP32 Arduino library that exposes a small HTTP API for AI agents to interact with a device (display/sensors/inputs/outputs).

Build (PlatformIO example):

```bash
cd examples/BasicDisplay
pio run
```

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
