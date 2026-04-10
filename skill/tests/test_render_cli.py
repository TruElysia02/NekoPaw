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
        self.assertEqual(sorted(payload["data"]["states"].keys()), ["cancelled", "confirmed", "pending", "timeout"])
        self.assertEqual(mocked_render.call_count, 4)


if __name__ == "__main__":
    unittest.main()
