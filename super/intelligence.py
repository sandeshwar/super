"""Autonomous intelligence loop: audit → agenda → auto-act → briefing.

This is the metacognition layer. Every turn SUPER:
  1. Scans gates, memory, tools, capabilities, agents, replay corpus
  2. Writes prioritized gap findings to an agenda
  3. Auto-executes safe improvements (low-risk composites, memory)
  4. Injects a briefing into the system prompt so the model pursues gaps
     without being asked

The model is not the only intelligence — the harness itself proposes work.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from . import store
from .errors import StoreError
from .tools.base import ToolResult, dump_json

FILE = "intelligence.json"
SCHEMA = 1
PRIORITIES = ("critical", "high", "medium", "low")
KINDS = (
    "missing_capability",
    "improve_workflow",
    "quality",
    "memory",
    "specialist",
    "config",
    "safety",
)
STATUSES = ("open", "acting", "done", "dismissed")
# Retired action types from the removed work-plan seeder — dismiss on load.
_DEAD_ACTIONS = frozenset({"seed_tasks", "seed_next_wave"})
_DEAD_KINDS = frozenset({"task_gap"})

# Fingerprints of composites we auto-propose when the raw tools exist but no cap does.
WORKFLOW_RECIPES: list[dict[str, Any]] = [
    {
        "id": "recipe_repo_pulse",
        "name": "repo_pulse",
        "summary": "Workspace pulse: list dir + repo tree",
        "needs_tools": ["list_dir", "repo_tree"],
        "impl": {
            "steps": [
                {"tool": "list_dir", "args": {"path": "."}, "as": "listing"},
                {"tool": "repo_tree", "args": {}, "as": "tree"},
            ],
            "merge": "text",
        },
        "risk": "low",
    },
    {
        "id": "recipe_git_snapshot",
        "name": "git_snapshot",
        "summary": "Git status + recent log + unstaged diff",
        "needs_tools": ["git_status", "git_log", "git_diff"],
        "impl": {
            "steps": [
                {"tool": "git_status", "args": {}, "as": "status"},
                {"tool": "git_log", "args": {"limit": 5}, "as": "log"},
                {"tool": "git_diff", "args": {}, "as": "diff"},
            ],
            "merge": "text",
        },
        "risk": "low",
    },
    {
        "id": "recipe_code_scout",
        "name": "code_scout",
        "summary": "Find symbol then grep nearby usage",
        "needs_tools": ["find_symbol", "grep"],
        "impl": {
            "steps": [
                {"tool": "find_symbol", "args": {"name": "$arg.symbol"}, "as": "defs"},
                {"tool": "grep", "args": {"pattern": "$arg.symbol"}, "as": "uses"},
            ],
            "merge": "text",
        },
        "risk": "low",
        "parameters": {
            "type": "object",
            "properties": {"symbol": {"type": "string", "description": "Symbol to scout"}},
            "required": ["symbol"],
            "additionalProperties": False,
        },
    },
]


def _path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{FILE}"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _now_ts() -> float:
    return time.time()


def _intel_cfg(cfg: dict) -> dict:
    return cfg.get("intelligence") or {}


def enabled(cfg: dict) -> bool:
    return bool(_intel_cfg(cfg).get("enabled", True))


def auto_act_on(cfg: dict) -> bool:
    return bool(_intel_cfg(cfg).get("auto_act", True))


def inject_briefing(cfg: dict) -> bool:
    return bool(_intel_cfg(cfg).get("inject_briefing", True))


def min_interval_s(cfg: dict) -> float:
    return max(5.0, float(_intel_cfg(cfg).get("min_interval_s", 30)))


def max_agenda(cfg: dict) -> int:
    return max(5, min(int(_intel_cfg(cfg).get("max_agenda", 40)), 100))


def _blank() -> dict:
    return {
        "schema": SCHEMA,
        "agenda": {},
        "last_audit_at": 0.0,
        "last_audit_iso": "",
        "stats": {"audits": 0, "auto_acts": 0, "findings_total": 0},
    }


def _load(cfg: dict) -> dict:
    data = store.load_json(_path(cfg), _blank())
    if not isinstance(data, dict) or not isinstance(data.get("agenda"), dict):
        raise StoreError("intelligence store is malformed")
    data.setdefault("stats", {"audits": 0, "auto_acts": 0, "findings_total": 0})
    dirty = False
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    for item in list((data.get("agenda") or {}).values()):
        if not isinstance(item, dict):
            continue
        atype = str((item.get("action") or {}).get("type") or "")
        kind = str(item.get("kind") or "")
        if atype in _DEAD_ACTIONS or kind in _DEAD_KINDS:
            if item.get("status") in ("open", "acting"):
                item["status"] = "dismissed"
                item["updated_at"] = now
                item["result"] = {"note": "retired action/kind removed from product"}
                dirty = True
    if dirty:
        _save(cfg, data)
    return data


def _save(cfg: dict, data: dict) -> None:
    store.save_json(_path(cfg), data)


def _fid(*parts: str) -> str:
    raw = "|".join(str(p) for p in parts)
    return "f_" + hashlib.sha1(raw.encode()).hexdigest()[:12]


def _public_item(item: dict) -> dict:
    return {
        "id": item["id"],
        "kind": item["kind"],
        "priority": item["priority"],
        "status": item["status"],
        "title": item["title"],
        "detail": item.get("detail") or "",
        "action": item.get("action") or {},
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or "",
        "result": item.get("result"),
    }


# ── audit sensors ─────────────────────────────────────────────────────

def _scan_gates(cfg: dict) -> list[dict]:
    out = []
    try:
        from . import ledger
        rates = ledger.catch_rates(cfg)
        criticals = ledger.open_criticals(cfg)
    except Exception:
        return out
    if criticals:
        out.append({
            "kind": "safety", "priority": "critical",
            "title": f"{len(criticals)} open critical issue(s)",
            "detail": "; ".join(str(c.get("text") or c)[:80] for c in criticals[:4]),
            "action": {"type": "resolve_criticals"},
            "key": "open_criticals",
        })
    weak = [g for g, r in (rates or {}).items() if r is not None and r < 0.02]
    if len(weak) >= 3:
        out.append({
            "kind": "quality", "priority": "low",
            "title": f"{len(weak)} gates near zero catch — consider descent",
            "detail": ", ".join(weak[:8]),
            "action": {"type": "meta_evolve"},
            "key": "gate_descent",
        })
    try:
        from . import meta
        matrix = meta.catch_matrix(cfg)
        if matrix.get("n_failures", 0) >= 3 and matrix.get("would_catch"):
            top = sorted(matrix["would_catch"].items(), key=lambda x: -x[1])[:3]
            out.append({
                "kind": "quality", "priority": "high",
                "title": "Replay corpus shows recurring failure classes",
                "detail": ", ".join(f"{g}×{n}" for g, n in top),
                "action": {"type": "meta_evolve"},
                "key": "corpus_failures",
            })
    except Exception:
        pass
    return out


def _scan_memory(cfg: dict) -> list[dict]:
    out = []
    try:
        from . import memory
        data = memory.list_claims(cfg, include_dead=False, limit=50)
        claims = data.get("claims") if isinstance(data, dict) else data
        claims = claims or []
    except Exception:
        return [{
            "kind": "memory", "priority": "medium",
            "title": "Memory store unavailable",
            "detail": "Repair claims store so durable knowledge accumulates.",
            "action": {"type": "note"},
            "key": "memory_down",
        }]
    if not claims:
        out.append({
            "kind": "memory", "priority": "medium",
            "title": "Memory empty — seed durable workspace facts",
            "detail": "After exploring the repo, memory_add atomic verified facts (stack, entrypoints, conventions).",
            "action": {"type": "seed_memory"},
            "key": "memory_empty",
        })
    else:
        unverified = [c for c in claims if c.get("verification") == "unverified"]
        if len(unverified) >= 5:
            out.append({
                "kind": "memory", "priority": "low",
                "title": f"{len(unverified)} unverified claims need confirm or retire",
                "detail": "Verify or supersede stale claims to keep context sharp.",
                "action": {"type": "curate_memory"},
                "key": "memory_unverified",
            })
    return out


def _scan_capabilities(cfg: dict) -> list[dict]:
    out = []
    try:
        from . import capabilities as caps
        from .tools.catalog import get_tool
        installed = [c for c in caps.list_capabilities(cfg) if c.get("status") == "installed"]
        pending = [c for c in caps.list_capabilities(cfg) if c.get("status") == "pending"]
        installed_names = {c["name"] for c in installed}
    except Exception:
        return out
    if pending:
        out.append({
            "kind": "missing_capability", "priority": "high",
            "title": f"{len(pending)} capability proposal(s) awaiting human approve",
            "detail": ", ".join(c["name"] for c in pending[:6]),
            "action": {"type": "note"},
            "key": "caps_pending",
        })
    for recipe in WORKFLOW_RECIPES:
        if recipe["name"] in installed_names:
            continue
        if all(get_tool(t) for t in recipe["needs_tools"]):
            out.append({
                "kind": "missing_capability", "priority": "medium",
                "title": f"Missing forged tool `{recipe['name']}`",
                "detail": recipe["summary"],
                "action": {"type": "forge_recipe", "recipe_id": recipe["id"]},
                "key": f"recipe:{recipe['id']}",
            })
    if not installed and not pending:
        out.append({
            "kind": "missing_capability", "priority": "medium",
            "title": "Capability forge unused — invent first composites",
            "detail": "Identify 1–3 repeated tool sequences and propose_capability (risk=low).",
            "action": {"type": "forge_bootstrap"},
            "key": "forge_unused",
        })
    return out


def _scan_agents(cfg: dict) -> list[dict]:
    out = []
    if not (cfg.get("agents") or {}).get("enabled", True):
        return out
    try:
        from . import agents
        specs = agents.list_agents(cfg, include_archived=False)
    except Exception:
        return out
    active = [a for a in specs if a.get("status") == "active"]
    pending = [a for a in specs if a.get("status") == "pending"]
    if pending:
        out.append({
            "kind": "specialist", "priority": "medium",
            "title": f"{len(pending)} agent(s) pending approval",
            "detail": ", ".join(a.get("name", a.get("id", "")) for a in pending[:6]),
            "action": {"type": "note"},
            "key": "agents_pending",
        })
    roles = {a.get("role") for a in active}
    if active and "reviewer" not in roles and "auditor" not in roles:
        out.append({
            "kind": "specialist", "priority": "low",
            "title": "No reviewer/auditor specialist",
            "detail": "create_agent role=reviewer (pending until human approve) for critique loops.",
            "action": {"type": "suggest_reviewer"},
            "key": "no_reviewer",
        })
    if not active:
        out.append({
            "kind": "specialist", "priority": "low",
            "title": "No specialized agents yet",
            "detail": "When work splits cleanly (research vs code vs review), create_agent + run_agent.",
            "action": {"type": "note"},
            "key": "no_agents",
        })
    return out


def _scan_config(cfg: dict) -> list[dict]:
    out = []
    tools = cfg.get("tools") or {}
    groups = tools.get("groups") or {}
    if not tools.get("enabled", True):
        out.append({
            "kind": "config", "priority": "critical",
            "title": "Tools disabled — intelligence is blind",
            "detail": "Enable tools in settings to act on the world.",
            "action": {"type": "note"},
            "key": "tools_off",
        })
    if not groups.get("web", False) and not any(
        (tools.get("packs") or {}).get(p) for p in ("lc_search", "lc_wikipedia", "lc_arxiv")
    ):
        out.append({
            "kind": "config", "priority": "low",
            "title": "No live-web tools enabled",
            "detail": "Enable web group or lc_search pack when current events matter.",
            "action": {"type": "note"},
            "key": "no_web",
        })
    return out


def audit(cfg: dict) -> list[dict]:
    """Run all sensors; return raw findings (not yet merged into agenda)."""
    findings: list[dict] = []
    for scanner in (
        _scan_gates, _scan_memory,
        _scan_capabilities, _scan_agents, _scan_config,
    ):
        try:
            findings.extend(scanner(cfg))
        except Exception:
            continue
    # normalize
    for f in findings:
        f.setdefault("priority", "medium")
        f.setdefault("kind", "improve_workflow")
        f.setdefault("action", {"type": "note"})
    pri = {p: i for i, p in enumerate(PRIORITIES)}
    findings.sort(key=lambda x: (pri.get(x["priority"], 9), x.get("title", "")))
    return findings


def refresh_agenda(cfg: dict, *, force: bool = False) -> dict:
    """Merge audit into durable agenda. Rate-limited unless force."""
    if not enabled(cfg):
        return {"ok": False, "skipped": "disabled", "agenda": []}
    data = _load(cfg)
    now = _now_ts()
    if not force and (now - float(data.get("last_audit_at") or 0)) < min_interval_s(cfg):
        return {
            "ok": True,
            "skipped": "rate_limited",
            "agenda": [_public_item(i) for i in data["agenda"].values() if i.get("status") == "open"],
            "last_audit_iso": data.get("last_audit_iso"),
        }

    findings = audit(cfg)
    now_iso = _now()
    seen_keys = set()
    for f in findings:
        key = str(f.get("key") or f["title"])
        seen_keys.add(key)
        fid = _fid(f["kind"], key)
        existing = data["agenda"].get(fid)
        if existing and existing.get("status") in ("done", "dismissed", "acting"):
            # reopen if critical and was dismissed long ago? keep dismissed
            if existing.get("status") == "acting":
                continue
            if existing.get("status") == "done":
                continue
            if existing.get("status") == "dismissed":
                continue
        if existing and existing.get("status") == "open":
            existing["detail"] = f.get("detail") or existing.get("detail")
            existing["priority"] = f["priority"]
            existing["updated_at"] = now_iso
            continue
        data["agenda"][fid] = {
            "id": fid,
            "key": key,
            "kind": f["kind"],
            "priority": f["priority"],
            "status": "open",
            "title": f["title"][:300],
            "detail": (f.get("detail") or "")[:1000],
            "action": f.get("action") or {"type": "note"},
            "created_at": now_iso,
            "updated_at": now_iso,
            "result": None,
        }

    # prune stale open items whose keys didn't reappear (max soft)
    for fid, item in list(data["agenda"].items()):
        if item.get("status") == "open" and item.get("key") not in seen_keys:
            # keep criticals briefly; auto-dismiss low after refresh miss
            if item.get("priority") in ("low", "medium"):
                item["status"] = "done"
                item["updated_at"] = now_iso
                item["result"] = {"note": "auto-cleared; sensor quiet"}

    # cap size
    opens = [i for i in data["agenda"].values() if i.get("status") == "open"]
    pri = {p: i for i, p in enumerate(PRIORITIES)}
    opens.sort(key=lambda x: (pri.get(x["priority"], 9), x.get("created_at", "")))
    overflow = opens[max_agenda(cfg):]
    for item in overflow:
        item["status"] = "dismissed"
        item["result"] = {"note": "agenda overflow"}
        item["updated_at"] = now_iso

    data["last_audit_at"] = now
    data["last_audit_iso"] = now_iso
    data["stats"]["audits"] = int(data["stats"].get("audits") or 0) + 1
    data["stats"]["findings_total"] = int(data["stats"].get("findings_total") or 0) + len(findings)
    _save(cfg, data)
    return {
        "ok": True,
        "findings": len(findings),
        "agenda": [_public_item(i) for i in data["agenda"].values() if i.get("status") == "open"],
        "last_audit_iso": now_iso,
    }


# ── auto-act ──────────────────────────────────────────────────────────

def _act_forge_recipe(cfg: dict, item: dict) -> dict:
    from . import capabilities as caps
    rid = (item.get("action") or {}).get("recipe_id")
    recipe = next((r for r in WORKFLOW_RECIPES if r["id"] == rid), None)
    if not recipe:
        return {"ok": False, "error": "unknown recipe"}
    # already installed?
    existing = caps.get_capability(cfg, name=recipe["name"])
    if existing and existing.get("status") == "installed":
        return {"ok": True, "skipped": "already_installed", "name": recipe["name"]}
    cap = caps.propose(
        cfg,
        name=recipe["name"],
        summary=recipe["summary"],
        description=recipe["summary"] + " (auto-forged by intelligence loop)",
        kind="composite",
        risk=recipe.get("risk") or "low",
        parameters=recipe.get("parameters"),
        impl=recipe["impl"],
        # structural check only — recipe tools already verified present
        tests=[],
        created_by="intelligence",
    )
    return {"ok": True, "capability": cap}


def _act_seed_memory(cfg: dict, item: dict) -> dict:
    from . import memory
    import os
    root = cfg.get("_root") or "."
    try:
        names = sorted(os.listdir(root))[:30]
    except OSError:
        names = []
    text = f"Workspace top-level entries: {', '.join(names) or '(empty)'}"
    claim = memory.remember(cfg, text, source="intelligence", verification="unverified", taint="local-exec")
    return {"ok": True, "claim": claim.get("id") if isinstance(claim, dict) else True}


def _act_meta_evolve(cfg: dict, item: dict) -> dict:
    from . import meta
    result = meta.evolve(cfg, proposals=None)
    return {"ok": True, "evolve": result}


def _act_suggest_reviewer(cfg: dict, item: dict) -> dict:
    from . import agents
    specs = agents.list_agents(cfg, include_archived=False)
    if any(a.get("role") == "reviewer" for a in specs):
        return {"ok": True, "skipped": "exists"}
    spec = agents.create_agent(
        cfg,
        name="critic",
        role="reviewer",
        summary="Reviews plans and diffs; no write rights",
        system_addon="Be a harsh but fair critic. Prefer concrete failure modes over praise.",
        groups=["files", "search", "git", "memory", "project"],
        created_by="agent:intelligence",
        force_active=False,
    )
    return {"ok": True, "agent": {"id": spec.get("id"), "status": spec.get("status")}}


_ACTORS = {
    "forge_recipe": _act_forge_recipe,
    "forge_bootstrap": lambda cfg, item: _act_forge_recipe(cfg, {
        **item,
        "action": {"type": "forge_recipe", "recipe_id": "recipe_repo_pulse"},
    }),
    "seed_memory": _act_seed_memory,
    "meta_evolve": _act_meta_evolve,
    "suggest_reviewer": _act_suggest_reviewer,
}


def auto_act(cfg: dict, *, limit: int = 3) -> dict:
    """Execute safe agenda actions without waiting for the model."""
    if not enabled(cfg) or not auto_act_on(cfg):
        return {"ok": False, "skipped": "disabled", "acted": []}
    data = _load(cfg)
    pri = {p: i for i, p in enumerate(PRIORITIES)}
    opens = [i for i in data["agenda"].values() if i.get("status") == "open"]
    opens.sort(key=lambda x: pri.get(x["priority"], 9))
    acted = []
    for item in opens:
        if len(acted) >= limit:
            break
        atype = (item.get("action") or {}).get("type") or "note"
        if atype in ("note", "address_blocked", "fix_deps", "resolve_criticals", "curate_memory") or atype in _DEAD_ACTIONS:
            # model must handle — or retired seeder actions
            continue
        fn = _ACTORS.get(atype)
        if not fn:
            continue
        item["status"] = "acting"
        item["updated_at"] = _now()
        _save(cfg, data)
        try:
            result = fn(cfg, item)
        except Exception as e:
            result = {"ok": False, "error": str(e)}
        data = _load(cfg)
        live = data["agenda"].get(item["id"])
        if not live:
            continue
        live["result"] = result
        live["updated_at"] = _now()
        live["status"] = "done" if result.get("ok") else "open"
        data["stats"]["auto_acts"] = int(data["stats"].get("auto_acts") or 0) + 1
        _save(cfg, data)
        acted.append({"id": item["id"], "title": item["title"], "result": result})
    return {"ok": True, "acted": acted}


def tick(cfg: dict, *, force: bool = False) -> dict:
    """One intelligence heartbeat: refresh agenda + auto-act."""
    if not enabled(cfg):
        return {"ok": False, "skipped": "disabled"}
    refreshed = refresh_agenda(cfg, force=force)
    acted = auto_act(cfg) if refreshed.get("ok") and not refreshed.get("skipped") == "disabled" else {"acted": []}
    # if rate-limited, still allow auto_act on existing open forge items? skip to avoid thrash
    return {
        "ok": True,
        "refresh": refreshed,
        "auto_act": acted,
        "briefing": compile_briefing(cfg, max_items=8),
    }


def list_agenda(cfg: dict, *, include_done: bool = False) -> list[dict]:
    data = _load(cfg)
    out = []
    for item in data["agenda"].values():
        if not include_done and item.get("status") not in ("open", "acting"):
            continue
        out.append(_public_item(item))
    pri = {p: i for i, p in enumerate(PRIORITIES)}
    out.sort(key=lambda x: (pri.get(x["priority"], 9), x.get("created_at", "")))
    return out


def dismiss(cfg: dict, item_id: str, *, reason: str = "") -> dict:
    data = _load(cfg)
    item = data["agenda"].get(item_id)
    if not item:
        raise KeyError(item_id)
    item["status"] = "dismissed"
    item["updated_at"] = _now()
    item["result"] = {"dismissed": True, "reason": (reason or "")[:300]}
    _save(cfg, data)
    return _public_item(item)


def pursue(cfg: dict, item_id: str) -> dict:
    """Force-run auto actor for one item, or return guidance for model-owned actions."""
    data = _load(cfg)
    item = data["agenda"].get(item_id)
    if not item:
        raise KeyError(item_id)
    atype = (item.get("action") or {}).get("type") or "note"
    if atype in _DEAD_ACTIONS or str(item.get("kind") or "") in _DEAD_KINDS:
        item["status"] = "dismissed"
        item["updated_at"] = _now()
        item["result"] = {"note": "retired action/kind removed from product"}
        _save(cfg, data)
        return {"ok": True, "dismissed": True, "item": _public_item(item)}
    fn = _ACTORS.get(atype)
    if not fn:
        return {
            "ok": True,
            "needs_model": True,
            "item": _public_item(item),
            "guidance": (
                f"Address this yourself with tools: {item['title']}. "
                f"Detail: {item.get('detail')}. Mark done via dismiss_agenda after."
            ),
        }
    try:
        result = fn(cfg, item)
    except Exception as e:
        result = {"ok": False, "error": str(e)}
    data = _load(cfg)
    live = data["agenda"].get(item_id)
    if live:
        live["result"] = result
        live["updated_at"] = _now()
        live["status"] = "done" if result.get("ok") else "open"
        data["stats"]["auto_acts"] = int(data["stats"].get("auto_acts") or 0) + 1
        _save(cfg, data)
    return {"ok": bool(result.get("ok")), "item": _public_item(live or item), "result": result}


def compile_briefing(cfg: dict, *, max_items: int = 6) -> str:
    """Text injected into the system prompt — standing orders for the model."""
    if not enabled(cfg) or not inject_briefing(cfg):
        return ""
    try:
        items = list_agenda(cfg, include_done=False)[:max_items]
        data = _load(cfg)
    except Exception:
        return ""
    if not items:
        return (
            "\n\nIntelligence: Agenda clear. Still: notice friction, missing tools, "
            "and weak acceptance criteria; propose_capability / create_agent "
            "proactively when you see a repeated gap — do not wait to be asked."
        )
    lines = [
        "\n\nIntelligence agenda (pursue autonomously — do not wait for the user to ask):",
    ]
    for i, it in enumerate(items, 1):
        lines.append(
            f"{i}. [{it['priority']}/{it['kind']}] {it['title']}"
            + (f" — {it['detail'][:160]}" if it.get("detail") else "")
            + f"  (id={it['id']})"
        )
    lines.append(
        "Standing orders: (1) If the user request is simple chat, answer briefly then "
        "optionally act on one high/critical agenda item. (2) If the user asks for work, "
        "fold the highest-priority related agenda item into the plan. "
        "(3) Use pursue_agenda / propose_capability / create_agent / memory_add. "
        "(4) After fixing an item, dismiss_agenda with a short reason. "
        f"Last audit: {data.get('last_audit_iso') or 'never'}."
    )
    return "\n".join(lines)


def stats(cfg: dict) -> dict:
    try:
        data = _load(cfg)
    except StoreError:
        return {}
    opens = sum(1 for i in data["agenda"].values() if i.get("status") == "open")
    return {
        **data.get("stats", {}),
        "open": opens,
        "last_audit_iso": data.get("last_audit_iso"),
    }


# ── tool handlers ─────────────────────────────────────────────────────

def handle_self_reflect(cfg: dict, args: dict) -> ToolResult:
    eff = cfg.get("_agent_effective")
    if isinstance(eff, dict) and not eff.get("may_manage_agents", True):
        # read-only reflect: refresh agenda text, no auto-act
        refreshed = refresh_agenda(cfg, force=bool(args.get("force", True)))
        return ToolResult(True, dump_json({
            "ok": True, "refresh": refreshed, "auto_act": {"skipped": "may_manage_agents=false"},
            "briefing": compile_briefing(cfg),
        }))
    force = bool(args.get("force", True))
    result = tick(cfg, force=force)
    return ToolResult(True, dump_json(result), data={"open": len((result.get("refresh") or {}).get("agenda") or [])})


def handle_list_agenda(cfg: dict, args: dict) -> ToolResult:
    items = list_agenda(cfg, include_done=bool(args.get("include_done")))
    return ToolResult(True, dump_json({"agenda": items, "stats": stats(cfg)}))


def handle_pursue_agenda(cfg: dict, args: dict) -> ToolResult:
    eff = cfg.get("_agent_effective")
    if isinstance(eff, dict) and not eff.get("may_manage_agents", True):
        return ToolResult(False, "may_manage_agents=false")
    item_id = str(args.get("id") or "").strip()
    if not item_id:
        items = list_agenda(cfg)
        if not items:
            return ToolResult(True, "agenda empty")
        item_id = items[0]["id"]
    try:
        result = pursue(cfg, item_id)
        return ToolResult(bool(result.get("ok", True)), dump_json(result), data=result)
    except KeyError:
        return ToolResult(False, f"no agenda item {item_id}")


def handle_dismiss_agenda(cfg: dict, args: dict) -> ToolResult:
    eff = cfg.get("_agent_effective")
    if isinstance(eff, dict) and not eff.get("may_manage_agents", True):
        return ToolResult(False, "may_manage_agents=false")
    item_id = str(args.get("id") or "").strip()
    if not item_id:
        return ToolResult(False, "id required")
    try:
        item = dismiss(cfg, item_id, reason=str(args.get("reason") or ""))
        return ToolResult(True, dump_json({"dismissed": item}))
    except KeyError:
        return ToolResult(False, f"no agenda item {item_id}")
