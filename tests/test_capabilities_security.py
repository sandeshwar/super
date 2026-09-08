"""Security regressions for capability forge."""

from __future__ import annotations

import os
import tempfile
import unittest

from super import capabilities as C
from super.tools import catalog
from super.tools.discovery import _session
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
                "files": True, "search": True, "shell": True, "git": True,
                "project": True, "capabilities": True, "agents": True,
            },
            "disabled": [],
            "packs": {},
        },
        "capabilities": {"enabled": True, "auto_install_low": True, "http_allowlist": []},
        "agents": {"enabled": True},
        "gates": {},
    }


class TestForgeSecurity(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.cfg = _cfg(self._td.name)
        os.makedirs(self.cfg["state_dir"], exist_ok=True)
        for name, spec in list(catalog.TOOLS.items()):
            if spec.group == C.GROUP:
                catalog.TOOLS.pop(name, None)
        ensure_bridge(self.cfg)

    def tearDown(self):
        self._td.cleanup()

    def test_claimed_low_with_run_command_becomes_high_pending(self):
        cap = C.propose(
            self.cfg,
            name="sneaky_sh",
            kind="composite",
            risk="low",
            impl={"steps": [{"tool": "run_command", "args": {"command": "echo pwn"}}]},
            tests=[{"args": {}, "expect_ok": True}],
            created_by="agent",
        )
        self.assertEqual(cap["risk"], "high")
        self.assertEqual(cap["status"], "pending")
        self.assertNotIn("sneaky_sh", catalog.TOOLS)

    def test_may_write_false_blocks_shell_step(self):
        cap = C.propose(
            self.cfg,
            name="shell_wrap",
            kind="composite",
            risk="high",
            impl={"steps": [{"tool": "run_command", "args": {"command": "echo hi"}}]},
            created_by="agent",
        )
        installed = C.approve(self.cfg, cap["id"], actor="user")
        self.assertEqual(installed["status"], "installed")
        self.cfg["_agent_effective"] = {
            "may_write": False,
            "may_manage_agents": False,
            "may_spawn": False,
            "tools": None,
        }
        _session(self.cfg)["activated"].add("shell_wrap")
        r = execute_tool(self.cfg, "shell_wrap", {})
        self.assertFalse(r.ok)
        self.assertIn("may_write", r.content)

    def test_allowlist_blocks_step(self):
        cap = C.propose(
            self.cfg,
            name="list_wrap",
            kind="composite",
            risk="low",
            impl={"steps": [{"tool": "list_dir", "args": {"path": "."}}]},
            tests=[{"args": {}, "expect_ok": True}],
            created_by="agent",
        )
        self.assertEqual(cap["status"], "installed")
        self.cfg["_agent_effective"] = {
            "may_write": True,
            "may_manage_agents": True,
            "tools": ["list_wrap", "read_file"],  # list_dir not allowed as step
        }
        _session(self.cfg)["activated"].add("list_wrap")
        # discovery tools still allowed by can_call_tool; list_dir is not discovery
        r = execute_tool(self.cfg, "list_wrap", {})
        self.assertFalse(r.ok)
        self.assertIn("allowlist", r.content)

    def test_http_localhost_rejected(self):
        with self.assertRaises(ValueError) as cm:
            C.propose(
                self.cfg,
                name="ssrf_try",
                kind="http",
                risk="low",
                impl={"url": "http://127.0.0.1/secret", "method": "GET"},
                created_by="agent",
            )
        self.assertIn("rejected", str(cm.exception).lower() + str(cm.exception))

    def test_http_metadata_rejected(self):
        with self.assertRaises(ValueError):
            C.propose(
                self.cfg,
                name="meta_try",
                kind="http",
                risk="medium",
                impl={"url": "http://169.254.169.254/latest/meta-data/", "method": "GET"},
                created_by="agent",
            )

    def test_cycle_detected(self):
        a = C.propose(
            self.cfg,
            name="cap_a",
            kind="composite",
            risk="low",
            impl={"steps": [{"tool": "list_dir", "args": {"path": "."}}]},
            tests=[{"args": {}, "expect_ok": True}],
            created_by="agent",
        )
        self.assertEqual(a["status"], "installed")
        b = C.propose(
            self.cfg,
            name="cap_b",
            kind="composite",
            risk="low",
            impl={"steps": [{"tool": "cap_a", "args": {}}]},
            tests=[{"args": {}, "expect_ok": True}],
            created_by="agent",
        )
        self.assertEqual(b["status"], "installed")
        C.retire(self.cfg, a["id"])
        with self.assertRaises(ValueError) as cm:
            C.propose(
                self.cfg,
                name="cap_a",
                kind="composite",
                risk="low",
                impl={"steps": [{"tool": "cap_b", "args": {}}]},
                tests=[],
                created_by="agent",
            )
        self.assertIn("cycle", str(cm.exception).lower())


if __name__ == "__main__":
    unittest.main()
