"""Production configuration loader.

Sources (ascending precedence): built-in defaults < super.config.json <
environment (SUPER_CONFIG, SUPER_TOKEN, SUPER_LLM_ENDPOINT, SUPER_LLM_MODEL,
SUPER_PORT). Every value is type/range validated; invalid config raises
ConfigError with the offending key instead of failing downstream.

Auth: the server requires a bearer token. Operators may pin
`server.token`; otherwise the first load generates a 32-byte token persisted
at <state_dir>/.token with mode 0600.
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
    },
    "envelope": {
        "max_microtask_lines": 50,
        "best_of_n": 5,
        "max_steps_per_task": 20,
        "early_abort_stall": 3,
    },
    "gates": {
        "grounding": True,
        "docs_before_write": True,
        "standards": True,
        "duplication": True,
        "verification": True,
        "mutation": True,
        "spec": True,
        "drift": True,
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
        "attention_budget_per_task": 10,
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
            "tasks": True,
            "memory": True,
            "project": True,
        },
        "disabled": [],
        "packs": {
            "lc_http": False,
            "lc_search": False,
            "lc_arxiv": False,
            "lc_wikipedia": False,
            "lc_python": False,
            "lc_shell": False,
            "lc_files": False,
            "lc_human": False,
            "crewai_stdlib": False,
            "lc_tavily": False,
            "lc_github": False,
        },
        "pack_config": {},
        "builtin_config": {},
        "runtime": "auto",
    },
    "server": {"host": "127.0.0.1", "port": 4311, "token": ""},
    "state_dir": ".super",
}

# Keys exposed via GET/POST /api/config (never includes server.token).
PUBLIC_SECTIONS = ("llm", "envelope", "gates", "verification", "quality", "security", "trust", "ambition", "mcp", "tools")

_BOOL_KEYS = {
    ("gates", k) for k in DEFAULTS["gates"]
} | {
    ("security", k) for k in DEFAULTS["security"]
}


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
        env = cfg["envelope"]
        for k in ("max_microtask_lines", "best_of_n", "max_steps_per_task"):
            if not isinstance(env[k], int) or env[k] < 1 or env[k] > 1000:
                raise ConfigError(f"envelope.{k} must be an int in [1, 1000]")
        for section, key in _BOOL_KEYS:
            if not isinstance(cfg[section][key], bool):
                raise ConfigError(f"{section}.{key} must be boolean")
        host = cfg["server"]["host"]
        if host not in ("127.0.0.1", "localhost"):
            raise ConfigError("server.host must be 127.0.0.1 or localhost (local-only binding)")
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
            s = dict(s)
            s.pop("has_env", None)
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
    """Persist cfg llm/model + envelope + gates back to super.config.json (keeps _config_path)."""
    path = cfg.get("_config_path") or find_config() or os.path.join(cfg.get("_root", os.getcwd()), "super.config.json")
    try:
        # load existing to preserve comments structure? just merge
        existing = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                existing = json.load(f)
        # only persist known top-level keys
        for k in ("llm", "envelope", "gates", "verification", "quality", "security", "trust", "ambition", "mcp", "tools", "server", "state_dir"):
            if k in cfg:
                # for llm, only persist endpoint/model/timeout etc, not _root
                existing[k] = cfg[k]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        raise ConfigError(f"cannot save config {path}: {e}") from e


def load(path: str | None = None) -> dict:
    path = path or find_config()
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
    # Environment overrides.
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
    if not os.path.isabs(cfg["state_dir"]):
        cfg["state_dir"] = os.path.join(cfg["_root"], cfg["state_dir"])
    _validate(cfg)
    return _ensure_token(cfg)
