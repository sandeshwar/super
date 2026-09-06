"""Quality budgets + debt ledger (doc 03 §5).

Per-edit LOC / complexity / nesting budgets catch bloat at line 300, not
line 2000. Repairs are differential (transform verified code, never wholesale
rewrites). Every violation files a persistent ledger entry with severity and
expiry; done-state is blocked on open criticals; waivers expire and escalate
— there is no permanent bypass. Reviewer checklists are mined from the
repo's own history, not generic style advice.
"""

from __future__ import annotations

import ast
import re

from . import ledger

SEVERITY_ORDER = {"minor": 0, "major": 1, "critical": 2}


def loc(source: str) -> int:
    return sum(1 for l in source.splitlines() if l.strip())


def complexity(source: str) -> int:
    """Cyclomatic approximation: branch keywords + boolean operators + 1."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 999
    score = 1
    for node in ast.walk(tree):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                             ast.With, ast.Assert, ast.BoolOp, ast.IfExp,
                             ast.comprehension)):
            score += 1
        elif isinstance(node, ast.Match):
            score += len(node.cases)
    return score


def max_nesting(source: str) -> int:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 999

    def depth(node, cur: int) -> int:
        kids = list(ast.iter_child_nodes(node))
        deep = [depth(k, cur + 1) for k in kids
                if isinstance(k, (ast.If, ast.For, ast.While, ast.With,
                                  ast.FunctionDef, ast.ClassDef, ast.Try))]
        nested = [depth(k, cur) for k in kids
                  if not isinstance(k, (ast.If, ast.For, ast.While, ast.With,
                                        ast.FunctionDef, ast.ClassDef, ast.Try))]
        return max([cur] + deep + nested, default=cur)

    return depth(tree, 0)


def check_budgets(cfg: dict, source: str, path: str = "") -> tuple[bool, list[str]]:
    """Returns (ok, violations). Each violation is also filed to the ledger."""
    if not cfg.get("gates", {}).get("quality", True):
        return True, []
    q = cfg.get("quality", {})
    violations = []
    n_loc = loc(source)
    if n_loc > int(q.get("max_loc_per_edit", 300)):
        violations.append(f"{path or 'edit'}: {n_loc} LOC > budget {q.get('max_loc_per_edit')}")
    c = complexity(source)
    if c > int(q.get("max_complexity", 10)):
        violations.append(f"{path or 'edit'}: complexity {c} > budget {q.get('max_complexity')}")
    n = max_nesting(source)
    if n > int(q.get("max_nesting", 4)):
        violations.append(f"{path or 'edit'}: nesting {n} > budget {q.get('max_nesting')}")
    for v in violations:
        sev = "critical" if n_loc > 2 * int(q.get("max_loc_per_edit", 300)) else "major"
        ledger.add_issue(cfg, sev, "quality", v)
        ledger.log_gate(cfg, "quality", "F1", "reject", detail=v)
    if not violations:
        ledger.log_gate(cfg, "quality", "F1", "pass", detail=f"budgets ok ({n_loc} LOC)")
    return (not violations), violations


def mine_checklist(reviewer_notes: list[str], top_n: int = 10) -> list[str]:
    """Mine a reviewer checklist from the repo's own rejection history.

    Ranks recurring non-stopword terms in past rejections — maintainer
    signal, not generic style advice.
    """
    stop = {"the", "and", "this", "that", "with", "please", "should", "would",
            "could", "have", "from", "into", "also", "just", "than", "then"}
    freq: dict[str, int] = {}
    for note in reviewer_notes:
        for w in re.findall(r"[a-z][a-z\-]{3,}", note.lower()):
            if w not in stop:
                freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: -kv[1])
    return [f"check {w} ({c} past rejections)" for w, c in ranked[:top_n]]


def done_state(cfg: dict, extra_blockers: list[str] | None = None) -> tuple[bool, list[str]]:
    """Done-state gate: blocked on open criticals, waivers visible."""
    blockers = ledger.done_blocked(cfg) + list(extra_blockers or [])
    return (not blockers), blockers
