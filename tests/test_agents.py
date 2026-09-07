"""AgentSpec CRUD + parent-rule inheritance."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests import make_cfg


class TestAgents(unittest.TestCase):
    def setUp(self):
        self.cfg, self.root = make_cfg()
        self.cfg.setdefault("tools", {})["enabled"] = True
        self.cfg["tools"]["discovery"] = True
        self.cfg["tools"]["groups"] = {
            "files": True, "search": True, "shell": True, "git": True,
            "web": True, "tasks": True, "memory": True, "project": True, "agents": True,
        }
        self.cfg["agents"] = {
            "enabled": True, "max_depth": 3, "max_agents": 50,
            "allow_agent_create_roles": ["worker", "planner"],
        }

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_crud_and_list(self):
        from super import agents as A
        a = A.create_agent(self.cfg, name="repo-reader", role="worker",
                           summary="reads files", groups=["files", "search"],
                           created_by="user")
        self.assertEqual(a["status"], "active")
        self.assertEqual(A.get_agent(self.cfg, a["id"])["name"], "repo-reader")
        self.assertEqual(len(A.list_agents(self.cfg)), 1)
        A.update_agent(self.cfg, a["id"], {"summary": "reads + greps"}, actor="user")
        self.assertIn("greps", A.get_agent(self.cfg, a["id"])["summary"])
        A.archive_agent(self.cfg, a["id"])
        self.assertEqual(len(A.list_agents(self.cfg)), 0)
        self.assertEqual(len(A.list_agents(self.cfg, include_archived=True)), 1)

    def test_judge_created_by_agent_is_pending(self):
        from super import agents as A
        a = A.create_agent(self.cfg, name="rev", role="reviewer", created_by="agent:main")
        self.assertEqual(a["status"], "pending")
        with self.assertRaises(Exception):
            A.make_child_cfg(self.cfg, a)
        approved = A.approve_agent(self.cfg, a["id"], actor="user")
        self.assertEqual(approved["status"], "active")

    def test_inheritance_tightens_only(self):
        from super import agents as A
        parent_eff = A.root_effective(self.cfg)
        self.assertIn("shell", parent_eff["groups"])
        child = A.create_agent(
            self.cfg, name="no-shell", role="worker",
            groups=["files", "search"],
            disabled=["edit_file"],
            budgets={"max_steps": 5},
            policy={"may_write": False},
            created_by="user",
        )
        eff = A.inherit_effective(parent_eff, child, self.cfg)
        self.assertEqual(set(eff["groups"]), {"files", "search"})
        self.assertIn("edit_file", eff["disabled"])
        self.assertFalse(eff["may_write"])
        self.assertEqual(eff["max_steps"], 5)
        self.assertEqual(eff["depth"], 1)
        # cannot widen beyond parent steps
        wide = A.create_agent(
            self.cfg, name="wide", role="worker",
            budgets={"max_steps": 10_000},
            created_by="user",
        )
        parent_eff2 = {**parent_eff, "max_steps": 8}
        eff2 = A.inherit_effective(parent_eff2, wide, self.cfg)
        self.assertEqual(eff2["max_steps"], 8)

    def test_child_cfg_blocks_write_tools(self):
        from super import agents as A
        from super.tools.discovery import is_callable
        from super.tools.runtime import execute_tool

        spec = A.create_agent(
            self.cfg, name="ro", role="reviewer",
            groups=["files", "search"],
            created_by="user",
        )
        # human-created reviewer is active but may_write default false
        child, eff = A.make_child_cfg(self.cfg, spec)
        self.assertFalse(eff["may_write"])
        # activate read_file then try write
        child.setdefault("_tool_session", {"activated": set(), "pack_groups": set()})
        child["_tool_session"]["activated"].add("read_file")
        child["_tool_session"]["activated"].add("write_file")
        self.assertTrue(is_callable(child, "read_file"))
        self.assertFalse(is_callable(child, "write_file"))
        r = execute_tool(child, "write_file", {"path": "x.py", "content": "hi"})
        self.assertFalse(r.ok)

    def test_nested_depth_and_tool_intersect(self):
        from super import agents as A
        a1 = A.create_agent(self.cfg, name="l1", role="worker",
                            tools=["read_file", "grep", "create_agent", "run_agent", "list_agents"],
                            groups=["files", "search", "agents"],
                            created_by="user")
        child1, eff1 = A.make_child_cfg(self.cfg, a1)
        self.assertEqual(eff1["depth"], 1)
        self.assertEqual(set(eff1["tools"]), {"read_file", "grep", "create_agent", "run_agent", "list_agents"})

        a2 = A.create_agent(
            child1, name="l2", role="worker",
            tools=["read_file", "write_file", "grep"],  # write_file not in parent allowlist
            groups=["files", "search", "shell"],  # shell not in parent
            created_by="agent:" + a1["id"],
        )
        # persisted tools intersected at create time by handle_*; create_agent raw doesn't
        # intersect — runtime inherit does:
        child2, eff2 = A.make_child_cfg(child1, a2)
        self.assertEqual(eff2["depth"], 2)
        self.assertNotIn("write_file", eff2["tools"] or [])
        self.assertNotIn("shell", eff2["groups"])
        self.assertIn("read_file", eff2["tools"])

    def test_handle_create_intersects_parent(self):
        from super import agents as A
        a1 = A.create_agent(self.cfg, name="l1", role="worker",
                            tools=["read_file", "grep"],
                            groups=["files", "search", "agents"],
                            created_by="user")
        child1, _ = A.make_child_cfg(self.cfg, a1)
        res = A.handle_create_agent(child1, {
            "name": "l2",
            "role": "worker",
            "tools": ["read_file", "write_file", "run_command"],
            "groups": ["files", "shell"],
        })
        self.assertTrue(res.ok)
        import json
        body = json.loads(res.content)
        self.assertEqual(set(body["agent"]["tools"]), {"read_file"})
        self.assertEqual(set(body["agent"]["groups"]), {"files"})

    def test_run_specialized_emits_span(self):
        from super import agents as A

        spec = A.create_agent(self.cfg, name="echo", role="worker",
                              groups=["files"], created_by="user")
        self.cfg["_session_id"] = "sess_test_1"
        emitted: list = []
        self.cfg["_emit"] = lambda ev: emitted.append(ev)

        def fake_chat(cfg, messages, tools=None):
            return {"role": "assistant", "content": "child ok"}, {
                "source": "provider", "prompt_tokens": 10, "completion_tokens": 2,
            }

        with patch("super.llm.chat_message", side_effect=fake_chat):
            out = A.run_specialized(self.cfg, spec["id"], "say hi")
        self.assertTrue(out["ok"])
        self.assertEqual(out["reply"], "child ok")
        self.assertTrue(out["span_id"])
        events = __import__("super.store", fromlist=["read_jsonl"]).read_jsonl(
            f"{self.cfg['state_dir']}/agent.events.jsonl"
        )
        kinds = [e.get("kind") for e in events]
        self.assertIn("span.start", kinds)
        self.assertIn("span.end", kinds)

        spans = A.list_spans(self.cfg, session_id="sess_test_1")
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["status"], "done")
        self.assertEqual(spans[0]["agent_name"], "echo")
        self.assertIn("done", spans[0]["summary"])
        by = A.spans_by_session(self.cfg)
        self.assertIn("sess_test_1", by)
        self.assertTrue(any(e.get("child_agent", {}).get("status") == "running" for e in emitted))
        self.assertTrue(any(e.get("child_agent", {}).get("status") == "done" for e in emitted))

    def test_oneliner(self):
        from super import agents as A
        self.assertEqual(A.oneliner("r", "running", tool="grep"), "r: grep…")
        self.assertIn("done", A.oneliner("r", "done", steps=3))
        self.assertIn("failed", A.oneliner("r", "error", error="boom"))


if __name__ == "__main__":
    unittest.main()
