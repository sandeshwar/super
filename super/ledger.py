"""Append-only gate ledger and issue ledger.

Every gate decision — pass *and* reject — is recorded with gate id, failure
class, model version, and session, so each gate earns its keep with a
measured catch rate (doc 02 §8). Issues carry severity, layer, expiry, and
owner; open criticals block done-state. Storage is JSONL with atomic
locked appends (see store.py).
"""

from __future__ import annotations

import time
from typing import Any

from . import store

GATE_LOG = "gate.log.jsonl"
ISSUE_LOG = "issues.log.jsonl"

SEVERITIES = ("critical", "major", "minor")
DECISIONS = ("pass", "reject")


def _gate_path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{GATE_LOG}"


def _issue_path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{ISSUE_LOG}"


def log_gate(
    cfg: dict,
    gate_id: str,
    failure_class: str,
    decision: str,
    detail: str = "",
    session: str = "local",
    model: str | None = None,
) -> dict:
    """Record one gate decision. Both outcomes are logged — passes prove
    catch-rate math; rejects prove the gate fires."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}")
    rec = {
        "gate": gate_id,
        "failure_class": failure_class,
        "decision": decision,
        "detail": detail,
        "session": session,
        "model": model or cfg.get("llm", {}).get("model", "unknown"),
    }
    store.append_jsonl(_gate_path(cfg), rec)
    return rec


def add_issue(
    cfg: dict,
    severity: str,
    layer: str,
    text: str,
    expires: str = "",
    owner: str = "",
    session: str = "local",
) -> dict:
    """File a debt/quality/security issue. Criticals block done-state."""
    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {SEVERITIES}")
    if not text or not text.strip():
        raise ValueError("issue text must be non-empty")
    rec = {
        "severity": severity,
        "layer": layer,
        "text": text,
        "status": "open",
        "expires": expires,
        "owner": owner,
        "session": session,
    }
    store.append_jsonl(_issue_path(cfg), rec)
    return rec


def _read_issues(cfg: dict) -> list:
    return store.read_jsonl(_issue_path(cfg))


def _expired(rec: dict, now: str | None = None) -> bool:
    exp = rec.get("expires", "")
    if not exp:
        return False
    return (now or time.strftime("%Y-%m-%dT%H:%M:%S")) > exp


def open_issues(cfg: dict, include_expired: bool = False) -> list:
    rows = [r for r in _read_issues(cfg) if r.get("status", "open") == "open"]
    if not include_expired:
        rows = [r for r in rows if not _expired(r)]
    return rows


def open_criticals(cfg: dict) -> list:
    return [r for r in open_issues(cfg) if r.get("severity") == "critical"]


def resolve_issue(cfg: dict, index: int, resolution: str = "") -> dict:
    """Append a resolution record closing the nth open issue (stable order)."""
    issues = _read_issues(cfg)
    opens = [r for r in issues if r.get("status", "open") == "open"]
    if index < 0 or index >= len(opens):
        raise IndexError(f"no open issue at index {index}")
    target = opens[index]
    store.append_jsonl(
        _issue_path(cfg),
        {
            "severity": target.get("severity", "minor"),
            "layer": target.get("layer", ""),
            "text": f"resolved: {target.get('text', '')} ({resolution})",
            "status": "resolved",
            "expires": "",
            "owner": target.get("owner", ""),
        },
    )
    return target


def gate_stats(cfg: dict) -> dict:
    rows = store.read_jsonl(_gate_path(cfg))
    stats: dict[str, dict[str, int]] = {}
    for r in rows:
        g = r.get("gate", "?")
        s = stats.setdefault(g, {"pass": 0, "reject": 0})
        d = r.get("decision", "pass")
        s[d] = s.get(d, 0) + 1
    return stats


def catch_rates(cfg: dict) -> dict:
    """reject / (pass + reject) per gate — the descent input (doc 02 §8)."""
    rates = {}
    for gate, s in gate_stats(cfg).items():
        total = s.get("pass", 0) + s.get("reject", 0)
        rates[gate] = (s.get("reject", 0) / total) if total else 0.0
    return rates


def catch_rate_per_model(cfg: dict) -> dict:
    """Nested {model: {gate: rate}} for per-version gate accounting."""
    rows = store.read_jsonl(_gate_path(cfg))
    agg: dict[str, dict[str, dict[str, int]]] = {}
    for r in rows:
        m = r.get("model", "unknown")
        g = r.get("gate", "?")
        cell = agg.setdefault(m, {}).setdefault(g, {"pass": 0, "reject": 0})
        cell[r.get("decision", "pass")] = cell.get(r.get("decision", "pass"), 0) + 1
    return {
        m: {g: (c.get("reject", 0) / max(1, c.get("pass", 0) + c.get("reject", 0))) for g, c in gates.items()}
        for m, gates in agg.items()
    }


def done_blocked(cfg: dict) -> list:
    """Reasons done-state is currently blocked (open criticals)."""
    return [
        f"critical open [{c.get('layer', '')}]: {c.get('text', '')}"
        for c in open_criticals(cfg)
    ]


def report(cfg: dict) -> dict[str, Any]:
    return {
        "gates": gate_stats(cfg),
        "catch_rates": catch_rates(cfg),
        "per_model": catch_rate_per_model(cfg),
        "open_issues": len(open_issues(cfg)),
        "open_criticals": open_criticals(cfg),
        "done_blocked": done_blocked(cfg),
    }
