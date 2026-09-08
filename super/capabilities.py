"""Capability forge: agent invents tools via propose → test → approve → install.

Only safe kinds ship in v1:
  composite — DAG of existing tools (recombination, no new code)
  http      — GET/POST with SSRF guards (no private/link-local/metadata)

Risk is computed from step tools (client claim is a ceiling, never a floor).
Auto-install requires computed risk=low AND at least one executed passing test
(or trusted intelligence recipes with only low-risk steps). Composites re-check
can_call_tool + side-effect rights per step so children cannot widen rights.
"""

from __future__ import annotations

import copy
import ipaddress
import json
import re
import socket
import time
import uuid
from typing import Any
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from . import store
from .errors import StoreError
from .tools.base import ToolResult, ToolSpec, dump_json

FILE = "capabilities.json"
SCHEMA = 1
GROUP = "user_caps"
GROUP_META = {
    "title": "User capabilities",
    "blurb": "Agent-invented tools (composites / HTTP) — propose, approve, install",
}
KINDS = ("composite", "http")
RISKS = ("low", "medium", "high")
_RISK_RANK = {"low": 0, "medium": 1, "high": 2}
STATUSES = ("pending", "approved", "installed", "retired", "rejected")
MAX_COMPOSITE_STEPS = 8
MAX_NEST_DEPTH = 4
MAX_CAPS = 80
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
RESERVED_PREFIXES = ("lc_", "crewai_", "system_")

SIDE_EFFECT_TOOLS = frozenset({
    "write_file", "edit_file", "delete_path", "mkdir",
    "file_delete", "copy_file", "lc_copy_file", "move_file",
    "run_command", "fetch_url",
})
BLOCKED_HEADER_KEYS = frozenset({
    "authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key",
})


def _path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{FILE}"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _load(cfg: dict) -> dict:
    data = store.load_json(_path(cfg), {"schema": SCHEMA, "capabilities": {}})
    if not isinstance(data, dict) or not isinstance(data.get("capabilities"), dict):
        raise StoreError("capabilities store is malformed")
    return data


def _save(cfg: dict, data: dict) -> None:
    store.save_json(_path(cfg), data)


def _caps_cfg(cfg: dict) -> dict:
    return cfg.get("capabilities") or {}


def enabled(cfg: dict) -> bool:
    return bool(_caps_cfg(cfg).get("enabled", True))


def auto_install_low(cfg: dict) -> bool:
    return bool(_caps_cfg(cfg).get("auto_install_low", True))


def http_host_allowlist(cfg: dict) -> list[str]:
    raw = _caps_cfg(cfg).get("http_allowlist") or []
    return [str(x).strip().lower() for x in raw if str(x).strip()]


def _new_id() -> str:
    return "cap_" + uuid.uuid4().hex[:10]


def _validate_name(name: str) -> str:
    name = (name or "").strip().lower()
    if not NAME_RE.match(name):
        raise ValueError("name must match ^[a-z][a-z0-9_]{1,47}$")
    if name.startswith(RESERVED_PREFIXES):
        raise ValueError(f"name reserved prefix: {name}")
    from .tools.catalog import TOOLS
    existing = TOOLS.get(name)
    if existing and existing.group != GROUP:
        raise ValueError(f"name collides with builtin/pack tool: {name}")
    return name


def _normalize_parameters(params: Any) -> dict:
    if params is None:
        return {"type": "object", "properties": {}, "additionalProperties": False}
    if not isinstance(params, dict):
        raise ValueError("parameters must be a JSON Schema object")
    out = dict(params)
    out.setdefault("type", "object")
    out.setdefault("properties", {})
    if "additionalProperties" not in out:
        out["additionalProperties"] = False
    return out


def _host_is_blocked(host: str) -> str | None:
    host = (host or "").strip().lower().rstrip(".")
    if not host:
        return "empty host"
    if host in ("localhost", "metadata.google.internal"):
        return f"blocked host {host}"
    bare = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        ip = ipaddress.ip_address(bare)
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        ):
            return f"blocked address {ip}"
        if str(ip) == "169.254.169.254":
            return "blocked metadata IP"
        return None
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(bare, None)
    except socket.gaierror:
        return f"unresolvable host {host}"
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
            or str(ip) == "169.254.169.254"
        ):
            return f"host {host} resolves to blocked {ip}"
    return None


def _validate_http_url(cfg: dict, url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("http impl.url must be http(s) with host")
    host = parsed.hostname or ""
    allow = http_host_allowlist(cfg)
    if allow:
        if host.lower() not in allow:
            raise ValueError(f"http host not in allowlist: {host}")
    else:
        why = _host_is_blocked(host)
        if why:
            raise ValueError(f"http url rejected: {why}")
    return url


def _sanitize_headers(headers: dict) -> dict:
    out = {}
    for k, v in headers.items():
        key = str(k)
        if key.lower() in BLOCKED_HEADER_KEYS:
            continue
        out[key] = str(v)[:500]
    return out


def _tool_risk(name: str) -> str:
    from .tools.catalog import get_tool
    spec = get_tool(name)
    if not spec:
        return "high"
    if name in ("run_command", "write_file", "edit_file", "delete_path"):
        return "high"
    if name in SIDE_EFFECT_TOOLS:
        return _max_risk(spec.risk if spec.risk in _RISK_RANK else "medium", "medium")
    return spec.risk if spec.risk in _RISK_RANK else "medium"


def _max_risk(*risks: str) -> str:
    best = "low"
    for r in risks:
        rr = r if r in _RISK_RANK else "medium"
        if _RISK_RANK[rr] > _RISK_RANK[best]:
            best = rr
    return best


def _compute_risk(cfg: dict, kind: str, impl: dict, claimed: str) -> str:
    derived = "low"
    if kind == "http":
        derived = "medium"
    elif kind == "composite":
        for step in impl.get("steps") or []:
            derived = _max_risk(derived, _tool_risk(step["tool"]))
            try:
                data = _load(cfg)
                for c in data["capabilities"].values():
                    if c.get("name") == step["tool"] and c.get("status") == "installed":
                        derived = _max_risk(derived, c.get("risk") or "medium")
                        break
            except Exception:
                pass
    return _max_risk(claimed if claimed in _RISK_RANK else "medium", derived)


def _assert_no_cycles(cfg: dict, name: str, steps: list[dict], *, stack: tuple[str, ...] = ()) -> None:
    if name in stack:
        raise ValueError(f"capability cycle involving {name}")
    if len(stack) >= MAX_NEST_DEPTH:
        raise ValueError(f"capability nest depth > {MAX_NEST_DEPTH}")
    data = _load(cfg)
    by_name = {
        c["name"]: c for c in data["capabilities"].values()
        if c.get("status") in ("installed", "pending", "approved")
    }
    for step in steps:
        tool = step["tool"]
        if tool == name or tool in stack:
            raise ValueError(f"capability cycle involving {tool}")
        child = by_name.get(tool)
        if child and child.get("kind") == "composite":
            _assert_no_cycles(cfg, tool, child.get("impl", {}).get("steps") or [], stack=stack + (name,))


def _normalize_impl(cfg: dict, kind: str, impl: Any, *, name: str = "") -> dict:
    if not isinstance(impl, dict):
        raise ValueError("impl must be an object")
    if kind == "composite":
        steps = impl.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError("composite impl.steps must be a non-empty list")
        if len(steps) > MAX_COMPOSITE_STEPS:
            raise ValueError(f"composite max {MAX_COMPOSITE_STEPS} steps")
        norm_steps = []
        seen_as: set[str] = set()
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ValueError(f"step {i} must be an object")
            tool = str(step.get("tool") or "").strip()
            if not tool:
                raise ValueError(f"step {i}: tool required")
            if tool == name:
                raise ValueError("composite cannot call itself")
            args = step.get("args") if isinstance(step.get("args"), dict) else {}
            as_name = str(step.get("as") or tool).strip()
            if as_name in seen_as:
                raise ValueError(f"duplicate step alias: {as_name}")
            seen_as.add(as_name)
            norm_steps.append({"tool": tool, "args": args, "as": as_name})
        if name:
            _assert_no_cycles(cfg, name, norm_steps)
        return {"steps": norm_steps, "merge": str(impl.get("merge") or "text")}
    if kind == "http":
        url = str(impl.get("url") or "").strip()
        if not url:
            raise ValueError("http impl.url required")
        _validate_http_url(cfg, url)
        method = str(impl.get("method") or "GET").upper()
        if method not in ("GET", "POST"):
            raise ValueError("http method must be GET or POST")
        headers = impl.get("headers") if isinstance(impl.get("headers"), dict) else {}
        return {
            "url": url,
            "method": method,
            "headers": _sanitize_headers(headers),
            "query_from": [str(x) for x in (impl.get("query_from") or []) if str(x).strip()],
            "body_from": [str(x) for x in (impl.get("body_from") or []) if str(x).strip()],
            "timeout_s": max(1, min(int(impl.get("timeout_s") or 20), 60)),
        }
    raise ValueError(f"unsupported kind: {kind}")


def _public(cap: dict) -> dict:
    return {
        "id": cap["id"],
        "name": cap["name"],
        "summary": cap.get("summary") or "",
        "description": cap.get("description") or "",
        "kind": cap["kind"],
        "risk": cap["risk"],
        "claimed_risk": cap.get("claimed_risk") or cap.get("risk"),
        "status": cap["status"],
        "group": GROUP,
        "parameters": cap.get("parameters") or {},
        "impl": cap.get("impl") or {},
        "tests": cap.get("tests") or [],
        "created_by": cap.get("created_by") or "",
        "created_at": cap.get("created_at") or "",
        "updated_at": cap.get("updated_at") or "",
        "test_report": cap.get("test_report"),
    }


def list_capabilities(cfg: dict, *, include_retired: bool = False) -> list[dict]:
    data = _load(cfg)
    out = []
    for cap in data["capabilities"].values():
        if not include_retired and cap.get("status") == "retired":
            continue
        out.append(_public(cap))
    out.sort(key=lambda c: (c["status"], c["name"]))
    return out


def get_capability(cfg: dict, cap_id: str | None = None, *, name: str | None = None) -> dict | None:
    data = _load(cfg)
    if cap_id:
        cap = data["capabilities"].get(cap_id)
        return _public(cap) if cap else None
    if name:
        for cap in data["capabilities"].values():
            if cap.get("name") == name and cap.get("status") != "retired":
                return _public(cap)
    return None


def propose(
    cfg: dict,
    *,
    name: str,
    summary: str = "",
    description: str = "",
    kind: str = "composite",
    risk: str = "medium",
    parameters: dict | None = None,
    impl: dict | None = None,
    tests: list | None = None,
    created_by: str = "agent",
) -> dict:
    if not enabled(cfg):
        raise ValueError("capabilities forge disabled")
    kind = (kind or "composite").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    claimed = (risk or "medium").strip().lower()
    if claimed not in RISKS:
        raise ValueError(f"risk must be one of {RISKS}")
    name = _validate_name(name)
    data = _load(cfg)
    live = [c for c in data["capabilities"].values() if c.get("status") not in ("retired", "rejected")]
    if len(live) >= MAX_CAPS:
        raise ValueError(f"max capabilities ({MAX_CAPS}) reached")
    for cap in live:
        if cap.get("name") == name:
            raise ValueError(f"capability name already exists: {name}")
    params = _normalize_parameters(parameters)
    body = _normalize_impl(cfg, kind, impl or {}, name=name)
    if kind == "composite":
        from .tools.catalog import get_tool
        for step in body["steps"]:
            if not get_tool(step["tool"]):
                raise ValueError(f"unknown tool in composite: {step['tool']}")
    effective_risk = _compute_risk(cfg, kind, body, claimed)
    test_list = []
    for t in tests or []:
        if not isinstance(t, dict):
            continue
        test_list.append({
            "args": t.get("args") if isinstance(t.get("args"), dict) else {},
            "expect_ok": bool(t.get("expect_ok", True)),
            "expect_contains": str(t.get("expect_contains") or "")[:200],
        })
    cap_id = _new_id()
    now = _now()
    cap = {
        "id": cap_id,
        "name": name,
        "summary": (summary or name)[:200],
        "description": (description or summary or name)[:2000],
        "kind": kind,
        "risk": effective_risk,
        "claimed_risk": claimed,
        "status": "pending",
        "parameters": params,
        "impl": body,
        "tests": test_list,
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
        "test_report": None,
    }
    data["capabilities"][cap_id] = cap
    _save(cfg, data)

    if effective_risk == "low" and kind == "composite" and auto_install_low(cfg):
        report = run_tests(cfg, cap_id)
        trusted = created_by == "intelligence" and report.get("structural_ok")
        if report.get("ok") and (int(report.get("ran") or 0) > 0 or trusted):
            return install(cfg, cap_id, actor=created_by, require_approved=False)
    return _public(cap)


def run_tests(cfg: dict, cap_id: str) -> dict:
    data = _load(cfg)
    cap = data["capabilities"].get(cap_id)
    if not cap:
        raise KeyError(cap_id)
    tests = cap.get("tests") or []
    structural_ok = True
    if cap["kind"] == "composite":
        from .tools.catalog import get_tool
        missing = [s["tool"] for s in cap["impl"]["steps"] if not get_tool(s["tool"])]
        structural_ok = not missing
    elif cap["kind"] == "http":
        try:
            _validate_http_url(cfg, cap["impl"]["url"])
        except ValueError:
            structural_ok = False
    if not tests:
        if cap["kind"] == "http":
            report = {
                "ok": False, "ran": 0, "passed": 0, "failed": 0,
                "structural_ok": structural_ok,
                "detail": "http requires explicit tests or human approve; structural="
                + ("ok" if structural_ok else "fail"),
            }
        else:
            report = {
                "ok": structural_ok, "ran": 0, "passed": 0, "failed": 0,
                "structural_ok": structural_ok,
                "detail": "no tests; structural check " + ("ok" if structural_ok else "fail"),
            }
    else:
        if cap["kind"] == "http":
            report = {
                "ok": False, "ran": 0, "passed": 0, "failed": len(tests),
                "structural_ok": structural_ok,
                "detail": "http tests are not auto-executed (SSRF); human must approve after review",
            }
        else:
            passed = failed = 0
            details = []
            for i, t in enumerate(tests):
                result = _execute_cap(cfg, cap, t.get("args") or {}, sandbox=True)
                expect_ok = bool(t.get("expect_ok", True))
                contains = str(t.get("expect_contains") or "")
                good = (result.ok == expect_ok) and (not contains or contains in (result.content or ""))
                if good:
                    passed += 1
                else:
                    failed += 1
                details.append({"i": i, "ok": good, "content": (result.content or "")[:300]})
            report = {
                "ok": failed == 0 and structural_ok,
                "ran": len(tests),
                "passed": passed,
                "failed": failed,
                "structural_ok": structural_ok,
                "detail": details,
            }
    cap["test_report"] = report
    cap["updated_at"] = _now()
    _save(cfg, data)
    return report


def approve(cfg: dict, cap_id: str, *, actor: str = "user") -> dict:
    data = _load(cfg)
    cap = data["capabilities"].get(cap_id)
    if not cap:
        raise KeyError(cap_id)
    if cap["status"] in ("retired", "rejected"):
        raise ValueError(f"cannot approve {cap['status']} capability")
    cap["risk"] = _compute_risk(
        cfg, cap["kind"], cap.get("impl") or {},
        cap.get("claimed_risk") or cap.get("risk") or "medium",
    )
    if cap["kind"] == "http":
        _validate_http_url(cfg, cap["impl"]["url"])
    if cap["kind"] == "composite":
        _assert_no_cycles(cfg, cap["name"], cap["impl"].get("steps") or [])
    cap["status"] = "approved"
    cap["updated_at"] = _now()
    cap["approved_by"] = actor
    _save(cfg, data)
    return install(cfg, cap_id, actor=actor, require_approved=True)


def reject(cfg: dict, cap_id: str, *, actor: str = "user", reason: str = "") -> dict:
    data = _load(cfg)
    cap = data["capabilities"].get(cap_id)
    if not cap:
        raise KeyError(cap_id)
    _unregister(cap["name"])
    cap["status"] = "rejected"
    cap["updated_at"] = _now()
    cap["rejected_by"] = actor
    cap["reject_reason"] = (reason or "")[:500]
    _save(cfg, data)
    return _public(cap)


def install(cfg: dict, cap_id: str, *, actor: str = "agent", require_approved: bool = True) -> dict:
    data = _load(cfg)
    cap = data["capabilities"].get(cap_id)
    if not cap:
        raise KeyError(cap_id)
    if cap["status"] == "retired":
        raise ValueError("cannot install retired capability")
    if require_approved and cap["status"] not in ("approved", "installed"):
        if not (cap["risk"] == "low" and cap["kind"] == "composite" and auto_install_low(cfg)):
            raise ValueError("capability not approved — human must approve first")
    report = run_tests(cfg, cap_id)
    data = _load(cfg)
    cap = data["capabilities"][cap_id]
    if require_approved and actor == "user":
        if cap["kind"] == "composite" and not report.get("structural_ok", True):
            raise ValueError(f"tests failed: {report}")
        if cap["kind"] == "http" and not report.get("structural_ok", True):
            raise ValueError(f"http structural check failed: {report}")
    else:
        if not report.get("ok"):
            if not (not require_approved and report.get("structural_ok") and cap["risk"] == "low"):
                raise ValueError(f"tests failed: {report}")
            if int(report.get("ran") or 0) == 0 and actor != "intelligence":
                raise ValueError("auto-install requires executed tests")
    if cap["kind"] == "composite":
        _assert_no_cycles(cfg, cap["name"], cap["impl"].get("steps") or [])
    _register_cap(cap)
    cap["status"] = "installed"
    cap["updated_at"] = _now()
    cap["installed_by"] = actor
    _save(cfg, data)
    return _public(cap)


def retire(cfg: dict, cap_id: str, *, actor: str = "agent") -> dict:
    data = _load(cfg)
    cap = data["capabilities"].get(cap_id)
    if not cap:
        raise KeyError(cap_id)
    _unregister(cap["name"])
    cap["status"] = "retired"
    cap["updated_at"] = _now()
    cap["retired_by"] = actor
    _save(cfg, data)
    return _public(cap)


def _unregister(name: str) -> None:
    from .tools import catalog
    spec = catalog.TOOLS.get(name)
    if spec and spec.group == GROUP:
        catalog.TOOLS.pop(name, None)


def _register_cap(cap: dict) -> ToolSpec:
    from .tools import catalog
    from .tools.langchain_bridge import register_tool

    if GROUP not in catalog.GROUPS:
        catalog.GROUPS[GROUP] = dict(GROUP_META)

    name = cap["name"]

    def handler(cfg: dict, args: dict, _cap_id: str = cap["id"]) -> ToolResult:
        data = _load(cfg)
        live = data["capabilities"].get(_cap_id)
        if not live or live.get("status") != "installed":
            return ToolResult(False, f"capability {_cap_id} not installed")
        return _execute_cap(cfg, live, args or {}, sandbox=False)

    spec = ToolSpec(
        name=name,
        group=GROUP,
        summary=cap.get("summary") or name,
        description=cap.get("description") or cap.get("summary") or name,
        parameters=cap.get("parameters") or {"type": "object", "properties": {}},
        handler=handler,
        risk=cap.get("risk") or "medium",
        keywords=f"capability forge user_caps {cap.get('kind', '')}",
    )
    register_tool(spec)
    return spec


def ensure_capabilities(cfg: dict) -> int:
    from .tools import catalog
    if GROUP not in catalog.GROUPS:
        catalog.GROUPS[GROUP] = dict(GROUP_META)
    if not enabled(cfg):
        return 0
    try:
        data = _load(cfg)
    except StoreError:
        return 0
    n = 0
    for cap in data["capabilities"].values():
        if cap.get("status") == "installed":
            _register_cap(cap)
            n += 1
    return n


def _lookup_ref(ref: str, args: dict, steps: dict[str, ToolResult]) -> Any:
    ref = (ref or "").strip()
    if ref.startswith("$"):
        ref = ref[1:]
    if ref.startswith("arg."):
        return args.get(ref[4:])
    if ref.startswith("step."):
        parts = ref[5:].split(".", 1)
        res = steps.get(parts[0])
        if res is None:
            return None
        if len(parts) == 1 or parts[1] == "content":
            return res.content
        if parts[1] == "ok":
            return res.ok
        if parts[1].startswith("data."):
            cur: Any = res.data
            for p in parts[1][5:].split("."):
                if isinstance(cur, dict):
                    cur = cur.get(p)
                else:
                    return None
            return cur
        return res.content
    return None


def _subst(obj: Any, args: dict, steps: dict[str, ToolResult]) -> Any:
    if isinstance(obj, str):
        if obj.startswith("$arg.") or obj.startswith("$step."):
            return _lookup_ref(obj, args, steps)
        if "{" in obj and "}" in obj:
            def repl(m: re.Match) -> str:
                val = _lookup_ref(m.group(1), args, steps)
                return "" if val is None else str(val)
            return re.sub(r"\{\s*(\$?arg\.[^}]+|\$?step\.[^}]+)\s*\}", repl, obj)
        return obj
    if isinstance(obj, dict):
        return {k: _subst(v, args, steps) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_subst(v, args, steps) for v in obj]
    return obj


def _execute_cap(cfg: dict, cap: dict, args: dict, *, sandbox: bool) -> ToolResult:
    kind = cap["kind"]
    if kind == "composite":
        return _run_composite(cfg, cap, args, sandbox=sandbox)
    if kind == "http":
        if sandbox:
            return ToolResult(False, "sandbox blocks http capability execution")
        return _run_http(cfg, cap, args)
    return ToolResult(False, f"unknown kind {kind}")


def _step_allowed(cfg: dict, tool: str, *, sandbox: bool) -> tuple[bool, str]:
    from .tools.catalog import get_tool
    from .tools.discovery import disabled_names

    if tool in disabled_names(cfg):
        return False, f"tool disabled: {tool}"
    spec = get_tool(tool)
    if not spec:
        return False, f"missing tool: {tool}"
    try:
        from . import agents as _agents
        ok, why = _agents.can_call_tool(cfg, tool)
        if not ok:
            return False, why or f"cannot call {tool}"
    except Exception as e:
        return False, f"policy check failed: {e}"
    eff = cfg.get("_agent_effective") if isinstance(cfg.get("_agent_effective"), dict) else {}
    if tool in SIDE_EFFECT_TOOLS or (spec.risk or "") == "high":
        if sandbox:
            return False, f"sandbox blocks side-effect tool: {tool}"
        if eff and not eff.get("may_write", True):
            return False, f"may_write=false blocks {tool}"
    return True, ""


def _run_composite(cfg: dict, cap: dict, args: dict, *, sandbox: bool) -> ToolResult:
    from .tools.catalog import get_tool

    steps_out: dict[str, ToolResult] = {}
    texts: list[str] = []
    depth = int(cfg.get("_cap_depth") or 0)
    if depth >= MAX_NEST_DEPTH:
        return ToolResult(False, f"capability nest depth > {MAX_NEST_DEPTH}")
    child_cfg = {**cfg, "_cap_depth": depth + 1}

    for step in cap["impl"]["steps"]:
        tool = step["tool"]
        ok, why = _step_allowed(child_cfg, tool, sandbox=sandbox)
        if not ok:
            return ToolResult(False, why)
        spec = get_tool(tool)
        assert spec is not None
        call_args = _subst(copy.deepcopy(step.get("args") or {}), args, steps_out)
        if not isinstance(call_args, dict):
            call_args = {}
        try:
            result = spec.handler(child_cfg, call_args)
        except Exception as e:
            result = ToolResult(False, f"{type(e).__name__}: {e}")
        if not isinstance(result, ToolResult):
            result = ToolResult(True, str(result))
        steps_out[step["as"]] = result
        texts.append(f"## {step['as']} ({tool})\nok={result.ok}\n{result.content}")
        if not result.ok:
            return ToolResult(
                False,
                "\n\n".join(texts),
                data={"steps": {k: {"ok": v.ok, "content": v.content[:500]} for k, v in steps_out.items()}},
            )
    merge = cap["impl"].get("merge") or "text"
    if merge == "json":
        payload = {k: {"ok": v.ok, "content": v.content, "data": v.data} for k, v in steps_out.items()}
        return ToolResult(True, dump_json(payload), data={"steps": list(steps_out)})
    return ToolResult(True, "\n\n".join(texts), data={"step_names": list(steps_out)})


def _run_http(cfg: dict, cap: dict, args: dict) -> ToolResult:
    impl = cap["impl"]
    try:
        _validate_http_url(cfg, impl["url"])
    except ValueError as e:
        return ToolResult(False, str(e), taint="untrusted")
    url = impl["url"]
    query = {k: args.get(k) for k in impl.get("query_from") or [] if k in args and args.get(k) is not None}
    if query:
        sep = "&" if "?" in url else "?"
        url = url + sep + urlencode({k: str(v) for k, v in query.items()})
    body = None
    headers = _sanitize_headers(dict(impl.get("headers") or {}))
    if impl["method"] == "POST":
        payload = {k: args.get(k) for k in (impl.get("body_from") or args.keys()) if k in args}
        body = json.dumps(payload).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    req = Request(url, data=body, headers=headers, method=impl["method"])
    try:
        with urlopen(req, timeout=int(impl.get("timeout_s") or 20)) as resp:
            final = getattr(resp, "geturl", lambda: url)()
            try:
                _validate_http_url(cfg, final)
            except ValueError as e:
                return ToolResult(False, f"redirect blocked: {e}", taint="untrusted")
            raw = resp.read(200_000)
            text = raw.decode("utf-8", errors="replace")
            return ToolResult(
                True, text,
                data={"status": getattr(resp, "status", 200), "url": final},
                taint="untrusted",
            )
    except Exception as e:
        return ToolResult(False, f"http error: {e}", taint="untrusted")


def _may_manage(cfg: dict) -> tuple[bool, str]:
    eff = cfg.get("_agent_effective")
    if isinstance(eff, dict) and not eff.get("may_manage_agents", True):
        return False, "may_manage_agents=false (capability forge requires manage rights)"
    return True, ""


def handle_propose_capability(cfg: dict, args: dict) -> ToolResult:
    ok, why = _may_manage(cfg)
    if not ok:
        return ToolResult(False, why)
    try:
        cap = propose(
            cfg,
            name=str(args.get("name") or ""),
            summary=str(args.get("summary") or ""),
            description=str(args.get("description") or ""),
            kind=str(args.get("kind") or "composite"),
            risk=str(args.get("risk") or "medium"),
            parameters=args.get("parameters") if isinstance(args.get("parameters"), dict) else None,
            impl=args.get("impl") if isinstance(args.get("impl"), dict) else None,
            tests=args.get("tests") if isinstance(args.get("tests"), list) else None,
            created_by=str((cfg.get("_agent") or {}).get("id") or "agent"),
        )
        tip = (
            "Installed and callable after activate_tools."
            if cap.get("status") == "installed"
            else "Pending human approval (Settings → Agents/Capabilities, or POST /api/capability approve)."
        )
        return ToolResult(True, dump_json({"capability": cap, "note": tip}), data={"id": cap["id"], "status": cap["status"]})
    except (ValueError, StoreError) as e:
        return ToolResult(False, str(e))


def handle_list_capabilities(cfg: dict, args: dict) -> ToolResult:
    caps = list_capabilities(cfg, include_retired=bool(args.get("include_retired")))
    return ToolResult(True, dump_json({"capabilities": caps, "count": len(caps)}))


def handle_describe_capability(cfg: dict, args: dict) -> ToolResult:
    cap = get_capability(cfg, str(args.get("id") or "") or None, name=str(args.get("name") or "") or None)
    if not cap:
        return ToolResult(False, "capability not found")
    return ToolResult(True, dump_json(cap))


def handle_test_capability(cfg: dict, args: dict) -> ToolResult:
    ok, why = _may_manage(cfg)
    if not ok:
        return ToolResult(False, why)
    cap_id = str(args.get("id") or "").strip()
    if not cap_id:
        return ToolResult(False, "id required")
    try:
        report = run_tests(cfg, cap_id)
        return ToolResult(bool(report.get("ok")), dump_json(report), data=report)
    except KeyError:
        return ToolResult(False, "capability not found")
    except (ValueError, StoreError) as e:
        return ToolResult(False, str(e))


def handle_install_capability(cfg: dict, args: dict) -> ToolResult:
    ok, why = _may_manage(cfg)
    if not ok:
        return ToolResult(False, why)
    cap_id = str(args.get("id") or "").strip()
    if not cap_id:
        return ToolResult(False, "id required")
    try:
        cap = install(cfg, cap_id, actor="agent", require_approved=True)
        return ToolResult(True, dump_json({"capability": cap, "note": "activate_tools then call by name"}))
    except KeyError:
        return ToolResult(False, "capability not found")
    except (ValueError, StoreError) as e:
        return ToolResult(False, str(e))


def handle_retire_capability(cfg: dict, args: dict) -> ToolResult:
    ok, why = _may_manage(cfg)
    if not ok:
        return ToolResult(False, why)
    cap_id = str(args.get("id") or "").strip()
    if not cap_id:
        return ToolResult(False, "id required")
    try:
        cap = retire(cfg, cap_id, actor="agent")
        return ToolResult(True, dump_json({"capability": cap}))
    except KeyError:
        return ToolResult(False, "capability not found")
    except (ValueError, StoreError) as e:
        return ToolResult(False, str(e))
