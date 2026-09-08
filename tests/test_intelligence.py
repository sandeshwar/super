"""Autonomous intelligence: audit → agenda → auto-act → briefing."""

from __future__ import annotations

import os
import tempfile
import unittest

from super import intelligence as I
from super.tools import catalog
from super.tools.langchain_bridge import ensure_bridge


def _cfg(tmpdir: str) -> dict:
    return {
        "_root": tmpdir,
        "state_dir": os.path.join(tmpdir, ".super"),
        "tools": {
            "enabled": True,
            "discovery": True,
            "groups": {
                "files": True, "search": True, "git": True, "project": True,
                "capabilities": True, "intelligence": True, "agents": True,
                "memory": True,
            },
            "disabled": [],
            "packs": {},
        },
        "capabilities": {"enabled": True, "auto_install_low": True},
        "intelligence": {
            "enabled": True,
            "auto_act": True,
            "inject_briefing": True,
            "min_interval_s": 0,
            "max_agenda": 40,
        },
        "agents": {"enabled": True, "allow_agent_create_roles": ["worker", "planner"]},
        "gates": {},
        "ambition": {},
    }


class TestIntelligence(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.cfg = _cfg(self._td.name)
        os.makedirs(self.cfg["state_dir"], exist_ok=True)
        for name, spec in list(catalog.TOOLS.items()):
            if spec.group in ("user_caps",):
                catalog.TOOLS.pop(name, None)

    def tearDown(self):
        self._td.cleanup()

    def test_tick_forges_and_seeds_memory(self):
        ensure_bridge(self.cfg)
        result = I.tick(self.cfg, force=True)
        self.assertTrue(result["ok"])
        agenda = I.list_agenda(self.cfg)
        # empty workspace should produce memory/forge findings (some auto-done)
        self.assertTrue(agenda or result["auto_act"].get("acted"))

        # repo_pulse recipe should install
        self.assertIn("repo_pulse", catalog.TOOLS)

    def test_briefing_lists_open_items(self):
        ensure_bridge(self.cfg)
        I.tick(self.cfg, force=True)
        text = I.compile_briefing(self.cfg)
        self.assertIn("Intelligence", text)
        self.assertTrue("agenda" in text.lower() or "Standing orders" in text or "Agenda clear" in text)

    def test_dismiss_and_pursue(self):
        ensure_bridge(self.cfg)
        I.refresh_agenda(self.cfg, force=True)
        items = I.list_agenda(self.cfg)
        self.assertTrue(items)
        top = items[0]
        I.dismiss(self.cfg, top["id"], reason="test")
        left_ids = {i["id"] for i in I.list_agenda(self.cfg)}
        self.assertNotIn(top["id"], left_ids)

    def test_harness_injects_briefing(self):
        ensure_bridge(self.cfg)
        from super import harness
        sys_prompt = harness.build_system(self.cfg)
        self.assertIn("Autonomy loop", sys_prompt)
        self.assertIn("Intelligence", sys_prompt)

    def test_rate_limit(self):
        ensure_bridge(self.cfg)
        self.cfg["intelligence"]["min_interval_s"] = 9999
        I.tick(self.cfg, force=True)
        r2 = I.refresh_agenda(self.cfg, force=False)
        self.assertEqual(r2.get("skipped"), "rate_limited")


if __name__ == "__main__":
    unittest.main()
