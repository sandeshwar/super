"""Bridge MCP servers into SUPER's tool catalog.

Config lives under ``mcp.servers`` (Settings → MCP servers). Enabled servers are
probed for tools and registered into the same discovery/activation flow as
builtins and LangChain packs.

Requires optional dep: ``pip install 'mcp>=1.9,<2'`` (or ``pip install -e '.[mcp]'``).

Transports: stdio, sse (legacy), http (streamable HTTP).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import logging
import os
import re
import threading
from contextlib import asynccontextmanager
from typing import Any, Callable

from .base import ToolResult, ToolSpec, dump_json

log = logging.getLogger("super.tools.mcp")

GROUP = "mcp"
GROUP_META = {
    "title": "MCP",
    "blurb": "Tools from configured Model Context Protocol servers",
}

# server_key → registered SUPER tool names
_registered: dict[str, set[str]] = {}
# fingerprint of last successful sync (config slice)
_fp: str | None = None
# remote tool name per SUPER tool name: (server_key, remote_name)
_remote: dict[str, tuple[str, str]] = {}
# last server dicts by key (for call-time reconnect)
_servers: dict[str, dict] = {}
_lock = threading.Lock()


def mcp_available() -> bool:
    try:
        import mcp  # noqa: F401
        from mcp import ClientSession  # noqa: F401
        return True
    except ImportError:
        return False


def status() -> dict[str, Any]:
    return {
        "mcp": mcp_available(),
        "servers_loaded": len(_servers),
        "tools_registered": sum(len(v) for v in _registered.values()),
    }


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", (name or "").strip()).strip("_").lower()
    return s or "server"


def _server_key(srv: dict) -> str:
    return str(srv.get("id") or srv.get("name") or "mcp").strip() or "mcp"


def _tool_name(server_name: str, remote: str) -> str:
    """Stable SUPER name: ``mcp_<server>__<tool>`` (OpenAI-safe)."""
    raw = f"mcp_{_slug(server_name)}__{_slug(remote)}"
    return raw[:64]


def _enabled_servers(cfg: dict) -> list[dict]:
    out = []
    for s in ((cfg.get("mcp") or {}).get("servers") or []):
        if not isinstance(s, dict):
            continue
        if s.get("enabled", True) is False:
            continue
        if not str(s.get("name", "")).strip():
            continue
        out.append(dict(s))
    return out


def _fingerprint(servers: list[dict]) -> str:
    """Hash connection-relevant fields (incl. env values — secrets stay local)."""
    slim = []
    for s in servers:
        slim.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "transport": str(s.get("transport", "sse")).lower(),
            "url": s.get("url"),
            "command": s.get("command"),
            "args": s.get("args") or [],
            "env": s.get("env") or {},
            "headers": s.get("headers") or {},
            "enabled": s.get("enabled", True),
        })
    blob = json.dumps(slim, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _run_async(coro: Any, timeout: float = 120.0) -> Any:
    """Run an async coroutine from sync tool handlers."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside an event loop — run on a worker thread.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=timeout)


def _headers(srv: dict) -> dict[str, str] | None:
    h = srv.get("headers")
    if not isinstance(h, dict) or not h:
        return None
    return {str(k): str(v) for k, v in h.items()}


def _stdio_env(srv: dict) -> dict[str, str]:
    env = {k: str(v) for k, v in os.environ.items()}
    extra = srv.get("env")
    if isinstance(extra, dict):
        for k, v in extra.items():
            if v is None:
                continue
            env[str(k)] = str(v)
    return env


def _stdio_args(srv: dict) -> list[str]:
    raw = srv.get("args") or []
    if isinstance(raw, str):
        return raw.split() if raw.strip() else []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return []


@asynccontextmanager
async def _open_session(srv: dict, cfg: dict):
    """Yield an initialized ClientSession for one server, then tear down."""
    from mcp import ClientSession

    transport = str(srv.get("transport", "sse")).lower()

    if transport == "stdio":
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        cmd = str(srv.get("command") or "").strip()
        if not cmd:
            raise RuntimeError("stdio MCP server missing command")
        params = StdioServerParameters(
            command=cmd,
            args=_stdio_args(srv),
            env=_stdio_env(srv),
            cwd=cfg.get("_root") or os.getcwd(),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
        return

    if transport == "sse":
        from mcp.client.sse import sse_client

        url = str(srv.get("url") or "").strip()
        if not url:
            raise RuntimeError("sse MCP server missing url")
        kwargs: dict[str, Any] = {}
        headers = _headers(srv)
        if headers:
            kwargs["headers"] = headers
        async with sse_client(url, **kwargs) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
        return

    if transport == "http":
        url = str(srv.get("url") or "").strip()
        if not url:
            raise RuntimeError("http MCP server missing url")
        headers = _headers(srv)
        try:
            from mcp.client.streamable_http import streamablehttp_client as _http_client
        except ImportError:
            from mcp.client.streamable_http import streamable_http_client as _http_client  # type: ignore

        if headers:
            try:
                import httpx
                async with httpx.AsyncClient(headers=headers, follow_redirects=True) as http_client:
                    async with _http_client(url, http_client=http_client) as streams:
                        read, write = streams[0], streams[1]
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            yield session
                return
            except TypeError:
                pass
        async with _http_client(url) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
        return

    raise RuntimeError(f"unsupported MCP transport: {transport}")


async def _list_remote_tools(srv: dict, cfg: dict) -> list[dict[str, Any]]:
    async with _open_session(srv, cfg) as session:
        result = await session.list_tools()
        tools = getattr(result, "tools", None) or []
        out = []
        for t in tools:
            name = str(getattr(t, "name", "") or "").strip()
            if not name:
                continue
            desc = str(getattr(t, "description", None) or name)
            schema = getattr(t, "inputSchema", None) or getattr(t, "input_schema", None) or {}
            if hasattr(schema, "model_dump"):
                schema = schema.model_dump(by_alias=True, exclude_none=True)
            elif hasattr(schema, "dict"):
                schema = schema.dict()
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            if schema.get("type") != "object":
                schema = {
                    "type": "object",
                    "properties": schema.get("properties") or {},
                    "required": schema.get("required") or [],
                    "additionalProperties": schema.get("additionalProperties", True),
                }
            out.append({
                "name": name,
                "description": desc,
                "parameters": schema,
            })
        return out


async def _call_remote(srv: dict, cfg: dict, remote_name: str, arguments: dict) -> ToolResult:
    from .. import media as _media

    async with _open_session(srv, cfg) as session:
        result = await session.call_tool(remote_name, arguments or {})
        is_err = bool(getattr(result, "isError", False) or getattr(result, "is_error", False))
        content, parts = _media.extract_from_mcp_blocks(
            cfg, getattr(result, "content", None) or [], source=f"mcp:{srv.get('name') or 'server'}"
        )
        if not content:
            content = "(error)" if is_err else ("(empty)" if not parts else f"[{len(parts)} image(s)]")
        data: dict = {}
        if parts:
            data["media"] = [_media.public_part(p) for p in parts]
        return ToolResult(not is_err, content, data=data, taint="untrusted")


def _make_handler(server_key: str, remote_name: str) -> Callable[[dict, dict], ToolResult]:
    def handler(cfg: dict, args: dict) -> ToolResult:
        srv = _servers.get(server_key)
        if not srv:
            return ToolResult(False, f"MCP server not loaded: {server_key}")
        try:
            return _run_async(_call_remote(srv, cfg, remote_name, args or {}))
        except Exception as e:
            return ToolResult(False, f"mcp {server_key}/{remote_name}: {type(e).__name__}: {e}")

    return handler


def _unregister_all() -> None:
    from . import catalog

    names = set()
    for s in _registered.values():
        names |= s
    for n in names:
        catalog.TOOLS.pop(n, None)
        _remote.pop(n, None)
    _registered.clear()
    _servers.clear()


def _register_one(cfg: dict, srv: dict, remote: dict[str, Any]) -> str | None:
    from . import catalog

    skey = _server_key(srv)
    sname = str(srv.get("name") or skey)
    remote_name = remote["name"]
    tname = _tool_name(sname, remote_name)
    # Collision with non-MCP tool → suffix
    existing = catalog.TOOLS.get(tname)
    if existing and existing.group != GROUP:
        tname = f"{tname}_mcp"[:64]

    desc = remote.get("description") or remote_name
    summary = (desc.split(".")[0] if desc else remote_name)[:80]
    params = remote.get("parameters") or {"type": "object", "properties": {}}
    if not isinstance(params, dict):
        params = {"type": "object", "properties": {}}

    spec = ToolSpec(
        name=tname,
        group=GROUP,
        summary=summary,
        description=f"[MCP:{sname}] {desc}",
        parameters=params,
        handler=_make_handler(skey, remote_name),
        risk="medium",
        keywords=f"mcp {sname} {remote_name}",
    )
    catalog.TOOLS[tname] = spec
    _remote[tname] = (skey, remote_name)
    _registered.setdefault(skey, set()).add(tname)
    return tname


def sync_mcp(cfg: dict, *, force: bool = False) -> dict[str, Any]:
    """Connect to enabled MCP servers and register their tools. Idempotent."""
    global _fp

    if not mcp_available():
        return {"ok": False, "error": "mcp package not installed (pip install 'mcp>=1.9,<2')", "tools": []}

    servers = _enabled_servers(cfg)
    fp = _fingerprint(servers)

    with _lock:
        from . import catalog
        if GROUP not in catalog.GROUPS:
            catalog.GROUPS[GROUP] = dict(GROUP_META)
        if not force and fp == _fp and _servers:
            return {
                "ok": True,
                "cached": True,
                "tools": sorted(_remote.keys()),
                "servers": list(_servers.keys()),
            }

    # Probe servers outside the lock (stdio/HTTP can be slow).
    probed: list[tuple[dict, list[dict[str, Any]] | None, str | None]] = []
    for srv in servers:
        skey = _server_key(srv)
        try:
            remotes = _run_async(_list_remote_tools(srv, cfg), timeout=60.0)
            probed.append((srv, remotes, None))
        except Exception as e:
            log.warning("MCP server %s list_tools failed: %s", skey, e)
            probed.append((srv, None, f"{type(e).__name__}: {e}"))

    with _lock:
        # Another thread may have synced meanwhile
        if not force and fp == _fp and _servers:
            return {
                "ok": True,
                "cached": True,
                "tools": sorted(_remote.keys()),
                "servers": list(_servers.keys()),
            }
        _unregister_all()
        errors: list[dict[str, str]] = []
        loaded: list[str] = []
        for srv, remotes, err in probed:
            skey = _server_key(srv)
            if err or remotes is None:
                errors.append({"server": skey, "error": err or "unknown"})
                continue
            _servers[skey] = srv
            for remote in remotes:
                name = _register_one(cfg, srv, remote)
                if name:
                    loaded.append(name)

        _fp = fp if not (errors and not loaded and servers) else None
        return {
            "ok": True,
            "cached": False,
            "tools": loaded,
            "servers": list(_servers.keys()),
            "errors": errors,
        }


def ensure_mcp(cfg: dict) -> None:
    """Ensure MCP group exists and tools are synced. Safe to call often."""
    global _fp
    from . import catalog

    if GROUP not in catalog.GROUPS:
        catalog.GROUPS[GROUP] = dict(GROUP_META)
    servers = _enabled_servers(cfg)
    if not servers:
        # Drop stale registrations when all servers disabled/removed
        if _registered:
            with _lock:
                _unregister_all()
                _fp = None
        return
    if not mcp_available():
        return
    try:
        sync_mcp(cfg)
    except Exception as e:
        log.warning("ensure_mcp failed: %s", e)


def mcp_group_enabled(cfg: dict) -> bool:
    """Whether the mcp group should be considered enabled for discovery."""
    groups = (cfg.get("tools") or {}).get("groups") or {}
    if "mcp" in groups:
        return bool(groups["mcp"])
    # Default on when any server is configured & enabled
    return bool(_enabled_servers(cfg))


def servers_public(cfg: dict) -> list[dict[str, Any]]:
    """Status rows for Settings / API (no secrets)."""
    rows = []
    for s in ((cfg.get("mcp") or {}).get("servers") or []):
        if not isinstance(s, dict):
            continue
        skey = _server_key(s)
        rows.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "transport": s.get("transport"),
            "enabled": s.get("enabled", True) is not False,
            "loaded": skey in _servers,
            "tool_count": len(_registered.get(skey, ())),
            "tools": sorted(_registered.get(skey, ())),
            "url": s.get("url") if str(s.get("transport", "")).lower() in ("sse", "http") else None,
            "command": s.get("command") if str(s.get("transport", "")).lower() == "stdio" else None,
            "args": s.get("args") if str(s.get("transport", "")).lower() == "stdio" else None,
            "has_env": bool(s.get("env")),
        })
    return rows


MAX_SERVERS = 24
_MANAGE_MUTATORS = frozenset({
    "add_mcp_server", "remove_mcp_server", "set_mcp_server", "reload_mcp",
})


def _new_server_id() -> str:
    import secrets
    return "mcp_" + secrets.token_hex(4)


def _all_servers(cfg: dict) -> list[dict]:
    raw = ((cfg.get("mcp") or {}).get("servers") or [])
    return [dict(s) for s in raw if isinstance(s, dict)]


def _find_server(servers: list[dict], *, id: str | None = None, name: str | None = None) -> tuple[int, dict] | None:
    id = (id or "").strip()
    name = (name or "").strip()
    for i, s in enumerate(servers):
        if id and str(s.get("id") or "") == id:
            return i, s
        if name and str(s.get("name") or "") == name:
            return i, s
    return None


def _validate_mcp_url(url: str) -> str:
    from urllib.parse import urlparse
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("url must be http(s) with a host")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("url missing host")
    if host in ("metadata.google.internal",) or host == "169.254.169.254":
        raise ValueError(f"blocked host {host}")
    if host.endswith(".internal") and host != "localhost":
        raise ValueError(f"blocked host {host}")
    return url


def _normalize_server(args: dict, *, existing: dict | None = None) -> dict:
    base = dict(existing or {})
    name = str(args.get("name") if args.get("name") is not None else base.get("name") or "").strip()
    if not name:
        raise ValueError("name required")
    transport = str(
        args.get("transport") if args.get("transport") is not None else base.get("transport") or "stdio"
    ).lower().strip()
    if transport not in ("sse", "stdio", "http"):
        raise ValueError("transport must be sse, stdio, or http")

    out: dict[str, Any] = {
        "id": str(base.get("id") or args.get("id") or _new_server_id()),
        "name": name,
        "transport": transport,
        "enabled": bool(args["enabled"]) if "enabled" in args else bool(base.get("enabled", True)),
    }

    if transport in ("sse", "http"):
        url = str(args.get("url") if args.get("url") is not None else base.get("url") or "").strip()
        if not url:
            raise ValueError(f"url required for {transport}")
        out["url"] = _validate_mcp_url(url)
        out.pop("command", None)
        out.pop("args", None)
    else:
        command = str(args.get("command") if args.get("command") is not None else base.get("command") or "").strip()
        if not command:
            raise ValueError("command required for stdio")
        if " " in command or any(c in command for c in ("\n", "\r", ";", "|", "&", "`", "$(", "'", '"')):
            raise ValueError("command must be a single executable name/path (put flags in args)")
        out["command"] = command
        if "args" in args:
            raw = args.get("args")
            if isinstance(raw, str):
                out["args"] = raw.split() if raw.strip() else []
            elif isinstance(raw, list):
                out["args"] = [str(x) for x in raw]
            elif raw is None:
                out["args"] = []
            else:
                raise ValueError("args must be a string or list of strings")
        else:
            out["args"] = list(base.get("args") or [])
        out.pop("url", None)

    # Optional env — only when explicitly provided (never wipe on partial update)
    if "env" in args and isinstance(args.get("env"), dict):
        env = {str(k): str(v) for k, v in args["env"].items() if v is not None}
        if env:
            out["env"] = env
        else:
            out.pop("env", None)
    elif existing and existing.get("env"):
        out["env"] = dict(existing["env"])

    if "headers" in args and isinstance(args.get("headers"), dict):
        headers = {str(k): str(v) for k, v in args["headers"].items() if v is not None}
        if headers:
            out["headers"] = headers
        else:
            out.pop("headers", None)
    elif existing and existing.get("headers"):
        out["headers"] = dict(existing["headers"])

    return out


def _persist_servers(cfg: dict, servers: list[dict]) -> dict[str, Any]:
    """Write servers into live cfg + disk, then force-sync the catalog."""
    from .. import config as C
    from ..errors import ConfigError

    if len(servers) > MAX_SERVERS:
        raise ValueError(f"max {MAX_SERVERS} MCP servers")

    # Validate via config rules
    try:
        updated = C.apply_patch(cfg, {"mcp": {"servers": servers}})
    except ConfigError as e:
        raise ValueError(str(e)) from e

    # Keep ephemeral runtime keys
    for k, v in list(cfg.items()):
        if k.startswith("_") and k not in updated:
            updated[k] = v
    cfg.clear()
    cfg.update(updated)
    C.save(cfg)
    return sync_mcp(cfg, force=True)


def handle_list_mcp_servers(cfg: dict, args: dict) -> ToolResult:
    ensure_mcp(cfg)
    return ToolResult(True, dump_json({
        "sdk": mcp_available(),
        "servers": servers_public(cfg),
        "tip": (
            "Use add_mcp_server / set_mcp_server / remove_mcp_server to manage; "
            "reload_mcp after external config edits. Then search_tools for mcp_ tools."
        ),
    }))


def handle_add_mcp_server(cfg: dict, args: dict) -> ToolResult:
    try:
        srv = _normalize_server(args, existing=None)
    except ValueError as e:
        return ToolResult(False, str(e))

    servers = _all_servers(cfg)
    if _find_server(servers, name=srv["name"]):
        return ToolResult(False, f"server name already exists: {srv['name']} (use set_mcp_server)")
    if _find_server(servers, id=srv["id"]):
        srv["id"] = _new_server_id()
    servers.append(srv)
    try:
        sync = _persist_servers(cfg, servers)
    except ValueError as e:
        return ToolResult(False, str(e))
    except Exception as e:
        return ToolResult(False, f"{type(e).__name__}: {e}")

    return ToolResult(True, dump_json({
        "server": {k: v for k, v in srv.items() if k != "env"},
        "has_env": bool(srv.get("env")),
        "sync": {
            "ok": sync.get("ok"),
            "tools": sync.get("tools") or [],
            "errors": sync.get("errors") or [],
            "sdk": mcp_available(),
        },
        "note": "Server saved. Activate mcp_* tools via search_tools / activate_tools.",
    }), {"id": srv["id"], "tools": sync.get("tools") or []})


def handle_set_mcp_server(cfg: dict, args: dict) -> ToolResult:
    servers = _all_servers(cfg)
    hit = _find_server(servers, id=str(args.get("id") or ""), name=str(args.get("name") or ""))
    if not hit:
        return ToolResult(False, "server not found (pass id or name)")
    idx, existing = hit
    # Allow enable-only without re-supplying transport fields
    patch = {k: v for k, v in args.items() if k not in ("id",) and v is not None}
    # If only toggling enabled, keep name from existing
    if "name" not in patch:
        patch["name"] = existing.get("name")
    try:
        updated = _normalize_server(patch, existing=existing)
    except ValueError as e:
        return ToolResult(False, str(e))

    # Rename collision
    other = _find_server(servers, name=updated["name"])
    if other and other[0] != idx:
        return ToolResult(False, f"name already taken: {updated['name']}")

    servers[idx] = updated
    try:
        sync = _persist_servers(cfg, servers)
    except ValueError as e:
        return ToolResult(False, str(e))
    except Exception as e:
        return ToolResult(False, f"{type(e).__name__}: {e}")

    return ToolResult(True, dump_json({
        "server": {k: v for k, v in updated.items() if k != "env"},
        "has_env": bool(updated.get("env")),
        "sync": {
            "ok": sync.get("ok"),
            "tools": sync.get("tools") or [],
            "errors": sync.get("errors") or [],
        },
    }), {"id": updated["id"]})


def handle_remove_mcp_server(cfg: dict, args: dict) -> ToolResult:
    servers = _all_servers(cfg)
    hit = _find_server(servers, id=str(args.get("id") or ""), name=str(args.get("name") or ""))
    if not hit:
        return ToolResult(False, "server not found (pass id or name)")
    idx, existing = hit
    removed = servers.pop(idx)
    try:
        sync = _persist_servers(cfg, servers)
    except ValueError as e:
        return ToolResult(False, str(e))
    except Exception as e:
        return ToolResult(False, f"{type(e).__name__}: {e}")

    return ToolResult(True, dump_json({
        "removed": {"id": removed.get("id"), "name": removed.get("name")},
        "remaining": len(servers),
        "sync": {"ok": sync.get("ok"), "tools": sync.get("tools") or []},
    }))


def handle_reload_mcp(cfg: dict, args: dict) -> ToolResult:
    if not mcp_available():
        return ToolResult(False, "mcp package not installed (pip install -e '.[mcp]')")
    try:
        sync = sync_mcp(cfg, force=True)
    except Exception as e:
        return ToolResult(False, f"{type(e).__name__}: {e}")
    return ToolResult(True, dump_json({
        "ok": sync.get("ok"),
        "servers": sync.get("servers") or [],
        "tools": sync.get("tools") or [],
        "errors": sync.get("errors") or [],
        "sdk": True,
    }))


# Test seams
def _reset_for_tests() -> None:
    global _fp
    with _lock:
        _unregister_all()
        _fp = None
