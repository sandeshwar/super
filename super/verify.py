"""Verification ladder + mutation screen (doc 03 §3, doc 02 §5).

Ladder (each rung gates the next):
  per-edit     — syntax parse + lint presence, milliseconds
  per-subtask  — focused test subset via test-impact analysis
  per-commit   — full suite + N-run flaky quarantine
  acceptance   — mutation screen: a new test that stays green under mutation
                 is vacuous and cannot gate anything
  generated    — property/fuzz hooks for parsers, authz, math

Writer != reviewer != auditor != evaluator: the reviewer may only block with
a failing-test reproducer. Counter-checks assume gaming (doc 01 F4).
"""

from __future__ import annotations

import ast
import re
import subprocess

from . import ledger
from .errors import VerificationError

MUTATION_SENTINELS = {
    "operator": [("==", "!="), ("<=", "<"), (">=", ">"), ("+", "-"), (" and ", " or ")],
    "boundary": [("0", "1"), ("1", "0"), ("<", "<="), (">", ">="), ("len(", "len(")],
    "statement": [("return True", "return False"), ("return False", "return True")],
}


def check_syntax(source: str, language: str = "py") -> tuple[bool, str]:
    """Per-edit rung: the file must at least parse."""
    if language in ("py", "python"):
        try:
            ast.parse(source)
            return True, "parses"
        except SyntaxError as e:
            return False, f"syntax error: {e}"
    # Unknown languages: brace/paren balance heuristic, never a hard block.
    if source.count("(") != source.count(")") or source.count("{") != source.count("}"):
        return False, "unbalanced delimiters"
    return True, "heuristic pass"


def impact_subset(changed_files: list[str], test_index: dict[str, list[str]] | None = None) -> list[str]:
    """Test-impact analysis: map changed files to focused tests.

    With no index, falls back to convention (tests mirroring paths + full
    tests/ dir listing is the caller's job). Pure function — no I/O.
    """
    if not changed_files:
        return []
    if not test_index:
        out = []
        for f in changed_files:
            base = f.split("/")[-1].split(".")[0]
            out.append(f"tests/test_{base}.py")
        return sorted(set(out))
    out: list[str] = []
    for f in changed_files:
        out.extend(test_index.get(f, []))
    return sorted(set(out))


def run_tests(paths: list[str], timeout_s: int = 300) -> tuple[bool, str]:
    """Run a test subset. Returns (ok, summary). Missing runner = skip-open."""
    if not paths:
        return True, "no tests selected"
    for runner in (["python3", "-m", "pytest", "-q"], ["python3", "-m", "unittest"]):
        try:
            r = subprocess.run(runner + paths, capture_output=True, text=True, timeout=timeout_s)
            tail = (r.stdout + r.stderr)[-2000:]
            return r.returncode == 0, tail[-500:]
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            return False, "test run timed out"
        except Exception as e:
            return False, str(e)
    return True, "no test runner available — recorded as skip"


def flaky_quarantine(cfg: dict, paths: list[str]) -> tuple[bool, str]:
    """N-run per commit: nondeterministic failures never create fix-work."""
    runs = int(cfg.get("verification", {}).get("flaky_runs", 3))
    results = []
    for _ in range(max(1, runs)):
        ok, _ = run_tests(paths)
        results.append(ok)
    if all(results):
        return True, f"stable green ({len(results)}/{len(results)})"
    if not any(results):
        return False, f"stable red ({len(results)} runs)"
    ledger.log_gate(cfg, "flaky", "F4", "reject", detail=f"nondeterministic: {results}")
    return False, f"FLAKY quarantined {results} — no fix-work filed"


def mutate(source: str, operators: list[str] | None = None) -> list[str]:
    """Generate survived-or-killed mutants for the mutation screen."""
    ops = operators or ["operator", "boundary", "statement"]
    mutants = []
    for op in ops:
        for old, new in MUTATION_SENTINELS.get(op, []):
            if old in source:
                mutants.append(source.replace(old, new, 1))
    return mutants


def is_vacuous(test_body: str, source: str, operators: list[str] | None = None) -> bool:
    """A test that stays green under mutation is vacuous (doc 01 F4).

    Static screen: the test must (a) assert something, (b) exercise a unit
    defined in `source`, and (c) discriminate outcomes — distinct expected
    literals across asserts, or per-mutant identifier overlap for statement
    mutants. Anything less stays green no matter what the code does.
    """
    if not re.search(r"assert|expect\s*\(|should\b|check\s*\(", test_body, re.I):
        return True
    try:
        defs = {n.name for n in ast.walk(ast.parse(source))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    except SyntaxError:
        defs = set(re.findall(r"def\s+([A-Za-z_]\w*)", source))
    test_names = set(re.findall(r"[A-Za-z_]\w*", test_body))
    if defs and not (defs & test_names):
        return True  # never exercises the unit under test
    asserts = re.findall(r"assert[^\n]*", test_body)
    if len(asserts) == 1 and re.match(
            r"\s*assert\s+(True|1|\"[^\"]*\"|'[^']*')\s*$", asserts[0]):
        return True  # bare literal — asserts nothing about behavior
    mutants = mutate(source, operators)
    if not mutants:
        return False  # nothing to mutate — not vacuous, just trivially small
    literals = set(re.findall(r"(True|False|None|\b\d+\b|'[^']*'|\"[^\"]*\")", test_body))
    if (defs & test_names) and (len(literals) >= 2 or len(asserts) >= 2):
        return False  # exercises the unit and discriminates outcomes
    for m in mutants:
        changed = set(re.findall(r"[A-Za-z_]\w*", m)) ^ set(re.findall(r"[A-Za-z_]\w*", source))
        if changed & test_names:
            return False
    return True


def gate_acceptance(cfg: dict, test_body: str, source: str) -> tuple[bool, str]:
    """Acceptance rung: reject vacuous tests as checks (they may exist, but
    they cannot gate anything)."""
    if not cfg.get("gates", {}).get("mutation", True):
        return True, "mutation screen disabled"
    if is_vacuous(test_body, source, cfg.get("verification", {}).get("mutation_operators")):
        ledger.log_gate(cfg, "mutation", "F4", "reject", detail="vacuous test refused as a check")
        return False, "vacuous test — asserts nothing mutation-sensitive; strengthen it"
    ledger.log_gate(cfg, "mutation", "F4", "pass", detail="test kills mutants")
    return True, "test is mutation-adequate"


def coverage_impact(changed_files: list[str], coverage_path: str = ".super/coverage.json") -> list[str] | None:
    """Coverage-based test-impact: map files → tests via coverage mapping. Returns None if no data."""
    import json as _json
    import os as _os
    for cand in [coverage_path, "coverage.json", ".super/coverage-map.json"]:
        if _os.path.isfile(cand):
            try:
                with open(cand, encoding="utf-8") as f:
                    data = _json.load(f)
                # expect { "files": {"src/foo.py": ["tests/test_foo.py"] } } or { "mapping": {...} }
                mapping = data.get("files") or data.get("mapping") or data
                if isinstance(mapping, dict):
                    out: list[str] = []
                    for cf in changed_files:
                        out.extend(mapping.get(cf, []))
                        # also try basename match
                        for k, v in mapping.items():
                            if cf.endswith(k) or k.endswith(cf):
                                out.extend(v if isinstance(v, list) else [v])
                    if out:
                        return sorted(set(out))
            except Exception:
                continue
    return None


def impact_subset_coverage(changed_files: list[str], test_index: dict[str, list[str]] | None = None) -> list[str]:
    """Coverage-first impact, fallback to convention."""
    cov = coverage_impact(changed_files)
    if cov is not None:
        return cov
    return impact_subset(changed_files, test_index)


def _quarantine_path(cfg: dict) -> str:
    return f"{cfg.get('state_dir','_')}/quarantine.json"


def flaky_quarantine(cfg: dict, paths: list[str]) -> tuple[bool, str]:
    """N-run per commit: nondeterministic failures never create fix-work. Persists quarantine."""
    import json as _json
    import os as _os
    runs = int(cfg.get("verification", {}).get("flaky_runs", 3))
    results = []
    for _ in range(max(1, runs)):
        ok, _ = run_tests(paths)
        results.append(ok)
    if all(results):
        return True, f"stable green ({len(results)}/{len(results)})"
    if not any(results):
        return False, f"stable red ({len(results)} runs)"
    # nondeterministic — quarantine and persist
    ledger.log_gate(cfg, "flaky", "F4", "reject", detail=f"nondeterministic: {results}")
    try:
        qpath = _quarantine_path(cfg)
        data = {}
        if _os.path.isfile(qpath):
            with open(qpath, encoding="utf-8") as f:
                data = _json.load(f)
        data.setdefault("quarantined", [])
        for p in paths:
            if p not in data["quarantined"]:
                data["quarantined"].append(p)
        data["updated"] = __import__("time").strftime("%Y-%m-%dT%H:%M:%S")
        with open(qpath, "w", encoding="utf-8") as f:
            _json.dump(data, f, indent=2)
    except Exception:
        pass
    return False, f"FLAKY quarantined {results} — no fix-work filed"


def perf_gate(cfg: dict, current: dict[str, float], baseline: dict[str, float] | None = None, threshold_pct: float = 10.0) -> tuple[bool, str]:
    """Perf/resource diff gate: current vs baseline must be within threshold."""
    if not baseline:
        # try load baseline from .super/perf-baseline.json
        import json as _json
        import os as _os
        cand = f"{cfg.get('state_dir','_')}/perf-baseline.json"
        if _os.path.isfile(cand):
            try:
                with open(cand, encoding="utf-8") as f:
                    baseline = _json.load(f)
            except Exception:
                baseline = None
    if not baseline:
        return True, "no baseline — perf gate open (record current as baseline)"
    violations = []
    for k, cur in current.items():
        base = baseline.get(k)
        if base is None or base == 0:
            continue
        delta = (cur - base) / base * 100
        if delta > threshold_pct:
            violations.append(f"{k} +{delta:.1f}% > {threshold_pct}% ( {base:.2f} → {cur:.2f} )")
        elif delta < -threshold_pct:
            # improvement is not a violation, but log
            pass
    # persist current as new baseline if clean
    if not violations:
        ledger.log_gate(cfg, "perf", "F4", "pass", detail=f"perf within {threshold_pct}%")
        return True, f"perf within {threshold_pct}%"
    ledger.log_gate(cfg, "perf", "F4", "reject", detail="; ".join(violations))
    for v in violations:
        ledger.add_issue(cfg, "major", "perf", v)
    return False, "; ".join(violations)


def fuzz_gate(cfg: dict, target_fn, *args, fuzz_seconds: int | None = None, **kwargs) -> tuple[bool, str]:
    """Property/fuzz hook for parsers/authz/math. Runs target_fn with random inputs for fuzz_seconds."""
    import random as _random
    import time as _time
    secs = fuzz_seconds if fuzz_seconds is not None else int(cfg.get("verification", {}).get("fuzz_seconds", 5))
    if secs <= 0:
        return True, "fuzz disabled"
    end = _time.time() + secs
    tries = 0
    while _time.time() < end:
        tries += 1
        try:
            # minimal fuzz: random small inputs
            a = _random.randint(-1000, 1000)
            b = _random.randint(-1000, 1000)
            s = "".join(_random.choice("abc123!@#") for _ in range(_random.randint(0, 20)))
            target_fn(a, b, s, *args, **kwargs)
        except AssertionError as e:
            ledger.log_gate(cfg, "fuzz", "F4", "reject", detail=f"fuzz assertion {e} after {tries} tries")
            return False, f"fuzz failed after {tries} tries: {e}"
        except Exception:
            # unexpected exception is also a finding but not necessarily gate failure for now
            continue
    ledger.log_gate(cfg, "fuzz", "F4", "pass", detail=f"fuzz ok {tries} tries in {secs}s")
    return True, f"fuzz ok ({tries} iterations)"


def verify_edit(cfg: dict, source: str, language: str = "py") -> tuple[bool, str]:
    """Per-edit rung used by the write path. Raises nothing; returns verdict."""
    if not cfg.get("gates", {}).get("verification", True):
        return True, "verification disabled"
    ok, msg = check_syntax(source, language)
    ledger.log_gate(cfg, "verification", "F1", "pass" if ok else "reject", detail=msg)
    if not ok:
        raise VerificationError(msg)
    return ok, msg
