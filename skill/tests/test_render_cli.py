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
                    "composition": "layered-direct-text-overlay",
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
        self.assertEqual(payload["data"]["composition"], "layered-direct-text-overlay")
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

    def test_build_confirm_scenes_pending_buttons_use_safer_low_res_height(self):
        scenes = pipeline.build_confirm_scenes(
            title="Smart Home",
            body="Turn on the fan?",
            confirm_label="Confirm (BTN1)",
            cancel_label="Cancel (BTN2)",
            confirmed_text="Confirmed",
            cancelled_text="Cancelled",
            timeout_text="Timed out",
        )

        button_blocks = [
            block
            for block in scenes["pending"]["blocks"]
            if block["type"] == "text" and block.get("role") == "badge"
        ]
        self.assertEqual([block["h"] for block in button_blocks], [18, 18])

    def test_scene_to_html_pending_confirm_buttons_fall_back_to_outline(self):
        scenes = pipeline.build_confirm_scenes(
            title="Smart Home",
            body="Turn on the fan?",
            confirm_label="Confirm (BTN1)",
            cancel_label="Cancel (BTN2)",
            confirmed_text="Confirmed",
            cancelled_text="Cancelled",
            timeout_text="Timed out",
        )

        html = pipeline.scene_to_html(scenes["pending"])

        self.assertNotIn("scene-invert", html)

    def test_scene_to_html_confirmed_feedback_badge_keeps_invert_when_tall_enough(self):
        scenes = pipeline.build_confirm_scenes(
            title="Smart Home",
            body="Turn on the fan?",
            confirm_label="Confirm (BTN1)",
            cancel_label="Cancel (BTN2)",
            confirmed_text="Confirmed",
            cancelled_text="Cancelled",
            timeout_text="Timed out",
        )

        html = pipeline.scene_to_html(scenes["confirmed"])

        self.assertIn("scene-invert", html)

    def test_scene_to_html_preserves_input_order_for_same_z(self):
        scene = {
            "blocks": [
                {"type": "text", "x": 0, "y": 0, "w": 40, "h": 16, "text": "First", "z": 2},
                {"type": "text", "x": 0, "y": 20, "w": 40, "h": 16, "text": "Second", "z": 2},
            ]
        }

        html = pipeline.scene_to_html(scene)

        self.assertLess(html.index("First"), html.index("Second"))
        self.assertEqual(html.count("z-index:1002"), 2)
        self.assertEqual(html.count('class="scene-block__copy"'), 2)

    def test_scene_to_html_keeps_text_above_image_layer(self):
        scene = {
            "blocks": [
                {"type": "image", "x": 0, "y": 0, "w": 80, "h": 80, "src": "https://example.com/cover.png", "z": 99},
                {"type": "text", "x": 8, "y": 8, "w": 60, "h": 20, "text": "Overlay", "z": 0},
            ]
        }

        html = pipeline.scene_to_html(scene)

        self.assertIn('style="left:0px;top:0px;width:80px;height:80px;z-index:99;"', html)
        self.assertIn('style="left:8px;top:8px;width:60px;height:20px;z-index:1000;"', html)

    def test_scene_to_html_applies_image_anchor(self):
        scene = {
            "blocks": [
                {
                    "type": "image",
                    "x": 0,
                    "y": 0,
                    "w": 100,
                    "h": 60,
                    "src": "https://example.com/cover.png",
                    "fit": "contain",
                    "anchor": "bottom-right",
                }
            ]
        }

        html = pipeline.scene_to_html(scene)

        self.assertIn("object-fit:contain;object-position:right bottom;", html)

    def test_scene_to_html_keeps_image_frame_in_decoration_layer(self):
        scene = {
            "blocks": [
                {
                    "type": "image",
                    "x": 4,
                    "y": 6,
                    "w": 100,
                    "h": 60,
                    "src": "https://example.com/cover.png",
                    "frame": True,
                    "z": 2,
                }
            ]
        }

        html = pipeline.scene_to_html(scene)

        self.assertIn('class="scene-block scene-block--image"', html)
        self.assertIn('class="scene-block scene-block--image-frame" data-np-layer="decoration"', html)
        self.assertIn("z-index:1002;", html)

    def test_scene_to_html_disables_small_invert_badge_on_low_res(self):
        scene = {
            "blocks": [
                {
                    "type": "text",
                    "x": 12,
                    "y": 96,
                    "w": 80,
                    "h": 16,
                    "text": "tiny badge",
                    "role": "badge",
                    "invert": True,
                    "frame": True,
                }
            ]
        }

        html = pipeline.scene_to_html(scene)

        self.assertIn("scene-single-line", html)
        self.assertNotIn("scene-invert", html)

    def test_scene_to_html_marks_low_res_title_as_two_line_clamp(self):
        scene = {
            "blocks": [
                {
                    "type": "text",
                    "x": 12,
                    "y": 20,
                    "w": 120,
                    "h": 28,
                    "text": "Long title",
                    "role": "title",
                }
            ]
        }

        html = pipeline.scene_to_html(scene)

        self.assertIn("scene-max-lines-2", html)

    def test_scene_font_candidates_use_latin_defaults_for_ascii_low_res_text(self):
        candidates = pipeline._scene_font_candidates(
            False,
            text="Signal report 42",
            settings=pipeline.RenderSettings(),
        )

        self.assertEqual(candidates[0].lower(), "c:\\windows\\fonts\\verdana.ttf")
        self.assertNotIn("C:\\Windows\\Fonts\\msyh.ttc", candidates)

    def test_scene_font_candidates_use_cjk_defaults_for_non_ascii_low_res_text(self):
        candidates = pipeline._scene_font_candidates(
            True,
            text="猫 paw",
            settings=pipeline.RenderSettings(),
        )

        self.assertEqual(candidates[0].lower(), "c:\\windows\\fonts\\msyhbd.ttc")

    def test_scene_font_candidates_prefer_env_override(self):
        with mock.patch.dict("os.environ", {"NEKOPAW_RENDER_FONT_REGULAR": "E:/fonts/custom.ttf"}):
            candidates = pipeline._scene_font_candidates(
                False,
                text="Signal report 42",
                settings=pipeline.RenderSettings(),
            )

        self.assertEqual(candidates, ["E:/fonts/custom.ttf"])

    def test_scene_to_html_rejects_invalid_anchor(self):
        scene = {
            "blocks": [
                {
                    "type": "image",
                    "x": 0,
                    "y": 0,
                    "w": 100,
                    "h": 60,
                    "src": "https://example.com/cover.png",
                    "anchor": "upper-left",
                }
            ]
        }

        with self.assertRaises(pipeline.RenderPipelineError) as ctx:
            pipeline.scene_to_html(scene)

        self.assertEqual(ctx.exception.code, "INVALID_JSON")
        self.assertEqual(ctx.exception.message, "image block anchor is invalid")

    def test_scene_to_html_rejects_negative_z(self):
        scene = {
            "blocks": [
                {"type": "text", "x": 0, "y": 0, "w": 40, "h": 16, "text": "Hi", "z": -1},
            ]
        }

        with self.assertRaises(pipeline.RenderPipelineError) as ctx:
            pipeline.scene_to_html(scene)

        self.assertEqual(ctx.exception.code, "INVALID_JSON")
        self.assertEqual(ctx.exception.message, "scene block z must be >= 0")

    def test_example_scenes_resolve_local_assets(self):
        examples_dir = SKILL_DIR / "render" / "examples"

        for name in ("scene_news_card.json", "scene_poster_card.json"):
            scene_path = examples_dir / name
            scene = json.loads(scene_path.read_text(encoding="utf-8"))

            html = pipeline.scene_to_html(scene, scene_path.parent.resolve())

            self.assertIn("data:image/svg+xml;base64,", html)

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

    def test_overlay_white_pixels_force_white_where_requested(self):
        composed = pipeline.overlay_white_pixels(
            [0, 0, 255, 255],
            [255, 0, 255, 0],
        )

        self.assertEqual(composed, [0, 255, 255, 255])

    def test_compose_scene_text_blocks_respects_z_when_white_text_overlaps_black_text(self):
        scene = pipeline.normalize_scene(
            {
                "blocks": [
                    {"type": "text", "x": 0, "y": 0, "w": 1, "h": 1, "text": "low", "z": 0},
                    {"type": "text", "x": 0, "y": 0, "w": 1, "h": 1, "text": "high", "z": 1},
                ]
            },
            settings=pipeline.RenderSettings(),
        )

        def fake_layers(block, settings, *, text_threshold):
            if block.text == "low":
                return pipeline.DirectTextLayers(black_values=[255], white_values=[0], width=1, height=1)
            return pipeline.DirectTextLayers(black_values=[0], white_values=[255], width=1, height=1)

        with mock.patch.object(pipeline, "_render_text_block_layers", side_effect=fake_layers):
            composed = pipeline._compose_scene_text_blocks(
                [0],
                scene,
                pipeline.RenderSettings(),
                text_threshold=160,
            )

        self.assertEqual(composed, [0])

    def test_compose_scene_text_blocks_preserves_input_order_for_same_z(self):
        scene = pipeline.normalize_scene(
            {
                "blocks": [
                    {"type": "text", "x": 0, "y": 0, "w": 1, "h": 1, "text": "first", "z": 0},
                    {"type": "text", "x": 0, "y": 0, "w": 1, "h": 1, "text": "second", "z": 0},
                ]
            },
            settings=pipeline.RenderSettings(),
        )

        def fake_layers(block, settings, *, text_threshold):
            if block.text == "first":
                return pipeline.DirectTextLayers(black_values=[255], white_values=[0], width=1, height=1)
            return pipeline.DirectTextLayers(black_values=[0], white_values=[255], width=1, height=1)

        with mock.patch.object(pipeline, "_render_text_block_layers", side_effect=fake_layers):
            composed = pipeline._compose_scene_text_blocks(
                [0],
                scene,
                pipeline.RenderSettings(),
                text_threshold=160,
            )

        self.assertEqual(composed, [0])

    def test_render_scene_to_artifacts_uses_direct_text_profile_for_296x128(self):
        scene = {"blocks": [{"type": "text", "x": 0, "y": 0, "w": 20, "h": 12, "text": "Hi"}]}

        with tempfile.TemporaryDirectory() as tmpdir:
            preview_path = Path(tmpdir) / "scene.png"
            bitmap_path = Path(tmpdir) / "scene.bin"

            with (
                mock.patch.object(
                    pipeline,
                    "render_html_capture_set",
                    return_value=((1184, 512), {"image": b"image", "decoration": b"decoration"}),
                ) as mocked_capture,
                mock.patch.object(
                    pipeline,
                    "convert_scene_captures_to_bitmap",
                    return_value=FakeBitmapArtifact(width=296, height=128, bitmap_byte_count=4736),
                ) as mocked_direct,
                mock.patch.object(pipeline, "convert_layer_captures_to_bitmap") as mocked_layered,
                mock.patch.object(pipeline, "convert_image_to_bitmap") as mocked_single,
            ):
                result = pipeline.render_scene_to_artifacts(
                    scene,
                    preview_path=preview_path,
                    bitmap_path=bitmap_path,
                    settings=pipeline.RenderSettings(),
                )

        self.assertEqual(result["profile"], "epd_296x128_bw")
        self.assertEqual(result["composition"], "layered-direct-text-overlay")
        self.assertEqual(result["bitmapBytes"], 4736)
        self.assertEqual(mocked_capture.call_count, 1)
        self.assertEqual(mocked_direct.call_count, 1)
        self.assertEqual(mocked_layered.call_count, 0)
        self.assertEqual(mocked_single.call_count, 0)
        self.assertEqual(mocked_direct.call_args.kwargs["text_threshold"], 160)

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
