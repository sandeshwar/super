"""Calibration + trust tiers + fatigue detection (doc 03 §10, doc 02 §7).

The human has a finite attention budget, modeled like one. Approval rates
per prompt type detect rubber-stamping (≥95% approve over the window means
the gate is waved through — promote to trusted or remove it, never launder
risk as consent). Blast-radius routing auto-passes small + proven changes
(logged) and mandates human review for big / new / auth / billing / crypto.
Per-agent trust tiers per repo area widen or narrow authority from history.
"""

from __future__ import annotations

from . import ledger, store

_FILE = "trust.json"
RISKY_AREAS = ("auth", "billing", "crypto", "security", "payment", "secret")
RISKY_TOKENS = ("auth", "login", "password", "billing", "payment", "crypto",
                "secret", "token", "permission", "admin")


def _path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{_FILE}"


def blast_radius(changed_files: list[str], loc_delta: int = 0) -> int:
    """0 (trivial) .. 4 (critical). Sensitive areas always score ≥ 3."""
    score = 0
    text = " ".join(changed_files).lower()
    if any(t in text for t in RISKY_TOKENS):
        score = max(score, 3)
    if len(changed_files) >= 10 or loc_delta >= 500:
        score = max(score, 3)
    elif len(changed_files) >= 4 or loc_delta >= 100:
        score = max(score, 2)
    elif changed_files or loc_delta > 0:
        score = max(score, 1)
    return score


def route(cfg: dict, changed_files: list[str], loc_delta: int = 0,
          proven_record: bool = False) -> tuple[str, int, str]:
    """Returns (decision, radius, reason).

    decision is 'auto-pass' (small + proven, logged) or 'human-required'.
    """
    radius = blast_radius(changed_files, loc_delta)
    auto_max = int(cfg.get("trust", {}).get("auto_pass_max_blast", 2))
    if radius <= auto_max and proven_record:
        return "auto-pass", radius, f"radius {radius} ≤ {auto_max} with proven record"
    if radius >= 3:
        return "human-required", radius, f"radius {radius}: sensitive or large blast radius"
    return "human-required", radius, f"radius {radius}: default human review"


def record_approval(cfg: dict, prompt_type: str, approved: bool) -> dict:
    """Append an approval outcome; returns current fatigue reading."""
    data = store.load_json(_path(cfg), {"approvals": []})
    data["approvals"].append({"type": prompt_type, "approved": approved})
    window = int(cfg.get("trust", {}).get("fatigue_window", 40))
    data["approvals"] = data["approvals"][-max(window, 1):]
    store.save_json(_path(cfg), data)
    return fatigue(cfg)


def fatigue(cfg: dict) -> dict:
    """Approval rate per prompt type; flags rubber-stamping (doc 02 §7)."""
    data = store.load_json(_path(cfg), {"approvals": []})
    threshold = float(cfg.get("trust", {}).get("fatigue_approve_threshold", 0.95))
    by_type: dict[str, dict[str, int]] = {}
    for a in data.get("approvals", []):
        cell = by_type.setdefault(a["type"], {"n": 0, "ok": 0})
        cell["n"] += 1
        cell["ok"] += 1 if a["approved"] else 0
    flags = {t: (c["ok"] / c["n"]) for t, c in by_type.items()
             if c["n"] >= 5 and (c["ok"] / c["n"]) >= threshold}
    return {"by_type": by_type, "threshold": threshold, "fatigued": flags}


def trust_tier(cfg: dict, agent: str = "default", area: str = "general") -> dict:
    """Tier from gate-accounting history: catch-free streaks widen authority,
    rejects narrow it. Read-only summary — no stored grades to game."""
    stats = ledger.gate_stats(cfg)
    passes = sum(s.get("pass", 0) for s in stats.values())
    rejects = sum(s.get("reject", 0) for s in stats.values())
    total = passes + rejects
    rate = (passes / total) if total else 1.0
    tier = "unproven" if total < 10 else ("trusted" if rate >= 0.9 and rejects <= 2 else "standard")
    return {"agent": agent, "area": area, "tier": tier,
            "pass": passes, "reject": rejects, "pass_rate": round(rate, 3)}


def critic_first_evidence(critic_note: str, diff_summary: str, blast: int,
                          checks: dict) -> dict:
    """Approval payload order: strongest objection first, builder summary
    never shown (doc 02 §7)."""
    return {
        "critic": critic_note,
        "blast_radius": blast,
        "diff": diff_summary,
        "checks": checks,
    }
