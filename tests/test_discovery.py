"""Unified tool discovery: builtins and pack stubs share search → describe → activate."""
import unittest

from tests import make_cfg


class TestToolDiscovery(unittest.TestCase):
    def setUp(self):
        self.cfg, self.root = make_cfg()
        self.cfg.setdefault("tools", {})["enabled"] = True
        self.cfg["tools"]["discovery"] = True
        self.cfg["tools"]["runtime"] = "stdlib"
        self.cfg["tools"].setdefault("packs", {})["lc_search"] = False
        from super.tools.langchain_bridge import ensure_bridge
        ensure_bridge(self.cfg)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_search_web_finds_duckduckgo_stub(self):
        from super.tools.discovery import handle_search_tools
        import json

        r = handle_search_tools(self.cfg, {"query": "web search", "limit": 10})
        self.assertTrue(r.ok)
        data = json.loads(r.content)
        names = [x["name"] for x in data["results"]]
        self.assertIn("duckduckgo_search", names)
        ddg = next(x for x in data["results"] if x["name"] == "duckduckgo_search")
        self.assertTrue(ddg["lazy"] or ddg["source"] == "pack")
        # DDG should rank at or above fetch_url for "web search"
        self.assertLessEqual(names.index("duckduckgo_search"), names.index("fetch_url") if "fetch_url" in names else 99)

    def test_list_groups_includes_lc_search(self):
        from super.tools.discovery import handle_list_groups
        import json

        r = handle_list_groups(self.cfg, {})
        data = json.loads(r.content)
        ids = [g["id"] for g in data["groups"]]
        self.assertIn("lc_search", ids)
        lc = next(g for g in data["groups"] if g["id"] == "lc_search")
        self.assertIn("duckduckgo_search", lc["tools"])

    def test_activate_materializes_duckduckgo(self):
        from super.tools.discovery import handle_activate_tools, is_callable
        from super.tools.catalog import TOOLS
        import json

        # force stub if a prior test loaded the real tool
        spec = TOOLS.get("duckduckgo_search")
        if spec and not spec.lazy_pack:
            # already loaded — still should activate
            pass

        r = handle_activate_tools(self.cfg, {"names": ["duckduckgo_search"]})
        self.assertTrue(r.ok)
        data = json.loads(r.content)
        self.assertIn("duckduckgo_search", data["added"])
        self.assertTrue(is_callable(self.cfg, "duckduckgo_search"))
        real = TOOLS["duckduckgo_search"]
        self.assertFalse(real.lazy_pack)

    def test_describe_builtin_and_pack_same_shape(self):
        from super.tools.discovery import handle_describe_tool
        import json

        b = handle_describe_tool(self.cfg, {"name": "grep"})
        self.assertTrue(b.ok)
        pb = json.loads(b.content)
        self.assertEqual(pb["name"], "grep")
        self.assertIn("parameters", pb)

        p = handle_describe_tool(self.cfg, {"name": "duckduckgo_search"})
        self.assertTrue(p.ok, p.content)
        pp = json.loads(p.content)
        self.assertEqual(pp["name"], "duckduckgo_search")
        self.assertIn("parameters", pp)
        self.assertTrue(pp["ready"])


if __name__ == "__main__":
    unittest.main()
