"""Bridge LangChain / LangGraph / CrewAI tools into SUPER's catalog.

Architecture:
  SUPER discovery registry  ←  wrap(BaseTool)  ←  LangChain community tools
                                               ←  CrewAI BaseTool (_run)
  Agent loop: stdlib ReAct (default) or LangGraph ToolNode when installed.

We do NOT dump every LC tool into the prompt. Packs are metadata-only until
enabled in settings or loaded via load_tool_pack / activate. Then their
schemas join the normal discovery/activation flow.

Install:  pip install -e '.[agent]'
"""

from __future__ import annotations

import importlib
import json
import logging
from typing import Any, Callable

from .base import ToolResult, ToolSpec, dump_json

log = logging.getLogger("super.tools.lc")

# ── availability ───────────────────────────────────────────────────────

def langchain_available() -> bool:
    try:
        import langchain_core  # noqa: F401
        return True
    except ImportError:
        return False


def langgraph_available() -> bool:
    try:
        import langgraph  # noqa: F401
        return True
    except ImportError:
        return False


def crewai_available() -> bool:
    try:
        import crewai  # noqa: F401
        return True
    except ImportError:
        return False


def status() -> dict[str, bool]:
    return {
        "langchain": langchain_available(),
        "langgraph": langgraph_available(),
        "crewai": crewai_available(),
    }


# ── pack catalog (no heavy imports until load) ─────────────────────────
# Each pack: id, title, blurb, group, risk, default, factory key

PACKS: dict[str, dict[str, Any]] = {
    "lc_search": {
        "title": "Web search",
        "blurb": "DuckDuckGo web search (LangChain)",
        "group": "lc_search",
        "risk": "medium",
        "default": False,
        "requires": ["langchain_community"],
        "factory": "search",
    },
    "lc_arxiv": {
        "title": "arXiv",
        "blurb": "Search scientific papers",
        "group": "lc_research",
        "risk": "low",
        "default": False,
        "requires": ["langchain_community"],
        "factory": "arxiv",
    },
    "lc_wikipedia": {
        "title": "Wikipedia",
        "blurb": "Wikipedia query tool (lang / depth configurable)",
        "group": "lc_research",
        "risk": "low",
        "default": False,
        "requires": ["langchain_community"],
        "factory": "wikipedia",
    },
    "lc_python": {
        "title": "Python REPL",
        "blurb": "Execute Python in a REPL (high risk)",
        "group": "lc_code",
        "risk": "high",
        "default": False,
        "requires": ["langchain_experimental"],
        "factory": "python",
    },
    "lc_human": {
        "title": "Human input",
        "blurb": "Pause for operator input (HumanInputTool)",
        "group": "lc_human",
        "risk": "low",
        "default": False,
        "requires": ["langchain_community"],
        "factory": "human",
    },
    "lc_github": {
        "title": "GitHub",
        "blurb": "Repo/issue tools — needs GitHub token",
        "group": "lc_github",
        "risk": "high",
        "default": False,
        "requires": ["langchain_community"],
        "factory": "github",
    },
}

GROUP_META: dict[str, dict[str, str]] = {
    "lc_search": {"title": "LangChain · Search", "blurb": "DuckDuckGo web search"},
    "lc_research": {"title": "LangChain · Research", "blurb": "Papers and encyclopedic lookup"},
    "lc_code": {"title": "LangChain · Code", "blurb": "Python REPL (high risk)"},
    "lc_human": {"title": "LangChain · Human", "blurb": "Operator-in-the-loop"},
    "lc_github": {"title": "LangChain · GitHub", "blurb": "GitHub API tools"},
    "crewai": {"title": "CrewAI", "blurb": "User-registered CrewAI tools"},
    "lc_custom": {"title": "LangChain · Custom", "blurb": "User-registered LC/CrewAI tools"},
}

# Expected tools per pack — registered as searchable stubs before heavy imports.
# Names must match what wrap_tool / load_pack will register (incl. lc_ prefix on collisions).
PACK_TOOLS: dict[str, list[dict[str, str]]] = {
    "lc_search": [
        {
            "name": "duckduckgo_search",
            "summary": "DuckDuckGo web search",
            "description": (
                "Search the live web with DuckDuckGo. Use for current events, facts, "
                "and questions that need up-to-date information. Input is a search query."
            ),
            "keywords": "web search internet duckduckgo google news current events browse online",
        },
    ],
    "lc_arxiv": [
        {
            "name": "arxiv",
            "summary": "Search arXiv papers",
            "description": "Search scientific papers on arXiv by topic or title.",
            "keywords": "arxiv papers research science pdf academic",
        },
    ],
    "lc_wikipedia": [
        {
            "name": "wikipedia",
            "summary": "Wikipedia lookup",
            "description": "Query Wikipedia for an encyclopedic summary of a topic.",
            "keywords": "wikipedia encyclopedia wiki research lookup",
        },
    ],
    "lc_python": [
        {
            "name": "Python_REPL",
            "summary": "Python REPL",
            "description": "Execute Python code in a REPL. High risk — side effects possible.",
            "keywords": "python repl code execute eval",
        },
    ],
    "lc_human": [
        {
            "name": "human",
            "summary": "Ask the human operator",
            "description": "Pause and request input from the human operator.",
            "keywords": "human input operator ask",
        },
    ],
}

_loaded_packs: set[str] = set()
_pack_tool_names: dict[str, list[str]] = {}
_pack_fingerprints: dict[str, str] = {}
_lazy_registered: bool = False


def _stub_handler(pack_id: str, tool_name: str):
    """Lazy tool: load pack on first call, then re-dispatch to the real handler."""

    def handler(cfg: dict, args: dict) -> ToolResult:
        ok, msg, _names = load_pack(cfg, pack_id)
        if not ok:
            return ToolResult(False, msg)
        from .catalog import TOOLS
        from .discovery import _session

        meta = PACKS.get(pack_id) or {}
        if meta.get("group"):
            _session(cfg)["pack_groups"].add(meta["group"])
        real = TOOLS.get(tool_name)
        if not real or real.lazy_pack:
            return ToolResult(False, f"pack loaded but tool missing: {tool_name}")
        return real.handler(cfg, args)

    return handler


def register_lazy_stubs(cfg: dict | None = None) -> int:
    """Register searchable stub ToolSpecs for unloaded pack tools (idempotent)."""
    global _lazy_registered
    from .catalog import TOOLS

    for gid, meta in GROUP_META.items():
        from . import catalog
        if gid not in catalog.GROUPS:
            catalog.GROUPS[gid] = meta

    n = 0
    for pid, tools in PACK_TOOLS.items():
        pack = PACKS.get(pid) or {}
        group = pack.get("group") or pid
        risk = pack.get("risk") or "medium"
        for t in tools:
            name = t["name"]
            existing = TOOLS.get(name)
            if existing and not existing.lazy_pack:
                continue  # real tool already registered
            if existing and existing.lazy_pack == pid:
                continue
            # Prefer the first pack that claims a shared name (e.g. wikipedia).
            if existing and existing.lazy_pack and existing.lazy_pack != pid:
                continue
            register_tool(
                ToolSpec(
                    name=name,
                    group=group,
                    summary=t["summary"],
                    description=t["description"],
                    parameters={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Primary input / search query"},
                            "input": {"type": "string", "description": "Alternate single-string input"},
                        },
                        "additionalProperties": True,
                    },
                    handler=_stub_handler(pid, name),
                    risk=risk,
                    lazy_pack=pid,
                    keywords=t.get("keywords") or "",
                )
            )
            n += 1
    _lazy_registered = True
    return n


def ensure_tool_materialized(cfg: dict, name: str) -> tuple[bool, str, ToolSpec | None]:
    """Ensure a tool is fully loaded (not a lazy stub). Loads its pack if needed."""
    from .catalog import TOOLS
    from .discovery import _session

    def _enable_pack_group(pid: str | None) -> None:
        if not pid:
            return
        meta = PACKS.get(pid) or {}
        if meta.get("group"):
            _session(cfg)["pack_groups"].add(meta["group"])

    def _pack_id_for(tool_name: str, spec: ToolSpec | None) -> str | None:
        if spec and spec.lazy_pack:
            return spec.lazy_pack
        for pid, names in _pack_tool_names.items():
            if tool_name in names:
                return pid
        for pid, tools in PACK_TOOLS.items():
            if any(t["name"] == tool_name for t in tools):
                return pid
        return None

    spec = TOOLS.get(name)
    if not spec:
        register_lazy_stubs(cfg)
        spec = TOOLS.get(name)
    if not spec:
        return False, f"unknown tool: {name}", None
    if not spec.lazy_pack:
        _enable_pack_group(_pack_id_for(name, spec))
        return True, "ready", spec
    ok, msg, _ = load_pack(cfg, spec.lazy_pack)
    if not ok:
        return False, msg, None
    _enable_pack_group(spec.lazy_pack)
    real = TOOLS.get(name)
    if not real or real.lazy_pack:
        return False, f"pack loaded but tool missing: {name}", None
    # Preserve discovery keywords from the pack index on the live tool
    for t in PACK_TOOLS.get(spec.lazy_pack) or []:
        if t["name"] == name and t.get("keywords"):
            from .base import ToolSpec as TS
            real = TS(
                name=real.name,
                group=real.group,
                summary=real.summary,
                description=real.description,
                parameters=real.parameters,
                handler=real.handler,
                risk=real.risk,
                keywords=t["keywords"],
            )
            TOOLS[name] = real
            break
    return True, msg, real


def packs_public(cfg: dict | None = None) -> list[dict]:
    from .tool_config import public_values, fields_for_pack

    tools_cfg = (cfg or {}).get("tools") or {}
    packs_cfg = tools_cfg.get("packs") or {}
    pack_config = tools_cfg.get("pack_config") or {}
    st = status()
    out = []
    for pid, meta in PACKS.items():
        reqs = meta.get("requires") or []
        install_ok = True
        missing = []
        for mod in reqs:
            try:
                importlib.import_module(mod.replace("-", "_") if not mod.startswith("langchain") else mod)
            except ImportError:
                try:
                    importlib.import_module(mod)
                except ImportError:
                    install_ok = False
                    missing.append(mod)
        if "crewai" in reqs and not st["crewai"]:
            install_ok = False
            if "crewai" not in missing:
                missing.append("crewai")
        if any(r.startswith("langchain") for r in reqs) and not st["langchain"]:
            install_ok = False
            if "langchain-core" not in missing:
                missing.append("langchain-core")
        fields = fields_for_pack(pid)
        stored = pack_config.get(pid) if isinstance(pack_config.get(pid), dict) else {}
        out.append({
            "id": pid,
            "title": meta["title"],
            "blurb": meta["blurb"],
            "group": meta["group"],
            "risk": meta["risk"],
            "enabled": bool(packs_cfg.get(pid, meta.get("default", False))),
            "loaded": pid in _loaded_packs,
            "install_ok": install_ok,
            "missing": missing,
            "default": bool(meta.get("default", False)),
            "config_fields": public_values(fields, stored) if fields else [],
            "needs_config": any(f.get("required") for f in fields),
        })
    return out


# ── schema helpers ─────────────────────────────────────────────────────

def _schema_from_lc(tool: Any) -> dict:
    """Best-effort JSON schema from a LangChain tool."""
    # langchain_core.tools.BaseTool
    for attr in ("args_schema", "tool_call_schema"):
        schema_obj = getattr(tool, attr, None)
        if schema_obj is None:
            continue
        try:
            if hasattr(schema_obj, "model_json_schema"):
                js = schema_obj.model_json_schema()
                return {
                    "type": "object",
                    "properties": js.get("properties") or {},
                    "required": js.get("required") or [],
                    "additionalProperties": True,
                }
            if hasattr(schema_obj, "schema"):
                js = schema_obj.schema()
                return {
                    "type": "object",
                    "properties": js.get("properties") or {},
                    "required": js.get("required") or [],
                    "additionalProperties": True,
                }
        except Exception:
            continue
    # fallback: single input string (classic LC tools)
    return {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Tool input"},
        },
        "required": ["input"],
        "additionalProperties": True,
    }


def _run_lc_tool(tool: Any, args: dict) -> str:
    """Invoke LC or CrewAI tool with either kwargs or single input."""
    # CrewAI BaseTool
    if hasattr(tool, "_run") and not hasattr(tool, "invoke"):
        try:
            if "input" in args and len(args) == 1:
                return str(tool._run(args["input"]))
            return str(tool._run(**args))
        except TypeError:
            return str(tool._run(args.get("input") or json.dumps(args)))
    # LangChain runnable interface
    try:
        if hasattr(tool, "invoke"):
            # Structured tools prefer dict; classic prefer string
            try:
                result = tool.invoke(args)
            except Exception:
                result = tool.invoke(args.get("input") or args)
            return result if isinstance(result, str) else dump_json(result)
        if hasattr(tool, "run"):
            if "input" in args and len(args) == 1:
                return str(tool.run(args["input"]))
            return str(tool.run(args))
    except Exception as e:
        raise RuntimeError(f"{type(e).__name__}: {e}") from e
    raise RuntimeError("tool has no invoke/run/_run")


def wrap_tool(tool: Any, *, group: str, risk: str = "medium", name: str | None = None) -> ToolSpec:
    """Convert LangChain BaseTool or CrewAI BaseTool → SUPER ToolSpec."""
    tname = name or getattr(tool, "name", None) or getattr(tool, "__name__", "tool")
    tname = str(tname).replace(" ", "_").replace("-", "_")
    desc = getattr(tool, "description", None) or getattr(tool, "description", "") or tname
    summary = (desc or tname).split(".")[0][:80]
    schema = _schema_from_lc(tool)

    def handler(cfg: dict, args: dict) -> ToolResult:
        try:
            out = _run_lc_tool(tool, args)
            taint = "untrusted" if group.startswith("lc_search") or group == "lc_research" else "local-exec"
            return ToolResult(True, str(out), taint=taint)
        except Exception as e:
            return ToolResult(False, str(e))

    return ToolSpec(
        name=tname,
        group=group,
        summary=summary,
        description=str(desc),
        parameters=schema,
        handler=handler,
        risk=risk,
    )


def register_tool(spec: ToolSpec) -> None:
    from . import catalog
    catalog.TOOLS[spec.name] = spec
    if spec.group not in catalog.GROUPS and spec.group in GROUP_META:
        catalog.GROUPS[spec.group] = GROUP_META[spec.group]
    elif spec.group not in catalog.GROUPS:
        catalog.GROUPS[spec.group] = {
            "title": spec.group,
            "blurb": "External tool pack",
        }


def register_langchain_tool(tool: Any, *, group: str = "lc_custom", risk: str = "medium") -> ToolSpec:
    spec = wrap_tool(tool, group=group, risk=risk)
    register_tool(spec)
    return spec


def register_crewai_tool(tool: Any, *, group: str = "crewai", risk: str = "medium") -> ToolSpec:
    return register_langchain_tool(tool, group=group, risk=risk)


# ── pack factories ─────────────────────────────────────────────────────

def _pc(cfg: dict, pack_id: str) -> dict:
    from .tool_config import resolve_pack
    return resolve_pack(cfg, pack_id)


def _factory_search(cfg: dict) -> list[Any]:
    tools = []
    try:
        from langchain_community.tools import DuckDuckGoSearchRun
        tools.append(DuckDuckGoSearchRun())
    except Exception as e:
        log.debug("DuckDuckGo unavailable: %s", e)
    return tools


def _factory_arxiv(cfg: dict) -> list[Any]:
    from langchain_community.tools import ArxivQueryRun
    from langchain_community.utilities import ArxivAPIWrapper
    pc = _pc(cfg, "lc_arxiv")
    wrapper = ArxivAPIWrapper(top_k_results=int(pc.get("max_results") or 3))
    return [ArxivQueryRun(api_wrapper=wrapper)]


def _factory_wikipedia(cfg: dict) -> list[Any]:
    from langchain_community.tools import WikipediaQueryRun
    from langchain_community.utilities import WikipediaAPIWrapper
    pc = _pc(cfg, "lc_wikipedia")
    wrapper = WikipediaAPIWrapper(
        lang=str(pc.get("lang") or "en"),
        top_k_results=int(pc.get("top_k_results") or 3),
        doc_content_chars_max=int(pc.get("doc_content_chars_max") or 4000),
    )
    return [WikipediaQueryRun(api_wrapper=wrapper)]


def _factory_python(cfg: dict) -> list[Any]:
    from langchain_experimental.tools import PythonREPLTool
    return [PythonREPLTool()]


def _factory_human(cfg: dict) -> list[Any]:
    from langchain_community.tools import HumanInputRun
    return [HumanInputRun()]


def _factory_github(cfg: dict) -> list[Any]:
    pc = _pc(cfg, "lc_github")
    token = pc.get("github_token")
    if not token:
        raise RuntimeError("lc_github requires github_token in Settings (or GITHUB_TOKEN)")
    try:
        from langchain_community.agent_toolkits.github.toolkit import GitHubToolkit
        from langchain_community.utilities.github import GitHubAPIWrapper
        wrapper = GitHubAPIWrapper(github_token=token)
        toolkit = GitHubToolkit.from_github_api_wrapper(wrapper)
        return list(toolkit.get_tools())
    except Exception as e:
        log.debug("GitHub toolkit unavailable: %s", e)
        raise RuntimeError(f"GitHub toolkit failed: {e}") from e


_FACTORIES: dict[str, Callable[[dict], list[Any]]] = {
    "search": _factory_search,
    "arxiv": _factory_arxiv,
    "wikipedia": _factory_wikipedia,
    "python": _factory_python,
    "human": _factory_human,
    "github": _factory_github,
}


def load_pack(cfg: dict, pack_id: str, *, force: bool = False) -> tuple[bool, str, list[str]]:
    """Instantiate a pack and register tools. Reloads automatically if pack config changed."""
    from .catalog import TOOLS
    from .tool_config import fields_for_pack, resolve_pack

    meta = PACKS.get(pack_id)
    if not meta:
        return False, f"unknown pack: {pack_id}", []

    pc = resolve_pack(cfg, pack_id)
    for f in fields_for_pack(pack_id):
        if f.get("required") and not pc.get(f["key"]):
            env = f.get("env") or ""
            return False, f"{pack_id} needs config '{f['key']}' in Settings" + (f" (or env {env})" if env else ""), []

    fp = json.dumps(pc, sort_keys=True, default=str)
    if pack_id in _loaded_packs and not force and _pack_fingerprints.get(pack_id) == fp:
        names = _pack_tool_names.get(pack_id) or []
        return True, f"pack {pack_id} already loaded", names

    for n in _pack_tool_names.get(pack_id) or []:
        TOOLS.pop(n, None)
    # Clear lazy stubs claimed by this pack so real tools can take the same names
    for t in PACK_TOOLS.get(pack_id) or []:
        cur = TOOLS.get(t["name"])
        if cur and cur.lazy_pack == pack_id:
            TOOLS.pop(t["name"], None)
    _loaded_packs.discard(pack_id)
    _pack_tool_names.pop(pack_id, None)

    factory = _FACTORIES.get(meta["factory"])
    if not factory:
        return False, f"no factory for {pack_id}", []
    try:
        tools = factory(cfg)
    except ImportError as e:
        return False, f"missing dependency for {pack_id}: {e}. Install with: pip install -e '.[agent]'", []
    except Exception as e:
        return False, f"failed to load {pack_id}: {e}", []
    if not tools:
        return False, f"pack {pack_id} produced no tools (optional deps missing?)", []
    names = []
    for t in tools:
        spec = wrap_tool(t, group=meta["group"], risk=meta["risk"])
        existing = TOOLS.get(spec.name)
        if existing and existing.lazy_pack:
            existing = None  # stub slot is free for this real tool
        if existing and not existing.group.startswith(("lc_", "crewai")) and not existing.discovery:
            spec = ToolSpec(
                name=f"lc_{spec.name}",
                group=spec.group,
                summary=spec.summary,
                description=spec.description,
                parameters=spec.parameters,
                handler=spec.handler,
                risk=spec.risk,
            )
            existing = TOOLS.get(spec.name)
            if existing and existing.lazy_pack:
                existing = None
        if existing and spec.name not in names:
            spec = ToolSpec(
                name=f"{pack_id}_{spec.name}",
                group=spec.group,
                summary=spec.summary,
                description=spec.description,
                parameters=spec.parameters,
                handler=spec.handler,
                risk=spec.risk,
            )
        register_tool(spec)
        names.append(spec.name)
    _loaded_packs.add(pack_id)
    _pack_tool_names[pack_id] = names
    _pack_fingerprints[pack_id] = fp
    return True, f"loaded {pack_id}: {', '.join(names)}", names


def sync_enabled_packs(cfg: dict) -> list[str]:
    """Load every pack marked enabled in config.tools.packs."""
    packs_cfg = (cfg.get("tools") or {}).get("packs") or {}
    loaded = []
    for pid, meta in PACKS.items():
        want = bool(packs_cfg.get(pid, meta.get("default", False)))
        if want:
            ok, _, names = load_pack(cfg, pid)
            if ok:
                loaded.extend(names)
    return loaded


def ensure_bridge(cfg: dict) -> None:
    """Ensure pack groups exist + lazy stubs + load enabled packs. Safe to call often."""
    from . import catalog
    for gid, meta in GROUP_META.items():
        if gid not in catalog.GROUPS:
            catalog.GROUPS[gid] = meta
    if "load_tool_pack" not in catalog.TOOLS:
        _register_pack_meta_tools()
    register_lazy_stubs(cfg)
    sync_enabled_packs(cfg)
    try:
        from .mcp_bridge import ensure_mcp
        ensure_mcp(cfg)
    except Exception:
        pass
    try:
        from .. import capabilities as _caps
        _caps.ensure_capabilities(cfg)
    except Exception:
        pass


def _register_pack_meta_tools() -> None:
    from .base import ToolSpec
    from .catalog import TOOLS

    def _props_pack(**kwargs: Any) -> dict:
        required = [k for k, v in kwargs.items() if isinstance(v, dict) and v.pop("_req", False)]
        return {"type": "object", "properties": kwargs, "required": required, "additionalProperties": False}

    def handle_list_packs(cfg: dict, args: dict) -> ToolResult:
        return ToolResult(True, dump_json({"status": status(), "packs": packs_public(cfg)}))

    def handle_load_pack(cfg: dict, args: dict) -> ToolResult:
        pid = str(args.get("pack_id") or args.get("id") or "").strip()
        if not pid:
            return ToolResult(False, "pack_id required")
        ok, msg, names = load_pack(cfg, pid)
        if ok and names:
            from .discovery import _session
            sess = _session(cfg)
            meta = PACKS.get(pid) or {}
            if meta.get("group"):
                sess["pack_groups"].add(meta["group"])
            max_act = int((cfg.get("tools") or {}).get("max_activated", 8))
            for n in names:
                if len(sess["activated"]) >= max_act:
                    break
                sess["activated"].add(n)
        return ToolResult(ok, dump_json({"message": msg, "tools": names}))

    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    TOOLS["list_tool_packs"] = ToolSpec(
        name="list_tool_packs",
        group="discovery",
        summary="List external tool packs (optional)",
        description=(
            "Optional: list LangChain/CrewAI pack install status. "
            "Prefer search_tools / list_tool_groups — pack tools appear in the same catalog."
        ),
        parameters=empty,
        handler=handle_list_packs,
        discovery=True,
    )
    TOOLS["load_tool_pack"] = ToolSpec(
        name="load_tool_pack",
        group="discovery",
        summary="Load an external tool pack (optional)",
        description=(
            "Optional: load an entire pack by id. Prefer activate_tools on specific tool names — "
            "activation loads the pack automatically."
        ),
        parameters=_props_pack(
            pack_id={"type": "string", "description": "Pack id, e.g. lc_search or lc_wikipedia", "_req": True}
        ),
        handler=handle_load_pack,
        discovery=True,
    )


def default_packs_config() -> dict[str, bool]:
    return {pid: bool(meta.get("default", False)) for pid, meta in PACKS.items()}
