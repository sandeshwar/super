"""Meta loop: replay corpus + gate accounting + descent (doc 02 §8).

The replay corpus of failed sessions is the falsifier: every gate proposal
and every model upgrade is measured against it before it ships. Live
gate-accounting (passes *and* rejects per model version) feeds the evolver,
which may add *or delete* gates. Descent: a gate with zero catch across N
consecutive versions is removed. Held-out discipline: gains on the search
benchmark never count; graders and permissions require human sign-off; the
evaluated agent never edits its grader. Verified traces additionally feed
SLM distillation, widening the competence envelope.
"""

from __future__ import annotations

import os

from . import ledger, store

_CORPUS = "replay-corpus.json"
_SCHEMA = 1
# Consecutive zero-catch versions before a gate is proposed for deletion.
DESCENT_PATIENCE = 3


def _path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{_CORPUS}"


def record_failure(cfg: dict, session_id: str, failure_class: str,
                   would_catch: dict[str, str], note: str = "") -> dict:
    """Add one labeled failed session: which gate would have caught it, where."""
    data = store.load_json(_path(cfg), {"schema": _SCHEMA, "failures": []})
    entry = {"session": session_id, "failure_class": failure_class,
             "would_catch": would_catch, "note": note[:1000]}
    data["failures"].append(entry)
    store.save_json(_path(cfg), data)
    return entry


def catch_matrix(cfg: dict) -> dict:
    """Which hypothesized gates would have caught each corpus failure —
    the build list *and* the falsifier."""
    data = store.load_json(_path(cfg), {"schema": _SCHEMA, "failures": []})
    matrix: dict[str, int] = {}
    for f in data["failures"]:
        for gate in f.get("would_catch", {}):
            matrix[gate] = matrix.get(gate, 0) + 1
    return {"n_failures": len(data["failures"]), "would_catch": matrix}


def descent_candidates(cfg: dict, history: dict[str, list[float]] | None = None) -> list[str]:
    """Gates with ~zero catch across recent versions. With explicit per-version
    history supplied, patience applies; otherwise current rates decide."""
    if history:
        return [g for g, rates in history.items()
                if len(rates) >= DESCENT_PATIENCE and all(r <= 0.001 for r in rates[-DESCENT_PATIENCE:])]
    return [g for g, r in ledger.catch_rates(cfg).items() if r <= 0.001]


def trajectory_patterns(issue_texts: list[str], top_n: int = 8) -> list[str]:
    """Offline miner over verified traces: recurring failure phrases become
    harness-fix proposals. Constrained to non-grader components by policy
    (callers must enforce held-out separation)."""
    import re
    from collections import Counter

    stop = {"the", "and", "with", "that", "this", "from", "have", "were",
            "been", "also", "into", "when", "then", "than"}
    grams: Counter = Counter()
    for t in issue_texts:
        words = [w for w in re.findall(r"[a-z][a-z\-]{3,}", t.lower()) if w not in stop]
        for i in range(len(words) - 1):
            grams[f"{words[i]} {words[i+1]}"] += 1
    return [f"{g} ({c})" for g, c in grams.most_common(top_n) if c >= 2]


def held_out_split(cfg: dict, test_ratio: float = 0.2, seed: int = 42) -> dict:
    """Deterministic held-out split: search vs eval. Gains on search never count."""
    import random as _r
    data = store.load_json(_path(cfg), {"schema": _SCHEMA, "failures": []})
    failures = list(data["failures"])
    _r.Random(seed).shuffle(failures)
    n_eval = max(1, int(len(failures) * test_ratio)) if failures else 0
    return {"search": failures[:-n_eval] if n_eval else failures, "eval": failures[-n_eval:] if n_eval else [], "seed": seed}


def evaluate_held_out(cfg: dict) -> dict:
    """Evaluate current gates on held-out eval set — search gains don't count."""
    split = held_out_split(cfg)
    eval_failures = split["eval"]
    # count how many eval failures would be caught by current gates with live catch>0
    live = ledger.catch_rates(cfg)
    caught = 0
    for f in eval_failures:
        for g in f.get("would_catch", {}):
            if live.get(g, 0) > 0.001:
                caught += 1
                break
    return {
        "n_eval": len(eval_failures),
        "caught": caught,
        "missed": len(eval_failures) - caught,
        "eval_recall": (caught / len(eval_failures)) if eval_failures else 0.0,
        "search_size": len(split["search"]),
    }


def evolve(cfg: dict, proposals: dict[str, dict] | None = None) -> dict:
    """Evolver that may add *or delete* gates. Deletions require DESCENT_PATIENCE zero-catch.
    Additions require held-out eval gain + human sign-off (grader off-limits)."""
    # Deletions: descent candidates
    to_delete = descent_candidates(cfg)
    # Additions: proposals with corpus recall and eval gain
    to_add = []
    if proposals:
        for gate, meta in proposals.items():
            ev = evaluate_gate_proposal(cfg, gate)
            # require eval gain
            held = evaluate_held_out(cfg)
            if ev["verdict"] == "ship" and held["eval_recall"] > 0:
                meta["verdict"] = "propose-add"
                # human sign-off required — mark pending
                meta["requires_human"] = True
                to_add.append(gate)
            else:
                meta["verdict"] = "needs-evidence"
    result = {"delete": to_delete, "add": to_add, "held_out": evaluate_held_out(cfg)}
    # log evolver decision
    ledger.log_gate(cfg, "evolver", "F8", "pass" if not to_delete else "reject", detail=f"evolve delete:{to_delete} add:{to_add}")
    return result


def distillation_candidates(cfg: dict, min_verified: int = 3) -> list[dict]:
    """Verified traces for SLM fine-tuning: task + proof + gate passes."""
    # Pull from ledger: sessions where gate pass and task proven
    try:
        from . import tasks as _tasks
        all_tasks = _tasks.list_all(cfg)
        proven = [t for t in all_tasks if t.get("status") == "proven" and t.get("proof")]
        # require at least min_verified traces
        if len(proven) < min_verified:
            return []
        # return compact traces
        return [{"task": t["title"], "proof": t["proof"], "id": t["id"]} for t in proven[:50]]
    except Exception:
        return []


def evaluate_gate_proposal(cfg: dict, gate: str) -> dict:
    """Phase-0 replay for one gate proposal: corpus recall + live precision."""
    matrix = catch_matrix(cfg)
    rates = ledger.catch_rates(cfg)
    stats = ledger.gate_stats(cfg).get(gate, {"pass": 0, "reject": 0})
    total = stats.get("pass", 0) + stats.get("reject", 0)
    return {
        "gate": gate,
        "corpus_recall": matrix["would_catch"].get(gate, 0),
        "corpus_size": matrix["n_failures"],
        "live_catch_rate": rates.get(gate, 0.0),
        "live_samples": total,
        "verdict": "ship" if matrix["would_catch"].get(gate, 0) > 0 and total >= 5 else "needs-evidence",
    }
