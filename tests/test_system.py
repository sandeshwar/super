"""System tests: memory, trust, ambition, sandbox, meta, harness, server, config token."""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import make_cfg  # noqa: E402


class TestMemory(unittest.TestCase):
    def test_remember_compile_supersede(self):
        from super import memory as M

        cfg, root = make_cfg()
        try:
            M.remember(cfg, "repo uses ruff", source="human", verification="verified")
            ctx = M.compile_context(cfg, {"id": "1"})
            self.assertIn("ruff", ctx)
            M.supersede(cfg, 0, "repo uses oxlint now")
            ctx2 = M.compile_context(cfg, {"id": "1"})
            self.assertNotIn("ruff", ctx2)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestTrust(unittest.TestCase):
    def test_routing(self):
        from super import trust as T

        cfg, root = make_cfg()
        try:
            d, r, _ = T.route(cfg, ["src/auth/login.py"], 50, proven_record=True)
            self.assertEqual(d, "human-required")
            self.assertGreaterEqual(r, 3)
            d2, _, _ = T.route(cfg, ["docs/readme.md"], 5, proven_record=True)
            self.assertEqual(d2, "auto-pass")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_fatigue_flags_rubber_stamp(self):
        from super import trust as T

        cfg, root = make_cfg()
        try:
            for _ in range(6):
                T.record_approval(cfg, "approve", True)
            self.assertIn("approve", T.fatigue(cfg)["fatigued"])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestAmbition(unittest.TestCase):
    def test_contract_done_gate(self):
        from super import ambition as A

        cfg, root = make_cfg()
        try:
            c = A.compile_contract(cfg, "build a login page", domain="software")
            self.assertEqual(c["target_loa"], 4)
            ok, blockers, _ = A.done_state(cfg, c)
            self.assertFalse(ok)
            self.assertTrue(blockers)
            critics = [{a: 4.0 for a in c["axes"]} for _ in range(3)]
            A.record_scores(cfg, c, {a: (4.0, "exemplar-matched") for a in c["axes"]})
            med = A.ensemble(critics)
            self.assertTrue(all(v == 4.0 for v in med.values()))
            ok, _, scorecard = A.done_state(cfg, c)
            self.assertTrue(ok)
            self.assertIn("axes", scorecard)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_builder_cannot_downgrade(self):
        from super import ambition as A
        from super.errors import AmbitionError

        cfg, root = make_cfg()
        try:
            c = A.compile_contract(cfg, "x", domain="general")
            axis = next(iter(c["axes"]))
            with self.assertRaises(AmbitionError):
                A.downgrade(c, axis, 2, "feels hard", user_keyed=False)
            A.downgrade(c, axis, 2, "budget exhausted at 40 render-min", user_keyed=True)
            self.assertEqual(c["axes"][axis]["target"], 2)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestSandbox(unittest.TestCase):
    def test_probe_and_diff(self):
        from super import sandbox as S

        p = S.probe()
        self.assertIn("python", p)
        d = S.diff_of("a\n", "b\n", path="f.py")
        self.assertIn("b/f.py", d)


class TestMeta(unittest.TestCase):
    def test_corpus_and_descent(self):
        from super import meta

        cfg, root = make_cfg()
        try:
            meta.record_failure(cfg, "s1", "F1", {"grounding": "step 3"})
            m = meta.catch_matrix(cfg)
            self.assertEqual(m["n_failures"], 1)
            self.assertEqual(m["would_catch"]["grounding"], 1)
            prop = meta.evaluate_gate_proposal(cfg, "grounding")
            self.assertIn(prop["verdict"], ("ship", "needs-evidence"))
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestHarness(unittest.TestCase):
    def test_extract_and_check(self):
        from super import harness as H

        cfg, root = make_cfg()
        try:
            syms = H.extract_symbols("See `os.path` and x.y.z in docs/a.py")
            self.assertIn("os.path", syms)
            gate = H.check_reply(cfg, "hello world, no symbols here... maybe")
            self.assertTrue(gate["ok"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_answer_with_stub_llm(self):
        from super import harness as H
        from super import llm, sessions

        cfg, root = make_cfg()
        try:
            # Force non-agent path so the stubbed llm.chat is used.
            cfg.setdefault("tools", {})["enabled"] = False
            llm.chat = lambda cfg, messages: "done, see `os`"
            sid = sessions.create(cfg, "t")
            reply, gate = H.answer(cfg, sid, "hi")
            self.assertIn("os", reply)
            self.assertIn("checked", gate)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestServer(unittest.TestCase):
    def _serve(self, cfg):
        import super.server as SV

        SV.CFG = cfg
        from http.server import ThreadingHTTPServer

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), SV.Handler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        return httpd

    def _get(self, base, path, token="test-token"):
        req = urllib.request.Request(f"{base}{path}",
                                     headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())

    def test_health_tree_report_metrics(self):
        import super.server as SV  # noqa: F401

        cfg, root = make_cfg()
        try:
            httpd = self._serve(cfg)
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            try:
                # health is public
                with urllib.request.urlopen(f"{base}/api/health", timeout=5) as r:
                    self.assertEqual(r.status, 200)
                # open local API — no auth
                for path in ("/api/tree", "/api/ledger", "/api/report", "/api/metrics"):
                    code, body = self._get(base, path, token="")
                    self.assertEqual(code, 200)
                    self.assertIsInstance(body, dict)
                # no token still works
                with urllib.request.urlopen(f"{base}/api/tree", timeout=5) as r:
                    self.assertEqual(r.status, 200)
            finally:
                httpd.shutdown()
                httpd.server_close()
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
