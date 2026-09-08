"""E2E: child_agent SSE frames + session-scoped spans via run_agent_stream."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from tests import make_cfg


class TestChildAgentMonitor(unittest.TestCase):
    def setUp(self):
        self.cfg, self.root = make_cfg()
        self.cfg.setdefault("tools", {})["enabled"] = True
        self.cfg["tools"]["discovery"] = True
        self.cfg["tools"]["runtime"] = "stdlib"
        self.cfg["tools"]["groups"] = {
            "files": True, "search": True, "shell": True, "git": True,
            "web": True, "memory": True, "project": True, "agents": True,
        }
        self.cfg["agents"] = {
            "enabled": True, "max_depth": 3, "max_agents": 50,
            "allow_agent_create_roles": ["worker", "planner"],
        }
        self.cfg["envelope"] = {"max_tool_steps": 8}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def test_stream_emits_child_agent_and_session_spans(self):
        from super import agents as A
        from super import sessions
        from super.tools.runtime import run_agent_stream

        spec = A.create_agent(
            self.cfg, name="repo-reader", role="worker",
            summary="reads files", groups=["files", "search"],
            created_by="user",
        )
        sid = sessions.create(self.cfg, title="monitor-test")
        run_cfg = dict(self.cfg)
        run_cfg["_session_id"] = sid
        run_cfg["_agent"] = {"id": "main", "run_id": "runtest01"}

        # Turn 0: main calls run_agent. Turn 1+: child replies / main finishes.
        state = {"n": 0}

        def fake_stream(cfg, messages, tools=None):
            state["n"] += 1
            # Child agent cfg has _agent.id == specialist id
            ag = (cfg.get("_agent") or {})
            if ag.get("id") and ag.get("id") != "main":
                yield {"delta": "child says hi"}
                yield {"message": {"role": "assistant", "content": "child says hi"}}
                yield {"usage": {"source": "provider", "completion_tokens": 3}}
                return
            if state["n"] == 1:
                tcs = [{
                    "id": "call_run",
                    "type": "function",
                    "function": {
                        "name": "run_agent",
                        "arguments": json.dumps({"id": spec["id"], "goal": "summarize repo root"}),
                    },
                }]
                yield {"tool_calls": tcs}
                yield {"message": {"role": "assistant", "content": "", "tool_calls": tcs}}
                yield {"usage": {"source": "provider", "prompt_tokens": 20}}
                return
            yield {"delta": "Parent wrapped the child."}
            yield {"message": {"role": "assistant", "content": "Parent wrapped the child."}}
            yield {"usage": {"source": "provider", "completion_tokens": 5}}

        def fake_chat(cfg, messages, tools=None):
            # Fallback path if stream raises — shouldn't be needed
            ag = (cfg.get("_agent") or {})
            if ag.get("id") and ag.get("id") != "main":
                return {"role": "assistant", "content": "child says hi"}, {"source": "provider"}
            return {"role": "assistant", "content": "Parent wrapped the child."}, {"source": "provider"}

        messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "use the specialist"},
        ]
        events = []
        with patch("super.llm.chat_stream", side_effect=fake_stream), \
             patch("super.llm.chat_message", side_effect=fake_chat):
            for ev in run_agent_stream(run_cfg, messages):
                events.append(ev)

        child_frames = [e["child_agent"] for e in events if isinstance(e.get("child_agent"), dict)]
        self.assertGreaterEqual(len(child_frames), 2, f"expected live child frames, got {events!r}")
        statuses = [c.get("status") for c in child_frames]
        self.assertIn("running", statuses)
        self.assertIn("done", statuses)
        self.assertTrue(any("repo-reader" in (c.get("summary") or "") for c in child_frames))

        spans = A.list_spans(self.cfg, session_id=sid)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["status"], "done")
        self.assertEqual(spans[0]["agent_name"], "repo-reader")
        self.assertTrue(spans[0].get("child_session_id"), "child transcript session missing")
        child = sessions.get(self.cfg, spans[0]["child_session_id"])
        self.assertIsNotNone(child)
        self.assertEqual(child.get("parent"), sid)
        self.assertGreaterEqual(len(child.get("messages") or []), 2)
        by = A.spans_by_session(self.cfg)
        self.assertIn(sid, by)
        self.assertEqual(by[sid][0]["agent_name"], "repo-reader")
        self.assertTrue(by[sid][0].get("child_session_id"))

        listed = sessions.list_all(self.cfg)
        row = next(s for s in listed if s["id"] == sid)
        self.assertTrue(row.get("spans"))
        self.assertEqual(row["spans"][0]["child_session_id"], spans[0]["child_session_id"])
        # Child sessions stay nested — not top-level list items
        self.assertFalse(any(s["id"] == spans[0]["child_session_id"] for s in listed))

        self.assertTrue(any(c.get("child_session_id") for c in child_frames))


if __name__ == "__main__":
    unittest.main()
