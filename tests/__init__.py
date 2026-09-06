"""Core state tests: config, store, tasks, ledger, sessions."""
import json
import os
import shutil
import tempfile
import unittest


def make_cfg(**over):
    from super import config as C

    root = tempfile.mkdtemp(prefix="super-test-")
    state = os.path.join(root, ".super")
    cfg = json.loads(json.dumps(C.DEFAULTS))
    cfg["_config_path"] = None
    cfg["_root"] = root
    cfg["state_dir"] = state
    cfg["envelope"]["best_of_n"] = 1
    for k, v in over.items():
        cfg[k] = v
    os.makedirs(state, exist_ok=True)
    # Pre-seed token to avoid generation in tests.
    cfg["server"]["token"] = "test-token"
    with open(os.path.join(state, ".token"), "w") as f:
        f.write("test-token")
    return cfg, root


class TestConfig(unittest.TestCase):
    def test_load_defaults_from_empty_dir(self):
        from super import config as C

        d = tempfile.mkdtemp(prefix="super-cfg-")
        try:
            cfg = C.load(os.path.join(d, "super.config.json"))
            self.assertEqual(cfg["server"]["host"], "127.0.0.1")
            self.assertTrue(cfg["gates"]["grounding"])
            self.assertTrue(cfg["server"]["token"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_rejects_non_localhost(self):
        from super import config as C
        from super.errors import ConfigError

        d = tempfile.mkdtemp(prefix="super-cfg-")
        try:
            p = os.path.join(d, "super.config.json")
            bad = json.loads(json.dumps(C.DEFAULTS))
            bad["server"]["host"] = "0.0.0.0"
            with open(p, "w") as f:
                json.dump(bad, f)
            with self.assertRaises(ConfigError):
                C.load(p)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_env_overrides(self):
        from super import config as C

        d = tempfile.mkdtemp(prefix="super-cfg-")
        try:
            os.environ["SUPER_PORT"] = "4321"
            cfg = C.load(os.path.join(d, "nope.json"))
            self.assertEqual(cfg["server"]["port"], 4321)
        finally:
            os.environ.pop("SUPER_PORT", None)
            shutil.rmtree(d, ignore_errors=True)


class TestStore(unittest.TestCase):
    def test_atomic_roundtrip(self):
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


class TestTasks(unittest.TestCase):
    def test_lifecycle(self):
        from super import tasks

        cfg, root = make_cfg()
        try:
            a = tasks.add(cfg, "A", done="t green")
            b = tasks.add(cfg, "B", needs=[a])
            self.assertIsNotNone(tasks.leaf(cfg))
            self.assertEqual(tasks.leaf(cfg)["id"], a)
            tasks.prove(cfg, a, "tests/a.py green")
            self.assertEqual(tasks.leaf(cfg)["id"], b)
            tasks.prove(cfg, b, "tests/b.py green")
            self.assertIsNone(tasks.leaf(cfg))
            self.assertEqual(tasks.stats(cfg)["proven"], 2)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_validation(self):
        from super import tasks
        from super.errors import TaskValidation

        cfg, root = make_cfg()
        try:
            with self.assertRaises(TaskValidation):
                tasks.add(cfg, "  ")
            a = tasks.add(cfg, "A")
            with self.assertRaises(TaskValidation):
                tasks.add(cfg, "B", needs=["999"])
            with self.assertRaises(TaskValidation):
                tasks.prove(cfg, a, "  ")
            with self.assertRaises(TaskValidation):
                tasks.set_status(cfg, a, "nope")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rollback(self):
        from super import tasks

        cfg, root = make_cfg()
        try:
            a = tasks.add(cfg, "A")
            b = tasks.add(cfg, "B")
            tasks.prove(cfg, a, "p1")
            tasks.prove(cfg, b, "p2")
            reopened = tasks.rollback(cfg, a)
            self.assertEqual(set(reopened), {a, b})
        finally:
            shutil.rmtree(root, ignore_errors=True)


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
