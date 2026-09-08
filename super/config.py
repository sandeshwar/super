"""Production configuration loader.

Sources (ascending precedence): built-in defaults < super.config.json <
environment (SUPER_CONFIG, SUPER_TOKEN, SUPER_LLM_ENDPOINT, SUPER_LLM_MODEL,
SUPER_PORT). Every value is type/range validated; invalid config raises
ConfigError with the offending key instead of failing downstream.

Auth: the dashboard is open on the LAN by default (binds 0.0.0.0). A server.token
may still be generated for legacy CLI helpers, but it is not required for API access.
"""

from __future__ import annotations

import json
import os
import secrets

from .errors import ConfigError

DEFAULTS = {
    "llm": {
        "endpoint": "http://localhost:11434",
        "model": "ddalcu/Qwen3.8-Flash-Next-MLX-Serve-4bit:latest",
        "timeout_s": 120,
        "retries": 2,
        "health_path": "/api/tags",
        # Ollama thinking models: true|false|"low"|"medium"|"high"|"max"
        "think": True,
    },
    "envelope": {
        "max_reply_lines": 50,
        "best_of_n": 5,
        "max_tool_steps": 20,
        "early_abort_stall": 3,
    },
    "gates": {
        "grounding": True,
        "docs_before_write": True,
        "standards": True,
        "duplication": True,
        "verification": True,
        "mutation": True,
        "quality": True,
        "security": True,
        "taint": True,
        "ambition": True,
    },
    "verification": {
        "mutation_operators": ["operator", "boundary", "statement"],
        "flaky_runs": 3,
        "fuzz_seconds": 5,
    },
    "quality": {
        "max_loc_per_edit": 300,
        "max_complexity": 10,
        "max_nesting": 4,
    },
    "security": {
        "block_secrets": True,
        "sast": True,
        "dependency_gate": True,
        "sink_audit": True,
    },
    "trust": {
        "auto_pass_max_blast": 2,
        "fatigue_approve_threshold": 0.95,
        "fatigue_window": 40,
        "attention_budget": 10,
    },
    "ambition": {
        "default_loa": 4,
        "critics": 3,
        "require_scorecard": True,
    },
    "mcp": {
        "servers": [],
    },
    "tools": {
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
            "memory": True,
            "project": True,
            "agents": True,
            "capabilities": True,
            "intelligence": True,
            "user_caps": True,
            "mcp": True,
        },
        "disabled": [],
        "packs": {
            "lc_search": False,
            "lc_arxiv": False,
            "lc_wikipedia": False,
            "lc_python": False,
            "lc_human": False,
            "lc_github": False,
        },
        "pack_config": {},
        "builtin_config": {},
        "runtime": "auto",
    },
    "agents": {
        "enabled": True,
        "max_depth": 3,
        "max_agents": 50,
        "allow_agent_create_roles": ["worker", "planner"],
    },
    "capabilities": {
        "enabled": True,
        "auto_install_low": True,
        "http_allowlist": [],
    },
    "intelligence": {
        "enabled": True,
        "auto_act": True,
        "inject_briefing": True,
        "min_interval_s": 30,
        "max_agenda": 40,
    },
    "server": {"host": "0.0.0.0", "port": 4311, "token": ""},
    "state_dir": ".super",
}

# Keys exposed via GET/POST /api/config (never includes server.token).
PUBLIC_SECTIONS = ("llm", "envelope", "gates", "verification", "quality", "security", "trust", "ambition", "mcp", "tools", "agents", "capabilities", "intelligence")

_BOOL_KEYS = {
    ("gates", k) for k in DEFAULTS["gates"]
} | {
    ("security", k) for k in DEFAULTS["security"]
}


def _sanitize_mcp_server(srv: dict) -> dict:
    """Drop transport-incompatible fields (e.g. leftover url after SSE→stdio)."""
    out = dict(srv)
    out.pop("has_env", None)
    transport = str(out.get("transport", "sse")).lower().strip() or "sse"
    out["transport"] = transport
    if transport == "stdio":
        out.pop("url", None)
        if "args" in out and out["args"] is None:
            out["args"] = []
        elif isinstance(out.get("args"), str):
            raw = out["args"].strip()
            out["args"] = raw.split() if raw else []
    else:
        out.pop("command", None)
        out.pop("args", None)
    # Drop empty optional blobs
    if not out.get("env"):
        out.pop("env", None)
    if not out.get("headers"):
        out.pop("headers", None)
    return out


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def find_config(start: str | None = None) -> str | None:
    """Search upward from start (or cwd) for super.config.json."""
    if os.environ.get("SUPER_CONFIG"):
        return os.environ["SUPER_CONFIG"]
    d = os.path.abspath(start or os.getcwd())
    while True:
        cand = os.path.join(d, "super.config.json")
        if os.path.exists(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent




def _validate(cfg: dict) -> None:
    try:
        if not isinstance(cfg["llm"]["endpoint"], str) or not cfg["llm"]["endpoint"].startswith("http"):
            raise ConfigError("llm.endpoint must be an http(s) URL")
        if not isinstance(cfg["llm"]["model"], str) or not cfg["llm"]["model"]:
            raise ConfigError("llm.model must be a non-empty string")
        timeout = cfg["llm"]["timeout_s"]
        if not isinstance(timeout, (int, float)) or timeout <= 0 or timeout > 3600:
            raise ConfigError("llm.timeout_s must be in (0, 3600]")
        think = cfg["llm"].get("think", True)
        if isinstance(think, bool):
            pass
        elif isinstance(think, str) and think.strip().lower() in (
            "true", "false", "off", "on", "low", "medium", "high", "max",
        ):
            pass
        else:
            raise ConfigError(
                "llm.think must be boolean or one of off|low|medium|high|max"
            )
        env = cfg["envelope"]
        for k in ("max_reply_lines", "best_of_n", "max_tool_steps"):
            if not isinstance(env[k], int) or env[k] < 1 or env[k] > 1000:
                raise ConfigError(f"envelope.{k} must be an int in [1, 1000]")
        for section, key in _BOOL_KEYS:
            if not isinstance(cfg[section][key], bool):
                raise ConfigError(f"{section}.{key} must be boolean")
        host = cfg["server"]["host"]
        if not isinstance(host, str) or not host.strip():
            raise ConfigError("server.host must be a non-empty bind address (e.g. 0.0.0.0, 127.0.0.1)")
        port = cfg["server"]["port"]
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise ConfigError("server.port must be an int in [1, 65535]")
        if not isinstance(cfg["state_dir"], str) or not cfg["state_dir"]:
            raise ConfigError("state_dir must be a non-empty string")
        q = cfg["quality"]
        if q["max_loc_per_edit"] < 1 or q["max_complexity"] < 1 or q["max_nesting"] < 1:
            raise ConfigError("quality budgets must be positive")
        mcp = cfg.get("mcp") or {}
        if not isinstance(mcp, dict) or not isinstance(mcp.get("servers", []), list):
            raise ConfigError("mcp.servers must be a list")
        for i, srv in enumerate(mcp.get("servers", [])):
            if not isinstance(srv, dict):
                raise ConfigError(f"mcp.servers[{i}] must be an object")
            if not str(srv.get("name", "")).strip():
                raise ConfigError(f"mcp.servers[{i}].name is required")
            transport = str(srv.get("transport", "sse")).lower()
            if transport not in ("sse", "stdio", "http"):
                raise ConfigError(f"mcp.servers[{i}].transport must be sse, stdio, or http")
            if transport in ("sse", "http") and not str(srv.get("url", "")).strip():
                raise ConfigError(f"mcp.servers[{i}].url is required for {transport}")
            if transport == "stdio" and not str(srv.get("command", "")).strip():
                raise ConfigError(f"mcp.servers[{i}].command is required for stdio")
        tools = cfg.get("tools") or {}
        if not isinstance(tools, dict):
            raise ConfigError("tools must be an object")
        for bk in ("enabled", "discovery"):
            if bk in tools and not isinstance(tools[bk], bool):
                raise ConfigError(f"tools.{bk} must be boolean")
        for ik in ("max_result_chars", "max_activated"):
            if ik in tools:
                v = tools[ik]
                if not isinstance(v, int) or v < 1 or v > 100_000:
                    raise ConfigError(f"tools.{ik} must be an int in [1, 100000]")
        if "groups" in tools and not isinstance(tools["groups"], dict):
            raise ConfigError("tools.groups must be an object")
        if "groups" in tools:
            for gk, gv in tools["groups"].items():
                if not isinstance(gv, bool):
                    raise ConfigError(f"tools.groups.{gk} must be boolean")
        if "disabled" in tools:
            if not isinstance(tools["disabled"], list) or not all(isinstance(x, str) for x in tools["disabled"]):
                raise ConfigError("tools.disabled must be a list of strings")
        if "packs" in tools:
            if not isinstance(tools["packs"], dict):
                raise ConfigError("tools.packs must be an object")
            for pk, pv in tools["packs"].items():
                if not isinstance(pv, bool):
                    raise ConfigError(f"tools.packs.{pk} must be boolean")
        for ck in ("pack_config", "builtin_config"):
            if ck in tools:
                if not isinstance(tools[ck], dict):
                    raise ConfigError(f"tools.{ck} must be an object")
                for name, vals in tools[ck].items():
                    if not isinstance(vals, dict):
                        raise ConfigError(f"tools.{ck}.{name} must be an object")
        if "runtime" in tools and tools["runtime"] not in ("auto", "stdlib", "langgraph"):
            raise ConfigError("tools.runtime must be auto, stdlib, or langgraph")
        agents = cfg.get("agents") or {}
        if not isinstance(agents, dict):
            raise ConfigError("agents must be an object")
        if "enabled" in agents and not isinstance(agents["enabled"], bool):
            raise ConfigError("agents.enabled must be boolean")
        for ik in ("max_depth", "max_agents"):
            if ik in agents:
                v = agents[ik]
                if not isinstance(v, int) or v < 1 or v > 200:
                    raise ConfigError(f"agents.{ik} must be an int in [1, 200]")
        if "allow_agent_create_roles" in agents:
            roles = agents["allow_agent_create_roles"]
            if not isinstance(roles, list) or not all(isinstance(x, str) for x in roles):
                raise ConfigError("agents.allow_agent_create_roles must be a list of strings")
        caps = cfg.get("capabilities") or {}
        if not isinstance(caps, dict):
            raise ConfigError("capabilities must be an object")
        for bk in ("enabled", "auto_install_low"):
            if bk in caps and not isinstance(caps[bk], bool):
                raise ConfigError(f"capabilities.{bk} must be boolean")
        intel = cfg.get("intelligence") or {}
        if not isinstance(intel, dict):
            raise ConfigError("intelligence must be an object")
        for bk in ("enabled", "auto_act", "inject_briefing"):
            if bk in intel and not isinstance(intel[bk], bool):
                raise ConfigError(f"intelligence.{bk} must be boolean")
        if "min_interval_s" in intel:
            v = intel["min_interval_s"]
            if not isinstance(v, (int, float)) or v < 0 or v > 3600:
                raise ConfigError("intelligence.min_interval_s must be in [0, 3600]")
        if "max_agenda" in intel:
            v = intel["max_agenda"]
            if not isinstance(v, int) or v < 5 or v > 100:
                raise ConfigError("intelligence.max_agenda must be an int in [5, 100]")
    except KeyError as e:
        raise ConfigError(f"missing required config key: {e}") from e


def public_view(cfg: dict) -> dict:
    """Safe config slice for the settings UI (no auth secrets)."""
    out = {}
    for section in PUBLIC_SECTIONS:
        if section in cfg and isinstance(cfg[section], dict):
            out[section] = dict(cfg[section])
            if section == "mcp":
                servers = []
                for s in (cfg[section].get("servers") or []):
                    if not isinstance(s, dict):
                        continue
                    clean = {k: v for k, v in s.items() if k != "env"}
                    if s.get("env"):
                        clean["has_env"] = True
                    servers.append(clean)
                out[section] = {"servers": servers}
            if section == "tools":
                from .tools.tool_config import redact_tools_for_public
                out[section] = redact_tools_for_public(out[section])
    out["workspace"] = cfg.get("_root", "")
    out["state_dir"] = cfg.get("state_dir", "")
    out["config_path"] = cfg.get("_config_path")
    return out


def apply_patch(cfg: dict, patch: dict) -> dict:
    """Merge a settings patch into cfg. Rejects server/token and unknown top-level keys."""
    if not isinstance(patch, dict):
        raise ConfigError("config patch must be an object")
    forbidden = {"server", "token", "_root", "_config_path", "state_dir"}
    for key in patch:
        if key in forbidden or key.startswith("_"):
            raise ConfigError(f"cannot update {key} via API")
        if key not in PUBLIC_SECTIONS:
            raise ConfigError(f"unknown config section: {key}")
    safe_patch = {k: v for k, v in patch.items() if k in PUBLIC_SECTIONS}
    # Preserve MCP env blobs when the UI omits them (never round-tripped).
    if "mcp" in safe_patch and isinstance(safe_patch["mcp"], dict):
        old_servers = (cfg.get("mcp") or {}).get("servers") or []
        by_id = {str(s.get("id")): s for s in old_servers if isinstance(s, dict) and s.get("id")}
        by_name = {str(s.get("name")): s for s in old_servers if isinstance(s, dict) and s.get("name")}
        new_servers = []
        for s in safe_patch["mcp"].get("servers") or []:
            if not isinstance(s, dict):
                continue
            s = _sanitize_mcp_server(s)
            prev = by_id.get(str(s.get("id"))) or by_name.get(str(s.get("name")))
            if prev and "env" in prev and "env" not in s:
                s["env"] = prev["env"]
            new_servers.append(s)
        safe_patch = {**safe_patch, "mcp": {**safe_patch["mcp"], "servers": new_servers}}
    # Preserve tool pack / builtin secrets when UI sends placeholders.
    if "tools" in safe_patch and isinstance(safe_patch["tools"], dict):
        from .tools.tool_config import apply_config_patch
        # Deep-merge tools with existing so partial patches don't wipe packs
        merged_tools = _deep_merge(cfg.get("tools") or {}, safe_patch["tools"])
        apply_config_patch(cfg, merged_tools)
        safe_patch = {**safe_patch, "tools": merged_tools}
    merged = _deep_merge(cfg, safe_patch)
    # Keep private keys from original
    for pk in ("_root", "_config_path", "server", "state_dir"):
        if pk in cfg:
            merged[pk] = cfg[pk]
    _migrate_legacy_keys(merged, safe_patch)
    _validate(merged)
    return merged


def _ensure_token(cfg: dict) -> dict:
    """Pin server.token: explicit config wins, else persisted .token file."""
    if cfg["server"].get("token"):
        return cfg
    token_path = os.path.join(cfg["state_dir"], ".token")
    try:
        os.makedirs(cfg["state_dir"], exist_ok=True)
        if os.path.exists(token_path):
            with open(token_path, "r", encoding="utf-8") as f:
                tok = f.read().strip()
            if tok:
                cfg["server"]["token"] = tok
                return cfg
        tok = secrets.token_urlsafe(32)
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, tok.encode())
        finally:
            os.close(fd)
        try:
            os.chmod(token_path, 0o600)
        except OSError:
            pass
        cfg["server"]["token"] = tok
    except OSError as e:
        raise ConfigError(f"cannot persist server token: {e}") from e
    return cfg


def save(cfg: dict) -> None:
    """Persist cfg sections back to super.config.json (keeps _config_path).

    Never climbs the filesystem via find_config — ephemeral/test cfgs with
    ``_root`` set must write under that root, not a parent checkout's config.
    """
    path = cfg.get("_config_path")
    if not path:
        root = cfg.get("_root") or os.getcwd()
        path = os.path.join(root, "super.config.json")
        cfg["_config_path"] = path
    try:
        # load existing to preserve unknown keys
        existing = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                existing = json.load(f)
        for k in ("llm", "envelope", "gates", "verification", "quality", "security", "trust", "ambition", "mcp", "tools", "server", "state_dir"):
            if k in cfg:
                existing[k] = cfg[k]
        _migrate_legacy_keys(existing, existing)
        # Prefer project-relative state_dir in the on-disk file (load() resolves abs).
        root = cfg.get("_root")
        sd = existing.get("state_dir")
        if isinstance(sd, str) and sd and root:
            abs_sd = os.path.abspath(sd)
            abs_root = os.path.abspath(root)
            try:
                if abs_sd == abs_root or abs_sd.startswith(abs_root + os.sep):
                    rel = os.path.relpath(abs_sd, abs_root)
                    if rel in (".super", os.path.join(".", ".super")):
                        existing["state_dir"] = "./.super"
                    else:
                        existing["state_dir"] = rel
            except ValueError:
                pass
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
            f.write("\n")
    except Exception as e:
        raise ConfigError(f"cannot save config {path}: {e}") from e


def _apply_env_overrides(cfg: dict) -> dict:
    if os.environ.get("SUPER_LLM_ENDPOINT"):
        cfg["llm"]["endpoint"] = os.environ["SUPER_LLM_ENDPOINT"]
    if os.environ.get("SUPER_LLM_MODEL"):
        cfg["llm"]["model"] = os.environ["SUPER_LLM_MODEL"]
    if os.environ.get("SUPER_PORT"):
        try:
            cfg["server"]["port"] = int(os.environ["SUPER_PORT"])
        except ValueError as e:
            raise ConfigError("SUPER_PORT must be an integer") from e
    if os.environ.get("SUPER_TOKEN"):
        cfg["server"]["token"] = os.environ["SUPER_TOKEN"]
    return cfg


def _migrate_legacy_keys(cfg: dict, user: dict | None = None) -> dict:
    """Fold renamed envelope/trust keys from older config files into current names.

    Deep-merge injects DEFAULT new keys (e.g. max_tool_steps=20) alongside a
    user's old max_steps_per_task=200 — without this, runtime silently uses 20.
    User-file new names always win; legacy names only fill when the new name
    was never set in the user file.
    """
    user = user if isinstance(user, dict) else {}
    uenv = user.get("envelope") if isinstance(user.get("envelope"), dict) else {}
    utrust = user.get("trust") if isinstance(user.get("trust"), dict) else {}
    env = cfg.setdefault("envelope", {})
    trust = cfg.setdefault("trust", {})
    if not isinstance(env, dict):
        cfg["envelope"] = {}
        env = cfg["envelope"]
    if not isinstance(trust, dict):
        cfg["trust"] = {}
        trust = cfg["trust"]

    # New names in the user file always win; legacy only fills when unset.
    if "max_tool_steps" not in uenv:
        src = uenv if "max_steps_per_task" in uenv else env
        if "max_steps_per_task" in src:
            try:
                env["max_tool_steps"] = int(src["max_steps_per_task"])
            except (TypeError, ValueError):
                pass
    env.pop("max_steps_per_task", None)

    if "max_reply_lines" not in uenv:
        src = uenv if "max_microtask_lines" in uenv else env
        if "max_microtask_lines" in src:
            try:
                env["max_reply_lines"] = int(src["max_microtask_lines"])
            except (TypeError, ValueError):
                pass
    env.pop("max_microtask_lines", None)

    if "attention_budget" not in utrust:
        src = utrust if "attention_budget_per_task" in utrust else trust
        if "attention_budget_per_task" in src:
            try:
                trust["attention_budget"] = int(src["attention_budget_per_task"])
            except (TypeError, ValueError):
                pass
    trust.pop("attention_budget_per_task", None)

    # Drop removed gate / tool-group leftovers from older configs.
    gates = cfg.get("gates")
    if isinstance(gates, dict):
        for dead in ("spec", "drift"):
            gates.pop(dead, None)
    tools = cfg.get("tools")
    if isinstance(tools, dict):
        groups = tools.get("groups")
        if isinstance(groups, dict):
            groups.pop("tasks", None)
    return cfg


def load(path: str | None = None) -> dict:
    path = path or find_config()
    user: dict | None = None
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                user = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise ConfigError(f"cannot read config {path}: {e}") from e
        if not isinstance(user, dict):
            raise ConfigError(f"config {path} must be a JSON object")
        cfg = _deep_merge(DEFAULTS, user)
        cfg["_config_path"] = path
        cfg["_root"] = os.path.dirname(os.path.abspath(path))
    else:
        cfg = json.loads(json.dumps(DEFAULTS))
        cfg["_config_path"] = None
        cfg["_root"] = os.getcwd()
    _migrate_legacy_keys(cfg, user)
    _apply_env_overrides(cfg)
    if not os.path.isabs(cfg["state_dir"]):
        cfg["state_dir"] = os.path.join(cfg["_root"], cfg["state_dir"])
    _validate(cfg)
    return _ensure_token(cfg)


def load_workspace(root: str) -> dict:
    """Load config for an explicit project/working directory.

    Uses ``<root>/super.config.json`` when present; otherwise defaults with
    ``_root`` pinned to ``root`` (does not fall back to process cwd / upward search).
    """
    root = os.path.abspath(os.path.expanduser(str(root or "").strip()))
    if not root or not os.path.isdir(root):
        raise ConfigError(f"workspace must be an existing directory: {root or '(empty)'}")
    cfg_path = os.path.join(root, "super.config.json")
    if os.path.isfile(cfg_path):
        return load(cfg_path)
    cfg = json.loads(json.dumps(DEFAULTS))
    cfg["_config_path"] = None
    cfg["_root"] = root
    _migrate_legacy_keys(cfg, None)
    _apply_env_overrides(cfg)
    if not os.path.isabs(cfg["state_dir"]):
        cfg["state_dir"] = os.path.join(cfg["_root"], cfg["state_dir"])
    _validate(cfg)
    return _ensure_token(cfg)
