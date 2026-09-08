"""Core state tests: config, store, ledger, sessions."""
import os
import shutil
import unittest

from tests import make_cfg


class TestConfig(unittest.TestCase):
    def test_load_defaults_from_empty_dir(self):
        from super import config as C

        d = __import__("tempfile").mkdtemp(prefix="super-cfg-")
        try:
            cfg = C.load(os.path.join(d, "super.config.json"))
            self.assertEqual(cfg["server"]["host"], "0.0.0.0")
            self.assertTrue(cfg["gates"]["grounding"])
            self.assertTrue(cfg["server"]["token"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_allows_lan_bind(self):
        import json
        import tempfile
        from super import config as C

        d = tempfile.mkdtemp(prefix="super-cfg-")
        try:
            p = os.path.join(d, "super.config.json")
            cfg = json.loads(json.dumps(C.DEFAULTS))
            cfg["server"]["host"] = "0.0.0.0"
            with open(p, "w") as f:
                json.dump(cfg, f)
            loaded = C.load(p)
            self.assertEqual(loaded["server"]["host"], "0.0.0.0")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_rejects_empty_host(self):
        import json
        import tempfile
        from super import config as C
        from super.errors import ConfigError

        d = tempfile.mkdtemp(prefix="super-cfg-")
        try:
            p = os.path.join(d, "super.config.json")
            bad = json.loads(json.dumps(C.DEFAULTS))
            bad["server"]["host"] = ""
            with open(p, "w") as f:
                json.dump(bad, f)
            with self.assertRaises(ConfigError):
                C.load(p)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_env_overrides(self):
        import tempfile
        from super import config as C

        d = tempfile.mkdtemp(prefix="super-cfg-")
        try:
            os.environ["SUPER_PORT"] = "4321"
            cfg = C.load(os.path.join(d, "nope.json"))
            self.assertEqual(cfg["server"]["port"], 4321)
        finally:
            os.environ.pop("SUPER_PORT", None)
            shutil.rmtree(d, ignore_errors=True)

    def test_legacy_keys_fill_when_new_absent(self):
        import json
        import tempfile
        from super import config as C

        d = tempfile.mkdtemp(prefix="super-cfg-")
        try:
            p = os.path.join(d, "super.config.json")
            with open(p, "w") as f:
                json.dump({
                    "envelope": {"max_steps_per_task": 77, "max_microtask_lines": 33},
                    "trust": {"attention_budget_per_task": 12},
                }, f)
            loaded = C.load(p)
            self.assertEqual(loaded["envelope"]["max_tool_steps"], 77)
            self.assertEqual(loaded["envelope"]["max_reply_lines"], 33)
            self.assertEqual(loaded["trust"]["attention_budget"], 12)
            self.assertNotIn("max_steps_per_task", loaded["envelope"])
            self.assertNotIn("max_microtask_lines", loaded["envelope"])
            self.assertNotIn("attention_budget_per_task", loaded["trust"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_new_keys_win_over_legacy_in_same_file(self):
        import json
        import tempfile
        from super import config as C

        d = tempfile.mkdtemp(prefix="super-cfg-")
        try:
            p = os.path.join(d, "super.config.json")
            with open(p, "w") as f:
                json.dump({
                    "envelope": {
                        "max_steps_per_task": 200,
                        "max_tool_steps": 42,
                        "max_microtask_lines": 99,
                        "max_reply_lines": 15,
                    },
                    "trust": {
                        "attention_budget_per_task": 99,
                        "attention_budget": 7,
                    },
                }, f)
            loaded = C.load(p)
            self.assertEqual(loaded["envelope"]["max_tool_steps"], 42)
            self.assertEqual(loaded["envelope"]["max_reply_lines"], 15)
            self.assertEqual(loaded["trust"]["attention_budget"], 7)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestStore(unittest.TestCase):
    def test_atomic_roundtrip(self):
        import tempfile
        from super import store

        d = tempfile.mkdtemp(prefix="super-store-")
        try:
            p = os.path.join(d, "x.json")
            store.save_json(p, {"a": [1, 2]})
            self.assertEqual(store.load_json(p, {}), {"a": [1, 2]})
            store.update_json(p, {}, lambda data: data.update({"b": 1}))
            self.assertEqual(store.load_json(p, {})["b"], 1)
            store.append_jsonl(p + "l", {"k": 1})
            self.assertEqual(store.read_jsonl(p + "l"), [{"k": 1, "ts": store.read_jsonl(p + "l")[0]["ts"]}])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_corrupt_quarantined(self):
        import tempfile
        from super import store
        from super.errors import StoreError

        d = tempfile.mkdtemp(prefix="super-store-")
        try:
            p = os.path.join(d, "x.json")
            with open(p, "w") as f:
                f.write("{not json")
            with self.assertRaises(StoreError):
                store.load_json(p, {})
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestLedger(unittest.TestCase):
    def test_pass_and_reject_counted(self):
        from super import ledger

        cfg, root = make_cfg()
        try:
            ledger.log_gate(cfg, "grounding", "F1", "pass", detail="x")
            ledger.log_gate(cfg, "grounding", "F1", "reject", detail="y")
            stats = ledger.gate_stats(cfg)
            self.assertEqual(stats["grounding"], {"pass": 1, "reject": 1})
            self.assertAlmostEqual(ledger.catch_rates(cfg)["grounding"], 0.5)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_criticals_block_done(self):
        from super import ledger
        from super import quality as Q

        cfg, root = make_cfg()
        try:
            ok, _ = Q.done_state(cfg)
            self.assertTrue(ok)
            ledger.add_issue(cfg, "critical", "security", "secret in diff")
            ok, blockers = Q.done_state(cfg)
            self.assertFalse(ok)
            self.assertTrue(blockers)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_resolve_clears_open_critical(self):
        from super import ledger
        from super import quality as Q

        cfg, root = make_cfg()
        try:
            ledger.add_issue(cfg, "critical", "security", "lodash@4.17.20 has known CVE")
            self.assertEqual(len(ledger.open_criticals(cfg)), 1)
            ledger.resolve_issue_text(cfg, "lodash@4.17.20 has known CVE", "upgraded")
            self.assertEqual(ledger.open_criticals(cfg), [])
            ok, _ = Q.done_state(cfg)
            self.assertTrue(ok)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_dependency_pass_reconciles_stale_critical(self):
        from super import ledger, security

        cfg, root = make_cfg()
        try:
            ledger.add_issue(
                cfg, "critical", "security",
                "lodash@4.17.20 has known CVE (fix ≥ 4.17.21) — update required",
            )
            ok, _ = security.gate_dependency(cfg, "lodash", "4.17.21")
            self.assertTrue(ok)
            self.assertEqual(ledger.open_criticals(cfg), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestSessions(unittest.TestCase):
    def test_roundtrip_and_limits(self):
        from super import sessions

        cfg, root = make_cfg()
        try:
            sid = sessions.create(cfg, "t")
            sessions.append(cfg, sid, "user", "hello")
            sessions.append(cfg, sid, "assistant", "hi", gate={"ok": True})
            self.assertEqual(len(sessions.history(cfg, sid)), 2)
            with self.assertRaises(KeyError):
                sessions.history(cfg, "nope")
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
