from __future__ import annotations

import contextlib
import importlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_DIR = Path(__file__).resolve().parents[1]
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

render_cli = importlib.import_module("render.cli")
pipeline = importlib.import_module("render.pipeline")


class FakeBitmapArtifact:
    def __init__(self, width: int, height: int, bitmap_byte_count: int):
        self.width = width
        self.height = height
        self.bitmap_byte_count = bitmap_byte_count


class RenderCliTests(unittest.TestCase):
    def run_cli(self, argv, *, stdin_text: str = ""):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            mock.patch("sys.stdin", io.StringIO(stdin_text)),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = render_cli.main(argv)

        output = stdout.getvalue().strip()
        payload = json.loads(output) if output else None
        return code, payload, stderr.getvalue()

    def test_pack_bitmap_bytes_uses_row_alignment(self):
        values = [
            0,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
            0,
            255,
            0,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
        ]

        packed = pipeline.pack_bitmap_bytes(values, width=9, height=2)
        self.assertEqual(packed, bytes([0x80, 0x80, 0x40, 0x00]))

    def test_markdown_command_passes_expected_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            markdown_path = Path(tmpdir) / "note.md"
            markdown_path.write_text("# Hello\n\nWorld", encoding="utf-8")
            preview_path = Path(tmpdir) / "note.png"
            bitmap_path = Path(tmpdir) / "note.bin"

            with mock.patch.object(
                render_cli,
                "render_markdown_to_artifacts",
                return_value={
                    "previewPath": str(preview_path),
                    "bitmapPath": str(bitmap_path),
                    "bitmapBytes": 4736,
                    "width": 296,
                    "height": 128,
                    "profile": "epd_296x128_bw",
                    "composition": "layered-foreground-overlay",
                },
            ) as mocked_render:
                code, payload, _ = self.run_cli(
                    [
                        "markdown",
                        "--input",
                        str(markdown_path),
                        "--preview",
                        str(preview_path),
                        "--bitmap",
                        str(bitmap_path),
                    ]
                )

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["inputType"], "markdown")
        self.assertEqual(payload["data"]["bitmapBytes"], 4736)
        self.assertEqual(payload["data"]["profile"], "epd_296x128_bw")
        self.assertEqual(payload["data"]["composition"], "layered-foreground-overlay")
        self.assertEqual(mocked_render.call_count, 1)
        call_kwargs = mocked_render.call_args.kwargs
        self.assertEqual(call_kwargs["base_dir"], markdown_path.parent.resolve())

    def test_bitmap_command_returns_conversion_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "preview.png"
            bitmap_path = Path(tmpdir) / "preview.bin"
            image_path.write_bytes(b"not-a-real-png")

            with mock.patch.object(
                render_cli,
                "convert_image_to_bitmap",
                return_value=FakeBitmapArtifact(width=296, height=128, bitmap_byte_count=4736),
            ) as mocked_convert:
                code, payload, _ = self.run_cli(
                    [
                        "bitmap",
                        "--input",
                        str(image_path),
                        "--output",
                        str(bitmap_path),
                    ]
                )

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["bitmapBytes"], 4736)
        self.assertEqual(payload["data"]["bitmapPath"], str(bitmap_path))
        self.assertEqual(payload["data"]["profile"], "epd_296x128_bw")
        self.assertEqual(payload["data"]["composition"], "single-layer-image")
        self.assertEqual(mocked_convert.call_count, 1)

    def test_confirm_assets_emits_all_states(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "confirm"

            with mock.patch.object(
                render_cli,
                "render_scene_to_artifacts",
                side_effect=lambda scene, **kwargs: {
                    "previewPath": str(kwargs["preview_path"]),
                    "bitmapPath": str(kwargs["bitmap_path"]),
                    "bitmapBytes": 4736,
                    "width": 296,
                    "height": 128,
                    "profile": "epd_296x128_bw",
                    "composition": "layered-foreground-overlay",
                    "sceneKeys": sorted(scene.keys()),
                },
            ) as mocked_render:
                code, payload, _ = self.run_cli(
                    [
                        "confirm-assets",
                        "--title",
                        "Smart Home",
                        "--body",
                        "Turn on the fan?",
                        "--output-dir",
                        str(output_dir),
                    ]
                )

        self.assertEqual(code, 0)
        self.assertEqual(payload["data"]["profile"], "epd_296x128_bw")
        self.assertEqual(payload["data"]["composition"], "layered-foreground-overlay")
        self.assertEqual(sorted(payload["data"]["states"].keys()), ["cancelled", "confirmed", "pending", "timeout"])
        self.assertEqual(mocked_render.call_count, 4)

    def test_build_confirm_scenes_feedback_omits_footer_caption(self):
        scenes = pipeline.build_confirm_scenes(
            title="Smart Home",
            body="Turn on the fan?",
            confirm_label="Confirm (BTN1)",
            cancel_label="Cancel (BTN2)",
            confirmed_text="Confirmed",
            cancelled_text="Cancelled",
            timeout_text="Timed out",
        )

        confirmed_texts = [block["text"] for block in scenes["confirmed"]["blocks"] if block["type"] == "text"]
        self.assertEqual(confirmed_texts, ["confirmed", "Smart Home", "Confirmed"])

    def test_reduce_oversampled_binary_keeps_any_black_subpixel(self):
        values = [
            255, 255, 255, 255,
            255, 0, 255, 255,
            255, 255, 255, 255,
            255, 255, 255, 0,
        ]

        reduced = pipeline.reduce_oversampled_binary(
            values,
            source_width=4,
            source_height=4,
            target_width=2,
            target_height=2,
        )

        self.assertEqual(reduced, [0, 255, 255, 0])

    def test_overlay_mono_layers_prefers_foreground_black_pixels(self):
        composed = pipeline.overlay_mono_layers(
            [255, 0, 255, 0],
            [255, 255, 0, 255],
        )

        self.assertEqual(composed, [255, 0, 0, 0])

    def test_render_scene_to_artifacts_uses_layered_profile_for_296x128(self):
        scene = {"blocks": [{"type": "text", "x": 0, "y": 0, "w": 20, "h": 12, "text": "Hi"}]}

        with tempfile.TemporaryDirectory() as tmpdir:
            preview_path = Path(tmpdir) / "scene.png"
            bitmap_path = Path(tmpdir) / "scene.bin"

            with (
                mock.patch.object(
                    pipeline,
                    "render_html_capture_set",
                    return_value=((1184, 512), {"image": b"image", "foreground": b"foreground"}),
                ) as mocked_capture,
                mock.patch.object(
                    pipeline,
                    "convert_layer_captures_to_bitmap",
                    return_value=FakeBitmapArtifact(width=296, height=128, bitmap_byte_count=4736),
                ) as mocked_layered,
                mock.patch.object(pipeline, "convert_image_to_bitmap") as mocked_single,
            ):
                result = pipeline.render_scene_to_artifacts(
                    scene,
                    preview_path=preview_path,
                    bitmap_path=bitmap_path,
                    settings=pipeline.RenderSettings(),
                )

        self.assertEqual(result["profile"], "epd_296x128_bw")
        self.assertEqual(result["composition"], "layered-foreground-overlay")
        self.assertEqual(result["bitmapBytes"], 4736)
        self.assertEqual(mocked_capture.call_count, 1)
        self.assertEqual(mocked_layered.call_count, 1)
        self.assertEqual(mocked_single.call_count, 0)

    def test_render_scene_to_artifacts_falls_back_to_single_layer_for_other_size(self):
        scene = {"blocks": [{"type": "text", "x": 0, "y": 0, "w": 20, "h": 12, "text": "Hi"}]}

        with tempfile.TemporaryDirectory() as tmpdir:
            preview_path = Path(tmpdir) / "scene.png"
            bitmap_path = Path(tmpdir) / "scene.bin"

            with (
                mock.patch.object(
                    pipeline,
                    "render_html_capture_set",
                    return_value=((1200, 600), {}),
                ) as mocked_capture,
                mock.patch.object(pipeline, "convert_layer_captures_to_bitmap") as mocked_layered,
                mock.patch.object(
                    pipeline,
                    "convert_image_to_bitmap",
                    return_value=FakeBitmapArtifact(width=300, height=150, bitmap_byte_count=5700),
                ) as mocked_single,
            ):
                result = pipeline.render_scene_to_artifacts(
                    scene,
                    preview_path=preview_path,
                    bitmap_path=bitmap_path,
                    settings=pipeline.RenderSettings(width=300, height=150),
                )

        self.assertEqual(result["profile"], "default")
        self.assertEqual(result["composition"], "single-layer-preview")
        self.assertEqual(result["bitmapBytes"], 5700)
        self.assertEqual(mocked_capture.call_count, 1)
        self.assertEqual(mocked_layered.call_count, 0)
        self.assertEqual(mocked_single.call_count, 1)


if __name__ == "__main__":
    unittest.main()
