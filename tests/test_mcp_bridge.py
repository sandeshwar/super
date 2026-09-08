"""MCP bridge: register remote tools into the unified catalog."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from tests import make_cfg


class TestMcpBridge(unittest.TestCase):
    def setUp(self):
        self.cfg, self.root = make_cfg()
        self.cfg.setdefault("tools", {})["enabled"] = True
        self.cfg["tools"]["discovery"] = True
        self.cfg["tools"]["runtime"] = "stdlib"
        self.cfg["mcp"] = {
            "servers": [
                {
                    "id": "mcp_fs",
                    "name": "filesystem",
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
                    "enabled": True,
                }
            ]
        }
        from super.tools import mcp_bridge as M
        M._reset_for_tests()
        self.M = M

    def tearDown(self):
        self.M._reset_for_tests()
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_tool_name_slug(self):
        self.assertEqual(self.M._tool_name("File System", "read_file"), "mcp_file_system__read_file")

    def test_sync_registers_and_activates(self):
        remotes = [
            {
                "name": "read_file",
                "description": "Read a file from disk.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "list_dir",
                "description": "List a directory.",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

        async def fake_list(srv, cfg):
            return remotes

        async def fake_call(srv, cfg, remote_name, arguments):
            from super.tools.base import ToolResult
            return ToolResult(True, f"ok:{remote_name}:{arguments.get('path')}", taint="untrusted")

        with patch.object(self.M, "_list_remote_tools", side_effect=fake_list), \
             patch.object(self.M, "mcp_available", return_value=True), \
             patch.object(self.M, "_call_remote", side_effect=fake_call):
            out = self.M.sync_mcp(self.cfg, force=True)
            self.assertTrue(out["ok"])
            self.assertEqual(len(out["tools"]), 2)

            from super.tools.catalog import TOOLS, get_tool
            from super.tools.discovery import handle_search_tools, handle_activate_tools, is_callable
            from super.tools.runtime import execute_tool

            name = "mcp_filesystem__read_file"
            self.assertIn(name, TOOLS)
            spec = get_tool(name)
            self.assertEqual(spec.group, "mcp")
            self.assertIn("MCP:filesystem", spec.description)

            r = handle_search_tools(self.cfg, {"query": "filesystem read", "limit": 10})
            data = json.loads(r.content)
            names = [x["name"] for x in data["results"]]
            self.assertIn(name, names)
            row = next(x for x in data["results"] if x["name"] == name)
            self.assertEqual(row["source"], "mcp")

            act = handle_activate_tools(self.cfg, {"names": [name]})
            self.assertTrue(act.ok)
            self.assertTrue(is_callable(self.cfg, name))

            result = execute_tool(self.cfg, name, {"path": "/tmp/x"})
            self.assertTrue(result.ok)
            self.assertEqual(result.taint, "untrusted")
            self.assertIn("ok:read_file:/tmp/x", result.content)

            # Second sync is cached
            out2 = self.M.sync_mcp(self.cfg)
            self.assertTrue(out2.get("cached"))

    def test_disabled_server_skipped(self):
        self.cfg["mcp"]["servers"][0]["enabled"] = False

        async def boom(*_a, **_k):
            raise AssertionError("should not connect")

        with patch.object(self.M, "_list_remote_tools", side_effect=boom), \
             patch.object(self.M, "mcp_available", return_value=True):
            out = self.M.sync_mcp(self.cfg, force=True)
            self.assertTrue(out["ok"])
            self.assertEqual(out["tools"], [])

    def test_ensure_clears_when_servers_removed(self):
        async def fake_list(srv, cfg):
            return [{"name": "ping", "description": "Ping", "parameters": {"type": "object", "properties": {}}}]

        with patch.object(self.M, "_list_remote_tools", side_effect=fake_list), \
             patch.object(self.M, "mcp_available", return_value=True):
            self.M.sync_mcp(self.cfg, force=True)
            self.assertTrue(any(n.startswith("mcp_") for n in self.M._remote))

            self.cfg["mcp"]["servers"] = []
            self.M.ensure_mcp(self.cfg)
            self.assertEqual(self.M._remote, {})

    def test_mcp_unavailable_is_soft_fail(self):
        with patch.object(self.M, "mcp_available", return_value=False):
            out = self.M.sync_mcp(self.cfg, force=True)
            self.assertFalse(out["ok"])
            self.assertIn("not installed", out["error"])

    def test_manage_add_list_set_remove(self):
        async def fake_list(srv, cfg):
            return [{
                "name": "echo",
                "description": "Echo",
                "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
            }]

        with patch.object(self.M, "_list_remote_tools", side_effect=fake_list), \
             patch.object(self.M, "mcp_available", return_value=True):
            self.cfg["mcp"] = {"servers": []}

            listed = self.M.handle_list_mcp_servers(self.cfg, {})
            self.assertTrue(listed.ok)
            self.assertEqual(json.loads(listed.content)["servers"], [])

            added = self.M.handle_add_mcp_server(self.cfg, {
                "name": "demo",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@scope/demo"],
            })
            self.assertTrue(added.ok, added.content)
            data = json.loads(added.content)
            self.assertEqual(data["server"]["name"], "demo")
            self.assertIn("mcp_demo__echo", data["sync"]["tools"])

            dup = self.M.handle_add_mcp_server(self.cfg, {
                "name": "demo", "transport": "stdio", "command": "npx",
            })
            self.assertFalse(dup.ok)

            sid = data["server"]["id"]
            sett = self.M.handle_set_mcp_server(self.cfg, {"id": sid, "enabled": False})
            self.assertTrue(sett.ok, sett.content)
            self.assertFalse(json.loads(sett.content)["server"]["enabled"])

            bad = self.M.handle_add_mcp_server(self.cfg, {
                "name": "evil", "transport": "stdio", "command": "bash -c 'id'",
            })
            self.assertFalse(bad.ok)

            badu = self.M.handle_add_mcp_server(self.cfg, {
                "name": "meta", "transport": "http",
                "url": "http://169.254.169.254/latest",
            })
            self.assertFalse(badu.ok)

            rem = self.M.handle_remove_mcp_server(self.cfg, {"id": sid})
            self.assertTrue(rem.ok, rem.content)
            self.assertEqual(self.cfg["mcp"]["servers"], [])

    def test_sanitize_strips_stale_url_on_stdio_patch(self):
        from super import config as C
        cfg, root = make_cfg()
        cfg["mcp"] = {"servers": [{
            "id": "mcp_x", "name": "x", "transport": "sse",
            "url": "http://127.0.0.1:3000/sse", "enabled": True,
        }]}
        updated = C.apply_patch(cfg, {"mcp": {"servers": [{
            "id": "mcp_x", "name": "x", "transport": "stdio",
            "command": "npx", "args": ["-y", "pkg"],
            "url": "http://127.0.0.1:3000/sse",  # stale
            "enabled": True,
        }]}})
        srv = updated["mcp"]["servers"][0]
        self.assertEqual(srv["transport"], "stdio")
        self.assertNotIn("url", srv)
        self.assertEqual(srv["command"], "npx")
        import shutil
        shutil.rmtree(root, ignore_errors=True)

    def test_manage_tools_registered(self):
        from super.tools.catalog import TOOLS
        for n in ("list_mcp_servers", "add_mcp_server", "set_mcp_server",
                  "remove_mcp_server", "reload_mcp"):
            self.assertIn(n, TOOLS)
            self.assertTrue(TOOLS[n].discovery)


if __name__ == "__main__":
    unittest.main()
