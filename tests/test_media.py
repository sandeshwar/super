"""Tests for generic media extraction / storage."""

from __future__ import annotations

import base64
import os
import tempfile
import unittest

from super import media
from super.tools.base import ToolResult


def _png_bytes() -> bytes:
    # Minimal 1x1 PNG
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )


class MediaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = {"state_dir": self.tmp.name, "_root": self.tmp.name}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_store_and_resolve(self) -> None:
        part = media.store_bytes(self.cfg, _png_bytes(), mime="image/png", hint="dot")
        self.assertTrue(part["src"].startswith("/api/media/"))
        mid = part["src"].rsplit("/", 1)[-1]
        hit = media.resolve_media_file(self.cfg, mid)
        self.assertIsNotNone(hit)
        path, mime = hit  # type: ignore[misc]
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(mime, "image/png")

    def test_extract_embedded_json(self) -> None:
        b64 = base64.b64encode(_png_bytes()).decode()
        text = f'Took a screenshot.\n{{"type": "image", "data": "{b64}", "mimeType": "image/png"}}'
        cleaned, parts = media.extract_from_text(self.cfg, text, source="mcp")
        self.assertEqual(len(parts), 1)
        self.assertIn("[image:", cleaned)
        self.assertNotIn(b64[:40], cleaned)
        self.assertTrue(parts[0]["src"].startswith("/api/media/") or parts[0]["src"].startswith("data:"))

    def test_extract_markdown_and_path(self) -> None:
        path = os.path.join(self.tmp.name, "shot.png")
        with open(path, "wb") as f:
            f.write(_png_bytes())
        text = f"See ![shot]({path}) please"
        cleaned, parts = media.extract_from_text(self.cfg, text, source="markdown")
        self.assertEqual(len(parts), 1)
        self.assertIn("/api/media/", cleaned)

    def test_enrich_tool_result(self) -> None:
        b64 = base64.b64encode(_png_bytes()).decode()
        raw = ToolResult(True, f'{{"type":"image","data":"{b64}"}}', data={})
        out = media.enrich_tool_result(self.cfg, raw, tool_name="take_screenshot")
        self.assertTrue(out.data.get("media"))
        self.assertNotIn(b64[:30], out.content)

    def test_mcp_blocks_image_attr(self) -> None:
        class FakeImage:
            type = "image"
            data = base64.b64encode(_png_bytes()).decode()
            mimeType = "image/png"
            text = None

        class FakeText:
            text = "hello"
            data = None

        content, parts = media.extract_from_mcp_blocks(self.cfg, [FakeText(), FakeImage()])
        self.assertIn("hello", content)
        self.assertEqual(len(parts), 1)


if __name__ == "__main__":
    unittest.main()
