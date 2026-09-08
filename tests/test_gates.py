"""Gate and enforcement tests: grounding, contract, verify, quality, security."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import make_cfg  # noqa: E402


class TestGrounding(unittest.TestCase):
    def test_observed_symbol_passes(self):
        from super import gates

        cfg, root = make_cfg()
        try:
            probe = os.path.join(root, "probe_marker_ABC123.py")
            with open(probe, "w") as f:
                f.write("def probe_marker_ABC123(): pass\n")
            ok, missing = gates.check(cfg, ["probe_marker_ABC123"])
            self.assertTrue(ok)
            self.assertEqual(missing, [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_unobserved_rejected_and_logged(self):
        from super import gates, ledger

        cfg, root = make_cfg()
        try:
            ok, missing = gates.check(cfg, ["SomeMadeUpSymbolXYZ"])
            self.assertFalse(ok)
            self.assertIn("SomeMadeUpSymbolXYZ", missing)
            self.assertEqual(ledger.gate_stats(cfg)["grounding"]["reject"], 1)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_write_gates_block_secrets(self):
        from super import gates

        cfg, root = make_cfg()
        try:
            ok, blockers = gates.run_write_gates(cfg, "x = 'sk-abcdefghijklmnop123456'\n", where="a.py")
            self.assertFalse(ok)
            self.assertTrue(blockers)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestContract(unittest.TestCase):
    def test_duplicate_blocked_without_waiver(self):
        from super import contract

        cfg, root = make_cfg()
        try:
            src = "def add(a, b):\n    return a + b\n"
            ok, _ = contract.check_write(cfg, src, {"existing_add": src})
            self.assertFalse(ok)
            ok2, _ = contract.check_write(cfg, src, {"existing_add": src}, waiver="test double")
            self.assertTrue(ok2)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_similarity_bounds(self):
        from super import contract

        self.assertEqual(contract.similarity("", "x"), 0.0)
        self.assertGreater(contract.similarity("def f(a): return a+1", "def f(a): return a+1"), 0.9)


class TestVerify(unittest.TestCase):
    def test_syntax_gate(self):
        from super import verify as V

        ok, _ = V.check_syntax("def f():\n    return 1\n")
        self.assertTrue(ok)
        ok, _ = V.check_syntax("def f(:\n")
        self.assertFalse(ok)

    def test_vacuous_refused(self):
        from super import verify as V

        cfg, root = make_cfg()
        try:
            ok, _ = V.gate_acceptance(cfg, "def test_x():\n    assert True\n", "def f(a, b):\n    return a == b\n")
            self.assertFalse(ok)
            ok, _ = V.gate_acceptance(
                cfg,
                "def test_eq():\n    assert f(1, 1) == True\n    assert f(1, 2) == False\n",
                "def f(a, b):\n    return a == b\n",
            )
            self.assertTrue(ok)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_impact_subset(self):
        from super import verify as V

        self.assertEqual(V.impact_subset(["src/auth.py"]), ["tests/test_auth.py"])
        self.assertEqual(V.impact_subset([]), [])


class TestQuality(unittest.TestCase):
    def test_budgets(self):
        from super import quality as Q

        cfg, root = make_cfg()
        try:
            ok, _ = Q.check_budgets(cfg, "x = 1\n")
            self.assertTrue(ok)
            big = "\n".join(f"x{i} = {i}" for i in range(500))
            ok, violations = Q.check_budgets(cfg, big, path="big.py")
            self.assertFalse(ok)
            self.assertTrue(violations)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestSecurity(unittest.TestCase):
    def test_secrets(self):
        from super import security as sec

        self.assertTrue(sec.scan_secrets("x = 1\n") == [])
        self.assertTrue(len(sec.scan_secrets("key = 'sk-abcdefghijklmnop'")) == 1)

    def test_sast(self):
        from super import security as sec

        self.assertIn("code-injection: eval()", " ".join(sec.sast_scan("eval(user_input)")))
        self.assertEqual(sec.sast_scan("def f():\n    return 1\n"), [])

    def test_dependency(self):
        from super import security as sec

        cfg, root = make_cfg()
        try:
            ok, _ = sec.gate_dependency(cfg, "requests", "")
            self.assertFalse(ok)
            # requests 2.20.0 has known CVEs (offline VULN_DB + live OSV agree)
            ok, msg = sec.gate_dependency(cfg, "requests", "2.20.0", "Apache-2.0")
            self.assertFalse(ok)
            self.assertIn("update required", msg)
            # clean pin passes (no VULN_DB entry, no OSV vulns for fastapi 0.115.6)
            ok, _ = sec.gate_dependency(cfg, "fastapi", "0.115.6", "MIT")
            self.assertTrue(ok)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_taint_authority(self):
        from super import security as sec

        ok, _ = sec.check_authority("local-exec", ["local-exec"])
        self.assertTrue(ok)
        ok, _ = sec.check_authority("local-exec", ["untrusted"])
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
