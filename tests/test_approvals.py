"""Approvals: chat-first pending extraction."""

from __future__ import annotations

import unittest

from super.approvals import from_tool_result


class ApprovalParseTests(unittest.TestCase):
    def test_pending_agent(self) -> None:
        ap = from_tool_result(
            "create_agent",
            '{"agent": {"id": "a1", "name": "Judge", "role": "reviewer", "status": "pending"}}',
        )
        self.assertIsNotNone(ap)
        assert ap is not None
        self.assertEqual(ap["kind"], "agent")
        self.assertEqual(ap["id"], "a1")
        self.assertEqual(ap["status"], "pending")

    def test_active_agent_ignored(self) -> None:
        self.assertIsNone(from_tool_result(
            "create_agent",
            '{"agent": {"id": "a1", "name": "Worker", "role": "worker", "status": "active"}}',
        ))

    def test_pending_capability(self) -> None:
        ap = from_tool_result(
            "propose_capability",
            '{"capability": {"id": "c1", "name": "fetch_x", "kind": "http", "risk": "high", "status": "pending", "summary": "hit X"}}',
        )
        self.assertIsNotNone(ap)
        assert ap is not None
        self.assertEqual(ap["kind"], "capability")
        self.assertEqual(ap["title"], "fetch_x")

    def test_memory_claim(self) -> None:
        ap = from_tool_result(
            "memory_add",
            '{"claim": {"id": 9, "text": "uses FastAPI", "verification": "unverified", "source": "agent"}}',
        )
        self.assertIsNotNone(ap)
        assert ap is not None
        self.assertEqual(ap["kind"], "memory")
        self.assertEqual(ap["id"], 9)

    def test_bad_json(self) -> None:
        self.assertIsNone(from_tool_result("create_agent", "not json"))
        self.assertIsNone(from_tool_result("create_agent", None))


if __name__ == "__main__":
    unittest.main()
