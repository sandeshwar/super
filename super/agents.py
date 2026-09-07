"""Specialized agent specs: CRUD + parent-rule inheritance + spawn.

Agents are durable AgentSpecs. The main (root) chat agent can create/manage
workers and spawn them. Judge roles (reviewer/auditor/evaluator/integrator)
are creatable as pending until a human approves.

Inheritance: a child never gains tools, groups, budgets, or write/spawn/manage
rights beyond its runtime parent. Spec allowlists only tighten further.
"""

from __future__ import annotations

import copy
import time
import uuid
from typing import Any

from . import store
from .errors import StoreError

FILE = "agents.json"
EVENTS = "agent.events.jsonl"
SPANS_FILE = "agent.spans.json"

ROLES = ("worker", "planner", "reviewer", "auditor", "evaluator", "integrator")
JUDGE_ROLES = frozenset({"reviewer", "auditor", "evaluator", "integrator"})
STATUSES = ("active", "archived", "pending")
SPAN_STATUSES = ("running", "done", "error")
MAX_SPANS_PER_SESSION = 24

ROLE_DEFAULTS: dict[str, dict[str, bool]] = {
    "worker": {"may_write": True, "may_spawn": True, "may_manage_agents": True},
    "planner": {"may_write": False, "may_spawn": False, "may_manage_agents": True},
    "reviewer": {"may_write": False, "may_spawn": False, "may_manage_agents": False},
    "auditor": {"may_write": False, "may_spawn": False, "may_manage_agents": False},
    "evaluator": {"may_write": False, "may_spawn": False, "may_manage_agents": False},
    "integrator": {"may_write": True, "may_spawn": False, "may_manage_agents": False},
}

WRITE_TOOLS = frozenset({
    "write_file", "edit_file", "delete_path", "mkdir",
    "file_delete", "copy_file", "lc_copy_file", "move_file",
})


def _path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{FILE}"


def _events_path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{EVENTS}"


def _spans_path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{SPANS_FILE}"


def _load(cfg: dict) -> dict:
    data = store.load_json(_path(cfg), {"schema": 1, "agents": {}})
    if not isinstance(data, dict) or not isinstance(data.get("agents"), dict):
        raise StoreError("agents store is malformed")
    return data


def _save(cfg: dict, data: dict) -> None:
    store.save_json(_path(cfg), data)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _agents_cfg(cfg: dict) -> dict:
    return cfg.get("agents") or {}


def max_depth(cfg: dict) -> int:
    return max(1, min(int(_agents_cfg(cfg).get("max_depth", 3)), 8))


def max_agents(cfg: dict) -> int:
    return max(1, min(int(_agents_cfg(cfg).get("max_agents", 50)), 200))


def agent_create_roles(cfg: dict) -> set[str]:
    raw = _agents_cfg(cfg).get("allow_agent_create_roles")
    if isinstance(raw, list) and raw:
        return {str(x) for x in raw if str(x) in ROLES}
    return {"worker", "planner"}


def log_event(cfg: dict, kind: str, **fields: Any) -> dict:
    rec = {"ts": _now(), "kind": kind, **fields}
    store.append_jsonl(_events_path(cfg), rec)
    return rec


def _load_spans(cfg: dict) -> dict:
    data = store.load_json(_spans_path(cfg), {"schema": 1, "spans": {}})
    if not isinstance(data, dict) or not isinstance(data.get("spans"), dict):
        raise StoreError("agent spans store is malformed")
    return data


def _save_spans(cfg: dict, data: dict) -> None:
    store.save_json(_spans_path(cfg), data)


def _prune_spans(data: dict) -> None:
    """Keep running spans + newest finished, capped per session."""
    by_sid: dict[str, list[str]] = {}
    for sid_key, row in data["spans"].items():
        if not isinstance(row, dict):
            continue
        sid = str(row.get("session_id") or "") or "_"
        by_sid.setdefault(sid, []).append(sid_key)
    drop: list[str] = []
    for ids in by_sid.values():
        if len(ids) <= MAX_SPANS_PER_SESSION:
            continue
        rows = [(i, data["spans"][i]) for i in ids]
        running = [i for i, r in rows if r.get("status") == "running"]
        rest = sorted(
            [(i, r) for i, r in rows if r.get("status") != "running"],
            key=lambda x: x[1].get("updated") or x[1].get("started") or "",
            reverse=True,
        )
        keep = set(running)
        for i, _ in rest:
            if len(keep) >= MAX_SPANS_PER_SESSION:
                break
            keep.add(i)
        for i, _ in rows:
            if i not in keep:
                drop.append(i)
    for i in drop:
        data["spans"].pop(i, None)


def oneliner(
    name: str,
    status: str,
    *,
    goal: str | None = None,
    tool: str | None = None,
    steps: int | None = None,
    error: str | None = None,
) -> str:
    """Compact status line for parent chat / session list."""
    label = (name or "agent").strip() or "agent"
    if status == "running":
        if tool:
            return f"{label}: {tool}…"
        g = (goal or "").strip()
        if g:
            return f"{label}: {g[:72]}{'…' if len(g) > 72 else ''}"
        return f"{label}: running…"
    if status == "error":
        err = (error or "failed").strip()
        return f"{label}: failed — {err[:60]}"
    extra = f" ({steps} step{'s' if steps != 1 else ''})" if steps is not None else ""
    return f"{label}: done{extra}"


def upsert_span(cfg: dict, span_id: str, **fields: Any) -> dict:
    """Create/update a session-scoped child span for UI monitoring."""
    sid = str(span_id or "").strip()
    if not sid:
        raise ValueError("span_id required")
    data = _load_spans(cfg)
    row = dict(data["spans"].get(sid) or {"span_id": sid})
    for k, v in fields.items():
        if v is not None:
            row[k] = v
    row["span_id"] = sid
    row["updated"] = _now()
    if not row.get("started"):
        row["started"] = row["updated"]
    data["spans"][sid] = row
    _prune_spans(data)
    _save_spans(cfg, data)
    return dict(row)


def get_span(cfg: dict, span_id: str) -> dict | None:
    return _load_spans(cfg)["spans"].get(span_id)


def _slim_span(row: dict) -> dict:
    return {
        "span_id": row.get("span_id"),
        "session_id": row.get("session_id"),
        "child_session_id": row.get("child_session_id"),
        "agent_id": row.get("agent_id"),
        "agent_name": row.get("agent_name") or "",
        "role": row.get("role") or "",
        "status": row.get("status") or "done",
        "summary": row.get("summary") or "",
        "goal": (row.get("goal") or "")[:200],
        "steps": row.get("steps"),
        "started": row.get("started"),
        "ended": row.get("ended"),
        "updated": row.get("updated"),
        "run_id": row.get("run_id"),
        "parent_span_id": row.get("parent_span_id"),
    }


def list_spans(
    cfg: dict,
    *,
    session_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    data = _load_spans(cfg)
    out = []
    for row in data["spans"].values():
        if not isinstance(row, dict):
            continue
        if session_id and row.get("session_id") != session_id:
            continue
        if status and row.get("status") != status:
            continue
        out.append(_slim_span(row))
    # Active first, then newest
    out.sort(key=lambda r: (
        0 if r.get("status") == "running" else 1,
        r.get("updated") or r.get("started") or "",
    ), reverse=False)
    # After status partition, newest within each: re-sort with running first
    running = [r for r in out if r.get("status") == "running"]
    done = [r for r in out if r.get("status") != "running"]
    done.sort(key=lambda r: r.get("updated") or r.get("started") or "", reverse=True)
    running.sort(key=lambda r: r.get("updated") or r.get("started") or "", reverse=True)
    merged = running + done
    return merged[: max(1, min(int(limit), 500))]


def spans_by_session(cfg: dict, *, per_session: int = 8) -> dict[str, list[dict]]:
    """session_id → slim spans (active + recent inactive) for chat list."""
    data = _load_spans(cfg)
    buckets: dict[str, list[dict]] = {}
    for row in data["spans"].values():
        if not isinstance(row, dict):
            continue
        sid = str(row.get("session_id") or "").strip()
        if not sid:
            continue
        buckets.setdefault(sid, []).append(_slim_span(row))
    out: dict[str, list[dict]] = {}
    n = max(1, min(int(per_session), MAX_SPANS_PER_SESSION))
    for sid, rows in buckets.items():
        running = [r for r in rows if r.get("status") == "running"]
        done = [r for r in rows if r.get("status") != "running"]
        done.sort(key=lambda r: r.get("updated") or "", reverse=True)
        running.sort(key=lambda r: r.get("updated") or "", reverse=True)
        out[sid] = (running + done)[:n]
    return out


def emit_child(cfg: dict, payload: dict) -> None:
    """Push a child_agent frame to the parent SSE stream if wired."""
    fn = cfg.get("_emit")
    if callable(fn):
        try:
            fn({"child_agent": payload})
        except Exception:
            pass


def _public(spec: dict) -> dict:
    return {k: v for k, v in spec.items()}


def list_agents(cfg: dict, *, include_archived: bool = False) -> list[dict]:
    data = _load(cfg)
    out = []
    for a in data["agents"].values():
        if not include_archived and a.get("status") == "archived":
            continue
        out.append(_public(a))
    out.sort(key=lambda x: x.get("updated") or x.get("created") or "", reverse=True)
    return out


def get_agent(cfg: dict, agent_id: str) -> dict | None:
    return _load(cfg)["agents"].get(agent_id)


def _normalize_tools(tools: Any) -> list[str] | None:
    if tools is None:
        return None
    if not isinstance(tools, list):
        raise ValueError("tools must be a list of names or null")
    return sorted({str(t).strip() for t in tools if str(t).strip()})


def _normalize_groups(groups: Any) -> list[str] | None:
    if groups is None:
        return None
    if not isinstance(groups, list):
        raise ValueError("groups must be a list or null")
    return sorted({str(g).strip() for g in groups if str(g).strip()})


def _normalize_disabled(disabled: Any) -> list[str]:
    if not disabled:
        return []
    if not isinstance(disabled, list):
        raise ValueError("disabled must be a list")
    return sorted({str(x).strip() for x in disabled if str(x).strip()})


def _policy_for(role: str, patch: dict | None = None) -> dict[str, bool]:
    base = dict(ROLE_DEFAULTS.get(role, ROLE_DEFAULTS["worker"]))
    if isinstance(patch, dict):
        for k in ("may_write", "may_spawn", "may_manage_agents"):
            if k in patch:
                base[k] = bool(patch[k])
    return base


def create_agent(
    cfg: dict,
    *,
    name: str,
    role: str = "worker",
    summary: str = "",
    system_addon: str = "",
    tools: list[str] | None = None,
    groups: list[str] | None = None,
    disabled: list[str] | None = None,
    inherits_from: str | None = None,
    budgets: dict | None = None,
    policy: dict | None = None,
    created_by: str = "user",
    force_active: bool = False,
) -> dict:
    """Create an AgentSpec. Judge roles default to pending unless force_active (human API)."""
    if not _agents_cfg(cfg).get("enabled", True):
        raise StoreError("agents disabled in config")
    name = (name or "").strip()[:80]
    if not name:
        raise ValueError("name required")
    role = (role or "worker").strip()
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")

    data = _load(cfg)
    active_n = sum(1 for a in data["agents"].values() if a.get("status") != "archived")
    if active_n >= max_agents(cfg):
        raise StoreError(f"agent limit reached ({max_agents(cfg)})")

    if inherits_from:
        parent_spec = data["agents"].get(inherits_from)
        if not parent_spec or parent_spec.get("status") == "archived":
            raise ValueError(f"inherits_from not found: {inherits_from}")

    # Agent-created: only allow listed roles; judges always pending until human approve
    is_agent = created_by.startswith("agent:")
    if is_agent:
        if role in JUDGE_ROLES:
            status = "pending"
        elif role not in agent_create_roles(cfg):
            raise ValueError(
                f"role {role!r} not creatable by agents; allowed={sorted(agent_create_roles(cfg))}"
            )
        else:
            status = "active"
    else:
        # Human CRUD activates immediately (operators own approval).
        status = "active"

    aid = uuid.uuid4().hex[:12]
    now = _now()
    pol = _policy_for(role, policy)
    # Never let an agent-created spec claim more rights than role defaults allow upward
    if is_agent:
        defaults = ROLE_DEFAULTS.get(role, ROLE_DEFAULTS["worker"])
        for k, v in list(pol.items()):
            pol[k] = bool(v) and bool(defaults.get(k, False))

    bud = {}
    if isinstance(budgets, dict):
        if "max_steps" in budgets and budgets["max_steps"] is not None:
            bud["max_steps"] = max(1, min(int(budgets["max_steps"]), 200))
        if "max_result_chars" in budgets and budgets["max_result_chars"] is not None:
            bud["max_result_chars"] = max(500, min(int(budgets["max_result_chars"]), 100_000))

    spec = {
        "id": aid,
        "name": name,
        "role": role,
        "summary": (summary or "")[:400],
        "system_addon": (system_addon or "")[:4000],
        "tools": _normalize_tools(tools),
        "groups": _normalize_groups(groups),
        "disabled": _normalize_disabled(disabled),
        "inherits_from": inherits_from or None,
        "budgets": bud,
        "policy": pol,
        "created_by": created_by,
        "status": status,
        "created": now,
        "updated": now,
    }
    data["agents"][aid] = spec
    _save(cfg, data)
    log_event(cfg, "agent.create", agent_id=aid, name=name, role=role,
              status=status, created_by=created_by)
    return _public(spec)


def update_agent(cfg: dict, agent_id: str, patch: dict, *, actor: str = "user") -> dict:
    data = _load(cfg)
    spec = data["agents"].get(agent_id)
    if not spec:
        raise KeyError(f"no agent {agent_id}")
    if spec.get("status") == "archived":
        raise StoreError("cannot update archived agent")

    is_agent = actor.startswith("agent:")
    if "role" in patch and patch["role"] != spec["role"]:
        if is_agent:
            raise ValueError("agents cannot change role")
        role = str(patch["role"])
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        spec["role"] = role
        spec["policy"] = _policy_for(role, patch.get("policy") if isinstance(patch.get("policy"), dict) else spec.get("policy"))

    for key in ("name", "summary", "system_addon"):
        if key in patch and patch[key] is not None:
            lim = 80 if key == "name" else (400 if key == "summary" else 4000)
            val = str(patch[key]).strip()[:lim]
            if key == "name" and not val:
                raise ValueError("name required")
            spec[key] = val

    if "tools" in patch:
        spec["tools"] = _normalize_tools(patch["tools"])
    if "groups" in patch:
        spec["groups"] = _normalize_groups(patch["groups"])
    if "disabled" in patch:
        spec["disabled"] = _normalize_disabled(patch["disabled"])
    if "inherits_from" in patch:
        inh = patch["inherits_from"]
        if inh:
            if inh == agent_id or not data["agents"].get(str(inh)):
                raise ValueError("invalid inherits_from")
            spec["inherits_from"] = str(inh)
        else:
            spec["inherits_from"] = None
    if "budgets" in patch and isinstance(patch["budgets"], dict):
        bud = dict(spec.get("budgets") or {})
        b = patch["budgets"]
        if "max_steps" in b:
            bud["max_steps"] = max(1, min(int(b["max_steps"]), 200)) if b["max_steps"] is not None else bud.pop("max_steps", None)
        if "max_result_chars" in b:
            if b["max_result_chars"] is None:
                bud.pop("max_result_chars", None)
            else:
                bud["max_result_chars"] = max(500, min(int(b["max_result_chars"]), 100_000))
        spec["budgets"] = {k: v for k, v in bud.items() if v is not None}
    if "policy" in patch and isinstance(patch["policy"], dict) and not is_agent:
        spec["policy"] = _policy_for(spec["role"], {**(spec.get("policy") or {}), **patch["policy"]})
    elif "policy" in patch and is_agent:
        # agents may only tighten
        cur = dict(spec.get("policy") or {})
        for k in ("may_write", "may_spawn", "may_manage_agents"):
            if k in patch["policy"] and patch["policy"][k] is False:
                cur[k] = False
        spec["policy"] = cur

    spec["updated"] = _now()
    data["agents"][agent_id] = spec
    _save(cfg, data)
    log_event(cfg, "agent.update", agent_id=agent_id, actor=actor)
    return _public(spec)


def archive_agent(cfg: dict, agent_id: str, *, actor: str = "user") -> dict:
    data = _load(cfg)
    spec = data["agents"].get(agent_id)
    if not spec:
        raise KeyError(f"no agent {agent_id}")
    spec["status"] = "archived"
    spec["updated"] = _now()
    data["agents"][agent_id] = spec
    _save(cfg, data)
    log_event(cfg, "agent.archive", agent_id=agent_id, actor=actor)
    return _public(spec)


def approve_agent(cfg: dict, agent_id: str, *, actor: str = "user") -> dict:
    """Human-only activation for pending (usually judge) agents."""
    if actor.startswith("agent:"):
        raise StoreError("only humans can approve judge/pending agents")
    data = _load(cfg)
    spec = data["agents"].get(agent_id)
    if not spec:
        raise KeyError(f"no agent {agent_id}")
    if spec.get("status") == "archived":
        raise StoreError("archived")
    spec["status"] = "active"
    spec["updated"] = _now()
    data["agents"][agent_id] = spec
    _save(cfg, data)
    log_event(cfg, "agent.approve", agent_id=agent_id, actor=actor)
    return _public(spec)


# ── Effective config / inheritance ────────────────────────────────────

def root_effective(cfg: dict) -> dict:
    """Authority of the main chat agent (no _agent context)."""
    from .tools.discovery import disabled_names, enabled_groups

    groups = sorted(enabled_groups(cfg) - {"discovery"})
    return {
        "agent_id": "main",
        "role": "worker",
        "groups": groups,
        "disabled": sorted(disabled_names(cfg)),
        "tools": None,  # all tools in enabled groups
        "max_steps": int((cfg.get("envelope") or {}).get("max_steps_per_task", 20)),
        "max_result_chars": int((cfg.get("tools") or {}).get("max_result_chars", 8000)),
        "may_write": True,
        "may_spawn": True,
        "may_manage_agents": True,
        "system_addon": "",
        "depth": 0,
    }


def current_effective(cfg: dict) -> dict:
    eff = cfg.get("_agent_effective")
    if isinstance(eff, dict) and eff:
        return eff
    return root_effective(cfg)


def _resolve_spec_chain(cfg: dict, spec: dict) -> dict:
    """Merge inherits_from chain (templates); child fields win; lists intersect."""
    data = _load(cfg)
    chain: list[dict] = []
    seen: set[str] = set()
    cur: dict | None = spec
    while cur:
        chain.append(cur)
        inh = cur.get("inherits_from")
        if not inh or inh in seen:
            break
        seen.add(inh)
        cur = data["agents"].get(inh)
        if not cur or cur.get("status") == "archived":
            break
    chain.reverse()  # root template → leaf spec

    tools: list[str] | None = None
    groups: list[str] | None = None
    disabled: set[str] = set()
    budgets: dict = {}
    policy: dict[str, bool] = {}
    addon_parts: list[str] = []

    for s in chain:
        if s.get("tools") is not None:
            tset = set(s["tools"])
            tools = sorted(tset if tools is None else (set(tools) & tset))
        if s.get("groups") is not None:
            gset = set(s["groups"])
            groups = sorted(gset if groups is None else (set(groups) & gset))
        disabled |= set(s.get("disabled") or [])
        for k, v in (s.get("budgets") or {}).items():
            if v is None:
                continue
            if k not in budgets:
                budgets[k] = v
            else:
                budgets[k] = min(int(budgets[k]), int(v))
        pol = s.get("policy") or {}
        if not policy:
            policy = dict(pol)
        else:
            for k in ("may_write", "may_spawn", "may_manage_agents"):
                policy[k] = bool(policy.get(k)) and bool(pol.get(k, True))
        if s.get("system_addon"):
            addon_parts.append(str(s["system_addon"]))

    role = spec.get("role") or "worker"
    if not policy:
        policy = _policy_for(role)
    return {
        "tools": tools,
        "groups": groups,
        "disabled": sorted(disabled),
        "budgets": budgets,
        "policy": policy,
        "system_addon": "\n\n".join(addon_parts),
        "role": role,
        "name": spec.get("name") or spec.get("id"),
        "id": spec.get("id"),
    }


def inherit_effective(parent_eff: dict, spec: dict, cfg: dict) -> dict:
    """Intersect parent runtime authority with resolved AgentSpec (never widen)."""
    resolved = _resolve_spec_chain(cfg, spec)
    parent_groups = set(parent_eff.get("groups") or [])
    parent_disabled = set(parent_eff.get("disabled") or [])

    if resolved["groups"] is None:
        groups = sorted(parent_groups)
    else:
        groups = sorted(parent_groups & set(resolved["groups"]))

    disabled = sorted(parent_disabled | set(resolved["disabled"]))

    # Tool allowlist: parent None = all in groups; intersect
    parent_tools = parent_eff.get("tools")
    child_tools = resolved["tools"]
    if parent_tools is None and child_tools is None:
        tools = None
    elif parent_tools is None:
        tools = sorted(child_tools or [])
    elif child_tools is None:
        tools = sorted(parent_tools)
    else:
        tools = sorted(set(parent_tools) & set(child_tools))

    parent_steps = int(parent_eff.get("max_steps") or 20)
    child_steps = resolved["budgets"].get("max_steps")
    max_steps = min(parent_steps, int(child_steps)) if child_steps else parent_steps

    parent_chars = int(parent_eff.get("max_result_chars") or 8000)
    child_chars = resolved["budgets"].get("max_result_chars")
    max_chars = min(parent_chars, int(child_chars)) if child_chars else parent_chars

    pol = resolved["policy"]
    return {
        "agent_id": resolved["id"],
        "name": resolved["name"],
        "role": resolved["role"],
        "groups": groups,
        "disabled": disabled,
        "tools": tools,
        "max_steps": max_steps,
        "max_result_chars": max_chars,
        "may_write": bool(parent_eff.get("may_write")) and bool(pol.get("may_write")),
        "may_spawn": bool(parent_eff.get("may_spawn")) and bool(pol.get("may_spawn")),
        "may_manage_agents": bool(parent_eff.get("may_manage_agents")) and bool(pol.get("may_manage_agents")),
        "system_addon": resolved["system_addon"],
        "depth": int(parent_eff.get("depth") or 0) + 1,
        "parent_agent_id": parent_eff.get("agent_id"),
    }


def apply_effective(cfg: dict, eff: dict) -> dict:
    """Mutate cfg in place with effective overlays used by discovery/runtime."""
    cfg["_agent_effective"] = eff
    cfg["_agent"] = {
        "id": eff.get("agent_id"),
        "role": eff.get("role"),
        "depth": eff.get("depth", 0),
        "parent_id": eff.get("parent_agent_id"),
        "name": eff.get("name"),
    }
    # Tighten envelope / tools without loosening global defaults for siblings
    env = dict(cfg.get("envelope") or {})
    env["max_steps_per_task"] = int(eff["max_steps"])
    cfg["envelope"] = env
    tools = dict(cfg.get("tools") or {})
    tools["max_result_chars"] = int(eff["max_result_chars"])
    # Group flags: only enable intersection; discovery always on if parent had tools
    groups = dict(tools.get("groups") or {})
    allowed = set(eff.get("groups") or [])
    for gid in list(groups.keys()):
        if gid == "discovery":
            continue
        groups[gid] = gid in allowed
    for gid in allowed:
        groups[gid] = True
    tools["groups"] = groups
    # Union disabled
    tools["disabled"] = sorted(set(tools.get("disabled") or []) | set(eff.get("disabled") or []))
    # Disable packs whose group is outside the inherited allow-set
    try:
        from .tools.langchain_bridge import PACKS
        packs = dict(tools.get("packs") or {})
        for pid, meta in PACKS.items():
            if meta.get("group") not in allowed:
                packs[pid] = False
        tools["packs"] = packs
    except Exception:
        pass
    cfg["tools"] = tools
    return cfg


def make_child_cfg(parent_cfg: dict, spec: dict) -> tuple[dict, dict]:
    """Deep-copy parent cfg, apply inherited effective authority for `spec`."""
    parent_eff = current_effective(parent_cfg)
    if not parent_eff.get("may_spawn"):
        raise StoreError("parent agent may not spawn children")
    if int(parent_eff.get("depth") or 0) >= max_depth(parent_cfg):
        raise StoreError(f"max agent depth {max_depth(parent_cfg)} reached")
    if spec.get("status") != "active":
        raise StoreError(f"agent {spec.get('id')} is {spec.get('status')}, not active")

    child = copy.deepcopy(parent_cfg)
    # Drop ephemeral turn state; keep paths
    child.pop("_tool_session", None)
    for k in list(child.keys()):
        if k.startswith("_") and k not in ("_root", "_config_path", "_agent", "_agent_effective"):
            if k in ("_tool_session",):
                child.pop(k, None)

    eff = inherit_effective(parent_eff, spec, parent_cfg)
    apply_effective(child, eff)
    child.pop("_tool_session", None)
    return child, eff


def can_call_tool(cfg: dict, name: str) -> tuple[bool, str]:
    """Extra agent-policy checks beyond discovery.is_callable."""
    eff = cfg.get("_agent_effective")
    if not isinstance(eff, dict):
        return True, ""
    if name in WRITE_TOOLS and not eff.get("may_write", True):
        return False, "agent may_write=false"
    allow = eff.get("tools")
    if isinstance(allow, list):
        # discovery meta-tools always allowed if discovery group on
        from .catalog import get_tool
        spec = get_tool(name)
        if spec and spec.discovery:
            return True, ""
        if name not in allow:
            return False, "tool not in agent allowlist"
    if name in ("create_agent", "update_agent", "archive_agent", "run_agent", "list_agents", "get_agent"):
        if name in ("create_agent", "update_agent", "archive_agent") and not eff.get("may_manage_agents", True):
            return False, "agent may_manage_agents=false"
        if name == "run_agent" and not eff.get("may_spawn", True):
            return False, "agent may_spawn=false"
    return True, ""


def build_child_system(cfg: dict, parent_system: str, eff: dict) -> str:
    role = eff.get("role") or "worker"
    name = eff.get("name") or eff.get("agent_id")
    addon = (eff.get("system_addon") or "").strip()
    rules = (
        f"You are specialized agent `{name}` (role={role}, id={eff.get('agent_id')}). "
        f"You inherit all harness rules from your parent (depth={eff.get('depth')}). "
        f"Rights: write={eff.get('may_write')} spawn={eff.get('may_spawn')} "
        f"manage_agents={eff.get('may_manage_agents')}. "
        "Do not claim capabilities outside your tools. Stay on the assigned goal.\n\n"
    )
    body = parent_system
    if addon:
        body = f"{body}\n\nAgent specialization:\n{addon}"
    return rules + body


def run_specialized(
    parent_cfg: dict,
    agent_id: str,
    goal: str,
    *,
    on_event=None,
) -> dict:
    """Spawn a child agent span: inherit parent rules, run stdlib loop, return result."""
    from . import harness
    from .tools.runtime import run_agent_stdlib

    spec = get_agent(parent_cfg, agent_id)
    if not spec:
        raise KeyError(f"no agent {agent_id}")

    child_cfg, eff = make_child_cfg(parent_cfg, spec)
    run_id = (parent_cfg.get("_agent") or {}).get("run_id") or uuid.uuid4().hex[:12]
    span_id = uuid.uuid4().hex[:12]
    session_id = str(parent_cfg.get("_session_id") or "").strip() or None
    parent_span = (parent_cfg.get("_agent") or {}).get("span_id")
    agent_name = str(spec.get("name") or agent_id)
    role = str(eff.get("role") or spec.get("role") or "worker")
    goal_txt = (goal or "").strip()

    child_cfg["_agent"] = {
        **(child_cfg.get("_agent") or {}),
        "run_id": run_id,
        "span_id": span_id,
        "id": agent_id,
    }
    # Relay child emits up to parent stream
    child_cfg["_emit"] = parent_cfg.get("_emit")

    child_session_id: str | None = None
    if session_id:
        from . import sessions as _sessions
        child_session_id = _sessions.create(
            parent_cfg,
            title=agent_name[:80] or "agent",
            parent=session_id,
            span_id=span_id,
            agent_id=agent_id,
            kind="agent",
        )
        # Parent session stays the span index key; child holds the transcript.
        child_cfg["_session_id"] = child_session_id

    summary = oneliner(agent_name, "running", goal=goal_txt)
    span_row = {
        "session_id": session_id,
        "child_session_id": child_session_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "role": role,
        "status": "running",
        "summary": summary,
        "goal": goal_txt[:500],
        "run_id": run_id,
        "parent_span_id": parent_span,
        "steps": 0,
    }
    upsert_span(parent_cfg, span_id, **span_row)
    child_payload = {
        "span_id": span_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "role": role,
        "status": "running",
        "summary": summary,
        "goal": goal_txt[:200],
        "run_id": run_id,
        "session_id": session_id,
        "child_session_id": child_session_id,
    }
    emit_child(parent_cfg, child_payload)

    log_event(
        parent_cfg, "span.start",
        run_id=run_id, span_id=span_id,
        agent_id=agent_id, role=role,
        parent_agent_id=eff.get("parent_agent_id"),
        depth=eff.get("depth"),
        goal=goal_txt[:500],
        session_id=session_id,
    )

    parent_system = harness.build_system(parent_cfg)
    system = build_child_system(child_cfg, parent_system, eff)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": goal_txt or "(empty goal)"},
    ]

    def _relay(ev: dict) -> None:
        if not isinstance(ev, dict):
            return
        # Live oneliner from child tool activity
        if ev.get("type") == "tool_call" and ev.get("name"):
            tool_name = str(ev["name"])
            line = oneliner(agent_name, "running", tool=tool_name, goal=goal_txt)
            upsert_span(parent_cfg, span_id, summary=line, status="running")
            emit_child(parent_cfg, {
                **child_payload,
                "status": "running",
                "summary": line,
                "tool": tool_name,
                "step": ev.get("step"),
            })
        if on_event:
            on_event({**ev, "span_id": span_id, "agent_id": agent_id, "run_id": run_id})

    try:
        reply, final_msgs, meta = run_agent_stdlib(child_cfg, messages, on_event=_relay)
        gate = harness.check_reply(child_cfg, reply)
        if isinstance(gate, dict):
            gate = {
                **gate,
                "agent": {
                    "id": agent_id,
                    "role": role,
                    "span_id": span_id,
                    "run_id": run_id,
                    "steps": meta.get("steps"),
                    "tools": meta.get("tools"),
                    "llm_stats": meta.get("llm_stats"),
                },
            }
        steps = meta.get("steps")
        done_line = oneliner(agent_name, "done", steps=steps if isinstance(steps, int) else None)
        if child_session_id:
            from . import sessions as _sessions
            try:
                _sessions.write_agent_transcript(
                    parent_cfg, child_session_id, final_msgs,
                    gate=gate if isinstance(gate, dict) else None,
                    tool_events=meta.get("events") if isinstance(meta, dict) else None,
                )
            except Exception:
                pass
        upsert_span(
            parent_cfg, span_id,
            status="done", summary=done_line, steps=steps,
            ended=_now(), child_session_id=child_session_id,
        )
        emit_child(parent_cfg, {
            **child_payload,
            "status": "done",
            "summary": done_line,
            "steps": steps,
            "child_session_id": child_session_id,
        })
        log_event(
            parent_cfg, "span.end",
            run_id=run_id, span_id=span_id,
            agent_id=agent_id, ok=True,
            steps=steps,
            reply_chars=len(reply or ""),
            session_id=session_id,
            child_session_id=child_session_id,
        )
        return {
            "ok": True,
            "reply": reply,
            "gate": gate,
            "meta": meta,
            "effective": eff,
            "run_id": run_id,
            "span_id": span_id,
            "child_session_id": child_session_id,
            "agent": _public(spec),
        }
    except Exception as e:
        err_line = oneliner(agent_name, "error", error=str(e))
        if child_session_id:
            from . import sessions as _sessions
            try:
                _sessions.write_agent_transcript(
                    parent_cfg, child_session_id, messages,
                    tool_events=None,
                )
            except Exception:
                pass
        upsert_span(
            parent_cfg, span_id,
            status="error", summary=err_line, ended=_now(),
            error=str(e)[:300], child_session_id=child_session_id,
        )
        emit_child(parent_cfg, {
            **child_payload,
            "status": "error",
            "summary": err_line,
            "error": str(e)[:200],
            "child_session_id": child_session_id,
        })
        log_event(
            parent_cfg, "span.end",
            run_id=run_id, span_id=span_id,
            agent_id=agent_id, ok=False,
            error=str(e)[:300],
            session_id=session_id,
            child_session_id=child_session_id,
        )
        raise


def actor_id(cfg: dict) -> str:
    ag = cfg.get("_agent") or {}
    if ag.get("id") and ag["id"] != "main":
        return f"agent:{ag['id']}"
    return "agent:main"


# ── Tool handlers ─────────────────────────────────────────────────────

def handle_list_agents(cfg: dict, args: dict):
    from .tools.base import ToolResult, dump_json
    include = bool(args.get("include_archived"))
    rows = list_agents(cfg, include_archived=include)
    slim = [{
        "id": a["id"], "name": a["name"], "role": a["role"],
        "status": a["status"], "summary": a.get("summary") or "",
        "created_by": a.get("created_by"),
    } for a in rows]
    return ToolResult(True, dump_json({"agents": slim, "count": len(slim)}))


def handle_get_agent(cfg: dict, args: dict):
    from .tools.base import ToolResult, dump_json
    aid = str(args.get("id") or "").strip()
    if not aid:
        return ToolResult(False, "id required")
    spec = get_agent(cfg, aid)
    if not spec:
        return ToolResult(False, f"no agent {aid}")
    parent_eff = current_effective(cfg)
    try:
        eff = inherit_effective(parent_eff, spec, cfg) if spec.get("status") == "active" else None
    except Exception:
        eff = None
    return ToolResult(True, dump_json({"agent": spec, "effective_if_spawned": eff}))


def handle_create_agent(cfg: dict, args: dict):
    from .tools.base import ToolResult, dump_json
    eff = current_effective(cfg)
    if not eff.get("may_manage_agents"):
        return ToolResult(False, "may_manage_agents=false")
    try:
        # Tighten tools/groups to parent ceiling before persist
        tools = args.get("tools")
        groups = args.get("groups")
        if tools is not None and eff.get("tools") is not None:
            tools = sorted(set(tools) & set(eff["tools"]))
        if groups is not None:
            groups = sorted(set(groups) & set(eff.get("groups") or []))
        spec = create_agent(
            cfg,
            name=str(args.get("name") or ""),
            role=str(args.get("role") or "worker"),
            summary=str(args.get("summary") or ""),
            system_addon=str(args.get("system_addon") or ""),
            tools=tools,
            groups=groups,
            disabled=args.get("disabled"),
            inherits_from=(str(args["inherits_from"]) if args.get("inherits_from") else None),
            budgets=args.get("budgets") if isinstance(args.get("budgets"), dict) else None,
            policy=args.get("policy") if isinstance(args.get("policy"), dict) else None,
            created_by=actor_id(cfg),
        )
    except (ValueError, StoreError) as e:
        return ToolResult(False, str(e))
    note = None
    if spec.get("status") == "pending":
        note = "pending human approval before run_agent can use this agent"
    return ToolResult(True, dump_json({"agent": spec, "note": note}))


def handle_update_agent(cfg: dict, args: dict):
    from .tools.base import ToolResult, dump_json
    eff = current_effective(cfg)
    if not eff.get("may_manage_agents"):
        return ToolResult(False, "may_manage_agents=false")
    aid = str(args.get("id") or "").strip()
    if not aid:
        return ToolResult(False, "id required")
    patch = {k: v for k, v in args.items() if k != "id" and v is not None}
    try:
        if "tools" in patch and eff.get("tools") is not None and isinstance(patch["tools"], list):
            patch["tools"] = sorted(set(patch["tools"]) & set(eff["tools"]))
        if "groups" in patch and isinstance(patch["groups"], list):
            patch["groups"] = sorted(set(patch["groups"]) & set(eff.get("groups") or []))
        spec = update_agent(cfg, aid, patch, actor=actor_id(cfg))
    except (KeyError, ValueError, StoreError) as e:
        return ToolResult(False, str(e))
    return ToolResult(True, dump_json({"agent": spec}))


def handle_archive_agent(cfg: dict, args: dict):
    from .tools.base import ToolResult, dump_json
    eff = current_effective(cfg)
    if not eff.get("may_manage_agents"):
        return ToolResult(False, "may_manage_agents=false")
    aid = str(args.get("id") or "").strip()
    if not aid:
        return ToolResult(False, "id required")
    try:
        spec = archive_agent(cfg, aid, actor=actor_id(cfg))
    except (KeyError, StoreError) as e:
        return ToolResult(False, str(e))
    return ToolResult(True, dump_json({"agent": spec}))


def handle_run_agent(cfg: dict, args: dict):
    from .tools.base import ToolResult, dump_json
    eff = current_effective(cfg)
    if not eff.get("may_spawn"):
        return ToolResult(False, "may_spawn=false")
    aid = str(args.get("id") or args.get("agent_id") or "").strip()
    goal = str(args.get("goal") or args.get("prompt") or "").strip()
    if not aid:
        return ToolResult(False, "id required")
    if not goal:
        return ToolResult(False, "goal required")
    try:
        result = run_specialized(cfg, aid, goal)
    except (KeyError, StoreError, ValueError) as e:
        return ToolResult(False, str(e))
    except Exception as e:
        return ToolResult(False, f"{type(e).__name__}: {e}")
    # Truncate reply for tool channel; full in meta for parent UI if needed
    reply = result.get("reply") or ""
    payload = {
        "ok": True,
        "agent_id": aid,
        "span_id": result.get("span_id"),
        "run_id": result.get("run_id"),
        "role": (result.get("effective") or {}).get("role"),
        "steps": (result.get("meta") or {}).get("steps"),
        "reply": reply[:6000],
        "gate_ok": (result.get("gate") or {}).get("ok"),
        "tools": (result.get("meta") or {}).get("tools") or [],
    }
    return ToolResult(True, dump_json(payload), {"span_id": result.get("span_id")})
