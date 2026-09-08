"""Capability forge: propose → test → approve/auto-install → live catalog."""

from __future__ import annotations

import os
import tempfile
import unittest

from super import capabilities as C
from super.tools import catalog
from super.tools.discovery import is_callable, _session
from super.tools.langchain_bridge import ensure_bridge
from super.tools.runtime import execute_tool


def _cfg(tmpdir: str) -> dict:
    return {
        "_root": tmpdir,
        "state_dir": os.path.join(tmpdir, ".super"),
        "tools": {
            "enabled": True,
            "discovery": True,
            "max_activated": 16,
            "groups": {
                "files": True,
                "search": True,
                "git": True,
                "project": True,
                "capabilities": True,
                "agents": True,
            },
            "disabled": [],
            "packs": {},
        },
        "capabilities": {"enabled": True, "auto_install_low": True},
        "agents": {"enabled": True},
        "gates": {},
    }


class TestCapabilityForge(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.cfg = _cfg(self._td.name)
        os.makedirs(self.cfg["state_dir"], exist_ok=True)
        # drop any prior user_caps from other tests in-process
        for name, spec in list(catalog.TOOLS.items()):
            if spec.group == C.GROUP:
                catalog.TOOLS.pop(name, None)

    def tearDown(self):
        self._td.cleanup()

    def test_low_risk_composite_auto_installs(self):
        ensure_bridge(self.cfg)
        cap = C.propose(
            self.cfg,
            name="repo_pulse",
            summary="list dir + tree",
            kind="composite",
            risk="low",
            parameters={"type": "object", "properties": {}},
            impl={
                "steps": [
                    {"tool": "list_dir", "args": {"path": "."}, "as": "listing"},
                    {"tool": "repo_tree", "args": {}, "as": "tree"},
                ],
                "merge": "text",
            },
            tests=[{"args": {}, "expect_ok": True}],
            created_by="test",
        )
        self.assertEqual(cap["status"], "installed", cap)
        self.assertEqual(cap["risk"], "low")
        self.assertIn("repo_pulse", catalog.TOOLS)

        _session(self.cfg)["activated"].add("repo_pulse")
        self.assertTrue(is_callable(self.cfg, "repo_pulse"))
        result = execute_tool(self.cfg, "repo_pulse", {})
        self.assertTrue(result.ok, result.content)
        self.assertIn("listing", result.content.lower())

    def test_empty_tests_do_not_auto_install_for_agent(self):
        ensure_bridge(self.cfg)
        cap = C.propose(
            self.cfg,
            name="bare_list",
            kind="composite",
            risk="low",
            impl={"steps": [{"tool": "list_dir", "args": {"path": "."}}]},
            tests=[],
            created_by="agent",
        )
        self.assertEqual(cap["status"], "pending")
        self.assertNotIn("bare_list", catalog.TOOLS)

    def test_medium_stays_pending_until_approve(self):
        ensure_bridge(self.cfg)
        cap = C.propose(
            self.cfg,
            name="status_only",
            summary="just list_dir",
            kind="composite",
            risk="medium",
            impl={"steps": [{"tool": "list_dir", "args": {"path": "."}, "as": "s"}]},
            created_by="agent",
        )
        self.assertEqual(cap["status"], "pending")
        self.assertNotIn("status_only", catalog.TOOLS)

        installed = C.approve(self.cfg, cap["id"], actor="user")
        self.assertEqual(installed["status"], "installed")
        self.assertIn("status_only", catalog.TOOLS)

    def test_arg_substitution(self):
        ensure_bridge(self.cfg)
        # write a small file then read via composite with $arg.path
        path = os.path.join(self.cfg["_root"], "note.txt")
        with open(path, "w") as f:
            f.write("hello-forge\n")
        cap = C.propose(
            self.cfg,
            name="read_note",
            summary="read a path",
            kind="composite",
            risk="low",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            impl={
                "steps": [
                    {"tool": "read_file", "args": {"path": "$arg.path", "limit": 10}, "as": "body"},
                ],
            },
            tests=[{"args": {"path": "note.txt"}, "expect_ok": True, "expect_contains": "hello-forge"}],
            created_by="test",
        )
        self.assertEqual(cap["status"], "installed", cap)
        _session(self.cfg)["activated"].add("read_note")
        r = execute_tool(self.cfg, "read_note", {"path": "note.txt"})
        self.assertTrue(r.ok, r.content)
        self.assertIn("hello-forge", r.content)

    def test_boot_reload(self):
        ensure_bridge(self.cfg)
        cap = C.propose(
            self.cfg,
            name="just_status",
            kind="composite",
            risk="low",
            impl={"steps": [{"tool": "list_dir", "args": {"path": "."}}]},
            tests=[{"args": {}, "expect_ok": True}],
            created_by="test",
        )
        self.assertEqual(cap["status"], "installed")
        catalog.TOOLS.pop("just_status", None)
        self.assertNotIn("just_status", catalog.TOOLS)
        n = C.ensure_capabilities(self.cfg)
        self.assertGreaterEqual(n, 1)
        self.assertIn("just_status", catalog.TOOLS)

    def test_reviewer_cannot_propose(self):
        ensure_bridge(self.cfg)
        self.cfg["_agent_effective"] = {
            "may_manage_agents": False,
            "may_write": False,
            "may_spawn": False,
            "tools": None,
        }
        r = C.handle_propose_capability(self.cfg, {
            "name": "should_fail",
            "kind": "composite",
            "risk": "low",
            "impl": {"steps": [{"tool": "list_dir", "args": {"path": "."}}]},
        })
        self.assertFalse(r.ok)
        self.assertIn("may_manage_agents", r.content)

    def test_retire_unregisters(self):
        ensure_bridge(self.cfg)
        cap = C.propose(
            self.cfg,
            name="temp_cap",
            kind="composite",
            risk="low",
            impl={"steps": [{"tool": "list_dir", "args": {"path": "."}}]},
            tests=[{"args": {}, "expect_ok": True}],
            created_by="test",
        )
        self.assertIn("temp_cap", catalog.TOOLS)
        C.retire(self.cfg, cap["id"])
        self.assertNotIn("temp_cap", catalog.TOOLS)


if __name__ == "__main__":
    unittest.main()
