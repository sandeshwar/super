"""Tests for agent canvas presentation tools."""

from __future__ import annotations

import os
import tempfile
import unittest

from super import canvas
from super.tools.catalog import TOOLS, get_tool
from super.tools.runtime import _canvas_payload, execute_tool


class CanvasTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = {
            "state_dir": self.tmp.name,
            "_root": self.tmp.name,
            "tools": {
                "enabled": True,
                "discovery": False,
                "groups": {"canvas": True},
                "disabled": [],
            },
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_tools_registered(self) -> None:
        for name in ("canvas_present", "canvas_update", "canvas_close", "canvas_list"):
            self.assertIn(name, TOOLS)
            self.assertEqual(TOOLS[name].group, "canvas")

    def test_present_markdown(self) -> None:
        r = canvas.handle_present(self.cfg, {
            "kind": "markdown",
            "title": "Notes",
            "content": "# Hello\n\nWorld",
            "id": "notes1",
        })
        self.assertTrue(r.ok)
        self.assertIn("canvas", r.data)
        part = r.data["canvas"]
        self.assertEqual(part["kind"], "markdown")
        self.assertEqual(part["id"], "notes1")
        self.assertTrue(part["open"])
        self.assertIn("Hello", part["content"])

    def test_present_url(self) -> None:
        r = canvas.handle_present(self.cfg, {
            "kind": "url",
            "title": "Example",
            "src": "https://example.com",
        })
        self.assertTrue(r.ok)
        self.assertEqual(r.data["canvas"]["src"], "https://example.com")

    def test_present_html_stores_large(self) -> None:
        big = "<html><body>" + ("x" * 20_000) + "</body></html>"
        r = canvas.handle_present(self.cfg, {
            "kind": "html",
            "title": "Big",
            "content": big,
            "id": "big1",
        })
        self.assertTrue(r.ok)
        part = r.data["canvas"]
        self.assertTrue(part["src"].startswith("/api/canvas/"))
        cid = part["src"].rsplit("/", 1)[-1]
        hit = canvas.resolve_canvas_file(self.cfg, cid)
        self.assertIsNotNone(hit)
        path, mime = hit  # type: ignore[misc]
        self.assertTrue(os.path.isfile(path))
        self.assertIn("html", mime)

    def test_present_image_path(self) -> None:
        import base64
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        path = os.path.join(self.tmp.name, "dot.png")
        with open(path, "wb") as f:
            f.write(png)
        r = canvas.handle_present(self.cfg, {
            "kind": "image",
            "title": "Dot",
            "path": path,
            "id": "img1",
        })
        self.assertTrue(r.ok)
        self.assertTrue(r.data["canvas"]["src"].startswith("/api/media/"))

    def test_update_and_close(self) -> None:
        canvas.handle_present(self.cfg, {
            "kind": "markdown", "title": "A", "content": "one", "id": "x",
        })
        u = canvas.handle_update(self.cfg, {
            "id": "x", "kind": "markdown", "content": "two", "title": "B",
        })
        self.assertTrue(u.ok)
        self.assertEqual(u.data["canvas"]["content"], "two")
        self.assertEqual(u.data["canvas"]["title"], "B")
        c = canvas.handle_close(self.cfg, {"id": "x"})
        self.assertTrue(c.ok)
        self.assertFalse(c.data["canvas"]["open"])
        self.assertEqual(c.data["canvas"]["action"], "close")

    def test_list(self) -> None:
        canvas.handle_present(self.cfg, {
            "kind": "url", "src": "https://a.test", "id": "a", "title": "A",
        })
        r = canvas.handle_list(self.cfg, {})
        self.assertTrue(r.ok)
        self.assertEqual(len(r.data["canvases"]), 1)

    def test_execute_tool_payload(self) -> None:
        self.assertIsNotNone(get_tool("canvas_present"))
        result = execute_tool(self.cfg, "canvas_present", {
            "kind": "markdown",
            "title": "Via runtime",
            "content": "**hi**",
            "id": "rt1",
        })
        self.assertTrue(result.ok)
        payload = _canvas_payload(result)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["id"], "rt1")

    def test_url_requires_src(self) -> None:
        r = canvas.handle_present(self.cfg, {"kind": "url", "title": "Nope"})
        self.assertFalse(r.ok)

    def test_google_not_embeddable(self) -> None:
        r = canvas.handle_present(self.cfg, {
            "kind": "url", "title": "Google", "src": "https://www.google.com", "id": "g",
        })
        self.assertTrue(r.ok)
        self.assertFalse(r.data["canvas"].get("embeddable"))
        self.assertIn("embed", (r.data["canvas"].get("embed_note") or "").lower())

    def test_activate_tools_soft_names(self) -> None:
        from super.tools.discovery import _coerce_tool_names, handle_activate_tools
        self.assertEqual(_coerce_tool_names({"name": '["canvas_present"]'}), ["canvas_present"])
        self.assertEqual(_coerce_tool_names({"names": "canvas_present, canvas_list"}), ["canvas_present", "canvas_list"])
        r = handle_activate_tools(self.cfg, {"name": '["canvas_present"]'})
        self.assertTrue(r.ok, r.content)


if __name__ == "__main__":
    unittest.main()
