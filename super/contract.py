"""Contract compiler (doc 03 §2): repo standards as machine-enforced rules.

On session start the harness compiles lockfile versions, lint/formatter
configs, and AGENTS.md/CONTRIBUTING.md guidance into a rule set that the
write path enforces. Duplication is blocked by AST-normalized similarity:
a near-duplicate helper is refused and the existing symbol returned, unless
the author files an explicit waiver (adapters, wrappers, test doubles).
"""

from __future__ import annotations

import ast
import difflib
import os
import re
from typing import Any

DUPLICATE_THRESHOLD = 0.82


def compile_contract(root: str) -> dict:
    """Collect machine-checkable repo rules. Never raises — unknown files
    simply yield fewer rules."""
    rules: dict[str, Any] = {
        "root": root,
        "lockfiles": {},
        "lint": {},
        "guidelines": [],
        "symbols": {},
    }
    for name in ("package-lock.json", "Cargo.lock", "go.mod", "requirements.lock",
                 "poetry.lock", "uv.lock", "Gemfile.lock"):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            try:
                rules["lockfiles"][name] = os.path.getmtime(p)
            except OSError:
                pass
    for name in (".oxlintrc.json", ".eslintrc.json", "pyproject.toml", "setup.cfg",
                 ".flake8", "ruff.toml", ".golangci.yml"):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            rules["lint"][name] = True
    for name in ("AGENTS.md", "CONTRIBUTING.md"):
        p = os.path.join(root, name)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    text = f.read(20000)
                bullets = [l.strip("- *\t ") for l in text.splitlines()
                           if l.strip().startswith(("-", "*", "1", "2", "3"))]
                rules["guidelines"].extend(b[:300] for b in bullets[:30])
            except OSError:
                pass
    return rules


def _normalize_py(source: str) -> str:
    """Parse and re-emit identifiers-normalized form for similarity compare."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return re.sub(r"\s+", " ", source).strip()
    names: dict[str, str] = {}
    counter = [0]

    class Renamer(ast.NodeTransformer):
        def visit_Name(self, node: ast.Name):  # noqa: N802
            if node.id not in names:
                names[node.id] = f"v{counter[0]}"
                counter[0] += 1
            node.id = names[node.id]
            return node

        def visit_arg(self, node: ast.arg):  # noqa: N802
            if node.arg not in names:
                names[node.arg] = f"v{counter[0]}"
                counter[0] += 1
            node.arg = names[node.arg]
            return node

    try:
        tree = Renamer().visit(tree)
        return ast.dump(tree)
    except Exception:
        return re.sub(r"\s+", " ", source).strip()


def similarity(a: str, b: str) -> float:
    """AST-normalized similarity in [0, 1]."""
    if not a.strip() or not b.strip():
        return 0.0
    return difflib.SequenceMatcher(None, _normalize_py(a), _normalize_py(b)).ratio()


def find_duplicate(candidate: str, existing: dict[str, str],
                   threshold: float = DUPLICATE_THRESHOLD) -> tuple[str | None, float]:
    """Return (name, score) of the most similar existing snippet, or (None, best)."""
    best, best_name = 0.0, None
    for name, src in existing.items():
        s = similarity(candidate, src)
        if s > best:
            best, best_name = s, name
    if best >= threshold:
        return best_name, best
    return None, best


def check_write(cfg: dict, candidate: str, existing: dict[str, str],
                waiver: str = "") -> tuple[bool, str]:
    """Enforce standards + duplication at write time.

    Returns (ok, message). Duplicates require a one-line waiver, which the
    caller must file to the ledger for reviewer visibility.
    """
    from . import ledger

    if not cfg.get("gates", {}).get("standards", True):
        pass
    else:
        if len(candidate.splitlines()) > cfg.get("quality", {}).get("max_loc_per_edit", 300):
            return False, "edit exceeds max_loc_per_edit budget — split the edit"
    if cfg.get("gates", {}).get("duplication", True):
        dup, score = find_duplicate(candidate, existing)
        if dup and not waiver:
            ledger.log_gate(cfg, "duplication", "F1", "reject",
                            detail=f"near-duplicate of {dup} ({score:.2f}); file a waiver or reuse it")
            return False, f"near-duplicate of {dup} ({score:.2f}) — reuse it or file a waiver"
    ledger.log_gate(cfg, "contract", "F1", "pass", detail="standards+duplication clear")
    return True, "contract clear"
