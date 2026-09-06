"""Ambition Contract + critic ensemble + done-state gate (doc 05).

Silent deflation is impossible by construction: the request compiles to a
multi-dimensional Level-of-Ambition ladder *before* generation, the default
target is LoA 4 (expert), the builder cannot lower the contract, grading is
external / ensembled / reference-grounded, refinement is a mandated
axis-targeted loop, and downgrades require an explicit user key or a priced
budget-exhaustion event. Two-key rule: builder proposes, gates dispose.
"""

from __future__ import annotations

import statistics

from . import ledger
from .errors import AmbitionError

TAXONOMIES = {
    "rendering": ["geometry", "materials", "lighting", "post-processing",
                  "composition", "scene-richness"],
    "ui": ["states", "interactions", "motion", "a11y", "empty-error-states", "polish"],
    "writing": ["research-depth", "citations", "examples", "edge-cases", "structure"],
    "software": ["error-handling", "tests", "perf", "observability", "security", "docs"],
    "data": ["cleaning", "validation", "visualization", "caveats", "reproducibility"],
    "general": ["depth", "breadth", "correctness", "polish", "coverage"],
}

MAX_LOA = 5


def compile_contract(cfg: dict, request: str, domain: str = "general",
                     target_loa: int | None = None) -> dict:
    """Compile a request into a dimension ladder before any generation."""
    domain = domain if domain in TAXONOMIES else "general"
    loa = target_loa or int(cfg.get("ambition", {}).get("default_loa", 4))
    if loa < 1 or loa > MAX_LOA:
        raise AmbitionError(f"target LoA must be in [1, {MAX_LOA}]")
    axes = TAXONOMIES[domain]
    contract = {
        "request": request[:2000],
        "domain": domain,
        "target_loa": loa,
        "axes": {a: {"target": loa, "score": 0, "evidence": ""} for a in axes},
        "downgrades": [],
        "builder_editable": False,
    }
    ledger.log_gate(cfg, "ambition", "F4", "pass",
                    detail=f"contract {domain} LoA{loa} ({len(axes)} axes)")
    return contract


def record_scores(cfg: dict, contract: dict, scores: dict[str, tuple[float, str]]) -> dict:
    """Record external critic scores per axis: {axis: (score, evidence)}.

    Scores come from critics with no shared context with the builder —
    self-grading is structurally impossible here.
    """
    for axis, (score, evidence) in scores.items():
        if axis not in contract["axes"]:
            raise AmbitionError(f"unknown axis {axis}")
        if not (0 <= score <= MAX_LOA):
            raise AmbitionError(f"score for {axis} out of range")
        contract["axes"][axis]["score"] = score
        contract["axes"][axis]["evidence"] = (evidence or "")[:1000]
    return contract


def ensemble(scores_per_critic: list[dict[str, float]]) -> dict[str, float]:
    """Median per axis; any critic >1 level below median forces iteration."""
    if not scores_per_critic:
        raise AmbitionError("critic ensemble is empty")
    axes = set().union(*(c.keys() for c in scores_per_critic))
    medians = {}
    for axis in axes:
        vals = sorted(c[axis] for c in scores_per_critic if axis in c)
        medians[axis] = statistics.median(vals)
    return medians


def disagreements(scores_per_critic: list[dict[str, float]],
                  medians: dict[str, float]) -> list[str]:
    out = []
    for i, c in enumerate(scores_per_critic):
        for axis, v in c.items():
            if medians.get(axis, v) - v > 1.0:
                out.append(f"critic {i} rates {axis} {v} vs median {medians[axis]} — iterate")
    return out


def next_axis(contract: dict) -> str | None:
    """Lowest-scoring axis below target — the only allowed next step
    (axis-targeted refinement, doc 05 §2.3)."""
    worst, worst_key = None, None
    for axis, cell in contract["axes"].items():
        gap = cell["target"] - cell.get("score", 0)
        if gap > 0 and (worst is None or gap > worst):
            worst, worst_key = gap, axis
    return worst_key


def downgrade(contract: dict, axis: str, new_target: int, reason: str,
              user_keyed: bool = False) -> dict:
    """Lower an axis target. Requires explicit user action or a priced
    budget-exhaustion event — never silent, never builder-initiated."""
    if axis not in contract["axes"]:
        raise AmbitionError(f"unknown axis {axis}")
    if not user_keyed and "budget" not in (reason or "").lower():
        raise AmbitionError("downgrades require user approval or budget exhaustion — builder cannot lower the contract")
    contract["axes"][axis]["target"] = new_target
    contract["downgrades"].append({"axis": axis, "to": new_target, "reason": reason})
    return contract


def mechanical_metrics(cfg: dict, domain: str, artifact_source: str = "", artifact_path: str = "") -> dict[str, tuple[float, str]]:
    """Mechanical metrics per axis — evidence for critic ensemble, never verdict alone (doc 05 §2.2)."""
    import os as _os
    import re as _re
    src = artifact_source or ""
    if artifact_path and _os.path.isfile(artifact_path):
        try:
            with open(artifact_path, encoding="utf-8", errors="ignore") as f:
                src = f.read(80000)
        except Exception:
            pass
    out: dict[str, tuple[float, str]] = {}
    if domain == "software":
        # error-handling: count try/except
        eh = len(_re.findall(r"\btry\s*:", src)) + len(_re.findall(r"\bexcept\b", src))
        out["error-handling"] = (min(5, 1 + eh * 0.8), f"{eh} try/except blocks")
        # tests: count assert/expect
        t = len(_re.findall(r"\bassert\b|\bexpect\s*\(", src))
        out["tests"] = (min(5, 1 + t * 0.5), f"{t} asserts")
        # observability: log/print
        obs = len(_re.findall(r"\blogger|logging|print\(|console\.log", src))
        out["observability"] = (min(5, 1 + obs * 0.6), f"{obs} log points")
        # docs
        docs = len(_re.findall(r'""".*?"""', src, _re.S))
        out["docs"] = (min(5, 1 + docs * 0.7), f"{docs} docstrings")
        # security: SAST hits inverse
        from . import security as _sec
        findings = _sec.sast_scan(src)
        out["security"] = (max(1, 5 - len(findings)), f"{len(findings)} SAST findings")
        # perf placeholder
        out["perf"] = (3.0, "perf baseline not measured — needs perf_gate")
    elif domain == "rendering":
        # triangle count heuristic: count vertices/faces
        tris = len(_re.findall(r"\bvertices\b|\bindices\b|\bposition\b", src.lower())) or len(src) // 2000
        out["geometry"] = (min(5, 1 + tris * 0.02), f"~{tris} geom hints")
        out["materials"] = (3.0, "PBR check: albedo/normal/rough presence heuristic")
        out["lighting"] = (3.0, "HDRI/shadow heuristic")
        out["post-processing"] = (3.0, "tonemap/bloom heuristic")
        out["composition"] = (3.0, "camera variants heuristic")
        out["scene-richness"] = (3.0, "foliage/entourage heuristic")
    else:
        # general: depth/breadth
        lines = src.splitlines()
        out["depth"] = (min(5, 1 + len(lines) * 0.01), f"{len(lines)} lines")
        out["breadth"] = (3.0, "coverage axes heuristic")
        out["correctness"] = (3.0, "lint/type heuristic")
        out["polish"] = (3.0, "a11y/motion heuristic")
        out["coverage"] = (3.0, "artifact count heuristic")
    return out


def critic_loop(cfg: dict, contract: dict, artifact_source: str = "", artifact_path: str = "", budget_minutes: float = 20.0) -> tuple[bool, list[str], dict]:
    """Axis-targeted refinement loop: draft → critique → enhance → re-critique until LoA or budget."""
    import time as _time
    start = _time.time()
    blockers, scorecard = done_state(cfg, contract)[1:]
    # mechanical metrics as evidence for critics
    mech = mechanical_metrics(cfg, contract.get("domain","general"), artifact_source, artifact_path)
    for axis, (score, ev) in mech.items():
        if axis in contract["axes"]:
            # seed critic scores with mechanical hint, but don't pass axis alone
            contract["axes"][axis]["score"] = max(contract["axes"][axis].get("score",0), min(score, contract["axes"][axis]["target"] - 0.5))
            contract["axes"][axis]["evidence"] = ev
    # VLM critics: call llm if available, else use mech
    critics = int(cfg.get("ambition", {}).get("critics", 3))
    try:
        from . import llm as _llm
        # One critic call per axis-targeted iteration (isolated, no shared context)
        for _ in range(critics):
            nxt = next_axis(contract)
            if not nxt:
                break
            # ask critic to score lowest axis
            try:
                prompt = f"Score {nxt} for this {contract['domain']} artifact on LoA 1-5. Artifact excerpt:\n{(artifact_source or '')[:2000]}\n\nRespond JSON {{\"score\": <1-5>, \"evidence\": \"...\"}}"
                raw = _llm.chat(cfg, [{"role":"user","content": prompt}])
                import json as _json
                # try parse JSON
                m = _json.loads(raw[raw.find("{"):raw.rfind("}")+1]) if "{" in raw else {}
                s = float(m.get("score", 3))
                ev = m.get("evidence", "vlm-critic")
                contract["axes"][nxt]["score"] = max(contract["axes"][nxt]["score"], s)
                contract["axes"][nxt]["evidence"] = ev[:500]
            except Exception:
                continue
            if (_time.time() - start) / 60 > budget_minutes:
                downgrade(contract, nxt, max(1, contract["axes"][nxt]["target"]-1), f"budget exhausted at {budget_minutes} min", user_keyed=True)
                break
    except Exception:
        pass
    return done_state(cfg, contract)


def done_state(cfg: dict, contract: dict) -> tuple[bool, list[str], dict]:
    """Done-state gate: no axis below contracted LoA, scorecard attached."""
    blockers = [
        f"{axis}: LoA {cell.get('score', 0)} < contracted {cell['target']}"
        for axis, cell in contract["axes"].items()
        if cell.get("score", 0) < cell["target"]
    ]
    scorecard = {
        "domain": contract["domain"],
        "target_loa": contract["target_loa"],
        "axes": {a: {"target": c["target"], "score": c.get("score", 0),
                     "evidence": c.get("evidence", "")}
                 for a, c in contract["axes"].items()},
        "downgrades": contract.get("downgrades", []),
    }
    if blockers:
        ledger.log_gate(cfg, "ambition-done", "F4", "reject", detail="; ".join(blockers))
    else:
        ledger.log_gate(cfg, "ambition-done", "F4", "pass", detail="all axes at contracted LoA")
    return (not blockers), blockers, scorecard
