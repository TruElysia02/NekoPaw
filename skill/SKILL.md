---
name: nekopaw
description: Control a NekoPaw device via HTTP (/api/bridge/*) using skill/bridge_cli.py.
---

# NekoPaw Control

Environment variables:

- `NEKOPAW_URL`: device (or gateway) base URL, e.g. `http://192.168.1.123`
- `NEKOPAW_DEVICE_ID`: optional, used by gateway mode
- `NEKOPAW_API_KEY`: optional, passed as `X-API-Key`

Examples:

```bash
python3 skill/bridge_cli.py device info
python3 skill/bridge_cli.py display text --body "Hello NekoPaw"
```
