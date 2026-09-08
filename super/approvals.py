"""Pending human approvals that should surface in chat first.

Settings is the backlog for items still unacknowledged (status still pending /
unverified). Chat cards act on the same store via existing approve APIs.
"""

from __future__ import annotations

import json
from typing import Any


def list_pending(cfg: dict) -> list[dict[str, Any]]:
    """All items awaiting human action, newest-ish first by kind groups."""
    out: list[dict[str, Any]] = []
    try:
        from . import agents as _agents
        for a in _agents.list_agents(cfg, include_archived=False):
            if a.get("status") != "pending":
                continue
            out.append({
                "kind": "agent",
                "id": a["id"],
                "title": a.get("name") or a["id"],
                "detail": a.get("summary") or a.get("role") or "",
                "meta": {"role": a.get("role"), "created_by": a.get("created_by")},
                "status": "pending",
            })
    except Exception:
        pass
    try:
        from . import capabilities as _caps
        for c in _caps.list_capabilities(cfg, include_retired=False):
            if c.get("status") != "pending":
                continue
            out.append({
                "kind": "capability",
                "id": c["id"],
                "title": c.get("name") or c["id"],
                "detail": c.get("summary") or f"{c.get('kind')} · {c.get('risk')}",
                "meta": {"kind": c.get("kind"), "risk": c.get("risk")},
                "status": "pending",
            })
    except Exception:
        pass
    try:
        from . import memory as _mem
        claims = _mem.list_claims(cfg, include_dead=False, limit=50, offset=0)
        rows = (claims or {}).get("claims") or []
        for c in rows:
            if not isinstance(c, dict):
                continue
            if c.get("verification", "unverified") != "unverified":
                continue
            out.append({
                "kind": "memory",
                "id": c.get("id"),
                "title": (c.get("text") or "")[:120],
                "detail": f"source={c.get('source') or '—'}",
                "meta": {"source": c.get("source")},
                "status": "pending",
            })
    except Exception:
        pass
    return out


def from_tool_result(tool_name: str, content: str | None, *, ok: bool = True) -> dict[str, Any] | None:
    """Parse a tool result payload into a chat approval card, if any."""
    if not ok or not content or not tool_name:
        return None
    raw = content.strip()
    if not raw.startswith("{"):
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    if tool_name == "create_agent":
        agent = data.get("agent") if isinstance(data.get("agent"), dict) else data
        if agent.get("status") == "pending" and agent.get("id"):
            return {
                "kind": "agent",
                "id": str(agent["id"]),
                "title": str(agent.get("name") or agent["id"]),
                "detail": str(agent.get("summary") or agent.get("role") or "Needs approval before run_agent"),
                "meta": {"role": agent.get("role"), "created_by": agent.get("created_by")},
                "status": "pending",
            }

    if tool_name in ("propose_capability", "create_capability"):
        cap = data.get("capability") if isinstance(data.get("capability"), dict) else data
        if cap.get("status") == "pending" and cap.get("id"):
            return {
                "kind": "capability",
                "id": str(cap["id"]),
                "title": str(cap.get("name") or cap["id"]),
                "detail": str(cap.get("summary") or f"{cap.get('kind')} · {cap.get('risk')}"),
                "meta": {"kind": cap.get("kind"), "risk": cap.get("risk")},
                "status": "pending",
            }

    if tool_name in ("memory_add", "add_memory"):
        claim = data.get("claim") if isinstance(data.get("claim"), dict) else data
        cid = claim.get("id")
        ver = claim.get("verification", "unverified")
        if cid is not None and ver == "unverified":
            return {
                "kind": "memory",
                "id": cid,
                "title": str(claim.get("text") or "")[:120],
                "detail": "Unverified memory claim — confirm if you trust it",
                "meta": {"source": claim.get("source")},
                "status": "pending",
            }

    return None
