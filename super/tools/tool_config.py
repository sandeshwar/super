"""Tool / pack configuration schemas and secret-safe resolve/merge.

`tools.pack_config`     — per LangChain/CrewAI pack (api keys, limits, …)
`tools.builtin_config`  — per built-in tool (timeouts, defaults, …)

Secret fields never round-trip to the UI; empty/•••• on save keeps the prior value.
Env fallbacks (field.env) apply when the stored value is empty.
"""

from __future__ import annotations

import os
from typing import Any

# Field: key, label, type (string|secret|number|boolean|url|json), required?,
# default, env?, placeholder?, desc?

Field = dict[str, Any]

SECRET_PLACEHOLDER = "••••••••"


def _f(
    key: str,
    label: str,
    *,
    type: str = "string",
    required: bool = False,
    default: Any = "",
    env: str | None = None,
    placeholder: str = "",
    desc: str = "",
) -> Field:
    return {
        "key": key,
        "label": label,
        "type": type,
        "required": required,
        "default": default,
        "env": env,
        "placeholder": placeholder,
        "desc": desc,
    }


# ── Pack field schemas (referenced by pack id) ─────────────────────────

PACK_FIELDS: dict[str, list[Field]] = {
    "lc_http": [
        _f("timeout_s", "Timeout (s)", type="number", default=15, desc="HTTP request timeout"),
        _f("headers_json", "Extra headers (JSON)", type="json", default="{}", placeholder='{"Authorization":"Bearer …"}'),
    ],
    "lc_search": [
        _f("max_results", "Max results", type="number", default=5),
        _f("tavily_api_key", "Tavily API key", type="secret", env="TAVILY_API_KEY", desc="Optional — enables Tavily search"),
        _f("serper_api_key", "Serper API key", type="secret", env="SERPER_API_KEY", desc="Optional — Google via Serper"),
    ],
    "lc_arxiv": [
        _f("max_results", "Max papers", type="number", default=3),
    ],
    "lc_wikipedia": [
        _f("lang", "Language", type="string", default="en", placeholder="en"),
        _f("top_k_results", "Top K results", type="number", default=3),
        _f("doc_content_chars_max", "Max chars per page", type="number", default=4000),
    ],
    "lc_python": [
        _f("timeout_s", "REPL timeout (s)", type="number", default=30),
    ],
    "lc_shell": [
        _f("timeout_s", "Command timeout (s)", type="number", default=60),
    ],
    "lc_files": [
        _f("root_dir", "Root directory", type="string", default="", placeholder="(workspace)", desc="Leave empty for workspace root"),
    ],
    "lc_human": [
        _f("prompt_prefix", "Prompt prefix", type="string", default="Operator input needed: "),
    ],
    "crewai_stdlib": [
        _f("root_dir", "Root directory", type="string", default="", placeholder="(workspace)"),
    ],
    "lc_tavily": [
        _f("api_key", "Tavily API key", type="secret", required=True, env="TAVILY_API_KEY"),
        _f("max_results", "Max results", type="number", default=5),
        _f("search_depth", "Search depth", type="string", default="basic", placeholder="basic | advanced"),
    ],
    "lc_github": [
        _f("github_token", "GitHub token", type="secret", required=True, env="GITHUB_TOKEN", desc="PAT for repo/issues tools"),
        _f("github_app_id", "GitHub App id", type="string", default=""),
    ],
}

# ── Built-in tool field schemas ────────────────────────────────────────

BUILTIN_FIELDS: dict[str, list[Field]] = {
    "run_command": [
        _f("default_timeout_s", "Default timeout (s)", type="number", default=60),
        _f("shell", "Shell binary", type="string", default="", placeholder="(system default)"),
    ],
    "fetch_url": [
        _f("timeout_s", "Default timeout (s)", type="number", default=15),
        _f("user_agent", "User-Agent", type="string", default="super-harness/1.0"),
        _f("max_bytes", "Max download bytes", type="number", default=200000),
    ],
    "grep": [
        _f("max_hits", "Default max hits", type="number", default=40),
    ],
    "read_file": [
        _f("default_limit", "Default line limit", type="number", default=200),
    ],
    "write_file": [
        _f("require_confirm_paths", "Paths needing extra care (comma globs)", type="string", default="", placeholder="**/secrets*,**/.env*"),
    ],
}


def fields_for_pack(pack_id: str) -> list[Field]:
    return list(PACK_FIELDS.get(pack_id) or [])


def fields_for_builtin(name: str) -> list[Field]:
    return list(BUILTIN_FIELDS.get(name) or [])


def _is_secret(field: Field) -> bool:
    return field.get("type") == "secret"


def resolve(fields: list[Field], stored: dict | None) -> dict[str, Any]:
    """Merge defaults ← env ← stored into a concrete config dict."""
    stored = stored or {}
    out: dict[str, Any] = {}
    for f in fields:
        key = f["key"]
        val = stored.get(key, None)
        if val is None or val == "":
            env_name = f.get("env")
            if env_name and os.environ.get(env_name):
                val = os.environ[env_name]
            else:
                val = f.get("default", "")
        # coerce numbers/bools
        if f.get("type") == "number":
            try:
                val = int(val) if val != "" and val is not None else f.get("default", 0)
            except (TypeError, ValueError):
                try:
                    val = float(val)
                except (TypeError, ValueError):
                    val = f.get("default", 0)
        elif f.get("type") == "boolean":
            if isinstance(val, str):
                val = val.strip().lower() in ("1", "true", "yes", "on")
            else:
                val = bool(val)
        out[key] = val
    return out


def resolve_pack(cfg: dict, pack_id: str) -> dict[str, Any]:
    stored = ((cfg.get("tools") or {}).get("pack_config") or {}).get(pack_id) or {}
    return resolve(fields_for_pack(pack_id), stored if isinstance(stored, dict) else {})


def resolve_builtin(cfg: dict, tool_name: str) -> dict[str, Any]:
    stored = ((cfg.get("tools") or {}).get("builtin_config") or {}).get(tool_name) or {}
    return resolve(fields_for_builtin(tool_name), stored if isinstance(stored, dict) else {})


def public_values(fields: list[Field], stored: dict | None) -> list[dict]:
    """UI-safe field list with values; secrets masked."""
    stored = stored or {}
    rows = []
    for f in fields:
        key = f["key"]
        raw = stored.get(key, f.get("default", ""))
        has = bool(raw) or bool(f.get("env") and os.environ.get(f["env"]))
        if _is_secret(f):
            value = SECRET_PLACEHOLDER if has and raw else ""
            # if only env provides it, still show placeholder when has
            if not raw and f.get("env") and os.environ.get(f["env"]):
                value = SECRET_PLACEHOLDER
                has = True
        else:
            value = raw if raw is not None else f.get("default", "")
        rows.append({
            **{k: f[k] for k in ("key", "label", "type", "required", "placeholder", "desc", "env") if k in f},
            "default": f.get("default", ""),
            "value": value,
            "has_value": has if _is_secret(f) else None,
        })
    return rows


def merge_secrets(fields: list[Field], old: dict | None, new: dict | None) -> dict:
    """Apply UI patch: blank/•••• secret fields keep old values."""
    old = dict(old or {})
    new = dict(new or {})
    out = dict(old)
    secret_keys = {f["key"] for f in fields if _is_secret(f)}
    for k, v in new.items():
        if k in secret_keys:
            if v is None or v == "" or v == SECRET_PLACEHOLDER or str(v).startswith("••"):
                continue  # keep old
        out[k] = v
    # drop unknown keys not in schema? keep extras for forward compat
    return out


def public_pack_configs(cfg: dict) -> dict[str, list[dict]]:
    pack_cfg = (cfg.get("tools") or {}).get("pack_config") or {}
    out = {}
    for pid, fields in PACK_FIELDS.items():
        if not fields:
            continue
        out[pid] = public_values(fields, pack_cfg.get(pid) if isinstance(pack_cfg.get(pid), dict) else {})
    return out


def public_builtin_configs(cfg: dict) -> dict[str, list[dict]]:
    bcfg = (cfg.get("tools") or {}).get("builtin_config") or {}
    out = {}
    for name, fields in BUILTIN_FIELDS.items():
        out[name] = public_values(fields, bcfg.get(name) if isinstance(bcfg.get(name), dict) else {})
    return out


def apply_config_patch(cfg: dict, tools_patch: dict) -> dict:
    """Mutate tools_patch in place to preserve secrets in pack_config / builtin_config."""
    old_tools = cfg.get("tools") or {}
    if "pack_config" in tools_patch and isinstance(tools_patch["pack_config"], dict):
        old_pc = old_tools.get("pack_config") or {}
        merged = {}
        for pid, vals in tools_patch["pack_config"].items():
            if not isinstance(vals, dict):
                continue
            merged[pid] = merge_secrets(fields_for_pack(pid), old_pc.get(pid) if isinstance(old_pc.get(pid), dict) else {}, vals)
        # keep packs not mentioned
        for pid, vals in old_pc.items():
            if pid not in merged and isinstance(vals, dict):
                merged[pid] = vals
        tools_patch["pack_config"] = merged
    if "builtin_config" in tools_patch and isinstance(tools_patch["builtin_config"], dict):
        old_bc = old_tools.get("builtin_config") or {}
        merged = {}
        for name, vals in tools_patch["builtin_config"].items():
            if not isinstance(vals, dict):
                continue
            merged[name] = merge_secrets(fields_for_builtin(name), old_bc.get(name) if isinstance(old_bc.get(name), dict) else {}, vals)
        for name, vals in old_bc.items():
            if name not in merged and isinstance(vals, dict):
                merged[name] = vals
        tools_patch["builtin_config"] = merged
    return tools_patch


def redact_tools_for_public(tools: dict) -> dict:
    """Copy tools section with secrets stripped from pack_config / builtin_config."""
    out = dict(tools)
    if "pack_config" in out:
        # replace with nothing — UI should use /api/tools packs[].config
        # but also expose sanitized map for getConfig consumers
        redacted = {}
        for pid, vals in (out.get("pack_config") or {}).items():
            if not isinstance(vals, dict):
                continue
            fields = {f["key"]: f for f in fields_for_pack(pid)}
            clean = {}
            for k, v in vals.items():
                f = fields.get(k)
                if f and _is_secret(f):
                    if v:
                        clean[k] = SECRET_PLACEHOLDER
                else:
                    clean[k] = v
            redacted[pid] = clean
        out["pack_config"] = redacted
    if "builtin_config" in out:
        redacted = {}
        for name, vals in (out.get("builtin_config") or {}).items():
            if not isinstance(vals, dict):
                continue
            fields = {f["key"]: f for f in fields_for_builtin(name)}
            clean = {}
            for k, v in vals.items():
                f = fields.get(k)
                if f and _is_secret(f):
                    if v:
                        clean[k] = SECRET_PLACEHOLDER
                else:
                    clean[k] = v
            redacted[name] = clean
        out["builtin_config"] = redacted
    return out
