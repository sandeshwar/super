"""Discovery meta-tool handlers + activation state for a turn.

Unified flow for built-in and third-party tools:
  search_tools / list_tool_groups → describe_tool → activate_tools → call
"""

from __future__ import annotations

from .base import ToolResult, dump_json
from .catalog import GROUPS, TOOLS, get_tool, search_tools


# Per-turn activation lives on cfg["_tool_session"] (ephemeral, not persisted).
def _session(cfg: dict) -> dict:
    s = cfg.setdefault("_tool_session", {"activated": set(), "pack_groups": set()})
    if not isinstance(s.get("activated"), set):
        s["activated"] = set(s.get("activated") or [])
    if not isinstance(s.get("pack_groups"), set):
        s["pack_groups"] = set(s.get("pack_groups") or [])
    return s


def enabled_groups(cfg: dict) -> set[str]:
    groups = (cfg.get("tools") or {}).get("groups") or {}
    out = set()
    for gid in GROUPS:
        if gid == "discovery":
            out.add(gid)
            continue
        # external packs default off unless explicitly enabled
        if gid.startswith("lc_") or gid == "crewai":
            default = False
        elif gid == "mcp":
            try:
                from .mcp_bridge import mcp_group_enabled
                default = mcp_group_enabled(cfg)
            except Exception:
                default = False
        else:
            default = gid != "web"
        if bool(groups.get(gid, default)):
            out.add(gid)
    # packs config also enables their groups
    try:
        from .langchain_bridge import PACKS
        packs_cfg = (cfg.get("tools") or {}).get("packs") or {}
        for pid, meta in PACKS.items():
            if bool(packs_cfg.get(pid, meta.get("default", False))):
                out.add(meta["group"])
    except Exception:
        pass
    # packs loaded this turn via activate/describe/load are usable without Settings toggle
    out |= set(_session(cfg).get("pack_groups") or ())
    return out


def disabled_names(cfg: dict) -> set[str]:
    return {str(x) for x in ((cfg.get("tools") or {}).get("disabled") or [])}


def discoverable_groups(cfg: dict) -> set[str]:
    """Groups the agent may browse (enabled builtins + all pack categories with stubs)."""
    eg = enabled_groups(cfg)
    out = set(eg)
    for spec in TOOLS.values():
        if spec.lazy_pack or (spec.group.startswith("lc_") or spec.group == "crewai" or spec.group == "mcp"):
            out.add(spec.group)
    return out


def is_callable(cfg: dict, name: str) -> bool:
    spec = get_tool(name)
    if not spec:
        return False
    if name in disabled_names(cfg):
        return False
    if spec.lazy_pack:
        return False  # must activate (materialize) first
    if spec.group not in enabled_groups(cfg) and not spec.discovery:
        return False
    tools_cfg = cfg.get("tools") or {}
    if not tools_cfg.get("enabled", True):
        return False
    try:
        from .. import agents as _agents
        ok, _ = _agents.can_call_tool(cfg, name)
        if not ok:
            return False
    except Exception:
        pass
    if tools_cfg.get("discovery", True):
        if spec.discovery:
            return True
        return name in _session(cfg)["activated"]
    # discovery off: all enabled-group tools callable
    return True


def schemas_for_llm(cfg: dict) -> list[dict]:
    """Minimal tool schemas for the model — discovery set or all enabled."""
    tools_cfg = cfg.get("tools") or {}
    if not tools_cfg.get("enabled", True):
        return []
    discovery = bool(tools_cfg.get("discovery", True))
    activated = _session(cfg)["activated"]
    out: list[dict] = []
    for spec in TOOLS.values():
        if spec.lazy_pack:
            continue  # never expose stub schemas directly
        if discovery:
            if spec.discovery or spec.name in activated:
                if spec.name not in disabled_names(cfg):
                    out.append(spec.openai_schema())
        elif is_callable(cfg, spec.name):
            out.append(spec.openai_schema())
    return out


def _row(spec) -> dict:
    if spec.lazy_pack or spec.group.startswith("lc_") or spec.group == "crewai":
        source = "pack"
    elif spec.group == "mcp":
        source = "mcp"
    else:
        source = "builtin"
    return {
        "name": spec.name,
        "group": spec.group,
        "summary": spec.summary,
        "risk": spec.risk,
        "source": source,
        "lazy": bool(spec.lazy_pack),
    }


def handle_search_tools(cfg: dict, args: dict) -> ToolResult:
    try:
        from .langchain_bridge import ensure_bridge
        ensure_bridge(cfg)
    except Exception:
        pass
    query = str(args.get("query") or "")
    group = args.get("group") or args.get("category") or args.get("type")
    limit = int(args.get("limit") or 12)
    hits = search_tools(
        query,
        group=str(group) if group else None,
        enabled_groups=enabled_groups(cfg),
        disabled=disabled_names(cfg),
        limit=limit,
        include_lazy=True,
    )
    rows = [_row(t) for t in hits]
    tip = (
        "Next: describe_tool on candidates you like, then activate_tools with those names, "
        "then call them. Built-in and third-party tools use the same flow."
    )
    return ToolResult(True, dump_json({"results": rows, "tip": tip}), {"count": len(rows)})


def handle_list_groups(cfg: dict, args: dict) -> ToolResult:
    try:
        from .langchain_bridge import ensure_bridge
        ensure_bridge(cfg)
    except Exception:
        pass
    eg = enabled_groups(cfg)
    browse = discoverable_groups(cfg)
    rows = []
    for gid, meta in GROUPS.items():
        if gid == "discovery":
            continue
        if gid not in browse and gid not in eg:
            # still show empty known groups? skip noise
            members = [t for t in TOOLS.values() if t.group == gid]
            if not members:
                continue
        members = [
            t for t in TOOLS.values()
            if t.group == gid and t.name not in disabled_names(cfg) and not t.discovery
        ]
        if not members and gid not in eg:
            continue
        rows.append({
            "id": gid,
            "title": meta.get("title") or gid,
            "blurb": meta.get("blurb") or "",
            "enabled": gid in eg,
            "discoverable": True,
            "tool_count": len(members),
            "tools": [t.name for t in members],
        })
    tip = "Use search_tools with a keyword, or group=<id>, then describe_tool / activate_tools."
    return ToolResult(True, dump_json({"groups": rows, "tip": tip}))


def handle_describe_tool(cfg: dict, args: dict) -> ToolResult:
    name = str(args.get("name") or "").strip()
    if not name:
        return ToolResult(False, "name required")
    try:
        from .langchain_bridge import ensure_bridge, ensure_tool_materialized
        ensure_bridge(cfg)
        ok, msg, spec = ensure_tool_materialized(cfg, name)
        if not ok or not spec:
            return ToolResult(False, msg or f"unknown tool: {name}")
    except Exception as e:
        spec = get_tool(name)
        if not spec:
            return ToolResult(False, f"unknown tool: {name} ({e})")
        if spec.lazy_pack:
            return ToolResult(False, f"could not load tool: {name} ({e})")

    if spec.name in disabled_names(cfg):
        return ToolResult(False, f"tool disabled in settings: {name}")
    if spec.group not in enabled_groups(cfg) and not spec.discovery:
        return ToolResult(False, f"tool disabled in settings: {name}")

    if spec.group.startswith("lc_") or spec.group == "crewai":
        source = "pack"
    elif spec.group == "mcp":
        source = "mcp"
    else:
        source = "builtin"
    return ToolResult(True, dump_json({
        "name": spec.name,
        "group": spec.group,
        "summary": spec.summary,
        "description": spec.description,
        "risk": spec.risk,
        "parameters": spec.parameters,
        "source": source,
        "ready": True,
    }))


def handle_activate_tools(cfg: dict, args: dict) -> ToolResult:
    names = _coerce_tool_names(args)
    if not names:
        return ToolResult(False, "names must be a non-empty list (or name=…)")
    try:
        from .langchain_bridge import ensure_bridge, ensure_tool_materialized
        ensure_bridge(cfg)
    except Exception:
        ensure_tool_materialized = None  # type: ignore
    max_act = int((cfg.get("tools") or {}).get("max_activated", 8))
    sess = _session(cfg)
    activated = sess["activated"]
    added, skipped = [], []
    for raw in names:
        name = str(raw).strip()
        if ensure_tool_materialized is not None:
            ok, msg, spec = ensure_tool_materialized(cfg, name)
            if not ok or not spec:
                skipped.append({"name": name, "reason": msg or "unknown"})
                continue
        else:
            spec = get_tool(name)
            if not spec or spec.discovery:
                skipped.append({"name": name, "reason": "unknown"})
                continue
        if name in disabled_names(cfg):
            skipped.append({"name": name, "reason": "disabled in settings"})
            continue
        if spec.group not in enabled_groups(cfg):
            # builtins: respect settings; packs should have been session-enabled by materialize
            skipped.append({"name": name, "reason": "disabled in settings"})
            continue
        if name in activated:
            added.append(name)
            continue
        if len(activated) >= max_act:
            skipped.append({"name": name, "reason": f"activation cap ({max_act})"})
            continue
        activated.add(name)
        added.append(name)
    schemas = []
    for n in added:
        t = get_tool(n)
        if t and not t.lazy_pack:
            schemas.append(t.openai_schema()["function"])
    return ToolResult(True, dump_json({
        "activated": sorted(activated),
        "added": added,
        "skipped": skipped,
        "schemas": schemas,
        "note": "These tools are now callable in this turn.",
    }), {"activated": sorted(activated)})


def _coerce_tool_names(args: dict) -> list[str]:
    """Accept names / name as list, comma-string, or JSON array string.

    Models often pass ``name='["canvas_present"]'`` or ``names='canvas_present'``.
    """
    import json as _json

    def _from_value(val: object) -> list[str]:
        if val is None:
            return []
        if isinstance(val, list):
            out: list[str] = []
            for item in val:
                out.extend(_from_value(item))
            return out
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return []
            if s.startswith("["):
                try:
                    parsed = _json.loads(s)
                    return _from_value(parsed)
                except Exception:
                    pass
            if "," in s:
                return [n.strip() for n in s.split(",") if n.strip()]
            return [s]
        return [str(val).strip()] if str(val).strip() else []

    names = _from_value(args.get("names"))
    if not names:
        names = _from_value(args.get("name"))
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out
