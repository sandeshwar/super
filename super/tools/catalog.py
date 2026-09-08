"""Tool catalog: groups + specs. Discovery meta-tools keep prompts small."""

from __future__ import annotations

from typing import Any

from . import builtins as B
from .base import ToolSpec

GROUPS: dict[str, dict[str, str]] = {
    "discovery": {
        "title": "Discovery",
        "blurb": "Search and activate tools without loading everything",
    },
    "files": {
        "title": "Files",
        "blurb": "Read, write, edit, and list project files",
    },
    "search": {
        "title": "Search",
        "blurb": "Find text, files, and symbols in the repo",
    },
    "shell": {
        "title": "Shell",
        "blurb": "Run commands in the project folder",
    },
    "git": {
        "title": "Git",
        "blurb": "Status, diff, log, and show",
    },
    "web": {
        "title": "Web",
        "blurb": "Fetch URLs (marked untrusted)",
    },
    "tasks": {
        "title": "Tasks",
        "blurb": "Read and update the task graph",
    },
    "memory": {
        "title": "Memory",
        "blurb": "Store and recall verified claims",
    },
    "project": {
        "title": "Project",
        "blurb": "Tree overview and public config",
    },
    "agents": {
        "title": "Agents",
        "blurb": "Create and run specialized sub-agents (inherit parent rules)",
    },
    "capabilities": {
        "title": "Capabilities",
        "blurb": "Propose, test, install agent-invented tools (capability forge)",
    },
    "intelligence": {
        "title": "Intelligence",
        "blurb": "Autonomous agenda: audit gaps, pursue improvements, self-reflect",
    },
}

_OBJ = {"type": "object", "properties": {}, "additionalProperties": False}


def _props(**kwargs: Any) -> dict:
    required = [k for k, v in kwargs.items() if v.pop("_req", False)]
    return {"type": "object", "properties": kwargs, "required": required, "additionalProperties": False}


def _str(desc: str, req: bool = False, **extra: Any) -> dict:
    d = {"type": "string", "description": desc, **extra}
    if req:
        d["_req"] = True
    return d


def _int(desc: str, req: bool = False, **extra: Any) -> dict:
    d = {"type": "integer", "description": desc, **extra}
    if req:
        d["_req"] = True
    return d


def _bool(desc: str, req: bool = False) -> dict:
    d = {"type": "boolean", "description": desc}
    if req:
        d["_req"] = True
    return d


# Discovery handlers need the registry; wired after TOOLS is built.
def _search_tools_handler(cfg: dict, args: dict):
    from .discovery import handle_search_tools
    return handle_search_tools(cfg, args)


def _list_groups_handler(cfg: dict, args: dict):
    from .discovery import handle_list_groups
    return handle_list_groups(cfg, args)


def _activate_tools_handler(cfg: dict, args: dict):
    from .discovery import handle_activate_tools
    return handle_activate_tools(cfg, args)


def _describe_tool_handler(cfg: dict, args: dict):
    from .discovery import handle_describe_tool
    return handle_describe_tool(cfg, args)


TOOLS: dict[str, ToolSpec] = {}


def _reg(spec: ToolSpec) -> None:
    TOOLS[spec.name] = spec


# ── discovery (always available when tools.enabled) ───────────────────
_reg(ToolSpec(
    name="search_tools",
    group="discovery",
    summary="Search the tool catalog by keyword",
    description=(
        "Search all available tools (built-in and third-party) by keyword or category. "
        "Returns short summaries only — call describe_tool for full schemas, then "
        "activate_tools for the ones you need. Prefer this over guessing tool names. "
        "Examples: query='web search', query='git', group='lc_search'."
    ),
    parameters=_props(query=_str("Search query, e.g. 'web search' or 'read file'", req=True),
                      group=_str("Optional category/group id filter, e.g. 'web' or 'lc_search'"),
                      limit=_int("Max results", **{"default": 12})),
    handler=_search_tools_handler,
    discovery=True,
))
_reg(ToolSpec(
    name="list_tool_groups",
    group="discovery",
    summary="List tool categories",
    description=(
        "List tool categories/groups with counts and member names. "
        "Includes built-in and third-party packs. Use search_tools to filter by keyword."
    ),
    parameters=_OBJ,
    handler=_list_groups_handler,
    discovery=True,
))
_reg(ToolSpec(
    name="describe_tool",
    group="discovery",
    summary="Get full schema for one tool",
    description=(
        "Return the full JSON schema and description for one tool. "
        "For third-party tools this loads the implementation if needed. "
        "Call this only for tools you are considering using."
    ),
    parameters=_props(name=_str("Exact tool name", req=True)),
    handler=_describe_tool_handler,
    discovery=True,
))
_reg(ToolSpec(
    name="activate_tools",
    group="discovery",
    summary="Load tool schemas into this turn",
    description=(
        "Activate named tools for subsequent steps in this turn. "
        "Works the same for built-in and third-party tools (loads packs on demand). "
        "Only activated (or discovery) tools are callable. Prefer activating 1–5 tools at a time."
    ),
    parameters=_props(names={"type": "array", "items": {"type": "string"}, "description": "Tool names to activate", "_req": True}),
    handler=_activate_tools_handler,
    discovery=True,
))

# ── files ─────────────────────────────────────────────────────────────
_reg(ToolSpec("list_dir", "files", "List a directory",
              "List files and directories. Path may be workspace-relative or absolute (~ ok).",
              _props(path=_str("Path (relative to working dir or absolute)", **{"default": "."})), B.list_dir))
_reg(ToolSpec("read_file", "files", "Read file lines",
              "Read a text file with optional line offset/limit. Prefer small ranges. "
              "Path may be workspace-relative or absolute.",
              _props(path=_str("Path (relative or absolute)", req=True),
                     offset=_int("Start line (0-based)", **{"default": 0}),
                     limit=_int("Max lines", **{"default": 200})), B.read_file))
_reg(ToolSpec("write_file", "files", "Write whole file",
              "Create or overwrite a file with full content. Prefer edit_file for small changes. "
              "Path may be workspace-relative or absolute.",
              _props(path=_str("Path (relative or absolute)", req=True), content=_str("Full file content", req=True)),
              B.write_file, risk="high"))
_reg(ToolSpec("edit_file", "files", "Surgical string replace",
              "Replace an exact old string with new in a file. Fails if old is missing or ambiguous. "
              "Path may be workspace-relative or absolute.",
              _props(path=_str("Path (relative or absolute)", req=True),
                     old=_str("Exact text to find", req=True),
                     new=_str("Replacement text", req=True),
                     replace_all=_bool("Replace all occurrences")),
              B.edit_file, risk="high"))
_reg(ToolSpec("mkdir", "files", "Create directory",
              "Create a directory (and parents). Path may be workspace-relative or absolute.",
              _props(path=_str("Path (relative or absolute)", req=True)), B.mkdir_tool))
_reg(ToolSpec("delete_path", "files", "Delete file or folder",
              "Delete a file or directory. Path may be workspace-relative or absolute. Use carefully.",
              _props(path=_str("Path (relative or absolute)", req=True)), B.delete_file, risk="high"))

# ── search ────────────────────────────────────────────────────────────
_reg(ToolSpec("grep", "search", "Search file contents",
              "Ripgrep (or fallback) content search. Returns path:line:text hits. "
              "Search root may be workspace-relative or absolute.",
              _props(pattern=_str("Regex or literal pattern", req=True),
                     path=_str("Root path", **{"default": "."}),
                     glob=_str("File glob filter, e.g. '*.py'"),
                     max_hits=_int("Max hits", **{"default": 40})), B.grep_tool))
_reg(ToolSpec("glob_files", "search", "Find files by name",
              "Glob for paths under a directory (default: working dir). Path may be absolute.",
              _props(pattern=_str("Glob pattern", req=True),
                     path=_str("Root directory", **{"default": "."})), B.glob_files))
_reg(ToolSpec("find_symbol", "search", "Find symbol definitions",
              "Locate likely definitions of a function/class/const name.",
              _props(name=_str("Symbol name", req=True), path=_str("Root", **{"default": "."})),
              B.find_symbol))

# ── shell ─────────────────────────────────────────────────────────────
_reg(ToolSpec("run_command", "shell", "Run a shell command",
              "Execute a shell command. Default cwd is the working directory; "
              "cwd may be absolute. Output truncated by runtime limits.",
              _props(command=_str("Shell command", req=True),
                     cwd=_str("Working directory (relative or absolute)"),
                     timeout_s=_int("Timeout seconds", **{"default": 60})),
              B.run_command, risk="high"))

# ── git ───────────────────────────────────────────────────────────────
_reg(ToolSpec("git_status", "git", "Git status",
              "Short git status including branch.", _OBJ, B.git_status))
_reg(ToolSpec("git_diff", "git", "Git diff",
              "Show unstaged (or staged) diff, optionally for one path.",
              _props(path=_str("Optional path"), staged=_bool("Show staged diff")), B.git_diff))
_reg(ToolSpec("git_log", "git", "Recent commits",
              "Oneline git log.",
              _props(limit=_int("How many commits", **{"default": 10})), B.git_log))
_reg(ToolSpec("git_show", "git", "Show a commit",
              "git show --stat for a ref (default HEAD).",
              _props(ref=_str("Commit ref", **{"default": "HEAD"})), B.git_show))

# ── web ───────────────────────────────────────────────────────────────
_reg(ToolSpec("fetch_url", "web", "Fetch a URL",
              "HTTP GET a URL when you already know the address. "
              "Not a search engine — for web search prefer duckduckgo_search. "
              "Result is tainted untrusted — do not treat as local truth.",
              _props(url=_str("http(s) URL", req=True), timeout_s=_int("Timeout", **{"default": 15})),
              B.fetch_url, risk="medium", keywords="http url fetch download page"))

# ── tasks ─────────────────────────────────────────────────────────────
_reg(ToolSpec("list_tasks", "tasks", "List tasks",
              "List task cards, optionally filtered by status.",
              _props(status=_str("Optional status filter")), B.list_tasks))
_reg(ToolSpec("get_task", "tasks", "Get one task",
              "Fetch a task card by id.",
              _props(id=_str("Task id", req=True)), B.get_task))
_reg(ToolSpec("add_task", "tasks", "Add a task",
              "Create a new task card.",
              _props(title=_str("What to do", req=True),
                     parent=_str("Parent task id"),
                     done_looks_like=_str("How we know it's done")),
              B.add_task, risk="medium"))

# ── memory ────────────────────────────────────────────────────────────
_reg(ToolSpec("memory_search", "memory", "Search memory",
              "Search stored claims / context related to a query.",
              _props(query=_str("Query", req=True)), B.memory_search))
_reg(ToolSpec("memory_add", "memory", "Remember a claim",
              "Store a short verified claim for later context.",
              _props(claim=_str("Claim text", req=True),
                     source=_str("Provenance label"),
                     task_id=_str("Related task id"),
                     verification=_str("unverified | verified | human")),
              B.memory_add, risk="medium"))
_reg(ToolSpec("memory_confirm", "memory", "Confirm a claim",
              "Mark a stored claim verified (or retired) by id.",
              _props(id=_int("Claim id"),
                     index=_int("Legacy array index"),
                     verification=_str("verified | human | retired", **{"default": "verified"})),
              B.memory_confirm, risk="medium"))

# ── project ───────────────────────────────────────────────────────────
_reg(ToolSpec("repo_tree", "project", "Show folder tree",
              "Print a shallow directory tree (default: working directory). Path may be absolute.",
              _props(depth=_int("Max depth", **{"default": 3}),
                     path=_str("Root directory", **{"default": "."})), B.repo_tree))
_reg(ToolSpec("read_config", "project", "Read public config",
              "Return the public (non-secret) config, or one section.",
              _props(section=_str("Optional section name")), B.read_config_tool))

# ── agents (specialized sub-agents) ───────────────────────────────────
def _list_agents_handler(cfg: dict, args: dict):
    from .. import agents as A
    return A.handle_list_agents(cfg, args)

def _get_agent_handler(cfg: dict, args: dict):
    from .. import agents as A
    return A.handle_get_agent(cfg, args)

def _create_agent_handler(cfg: dict, args: dict):
    from .. import agents as A
    return A.handle_create_agent(cfg, args)

def _update_agent_handler(cfg: dict, args: dict):
    from .. import agents as A
    return A.handle_update_agent(cfg, args)

def _archive_agent_handler(cfg: dict, args: dict):
    from .. import agents as A
    return A.handle_archive_agent(cfg, args)

def _run_agent_handler(cfg: dict, args: dict):
    from .. import agents as A
    return A.handle_run_agent(cfg, args)

_reg(ToolSpec(
    "list_agents", "agents", "List specialized agents",
    "List AgentSpecs (id, name, role, status). Children inherit parent tool/gate budgets.",
    _props(include_archived=_bool("Include archived")),
    _list_agents_handler,
    discovery=True,
    keywords="subagent multi-agent specialist",
))
_reg(ToolSpec(
    "get_agent", "agents", "Get agent details",
    "Fetch one AgentSpec and the effective rights if spawned under the current agent.",
    _props(id=_str("Agent id", req=True)),
    _get_agent_handler,
    discovery=True,
))
_reg(ToolSpec(
    "create_agent", "agents", "Create a specialized agent",
    "Create an AgentSpec. Workers/planners activate immediately; judge roles "
    "(reviewer/auditor/evaluator/integrator) stay pending until human approval. "
    "Tools/groups can only tighten relative to you (the parent).",
    _props(
        name=_str("Short name", req=True),
        role=_str("worker|planner|reviewer|auditor|evaluator|integrator", **{"default": "worker"}),
        summary=_str("What this agent is for"),
        system_addon=_str("Extra instructions for this specialist"),
        tools={"type": "array", "items": {"type": "string"}, "description": "Optional tool-name allowlist"},
        groups={"type": "array", "items": {"type": "string"}, "description": "Optional group allowlist"},
        disabled={"type": "array", "items": {"type": "string"}, "description": "Extra disabled tool names"},
        inherits_from=_str("Optional parent AgentSpec id to inherit from"),
    ),
    _create_agent_handler,
    risk="medium",
    discovery=True,
    keywords="spawn create subagent specialist",
))
_reg(ToolSpec(
    "update_agent", "agents", "Update an agent",
    "Update fields on an AgentSpec. Agents may only tighten policy flags.",
    _props(
        id=_str("Agent id", req=True),
        name=_str("New name"),
        summary=_str("New summary"),
        system_addon=_str("New specialization prompt"),
        tools={"type": "array", "items": {"type": "string"}, "description": "Tool allowlist"},
        groups={"type": "array", "items": {"type": "string"}, "description": "Group allowlist"},
        disabled={"type": "array", "items": {"type": "string"}, "description": "Disabled tools"},
    ),
    _update_agent_handler,
    risk="medium",
    discovery=True,
))
_reg(ToolSpec(
    "archive_agent", "agents", "Archive an agent",
    "Archive an AgentSpec (keeps history; cannot be run).",
    _props(id=_str("Agent id", req=True)),
    _archive_agent_handler,
    risk="medium",
    discovery=True,
))
_reg(ToolSpec(
    "run_agent", "agents", "Run a specialized agent",
    "Spawn an active AgentSpec as a child span. It inherits your gates, security, "
    "tool ceiling, and budgets (can only be narrower). Returns its reply + span ids.",
    _props(
        id=_str("Agent id", req=True),
        goal=_str("Goal / prompt for the child agent", req=True),
    ),
    _run_agent_handler,
    risk="high",
    discovery=True,
    keywords="spawn subagent delegate",
))

# ── capabilities (self-extending forge) ───────────────────────────────
def _propose_cap_handler(cfg: dict, args: dict):
    from .. import capabilities as C
    return C.handle_propose_capability(cfg, args)

def _list_caps_handler(cfg: dict, args: dict):
    from .. import capabilities as C
    return C.handle_list_capabilities(cfg, args)

def _describe_cap_handler(cfg: dict, args: dict):
    from .. import capabilities as C
    return C.handle_describe_capability(cfg, args)

def _test_cap_handler(cfg: dict, args: dict):
    from .. import capabilities as C
    return C.handle_test_capability(cfg, args)

def _install_cap_handler(cfg: dict, args: dict):
    from .. import capabilities as C
    return C.handle_install_capability(cfg, args)

def _retire_cap_handler(cfg: dict, args: dict):
    from .. import capabilities as C
    return C.handle_retire_capability(cfg, args)

_reg(ToolSpec(
    "propose_capability", "capabilities", "Invent a new tool",
    "Propose a new capability (composite of existing tools, or HTTP). "
    "Low-risk composites with passing tests auto-install; others stay pending "
    "until human approval. Does NOT eval arbitrary code — compose trusted tools.",
    _props(
        name=_str("snake_case tool name", req=True),
        summary=_str("One-line summary"),
        description=_str("Full description for the catalog"),
        kind=_str("composite|http", **{"default": "composite"}),
        risk=_str("low|medium|high", **{"default": "medium"}),
        parameters={"type": "object", "description": "JSON Schema for the new tool's args"},
        impl={"type": "object", "description": "composite: {steps:[{tool,args,as}], merge}; http: {url,method,query_from,body_from}"},
        tests={"type": "array", "items": {"type": "object"}, "description": "Optional [{args, expect_ok, expect_contains}]"},
    ),
    _propose_cap_handler,
    risk="high",
    discovery=True,
    keywords="forge invent extend self-modify capability tool",
))
_reg(ToolSpec(
    "list_capabilities", "capabilities", "List forged capabilities",
    "List pending/installed/retired agent-invented capabilities.",
    _props(include_retired=_bool("Include retired")),
    _list_caps_handler,
    discovery=True,
    keywords="forge capabilities",
))
_reg(ToolSpec(
    "describe_capability", "capabilities", "Describe one capability",
    "Show full capability record (impl, tests, status).",
    _props(id=_str("Capability id"), name=_str("Capability tool name")),
    _describe_cap_handler,
    discovery=True,
))
_reg(ToolSpec(
    "test_capability", "capabilities", "Run capability tests",
    "Execute the capability's test cases (sandbox: blocks write tools unless risk=low).",
    _props(id=_str("Capability id", req=True)),
    _test_cap_handler,
    risk="medium",
    discovery=True,
))
_reg(ToolSpec(
    "install_capability", "capabilities", "Install approved capability",
    "Register an approved (or auto-eligible low-risk) capability into the live tool catalog.",
    _props(id=_str("Capability id", req=True)),
    _install_cap_handler,
    risk="high",
    discovery=True,
))
_reg(ToolSpec(
    "retire_capability", "capabilities", "Retire a capability",
    "Unregister and retire a capability (tighten only).",
    _props(id=_str("Capability id", req=True)),
    _retire_cap_handler,
    risk="medium",
    discovery=True,
))

# ── intelligence (autonomous agenda) ──────────────────────────────────
def _self_reflect_handler(cfg: dict, args: dict):
    from .. import intelligence as I
    return I.handle_self_reflect(cfg, args)

def _list_agenda_handler(cfg: dict, args: dict):
    from .. import intelligence as I
    return I.handle_list_agenda(cfg, args)

def _pursue_agenda_handler(cfg: dict, args: dict):
    from .. import intelligence as I
    return I.handle_pursue_agenda(cfg, args)

def _dismiss_agenda_handler(cfg: dict, args: dict):
    from .. import intelligence as I
    return I.handle_dismiss_agenda(cfg, args)

_reg(ToolSpec(
    "self_reflect", "intelligence", "Audit gaps and refresh agenda",
    "Run the autonomous intelligence audit: scan tasks, gates, memory, capabilities, "
    "agents, config; refresh the agenda; auto-act safe improvements (forge recipes, "
    "seed tasks/memory). Call when stuck or at the start of ambitious work.",
    _props(force=_bool("Bypass rate limit")),
    _self_reflect_handler,
    discovery=True,
    keywords="reflect audit agenda improve metacognition",
))
_reg(ToolSpec(
    "list_agenda", "intelligence", "List intelligence agenda",
    "Show open (or all) agenda items the harness wants pursued.",
    _props(include_done=_bool("Include done/dismissed")),
    _list_agenda_handler,
    discovery=True,
))
_reg(ToolSpec(
    "pursue_agenda", "intelligence", "Act on an agenda item",
    "Force-run the auto-actor for an agenda id, or get guidance if the model must handle it. "
    "Omit id to pursue the top open item.",
    _props(id=_str("Agenda item id (optional — top item if omitted)")),
    _pursue_agenda_handler,
    risk="medium",
    discovery=True,
))
_reg(ToolSpec(
    "dismiss_agenda", "intelligence", "Dismiss an agenda item",
    "Mark an agenda item done/dismissed after you addressed it (or as not applicable).",
    _props(id=_str("Agenda item id", req=True), reason=_str("Why dismissed")),
    _dismiss_agenda_handler,
    discovery=True,
))


def get_tool(name: str) -> ToolSpec | None:
    return TOOLS.get(name)


def search_tools(query: str, group: str | None = None, enabled_groups: set[str] | None = None,
                 disabled: set[str] | None = None, limit: int = 12,
                 *, include_lazy: bool = True) -> list[ToolSpec]:
    """Search the unified catalog (builtins + lazy third-party stubs).

    Lazy pack tools are searchable even when their group is not Settings-enabled;
    activate/describe will materialize them for the turn.
    """
    q = (query or "").strip().lower()
    tokens = [t for t in q.replace("/", " ").replace("_", " ").replace("-", " ").split() if t]
    disabled = disabled or set()
    out: list[tuple[int, ToolSpec]] = []
    for spec in TOOLS.values():
        if spec.discovery:
            continue
        if spec.name in disabled:
            continue
        if group and spec.group != group:
            continue
        lazy = bool(spec.lazy_pack)
        packish = lazy or spec.group.startswith("lc_") or spec.group == "crewai"
        if enabled_groups is not None and spec.group not in enabled_groups:
            if not (include_lazy and packish):
                continue
        # Prefer pack-index keywords when the live tool was loaded without them
        extra = spec.keywords or ""
        if not extra and packish:
            try:
                from .langchain_bridge import PACK_TOOLS
                for tools in PACK_TOOLS.values():
                    for t in tools:
                        if t["name"] == spec.name:
                            extra = t.get("keywords") or ""
                            break
            except Exception:
                pass
        hay = f"{spec.name} {spec.group} {spec.summary} {spec.description} {extra}".lower()
        if not tokens:
            score = 1
        else:
            score = sum(1 for t in tokens if t in hay)
            if score == 0:
                continue
            if q == spec.name.lower() or spec.name.lower() in tokens:
                score += 3
            if {"web", "search"}.issubset(set(tokens)) and "duckduckgo" in hay:
                score += 2
        out.append((score, spec))
    out.sort(key=lambda x: (-x[0], x[1].name))
    return [s for _, s in out[: max(1, min(limit, 40))]]


def catalog_public(cfg: dict | None = None) -> dict:
    """Settings / API view of the catalog with enable state."""
    try:
        from .langchain_bridge import ensure_bridge, packs_public, status as lc_status
        from .tool_config import public_builtin_configs
        if cfg is not None:
            ensure_bridge(cfg)
    except Exception:
        packs_public = lambda _c=None: []  # noqa: E731
        lc_status = lambda: {"langchain": False, "langgraph": False, "crewai": False}  # noqa: E731
        public_builtin_configs = lambda _c=None: {}  # noqa: E731

    tools_cfg = (cfg or {}).get("tools") or {}
    groups_cfg = tools_cfg.get("groups") or {}
    disabled = set(tools_cfg.get("disabled") or [])
    groups_out = []
    for gid, meta in GROUPS.items():
        if gid == "discovery":
            enabled = True
        elif gid.startswith("lc_") or gid == "crewai":
            enabled = bool(groups_cfg.get(gid, False))
        else:
            enabled = bool(groups_cfg.get(gid, gid != "web"))
        members = [t for t in TOOLS.values() if t.group == gid]
        groups_out.append({
            "id": gid,
            "title": meta["title"],
            "blurb": meta["blurb"],
            "enabled": enabled,
            "tools": [
                {
                    "name": t.name,
                    "summary": t.summary,
                    "risk": t.risk,
                    "enabled": t.name not in disabled and enabled,
                    "discovery": t.discovery,
                }
                for t in members
            ],
        })
    return {
        "enabled": bool(tools_cfg.get("enabled", True)),
        "discovery": bool(tools_cfg.get("discovery", True)),
        "max_result_chars": int(tools_cfg.get("max_result_chars", 8000)),
        "max_activated": int(tools_cfg.get("max_activated", 8)),
        "groups": groups_out,
        "packs": packs_public(cfg),
        "integrations": lc_status(),
        "packs_config": tools_cfg.get("packs") or {},
        "builtin_configs": public_builtin_configs(cfg) if cfg is not None else {},
    }


def default_tools_config() -> dict:
    from .langchain_bridge import default_packs_config
    return {
        "enabled": True,
        "discovery": True,
        "max_result_chars": 8000,
        "max_activated": 8,
        "groups": {
            "files": True,
            "search": True,
            "shell": True,
            "git": True,
            "web": False,
            "tasks": True,
            "memory": True,
            "project": True,
            "agents": True,
            "capabilities": True,
            "intelligence": True,
        },
        "disabled": [],
        "packs": default_packs_config(),
        "runtime": "auto",  # auto | stdlib | langgraph
    }
