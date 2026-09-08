"""Chat run registry: disconnect ≠ cancel; cancel is explicit."""

from __future__ import annotations

import threading
import time
import unittest

from super import server


class ChatRunRegistryTests(unittest.TestCase):
    def tearDown(self) -> None:
        with server._CHAT_RUNS_LOCK:
            server._CHAT_RUNS.clear()

    def test_begin_end_active(self) -> None:
        ev = server._chat_run_begin("s1")
        self.assertTrue(server._chat_run_active("s1"))
        self.assertFalse(server._chat_run_active("s2"))
        server._chat_run_end("s1", ev)
        self.assertFalse(server._chat_run_active("s1"))

    def test_cancel_sets_event(self) -> None:
        ev = server._chat_run_begin("s1")
        self.assertTrue(server._chat_run_cancel("s1"))
        self.assertTrue(ev.is_set())
        self.assertFalse(server._chat_run_cancel("missing"))

    def test_newer_run_cancels_previous(self) -> None:
        first = server._chat_run_begin("s1")
        second = server._chat_run_begin("s1")
        self.assertTrue(first.is_set())
        self.assertFalse(second.is_set())
        self.assertTrue(server._chat_run_active("s1"))
        server._chat_run_end("s1", first)  # stale end must not clear newer
        self.assertTrue(server._chat_run_active("s1"))
        server._chat_run_end("s1", second)
        self.assertFalse(server._chat_run_active("s1"))

    def test_cancel_wakes_waiter(self) -> None:
        ev = server._chat_run_begin("s1")
        seen = []

        def waiter() -> None:
            self.assertTrue(ev.wait(timeout=2))
            seen.append(True)

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.05)
        server._chat_run_cancel("s1")
        t.join(timeout=2)
        self.assertEqual(seen, [True])


if __name__ == "__main__":
    unittest.main()
