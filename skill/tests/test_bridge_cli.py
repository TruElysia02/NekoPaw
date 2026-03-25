from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests


def _load_bridge_cli():
    module_path = Path(__file__).resolve().parents[1] / "bridge_cli.py"
    spec = importlib.util.spec_from_file_location("bridge_cli_under_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, status_code: int, payload=None, text: str | None = None):
        self.status_code = status_code
        self._payload = payload
        if text is not None:
            self.text = text
        elif payload is None:
            self.text = ""
        else:
            self.text = json.dumps(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("response has no JSON payload")
        return self._payload


class BridgeCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cli = _load_bridge_cli()

    def run_cli(self, argv, *, request_side_effect, stdin_text: str = ""):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            mock.patch.object(self.cli.requests, "request", side_effect=request_side_effect),
            mock.patch("sys.stdin", io.StringIO(stdin_text)),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = self.cli.main(argv)

        output = stdout.getvalue().strip()
        payload = json.loads(output) if output else None
        return code, payload, stderr.getvalue()

    def test_display_confirm_wait_polls_until_terminal_status(self):
        responses = iter(
            [
                FakeResponse(200, {"ok": True, "data": {"requestId": "cfm_123", "status": "pending"}}),
                FakeResponse(200, {"ok": True, "data": {"requestId": "cfm_123", "status": "pending"}}),
                FakeResponse(200, {"ok": True, "data": {"requestId": "cfm_123", "status": "confirmed"}}),
            ]
        )
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return next(responses)

        with mock.patch.object(self.cli.time, "sleep", return_value=None):
            code, payload, _ = self.run_cli(
                ["display", "confirm", "wait", "--id", "cfm_123", "--interval", "0.01"],
                request_side_effect=fake_request,
            )

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["status"], "confirmed")
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call[0] == "GET" for call in calls))
        self.assertTrue(all(call[1].endswith("/api/bridge/display/confirm") for call in calls))
        self.assertTrue(all(call[2]["params"]["id"] == "cfm_123" for call in calls))

    def test_events_watch_sensor_builds_expected_payload(self):
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse(200, {"ok": True, "data": {"watchCount": 1}})

        code, payload, _ = self.run_cli(
            [
                "events",
                "watch",
                "sensor",
                "--id",
                "temp_alert",
                "--sensor",
                "battery",
                "--op",
                "gt",
                "--value",
                "3.8",
                "--cooldown",
                "60",
                "--message",
                "Battery exceeded threshold",
            ],
            request_side_effect=fake_request,
        )

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["watchCount"], 1)
        self.assertEqual(len(calls), 1)
        method, url, kwargs = calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/api/bridge/events/watch"))
        self.assertEqual(
            kwargs["json"],
            {
                "watches": [
                    {
                        "id": "temp_alert",
                        "sensor": "battery",
                        "condition": {"op": "gt", "value": 3.8},
                        "cooldown": 60,
                        "message": "Battery exceeded threshold",
                    }
                ]
            },
        )

    def test_outputs_led_set_builds_expected_payload(self):
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse(200, {"ok": True, "data": {"id": "led_rgb"}})

        code, payload, _ = self.run_cli(
            ["outputs", "led", "set", "--color", "green", "--duration", "1500"],
            request_side_effect=fake_request,
        )

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["id"], "led_rgb")
        self.assertEqual(len(calls), 1)
        method, url, kwargs = calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/api/bridge/outputs"))
        self.assertEqual(kwargs["params"]["id"], "led_rgb")
        self.assertEqual(kwargs["json"], {"action": "set", "color": "green", "duration": 1500})

    def test_outputs_buzzer_beep_builds_expected_payload(self):
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse(200, {"ok": True, "data": {"id": "buzzer"}})

        code, payload, _ = self.run_cli(
            ["outputs", "buzzer", "beep", "--frequency", "800", "--duration", "200", "--count", "2"],
            request_side_effect=fake_request,
        )

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["id"], "buzzer")
        self.assertEqual(len(calls), 1)
        method, url, kwargs = calls[0]
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/api/bridge/outputs"))
        self.assertEqual(kwargs["params"]["id"], "buzzer")
        self.assertEqual(kwargs["json"], {"action": "beep", "frequency": 800, "duration": 200, "count": 2})

    def test_http_json_error_is_printed_and_returns_one(self):
        error_payload = {
            "ok": False,
            "data": None,
            "error": {"code": "CONFIRM_NOT_FOUND", "message": "confirm missing"},
            "ts": 1,
            "device": "NekoPaw-1",
        }

        code, payload, _ = self.run_cli(
            ["display", "confirm", "get", "--id", "cfm_missing"],
            request_side_effect=lambda method, url, **kwargs: FakeResponse(404, error_payload),
        )

        self.assertEqual(code, 1)
        self.assertEqual(payload, error_payload)

    def test_network_timeout_returns_local_error_json(self):
        code, payload, _ = self.run_cli(
            ["device", "info"],
            request_side_effect=requests.Timeout("timed out"),
        )

        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "REQUEST_TIMEOUT")
        self.assertEqual(payload["source"], "bridge_cli")

    def test_display_bitmap_preflight_rejects_size_mismatch_before_upload(self):
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            return FakeResponse(
                200,
                {
                    "ok": True,
                    "data": {
                        "capabilities": {
                            "display": {"width": 296, "height": 128},
                        }
                    },
                },
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            bitmap_path = Path(tmpdir) / "bad.bin"
            bitmap_path.write_bytes(b"\x00" * 100)

            code, payload, _ = self.run_cli(
                ["display", "bitmap", "--input", str(bitmap_path)],
                request_side_effect=fake_request,
            )

        self.assertEqual(code, 2)
        self.assertEqual(payload["error"]["code"], "BITMAP_SIZE_MISMATCH")
        self.assertEqual(payload["error"]["details"]["expectedBytes"], 4736)
        self.assertEqual(payload["error"]["details"]["actualBytes"], 100)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "GET")
        self.assertTrue(calls[0][1].endswith("/api/bridge/device"))

    def test_display_bitmap_preflight_uses_row_aligned_byte_size(self):
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs))
            if method == "GET":
                return FakeResponse(
                    200,
                    {
                        "ok": True,
                        "data": {
                            "capabilities": {
                                "display": {"width": 9, "height": 2},
                            }
                        },
                    },
                )

            return FakeResponse(200, {"ok": True, "data": {"source": "bitmap"}})

        with tempfile.TemporaryDirectory() as tmpdir:
            bitmap_path = Path(tmpdir) / "row_aligned.bin"
            bitmap_path.write_bytes(b"\x00" * 4)

            code, payload, _ = self.run_cli(
                ["display", "bitmap", "--input", str(bitmap_path)],
                request_side_effect=fake_request,
            )

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["source"], "bitmap")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], "GET")
        self.assertEqual(calls[1][0], "POST")
        self.assertEqual(calls[1][2]["data"], b"\x00" * 4)

    def test_events_watch_sensor_change_rejects_negative_threshold(self):
        code, payload, _ = self.run_cli(
            [
                "events",
                "watch",
                "sensor",
                "--id",
                "battery_delta",
                "--sensor",
                "battery",
                "--op",
                "change",
                "--value",
                "-0.1",
            ],
            request_side_effect=AssertionError("request should not be sent"),
        )

        self.assertEqual(code, 2)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")
        self.assertIn("op=change", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
