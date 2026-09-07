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


def _resolved_texts(rows: list) -> set[str]:
    """Texts closed by a later resolve record (append-only ledger)."""
    out: set[str] = set()
    for r in rows:
        if r.get("status") != "resolved":
            continue
        key = (r.get("resolves_text") or "").strip()
        if key:
            out.add(key)
            continue
        # Legacy resolve_issue format: "resolved: <original> (<resolution>)"
        text = (r.get("text") or "").strip()
        if text.startswith("resolved: "):
            body = text[len("resolved: "):]
            if " (" in body:
                body = body.rsplit(" (", 1)[0]
            if body:
                out.add(body)
    return out


def open_issues(cfg: dict, include_expired: bool = False) -> list:
    rows = _read_issues(cfg)
    closed = _resolved_texts(rows)
    opens = [
        r for r in rows
        if r.get("status", "open") == "open" and (r.get("text") or "").strip() not in closed
    ]
    if not include_expired:
        opens = [r for r in opens if not _expired(r)]
    return opens


def open_criticals(cfg: dict) -> list:
    reconcile_dependency_issues(cfg)
    return [r for r in open_issues(cfg) if r.get("severity") == "critical"]


def resolve_issue(cfg: dict, index: int, resolution: str = "") -> dict:
    """Append a resolution record closing the nth open issue (stable order)."""
    opens = open_issues(cfg, include_expired=True)
    if index < 0 or index >= len(opens):
        raise IndexError(f"no open issue at index {index}")
    return resolve_issue_text(cfg, opens[index].get("text", ""), resolution)


def resolve_issue_text(cfg: dict, text: str, resolution: str = "") -> dict:
    """Close every open issue whose text matches exactly."""
    text = (text or "").strip()
    if not text:
        raise ValueError("issue text required")
    target = None
    for iss in open_issues(cfg, include_expired=True):
        if (iss.get("text") or "").strip() == text:
            target = iss
            break
    if target is None:
        raise IndexError(f"no open issue matching text")
    store.append_jsonl(
        _issue_path(cfg),
        {
            "severity": target.get("severity", "minor"),
            "layer": target.get("layer", ""),
            "text": f"resolved: {text}" + (f" ({resolution})" if resolution else ""),
            "resolves_text": text,
            "status": "resolved",
            "expires": "",
            "owner": target.get("owner", ""),
            "session": target.get("session", "local"),
        },
    )
    return target


def resolve_matching(cfg: dict, contains: str, resolution: str = "", layer: str | None = None) -> int:
    """Resolve open issues whose text contains `contains` (case-insensitive)."""
    needle = (contains or "").strip().lower()
    if not needle:
        return 0
    n = 0
    for iss in list(open_issues(cfg)):
        if layer and iss.get("layer") != layer:
            continue
        if needle in (iss.get("text") or "").lower():
            resolve_issue_text(cfg, iss.get("text", ""), resolution=resolution or f"matched {contains}")
            n += 1
    return n


def reconcile_dependency_issues(cfg: dict) -> int:
    """Close security issues for packages that later passed the dependency gate."""
    gates = store.read_jsonl(_gate_path(cfg))
    passed: set[str] = set()
    for r in gates:
        if r.get("gate") != "dependency" or r.get("decision") != "pass":
            continue
        detail = (r.get("detail") or "").strip()
        name = detail.split("@", 1)[0].strip().lower()
        if name and name not in ("dependency clear", "?"):
            passed.add(name)
    if not passed:
        return 0
    n = 0
    for iss in list(open_issues(cfg)):
        if iss.get("layer") not in ("security", "legal"):
            continue
        text = (iss.get("text") or "").lower()
        for pkg in passed:
            if pkg in text:
                resolve_issue_text(cfg, iss.get("text", ""), resolution=f"superseded by dependency pass ({pkg})")
                n += 1
                break
    return n


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
