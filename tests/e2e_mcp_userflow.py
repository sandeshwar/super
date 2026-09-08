#!/usr/bin/env python3
"""User-flow E2E for MCP manage + tool call (no dashboard click-driving).

Simulates what a user/agent does:
  list → add stdio echo server → reload → activate → call → disable → enable → remove
Also hits the live HTTP API when SUPER is up on :4311.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

ECHO = os.path.join(ROOT, "tests", "fixtures", "mcp_echo_server.py")
BASE = os.environ.get("SUPER_URL", "http://127.0.0.1:4311")
TOKEN = os.environ.get("SUPER_TOKEN", "test-token")

PASS = 0
FAIL = 0


def ok(label: str, detail: str = "") -> None:
    global PASS
    PASS += 1
    print(f"  ✓ {label}" + (f" — {detail}" if detail else ""))


def bad(label: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    print(f"  ✗ {label}" + (f" — {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n== {title} ==")


def http(method: str, path: str, body: dict | None = None) -> tuple[int, dict | list | str]:
    data = None
    headers = {"Authorization": f"Bearer {TOKEN}"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def run_inprocess() -> None:
    section("In-process agent tools (isolated workspace)")
    from tests import make_cfg
    from super.tools import mcp_bridge as M
    from super.tools.discovery import handle_activate_tools, is_callable
    from super.tools.runtime import execute_tool
    from super.tools.catalog import TOOLS

    cfg, root = make_cfg()
    cfg["tools"]["enabled"] = True
    cfg["tools"]["discovery"] = True
    cfg["mcp"] = {"servers": []}
    M._reset_for_tests()

    # 1. list empty
    r = M.handle_list_mcp_servers(cfg, {})
    if r.ok and json.loads(r.content)["servers"] == []:
        ok("list_mcp_servers empty")
    else:
        bad("list_mcp_servers empty", r.content)

    # 2. reject shell command
    r = M.handle_add_mcp_server(cfg, {
        "name": "evil", "transport": "stdio", "command": "bash -c id",
    })
    if not r.ok:
        ok("rejects shell-y command", r.content[:80])
    else:
        bad("rejects shell-y command", "should have failed")

    # 3. reject metadata URL
    r = M.handle_add_mcp_server(cfg, {
        "name": "meta", "transport": "http", "url": "http://169.254.169.254/",
    })
    if not r.ok:
        ok("rejects metadata URL", r.content[:80])
    else:
        bad("rejects metadata URL")

    # 4. add real echo server
    if not os.path.isfile(ECHO):
        bad("echo fixture missing", ECHO)
        return
    r = M.handle_add_mcp_server(cfg, {
        "name": "echo",
        "transport": "stdio",
        "command": sys.executable,
        "args": [ECHO],
        "enabled": True,
    })
    if not r.ok:
        bad("add_mcp_server echo", r.content)
        return
    data = json.loads(r.content)
    tools = data.get("sync", {}).get("tools") or []
    sid = data["server"]["id"]
    if "mcp_echo__ping" in tools and "mcp_echo__echo" in tools:
        ok("add_mcp_server synced tools", ", ".join(tools))
    else:
        bad("add_mcp_server synced tools", str(data.get("sync")))
        # still continue if errors show why
        if data.get("sync", {}).get("errors"):
            print("    sync errors:", data["sync"]["errors"])

    # 5. list shows loaded
    r = M.handle_list_mcp_servers(cfg, {})
    rows = json.loads(r.content)["servers"]
    if rows and rows[0].get("loaded") and rows[0].get("tool_count", 0) >= 2:
        ok("list shows loaded tools", f"count={rows[0]['tool_count']}")
    else:
        bad("list shows loaded tools", str(rows))

    # 6. activate + call ping
    name = "mcp_echo__ping"
    if name not in TOOLS:
        bad("tool registered in catalog", name)
    else:
        act = handle_activate_tools(cfg, {"names": [name, "mcp_echo__echo"]})
        if act.ok and is_callable(cfg, name):
            ok("activate_tools mcp_echo__*")
        else:
            bad("activate_tools", act.content)

        out = execute_tool(cfg, name, {})
        if out.ok and "pong" in out.content and out.taint == "untrusted":
            ok("call mcp_echo__ping", f"taint={out.taint} content={out.content!r}")
        else:
            bad("call mcp_echo__ping", f"ok={out.ok} {out.content!r} taint={out.taint}")

        out = execute_tool(cfg, "mcp_echo__echo", {"text": "hello-user"})
        if out.ok and "hello-user" in out.content:
            ok("call mcp_echo__echo", out.content[:60])
        else:
            bad("call mcp_echo__echo", out.content)

    # 7. disable
    r = M.handle_set_mcp_server(cfg, {"id": sid, "enabled": False})
    if r.ok and json.loads(r.content)["server"]["enabled"] is False:
        ok("set_mcp_server disable")
    else:
        bad("set_mcp_server disable", r.content)

    # disabled → sync should drop tools
    sync = json.loads(r.content).get("sync") or {}
    if "mcp_echo__ping" not in (sync.get("tools") or []):
        ok("disable drops catalog tools")
    else:
        bad("disable drops catalog tools", str(sync.get("tools")))

    # 8. re-enable
    r = M.handle_set_mcp_server(cfg, {"id": sid, "enabled": True})
    if r.ok and "mcp_echo__ping" in (json.loads(r.content).get("sync", {}).get("tools") or []):
        ok("set_mcp_server re-enable + sync")
    else:
        bad("set_mcp_server re-enable", r.content)

    # 9. reload
    r = M.handle_reload_mcp(cfg, {})
    if r.ok and "mcp_echo__ping" in (json.loads(r.content).get("tools") or []):
        ok("reload_mcp")
    else:
        bad("reload_mcp", r.content)

    # 10. remove
    r = M.handle_remove_mcp_server(cfg, {"id": sid})
    if r.ok and cfg["mcp"]["servers"] == []:
        ok("remove_mcp_server")
    else:
        bad("remove_mcp_server", r.content)

    # config saved under isolated root, not workspace
    saved = os.path.join(root, "super.config.json")
    if os.path.isfile(saved):
        ok("persisted under isolated workspace", saved)
    else:
        bad("persisted under isolated workspace")

    ws_cfg = os.path.join(ROOT, "super.config.json")
    try:
        with open(ws_cfg, encoding="utf-8") as f:
            live = json.load(f)
        # should not have been rewritten with only our echo server as sole content from this run
        # (mcp may be empty from restore — just ensure state_dir isn't a vanished temp from THIS root)
        if live.get("state_dir") == "./.super" or str(live.get("state_dir", "")).endswith("/.super"):
            ok("workspace config state_dir intact", str(live.get("state_dir")))
        else:
            bad("workspace config state_dir intact", str(live.get("state_dir")))
    except Exception as e:
        bad("read workspace config", str(e))

    M._reset_for_tests()
    import shutil
    shutil.rmtree(root, ignore_errors=True)


def run_http() -> None:
    section("Live HTTP API (Settings-equivalent)")
    code, health = http("GET", "/api/health")
    if code != 200 or not (isinstance(health, dict) and health.get("ok")):
        bad("GET /api/health", f"{code} {health}")
        print("  (skipping live API — start with: python -m super.cli serve)")
        return
    ok("GET /api/health", str(health.get("model")))

    # Patch MCP servers via Settings path
    code, body = http("POST", "/api/config", {
        "config": {
            "mcp": {
                "servers": [{
                    "id": "mcp_e2e_http",
                    "name": "echo_http",
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [ECHO],
                    "enabled": True,
                }]
            }
        }
    })
    if code == 200 and isinstance(body, dict) and body.get("ok"):
        servers = ((body.get("config") or {}).get("mcp") or {}).get("servers") or []
        if any(s.get("name") == "echo_http" for s in servers):
            ok("POST /api/config add MCP server", f"{len(servers)} server(s)")
        else:
            bad("POST /api/config add MCP server", str(servers))
    else:
        bad("POST /api/config add MCP server", f"{code} {body}")

    code, tools = http("GET", "/api/tools")
    if code == 200 and isinstance(tools, dict):
        cat = tools.get("tools") or tools
        integ = cat.get("integrations") or {}
        mcp_rows = cat.get("mcp_servers") or []
        groups = {g["id"]: g for g in (cat.get("groups") or [])}
        mcp_group = groups.get("mcp") or {}
        names = [t["name"] for t in (mcp_group.get("tools") or [])]
        manage = [n for n in names if n in (
            "list_mcp_servers", "add_mcp_server", "set_mcp_server",
            "remove_mcp_server", "reload_mcp",
        )]
        remote = [n for n in names if n.startswith("mcp_echo_http__") or n.startswith("mcp_")]
        if integ.get("mcp"):
            ok("GET /api/tools integrations.mcp=true")
        else:
            bad("GET /api/tools integrations.mcp", str(integ))
        if len(manage) >= 5:
            ok("manage tools in catalog", ", ".join(manage))
        else:
            bad("manage tools in catalog", str(names[:20]))
        # After config save, server should have force-synced
        echo_tools = [n for n in names if "echo" in n and n.startswith("mcp_")]
        if echo_tools or any(r.get("loaded") for r in mcp_rows):
            ok("synced remote MCP tools via API", str(echo_tools or mcp_rows))
        else:
            # Older server process may not have force-sync — still report
            bad("synced remote MCP tools via API", f"names={names} rows={mcp_rows}")
    else:
        bad("GET /api/tools", f"{code} {tools}")

    # Cleanup via API
    code, body = http("POST", "/api/config", {"config": {"mcp": {"servers": []}}})
    if code == 200 and isinstance(body, dict) and body.get("ok"):
        ok("POST /api/config clear MCP servers")
    else:
        bad("POST /api/config clear MCP servers", f"{code} {body}")


def main() -> int:
    print("SUPER MCP user-flow E2E")
    print(f"  echo server: {ECHO}")
    print(f"  API: {BASE}")
    try:
        run_inprocess()
    except Exception:
        bad("in-process crashed")
        traceback.print_exc()
    try:
        run_http()
    except Exception:
        bad("http crashed")
        traceback.print_exc()

    section("Summary")
    print(f"  passed={PASS} failed={FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
