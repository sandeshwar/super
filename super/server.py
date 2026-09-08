"""Production local API + dashboard (doc 06).

Binds 0.0.0.0 by default so the dashboard is reachable on the LAN.
No bearer token required. Stdlib only. All mutations validate input, audit-log,
and return typed errors without stack leaks.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

CFG: dict | None = None
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "dist")
MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
        ".svg": "image/svg+xml", ".json": "application/json", ".png": "image/png"}

MAX_BODY = 1_000_000

# In-flight chat generations: session_id → cancel Event.
# Client disconnect does NOT cancel; only /api/chat/cancel (or a newer run) does.
_CHAT_RUNS: dict[str, threading.Event] = {}
_CHAT_RUNS_LOCK = threading.Lock()


def _chat_run_begin(sid: str) -> threading.Event:
    ev = threading.Event()
    with _CHAT_RUNS_LOCK:
        prev = _CHAT_RUNS.get(sid)
        if prev is not None:
            prev.set()
        _CHAT_RUNS[sid] = ev
    return ev


def _chat_run_end(sid: str, ev: threading.Event) -> None:
    with _CHAT_RUNS_LOCK:
        if _CHAT_RUNS.get(sid) is ev:
            _CHAT_RUNS.pop(sid, None)


def _chat_run_active(sid: str) -> bool:
    with _CHAT_RUNS_LOCK:
        return sid in _CHAT_RUNS


def _chat_run_cancel(sid: str) -> bool:
    with _CHAT_RUNS_LOCK:
        ev = _CHAT_RUNS.get(sid)
    if ev is None:
        return False
    ev.set()
    return True


def _report(cfg: dict) -> dict:
    from . import ledger, quality, tasks, trust

    all_tasks = tasks.list_all(cfg)
    proven = sum(1 for t in all_tasks if t["status"] == "proven")
    done_ok, blockers = quality.done_state(cfg)
    return {
        "tasks": all_tasks,
        "proven": proven,
        "total": len(all_tasks),
        "gates": ledger.gate_stats(cfg),
        "catch_rates": ledger.catch_rates(cfg),
        "open_criticals": ledger.open_criticals(cfg),
        "done_ok": done_ok,
        "done_blockers": blockers,
        "fatigue": trust.fatigue(cfg),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "SUPER/1.0"

    # -- helpers ---------------------------------------------------------
    def _send_json(self, obj: dict | list, code: int = 200) -> None:
        body = json.dumps(obj).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # Client navigated away / aborted poll — not a server fault.
            pass

    def _send_file(self, name: str) -> None:
        path = os.path.normpath(os.path.join(WEB_DIR, name))
        if not path.startswith(WEB_DIR) or not os.path.isfile(path):
            return self._send_json({"error": "not found", "code": 404}, 404)
        with open(path, "rb") as f:
            body = f.read()
        try:
            self.send_response(200)
            self.send_header("Content-Type", MIME.get(os.path.splitext(name)[1], "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        if n > MAX_BODY:
            raise ValueError("body too large")
        raw = self.rfile.read(n).decode() if n else "{}"
        try:
            obj = json.loads(raw or "{}")
        except ValueError as e:
            raise ValueError(f"invalid JSON: {e}") from e
        return obj if isinstance(obj, dict) else {}

    def _require_auth(self, query: dict) -> bool:
        return True

    def _prefers_html(self) -> bool:
        """Browser navigations prefer text/html; curl/fetch keep JSON on colliding paths."""
        accept = (self.headers.get("Accept") or "").lower()
        if "text/html" not in accept:
            return False
        html_i = accept.find("text/html")
        json_i = accept.find("application/json")
        return json_i < 0 or html_i < json_i

    def _is_spa_path(self, path: str) -> bool:
        if path in ("/", "/chat", "/tree", "/approve", "/report", "/settings", "/canvas"):
            return True
        for prefix in ("/chat/", "/tree/", "/approve/", "/report/", "/settings/", "/canvas/"):
            if path.startswith(prefix):
                return True
        return False

    # -- routes ----------------------------------------------------------
    def do_GET(self) -> None:
        assert CFG is not None
        from . import ledger, sessions, tasks, trust
        from . import security as sec

        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/" or (self._prefers_html() and self._is_spa_path(u.path)):
            return self._send_file("index.html")
        if u.path.startswith("/assets/") or u.path in ("/favicon.svg", "/icons.svg"):
            return self._send_file(u.path.lstrip("/"))
        if u.path.startswith("/api/media/"):
            from . import media as _media
            mid = u.path[len("/api/media/"):].strip("/")
            hit = _media.resolve_media_file(CFG, mid)
            if not hit:
                return self._send_json({"error": "not found", "code": 404}, 404)
            path, mime = hit
            try:
                with open(path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return
        if u.path.startswith("/api/canvas/"):
            from . import canvas as _canvas
            cid = u.path[len("/api/canvas/"):].strip("/")
            hit = _canvas.resolve_canvas_file(CFG, cid)
            if not hit:
                return self._send_json({"error": "not found", "code": 404}, 404)
            path, mime = hit
            try:
                with open(path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return
        if u.path in ("/health", "/api/health"):
            from . import llm

            reachable, detail = llm.health(CFG)
            return self._send_json({"ok": True, "model": CFG["llm"]["model"],
                                    "version": "1.0.0", "llm_reachable": reachable,
                                    "llm_detail": detail})
        # Everything below requires auth (covers /api/* and bare aliases per doc 06)
        needs_auth = u.path.startswith("/api/") or u.path in ("/tree", "/job", "/report", "/ledger", "/approve", "/waive", "/rollback", "/revert", "/prove", "/send-back")
        if needs_auth and not self._require_auth(q):
            return
        if u.path in ("/tree", "/api/tree"):
            return self._send_json({"tasks": tasks.list_all(CFG), "tree": tasks.to_tree(CFG)})
        if u.path in ("/ledger", "/api/ledger"):
            return self._send_json({"gates": ledger.gate_stats(CFG),
                                    "catch_rates": ledger.catch_rates(CFG),
                                    "open_criticals": ledger.open_criticals(CFG),
                                    "open_issues": len(ledger.open_issues(CFG))})
        if u.path in ("/report", "/api/report"):
            return self._send_json(_report(CFG))
        if u.path in ("/job", "/api/job"):
            from .errors import TaskNotFound
            node_id = (q.get("id", [""])[0] or "").strip()
            if not node_id:
                return self._send_json({"error": "missing ?id=", "code": 400}, 400)
            try:
                return self._send_json(tasks.get(CFG, node_id))
            except (KeyError, TaskNotFound):
                return self._send_json({"error": "no such task", "code": 404}, 404)
        if u.path in ("/approve",) and not self._prefers_html():
            # Bare /approve API alias (doc 06): pending review candidates as JSON.
            waiting = [t for t in tasks.list_all(CFG) if t.get("status") in ("waiting", "doing")]
            return self._send_json({"pending": waiting, "count": len(waiting)})
        if u.path == "/api/metrics":
            return self._send_json({"tasks": tasks.stats(CFG), "ledger": ledger.report(CFG),
                                    "fatigue": trust.fatigue(CFG), "sink": sec.sink_audit(CFG)})
        if u.path == "/api/sink":
            return self._send_json(sec.sink_audit(CFG))
        if u.path == "/api/sbom":
            return self._send_json(sec.generate_sbom(CFG))
        if u.path == "/api/checklist":
            from . import quality as _q
            # mine checklist from recent ledger issues
            notes = [iss.get("text","") for iss in ledger.open_issues(CFG)]
            return self._send_json({"checklist": _q.mine_checklist(notes)})
        if u.path == "/api/waivers":
            # waivers are open issues with layer waiver
            waivers = [iss for iss in ledger.open_issues(CFG) if iss.get("layer") == "waiver"]
            return self._send_json({"waivers": waivers})
        if u.path == "/api/models":
            from . import llm as _llm
            models = _llm.list_models(CFG)
            ctx = _llm.model_context_length(CFG)
            return self._send_json({
                "models": models,
                "current": CFG["llm"]["model"],
                "context_length": ctx,
            })
        if u.path == "/api/workspace":
            return self._send_json({"workspace": CFG.get("_root",""), "state_dir": CFG.get("state_dir",""), "config_path": CFG.get("_config_path")})
        if u.path == "/api/config":
            from . import config as _cfg
            return self._send_json({"config": _cfg.public_view(CFG)})
        if u.path == "/api/tools":
            from .tools.catalog import catalog_public
            return self._send_json({"tools": catalog_public(CFG)})
        if u.path == "/api/agents":
            from . import agents as _agents
            include = (q.get("include_archived", ["0"])[0] or "0") in ("1", "true", "yes")
            return self._send_json({"agents": _agents.list_agents(CFG, include_archived=include)})
        if u.path == "/api/capabilities":
            from . import capabilities as _caps
            include = (q.get("include_retired", ["0"])[0] or "0") in ("1", "true", "yes")
            return self._send_json({"capabilities": _caps.list_capabilities(CFG, include_retired=include)})
        if u.path == "/api/intelligence":
            from . import intelligence as _intel
            return self._send_json({
                "agenda": _intel.list_agenda(CFG, include_done=(q.get("include_done", ["0"])[0] or "0") in ("1", "true", "yes")),
                "stats": _intel.stats(CFG),
                "briefing": _intel.compile_briefing(CFG),
            })
        if u.path == "/api/capability":
            from . import capabilities as _caps
            cid = (q.get("id", [""])[0] or "").strip()
            name = (q.get("name", [""])[0] or "").strip()
            cap = _caps.get_capability(CFG, cid or None, name=name or None)
            if not cap:
                return self._send_json({"error": "no such capability", "code": 404}, 404)
            return self._send_json({"capability": cap})
        if u.path == "/api/memory":
            from . import memory as _mem
            query = (q.get("q", [""])[0] or q.get("query", [""])[0] or "").strip()
            include_dead = (q.get("include_dead", ["0"])[0] or "0") in ("1", "true", "yes")
            try:
                lim = int((q.get("limit", ["100"])[0] or "100"))
            except ValueError:
                lim = 100
            try:
                off = int((q.get("offset", ["0"])[0] or "0"))
            except ValueError:
                off = 0
            if query:
                hits = _mem.search(CFG, query, limit=lim, include_dead=include_dead)
                return self._send_json({"claims": hits, "total": len(hits), "query": query})
            return self._send_json(_mem.list_claims(CFG, include_dead=include_dead, limit=lim, offset=off))
        if u.path == "/api/agent":
            from . import agents as _agents
            aid = (q.get("id", [""])[0] or "").strip()
            if not aid:
                return self._send_json({"error": "missing ?id=", "code": 400}, 400)
            spec = _agents.get_agent(CFG, aid)
            if not spec:
                return self._send_json({"error": "no such agent", "code": 404}, 404)
            return self._send_json({"agent": spec})
        if u.path == "/api/spans":
            from . import agents as _agents
            sid = (q.get("session_id", [""])[0] or "").strip() or None
            status = (q.get("status", [""])[0] or "").strip() or None
            try:
                lim = int((q.get("limit", ["100"])[0] or "100"))
            except ValueError:
                lim = 100
            return self._send_json({
                "spans": _agents.list_spans(CFG, session_id=sid, status=status, limit=lim),
            })
        if u.path == "/api/diff":
            # Review surface: git diff for task files. Empty paths → no whole-repo dump.
            paths = [p for p in (q.get("path", []) or []) if str(p).strip()]
            tid = (q.get("id", [""])[0] or "").strip()
            if tid and not paths:
                try:
                    from .errors import TaskNotFound as _TNF
                    node = tasks.get(CFG, tid)
                    paths = [str(f) for f in (node.get("files") or []) if str(f).strip()]
                except Exception:
                    paths = []
            if not paths:
                return self._send_json({
                    "ok": True, "diff": "", "paths": [], "empty": True,
                    "error": None,
                })
            from .tools.builtins import git_diff
            chunks = []
            last_err = ""
            for p in paths[:40]:
                r = git_diff(CFG, {"path": p})
                if r.ok and (r.content or "").strip():
                    chunks.append(r.content)
                elif not r.ok:
                    last_err = r.content or "git diff failed"
            text = "\n".join(chunks)
            if not text.strip():
                # try staged for the same paths
                for p in paths[:40]:
                    r = git_diff(CFG, {"path": p, "staged": True})
                    if r.ok and (r.content or "").strip():
                        chunks.append(r.content)
                text = "\n".join(chunks)
            return self._send_json({
                "ok": True if text.strip() or not last_err else False,
                "diff": text or "",
                "paths": paths,
                "empty": not bool((text or "").strip()),
                "error": None if text.strip() or not last_err else last_err,
            })
        if u.path == "/api/spec":
            from .errors import TaskNotFound
            tid = (q.get("id", [""])[0] or "").strip()
            if not tid:
                return self._send_json({"error": "missing ?id=", "code": 400}, 400)
            # Pinned contract from specs.json (via `spec pin`); falls back to an
            # unpinned draft derived from the task's done-looks-like text.
            try:
                t = tasks.get(CFG, tid)
                from . import spec as _spec
                pinned = _spec.get_spec(CFG, tid)
                if pinned:
                    return self._send_json({"task": t, "spec": pinned})
                draft = (t.get("done") or "").strip()
                return self._send_json({"task": t, "spec": {
                    "task_id": tid,
                    "acceptance": [draft] if draft else [],
                    "pinned": False,
                    "hint": "no pinned spec — run `spec pin <id> <acceptance...>` or POST /api/spec/pin",
                }})
            except (KeyError, TaskNotFound):
                return self._send_json({"error": "no such task", "code": 404}, 404)
        if u.path == "/api/sessions":
            rows = sessions.list_all(CFG)
            for r in rows:
                r["generating"] = _chat_run_active(r["id"])
            return self._send_json({"sessions": rows})
        if u.path == "/api/approvals":
            from . import approvals as _appr
            items = _appr.list_pending(CFG)
            return self._send_json({"approvals": items, "count": len(items)})
        if u.path == "/api/session":
            sid = (q.get("id", [""])[0] or "").strip()
            s = sessions.get(CFG, sid) if sid else None
            if not s:
                return self._send_json({"error": "no such session", "code": 404}, 404)
            out = dict(s)
            out["generating"] = _chat_run_active(sid)
            return self._send_json(out)
        if u.path == "/api/leaf":
            from . import tasks as _tasks
            leaf = _tasks.leaf(CFG)
            return self._send_json({"leaf": leaf, "rendered": _tasks.render_leaf(leaf) if leaf else "No actionable leaf"})
        # Deep-link fallback for unknown SPA paths (no file extension)
        if self._prefers_html() and "." not in u.path.rsplit("/", 1)[-1]:
            return self._send_file("index.html")
        return self._send_json({"error": "not found", "code": 404}, 404)

    def do_POST(self) -> None:
        assert CFG is not None
        from . import harness, ledger, sessions, tasks, trust

        u = urlparse(self.path)
        q = parse_qs(u.query)
        path_no_q = self.path.split("?")[0]
        # Auth: all POST except health require token (covers /api/* and bare /approve alias per doc 06)
        if path_no_q not in ("/api/health", "/health") and not self._require_auth(q):
            return
        try:
            body = self._body()
        except ValueError as e:
            return self._send_json({"error": str(e), "code": 400}, 400)
        from .errors import TaskNotFound, TaskValidation
        try:
            if path_no_q in ("/api/prove", "/prove"):
                tid, proof = str(body.get("id", "")), str(body.get("proof", ""))
                if not tid or not proof:
                    return self._send_json({"error": "id and proof required", "code": 400}, 400)
                try:
                    tasks.prove(CFG, tid, proof)
                except TaskNotFound:
                    return self._send_json({"error": "no such task", "code": 404}, 404)
                except TaskValidation as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
                ledger.log_gate(CFG, "prove", "F10", "pass", detail=f"proved {tid}")
                return self._send_json({"ok": True})
            if path_no_q in ("/api/task", "/task"):
                title = str(body.get("title", "")).strip()
                if not title:
                    return self._send_json({"error": "title required", "code": 400}, 400)
                try:
                    nid = tasks.add(
                        CFG,
                        title,
                        done=str(body.get("done") or body.get("done_looks_like") or ""),
                        parent=body.get("parent"),
                        why=str(body.get("why") or ""),
                    )
                    node = tasks.get(CFG, nid)
                except Exception as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
                return self._send_json({"ok": True, "id": nid, "task": node})
            if path_no_q in ("/api/approve", "/approve"):
                tid = str(body.get("id", ""))
                if not tid:
                    return self._send_json({"error": "id required", "code": 400}, 400)
                try:
                    tasks.prove(CFG, tid, f"human-approved: {body.get('note', '')}")
                except TaskNotFound:
                    return self._send_json({"error": "no such task", "code": 404}, 404)
                except TaskValidation as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
                ledger.log_gate(CFG, "human", "F7", "pass", detail=f"approved {tid}")
                trust.record_approval(CFG, "approve", True)
                return self._send_json({"ok": True})
            if path_no_q in ("/api/waive", "/waive"):
                text = str(body.get("text", "")).strip()
                if not text:
                    return self._send_json({"error": "text required", "code": 400}, 400)
                # enforce expiry — no permanent bypass per doc 03 §5
                expires = str(body.get("expires", "")).strip()
                if not expires:
                    return self._send_json({"error": "expires required (YYYY-MM-DD) — no permanent bypass", "code": 400}, 400)
                # validate date shape YYYY-MM-DD and future
                import re as _re, datetime as _dt
                if not _re.match(r"^\d{4}-\d{2}-\d{2}$", expires):
                    return self._send_json({"error": "expires must be YYYY-MM-DD", "code": 400}, 400)
                try:
                    ed = _dt.date.fromisoformat(expires)
                    if ed <= _dt.date.today():
                        return self._send_json({"error": "expires must be in the future", "code": 400}, 400)
                except ValueError:
                    return self._send_json({"error": "expires must be valid YYYY-MM-DD", "code": 400}, 400)
                ledger.add_issue(CFG, str(body.get("severity", "minor")), str(body.get("layer", "waiver")),
                                 f"WAIVER by {body.get('owner', 'human')}: {text}",
                                 expires=expires, owner=str(body.get("owner", "")))
                ledger.log_gate(CFG, "waiver", "F7", "pass", detail=text[:200])
                return self._send_json({"ok": True})
            if path_no_q in ("/api/send-back", "/send-back"):
                tid = str(body.get("id", ""))
                if not tid:
                    return self._send_json({"error": "id required", "code": 400}, 400)
                try:
                    tasks.set_status(CFG, tid, "doing")
                except TaskNotFound:
                    return self._send_json({"error": "no such task", "code": 404}, 404)
                except TaskValidation as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
                ledger.add_issue(CFG, "major", "review", f"sent back {tid}: {body.get('note', '')}")
                trust.record_approval(CFG, "approve", False)
                return self._send_json({"ok": True})
            if path_no_q in ("/api/rollback", "/rollback", "/api/revert", "/revert"):
                tid = str(body.get("id", "") or body.get("to_id", "") or body.get("pivot", "")).strip()
                if not tid:
                    return self._send_json({"error": "id (pivot) required", "code": 400}, 400)
                try:
                    reopened = tasks.rollback(CFG, tid)
                except (KeyError, TaskNotFound):
                    return self._send_json({"error": "no such task", "code": 404}, 404)
                ledger.log_gate(CFG, "rollback", "F2", "pass", detail=f"rollback to {tid} reopened {reopened}")
                return self._send_json({"ok": True, "reopened": reopened})
            if path_no_q in ("/api/spec/pin", "/spec/pin"):
                tid = str(body.get("id", "")).strip()
                acceptance = body.get("acceptance", [])
                if isinstance(acceptance, str):
                    acceptance = [acceptance]
                if not tid:
                    return self._send_json({"error": "id required", "code": 400}, 400)
                try:
                    task = tasks.get(CFG, tid)
                except (KeyError, TaskNotFound):
                    return self._send_json({"error": "no such task", "code": 404}, 404)
                try:
                    from . import spec as _specmod
                    s = _specmod.pin_spec(CFG, task, [str(a) for a in acceptance])
                    return self._send_json({"ok": True, "spec": s})
                except Exception as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
            if path_no_q == "/api/agents":
                from . import agents as _agents
                from .errors import StoreError as _SE
                try:
                    spec = _agents.create_agent(
                        CFG,
                        name=str(body.get("name") or ""),
                        role=str(body.get("role") or "worker"),
                        summary=str(body.get("summary") or ""),
                        system_addon=str(body.get("system_addon") or ""),
                        tools=body.get("tools"),
                        groups=body.get("groups"),
                        disabled=body.get("disabled"),
                        inherits_from=(str(body["inherits_from"]) if body.get("inherits_from") else None),
                        budgets=body.get("budgets") if isinstance(body.get("budgets"), dict) else None,
                        policy=body.get("policy") if isinstance(body.get("policy"), dict) else None,
                        created_by="user",
                        force_active=True,
                    )
                    return self._send_json({"ok": True, "agent": spec})
                except (ValueError, _SE) as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
            if path_no_q == "/api/capabilities":
                from . import capabilities as _caps
                from .errors import StoreError as _SE
                try:
                    cap = _caps.propose(
                        CFG,
                        name=str(body.get("name") or ""),
                        summary=str(body.get("summary") or ""),
                        description=str(body.get("description") or ""),
                        kind=str(body.get("kind") or "composite"),
                        risk=str(body.get("risk") or "medium"),
                        parameters=body.get("parameters") if isinstance(body.get("parameters"), dict) else None,
                        impl=body.get("impl") if isinstance(body.get("impl"), dict) else None,
                        tests=body.get("tests") if isinstance(body.get("tests"), list) else None,
                        created_by="user",
                    )
                    return self._send_json({"ok": True, "capability": cap})
                except (ValueError, _SE) as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
            if path_no_q == "/api/intelligence":
                from . import intelligence as _intel
                from .errors import StoreError as _SE
                action = str(body.get("action") or "tick").strip().lower()
                try:
                    if action in ("tick", "reflect", "audit"):
                        result = _intel.tick(CFG, force=bool(body.get("force", True)))
                        return self._send_json({"ok": True, **result})
                    if action == "pursue":
                        iid = str(body.get("id") or "").strip()
                        if not iid:
                            items = _intel.list_agenda(CFG)
                            if not items:
                                return self._send_json({"ok": True, "empty": True})
                            iid = items[0]["id"]
                        result = _intel.pursue(CFG, iid)
                        return self._send_json({"ok": True, **result})
                    if action == "dismiss":
                        item = _intel.dismiss(CFG, str(body.get("id") or ""), reason=str(body.get("reason") or ""))
                        return self._send_json({"ok": True, "item": item})
                    return self._send_json({"error": f"unknown action {action}", "code": 400}, 400)
                except KeyError:
                    return self._send_json({"error": "no such agenda item", "code": 404}, 404)
                except (ValueError, _SE) as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
            if path_no_q == "/api/capability":
                from . import capabilities as _caps
                from .errors import StoreError as _SE
                cid = str(body.get("id") or "").strip()
                if not cid:
                    return self._send_json({"error": "id required", "code": 400}, 400)
                action = str(body.get("action") or "approve").strip().lower()
                try:
                    if action == "approve":
                        cap = _caps.approve(CFG, cid, actor="user")
                    elif action == "reject":
                        cap = _caps.reject(CFG, cid, actor="user", reason=str(body.get("reason") or ""))
                    elif action == "install":
                        cap = _caps.install(CFG, cid, actor="user", require_approved=True)
                    elif action == "retire":
                        cap = _caps.retire(CFG, cid, actor="user")
                    elif action == "test":
                        report = _caps.run_tests(CFG, cid)
                        return self._send_json({"ok": bool(report.get("ok")), "report": report})
                    else:
                        return self._send_json({"error": f"unknown action {action}", "code": 400}, 400)
                    return self._send_json({"ok": True, "capability": cap})
                except KeyError:
                    return self._send_json({"error": "no such capability", "code": 404}, 404)
                except (ValueError, _SE) as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
            if path_no_q == "/api/memory":
                from . import memory as _mem
                from .errors import StoreError as _SE
                action = str(body.get("action") or "add").strip().lower()
                try:
                    if action in ("add", "remember"):
                        claim = _mem.remember(
                            CFG,
                            str(body.get("text") or body.get("claim") or ""),
                            source=str(body.get("source") or "human"),
                            taint=str(body.get("taint") or "human"),
                            task_id=str(body.get("task_id") or ""),
                            verification=str(body.get("verification") or "human"),
                        )
                        return self._send_json({"ok": True, "claim": claim})
                    if action == "confirm":
                        claim = _mem.confirm(
                            CFG,
                            index=int(body["index"]) if body.get("index") is not None and str(body.get("index")) != "" else None,
                            claim_id=int(body["id"]) if body.get("id") is not None and str(body.get("id")) != "" else None,
                            verification=str(body.get("verification") or "verified"),
                        )
                        return self._send_json({"ok": True, "claim": claim})
                    if action == "supersede":
                        claim = _mem.supersede(
                            CFG,
                            index=int(body["index"]) if body.get("index") is not None and str(body.get("index")) != "" else None,
                            claim_id=int(body["id"]) if body.get("id") is not None and str(body.get("id")) != "" else None,
                            replacement=str(body.get("replacement") or body.get("text") or ""),
                        )
                        return self._send_json({"ok": True, "claim": claim})
                    if action == "retire":
                        claim = _mem.confirm(
                            CFG,
                            index=int(body["index"]) if body.get("index") is not None and str(body.get("index")) != "" else None,
                            claim_id=int(body["id"]) if body.get("id") is not None and str(body.get("id")) != "" else None,
                            verification="retired",
                        )
                        return self._send_json({"ok": True, "claim": claim})
                    return self._send_json({"error": f"unknown action {action}", "code": 400}, 400)
                except (ValueError, _SE, TypeError) as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
            if path_no_q == "/api/agent":
                from . import agents as _agents
                from .errors import StoreError as _SE
                aid = str(body.get("id") or "").strip()
                if not aid:
                    return self._send_json({"error": "id required", "code": 400}, 400)
                action = str(body.get("action") or "update").strip()
                try:
                    if action == "approve":
                        spec = _agents.approve_agent(CFG, aid, actor="user")
                    elif action == "archive":
                        spec = _agents.archive_agent(CFG, aid, actor="user")
                    elif action == "run":
                        goal = str(body.get("goal") or "").strip()
                        if not goal:
                            return self._send_json({"error": "goal required", "code": 400}, 400)
                        result = _agents.run_specialized(CFG, aid, goal)
                        return self._send_json({"ok": True, **{k: result[k] for k in (
                            "reply", "span_id", "run_id", "effective", "gate", "meta", "agent"
                        ) if k in result}})
                    else:
                        patch = {k: v for k, v in body.items() if k not in ("id", "action")}
                        spec = _agents.update_agent(CFG, aid, patch, actor="user")
                    return self._send_json({"ok": True, "agent": spec})
                except KeyError:
                    return self._send_json({"error": "no such agent", "code": 404}, 404)
                except (ValueError, _SE) as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
            if self.path.split("?")[0] == "/api/sessions":
                sid = sessions.create(CFG, str(body.get("title", "New chat"))[:120])
                return self._send_json({"id": sid})
            if self.path.split("?")[0] == "/api/session/rename":
                sid = str(body.get("id", "")).strip()
                if not sid:
                    return self._send_json({"error": "id required", "code": 400}, 400)
                raw_title = body.get("title", None)
                # None or empty → auto-summarize via LLM
                if raw_title is None or (isinstance(raw_title, str) and not raw_title.strip()):
                    try:
                        title = sessions.summarize_title(CFG, sid)
                    except KeyError:
                        return self._send_json({"error": "no such session", "code": 404}, 404)
                    except Exception as e:
                        return self._send_json({"error": f"summarize failed: {e}", "code": 500}, 500)
                else:
                    title = str(raw_title).strip()[:60]
                try:
                    s = sessions.rename(CFG, sid, title)
                    return self._send_json({"ok": True, "id": sid, "title": s["title"]})
                except KeyError:
                    return self._send_json({"error": "no such session", "code": 404}, 404)
                except Exception as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
            if self.path.split("?")[0] == "/api/session/branch":
                sid = str(body.get("id", "")).strip()
                if not sid:
                    return self._send_json({"error": "id required", "code": 400}, 400)
                up_to = body.get("up_to", -1)
                try:
                    up_to = int(up_to) if up_to is not None else -1
                except Exception:
                    up_to = -1
                title = body.get("title", None)
                if title is not None:
                    title = str(title)[:60]
                try:
                    new_sid = sessions.branch(CFG, sid, up_to, title)
                    return self._send_json({"ok": True, "id": new_sid})
                except KeyError:
                    return self._send_json({"error": "no such session", "code": 404}, 404)
                except Exception as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
            if self.path.split("?")[0] == "/api/session/edit":
                sid = str(body.get("id", "")).strip()
                idx = body.get("idx", None)
                content = str(body.get("content", ""))
                if not sid:
                    return self._send_json({"error": "id required", "code": 400}, 400)
                try:
                    idx = int(idx)
                except Exception:
                    return self._send_json({"error": "idx must be int", "code": 400}, 400)
                try:
                    sessions.edit_message(CFG, sid, idx, content)
                    return self._send_json({"ok": True})
                except KeyError:
                    return self._send_json({"error": "no such session", "code": 404}, 404)
                except Exception as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
            if self.path.split("?")[0] == "/api/model":
                new_model = str(body.get("model", "")).strip()
                if not new_model:
                    return self._send_json({"error": "model required", "code": 400}, 400)
                from . import llm as _llm
                available = _llm.list_models(CFG)
                if available and new_model not in available:
                    # Allow exact current model even if list endpoint flaked empty tags
                    if new_model != CFG["llm"].get("model"):
                        return self._send_json({
                            "error": f"unknown model — choose one of: {', '.join(available[:12])}"
                                     + ("…" if len(available) > 12 else ""),
                            "code": 400,
                            "models": available,
                        }, 400)
                CFG["llm"]["model"] = new_model
                try:
                    from . import config as _cfg
                    _cfg.save(CFG)
                except Exception as e:
                    return self._send_json({"error": f"cannot persist model: {e}", "code": 500}, 500)
                ctx = _llm.model_context_length(CFG, new_model)
                return self._send_json({"ok": True, "model": new_model, "context_length": ctx})
            if self.path.split("?")[0] == "/api/config":
                from . import config as _cfg
                from .errors import ConfigError
                patch = body.get("config") if isinstance(body.get("config"), dict) else body
                try:
                    updated = _cfg.apply_patch(CFG, patch if isinstance(patch, dict) else {})
                    CFG.clear()
                    CFG.update(updated)
                    _cfg.save(CFG)
                    if isinstance(patch, dict) and "mcp" in patch:
                        try:
                            from .tools.mcp_bridge import sync_mcp
                            sync_mcp(CFG, force=True)
                        except Exception:
                            pass
                    return self._send_json({"ok": True, "config": _cfg.public_view(CFG)})
                except ConfigError as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
                except Exception as e:
                    return self._send_json({"error": str(e), "code": 500}, 500)
            if self.path.split("?")[0] == "/api/workspace":
                new_ws = str(body.get("path", "")).strip()
                if not new_ws:
                    return self._send_json({"error": "path required", "code": 400}, 400)
                import pathlib as _pl
                p = _pl.Path(new_ws).expanduser().resolve()
                if not p.exists() or not p.is_dir():
                    return self._send_json({"error": "workspace must be an existing directory", "code": 400}, 400)
                try:
                    (p / ".super").mkdir(exist_ok=True)
                except Exception as e:
                    return self._send_json({"error": f"cannot init workspace: {e}", "code": 500}, 500)
                try:
                    from . import config as _cfg
                    from .errors import ConfigError
                    new_cfg = _cfg.load_workspace(str(p))
                    if not new_cfg["server"]["token"]:
                        new_cfg["server"]["token"] = CFG["server"]["token"]
                    CFG.clear()
                    CFG.update(new_cfg)
                    return self._send_json({"ok": True, "workspace": CFG["_root"]})
                except ConfigError as e:
                    return self._send_json({"error": str(e), "code": 400}, 400)
                except Exception as e:
                    return self._send_json({"error": f"cannot load workspace: {e}", "code": 500}, 500)
            if self.path.split("?")[0] == "/api/fs/pick":
                try:
                    from . import fsutil
                    initial = str(body.get("path") or CFG.get("_root") or "").strip() or None
                    picked = fsutil.pick_directory(initial)
                    if not picked:
                        return self._send_json({"ok": False, "cancelled": True, "path": None})
                    return self._send_json({"ok": True, "cancelled": False, "path": picked})
                except Exception as e:
                    return self._send_json({"error": f"folder picker failed: {e}", "code": 500}, 500)
            if self.path.split("?")[0] == "/api/reload":
                try:
                    from . import config as _cfg
                    reloaded = _cfg.load(CFG.get("_config_path"))
                    # keep in-memory token if file had empty
                    if not reloaded["server"]["token"]:
                        reloaded["server"]["token"] = CFG["server"]["token"]
                    CFG.clear()
                    CFG.update(reloaded)
                    return self._send_json({"ok": True, "workspace": CFG["_root"], "model": CFG["llm"]["model"]})
                except Exception as e:
                    return self._send_json({"error": f"reload failed: {e}", "code": 500}, 500)
            if self.path.split("?")[0] == "/api/chat/cancel":
                sid = str(body.get("session_id") or body.get("id") or "").strip()
                if not sid:
                    return self._send_json({"error": "session_id required", "code": 400}, 400)
                return self._send_json({"ok": True, "cancelled": _chat_run_cancel(sid)})
            if self.path.split("?")[0] == "/api/chat":
                msg = str(body.get("message", ""))
                if not msg.strip():
                    return self._send_json({"error": "message required", "code": 400}, 400)
                _raw = body.get("session_id")
                if _raw is None or (isinstance(_raw, str) and not _raw.strip()) or str(_raw).strip().lower() == "none":
                    sid = sessions.create(CFG)
                else:
                    sid = str(_raw).strip()
                if not sessions.get(CFG, sid):
                    return self._send_json({"error": "no such session", "code": 404}, 404)
                reply, gate = harness.answer(CFG, sid, msg[:20000])
                return self._send_json({"session_id": sid, "reply": reply, "gate": gate})
            if self.path.split("?")[0] == "/api/chat/stream":
                msg = str(body.get("message", ""))
                if not msg.strip():
                    return self._send_json({"error": "message required", "code": 400}, 400)
                _raw = body.get("session_id")
                if _raw is None or (isinstance(_raw, str) and not _raw.strip()) or str(_raw).strip().lower() == "none":
                    sid = sessions.create(CFG)
                else:
                    sid = str(_raw).strip()
                if not sessions.get(CFG, sid):
                    return self._send_json({"error": "no such session", "code": 404}, 404)
                user_text = msg[:20000]
                skip_user = bool(body.get("skip_user_append"))
                hist = sessions.history(CFG, sid)
                messages = [{"role": "system", "content": harness.build_system(CFG)}]
                for m in hist:
                    if m["role"] in ("user", "assistant"):
                        messages.append({"role": m["role"], "content": m["content"]})
                if skip_user:
                    # Regenerate / edit-resend: last hist turn must already be this user text.
                    if not hist or hist[-1].get("role") != "user":
                        return self._send_json(
                            {"error": "skip_user_append requires last message to be user", "code": 400}, 400
                        )
                    if not messages or messages[-1].get("role") != "user":
                        messages.append({"role": "user", "content": hist[-1].get("content") or user_text})
                else:
                    messages.append({"role": "user", "content": user_text})
                    sessions.append(CFG, sid, "user", user_text)
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                except (BrokenPipeError, ConnectionResetError):
                    # Client already gone — still run to completion and persist.
                    pass

                cancel_ev = _chat_run_begin(sid)
                client_gone = False

                def _emit(obj: dict) -> None:
                    nonlocal client_gone
                    if client_gone:
                        return
                    try:
                        self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        client_gone = True

                try:
                    from . import approvals as _appr
                    tools_on = bool((CFG.get("tools") or {}).get("enabled", True))
                    reply = ""
                    thinking = ""
                    thoughts: list[str] = []
                    blocks: list[dict] = []
                    agent_meta: dict = {}
                    tool_events: list[dict] = []
                    child_by_span: dict[str, dict] = {}
                    approval_events: list[dict] = []
                    cancelled = False
                    if tools_on:
                        from .tools.runtime import run_agent_stream
                        import uuid as _uuid
                        run_cfg = dict(CFG)
                        run_cfg["_session_id"] = sid
                        run_cfg["_agent"] = {
                            **(CFG.get("_agent") or {}),
                            "id": "main",
                            "run_id": _uuid.uuid4().hex[:12],
                        }
                        for ev in run_agent_stream(run_cfg, messages):
                            if cancel_ev.is_set():
                                cancelled = True
                                break
                            if "thinking_delta" in ev and ev["thinking_delta"]:
                                thinking += ev["thinking_delta"]
                            if "delta" in ev:
                                reply += ev["delta"]
                            if isinstance(ev.get("blocks"), list):
                                blocks = [b for b in ev["blocks"] if isinstance(b, dict)]
                            ts = ev.get("thinking_step")
                            if isinstance(ts, dict) and isinstance(ts.get("content"), str) and ts["content"]:
                                idx = ts.get("index")
                                if isinstance(idx, int) and 0 <= idx < len(thoughts):
                                    thoughts[idx] = ts["content"]
                                elif isinstance(idx, int) and idx == len(thoughts):
                                    thoughts.append(ts["content"])
                                else:
                                    thoughts.append(ts["content"])
                                thinking = "\n\n".join(thoughts)
                            if "thoughts" in ev and isinstance(ev.get("thoughts"), list):
                                thoughts = [str(x) for x in ev["thoughts"] if isinstance(x, str) and x]
                                thinking = "\n\n".join(thoughts) if thoughts else thinking
                            if "thinking" in ev and isinstance(ev.get("thinking"), str) and ev["thinking"]:
                                thinking = ev["thinking"]
                            if "agent_meta" in ev:
                                agent_meta = ev["agent_meta"]
                                reply = ev.get("reply") or reply
                                if isinstance(ev.get("blocks"), list):
                                    blocks = [b for b in ev["blocks"] if isinstance(b, dict)]
                                elif isinstance(agent_meta.get("blocks"), list):
                                    blocks = [b for b in agent_meta["blocks"] if isinstance(b, dict)]
                                if isinstance(ev.get("thoughts"), list):
                                    thoughts = [str(x) for x in ev["thoughts"] if isinstance(x, str) and x]
                                elif isinstance(agent_meta.get("thoughts"), list):
                                    thoughts = [
                                        str(x) for x in agent_meta["thoughts"]
                                        if isinstance(x, str) and x
                                    ]
                                if isinstance(ev.get("thinking"), str) and ev["thinking"]:
                                    thinking = ev["thinking"]
                                elif isinstance(agent_meta.get("thinking"), str) and agent_meta["thinking"]:
                                    thinking = agent_meta["thinking"]
                                elif thoughts:
                                    thinking = "\n\n".join(thoughts)
                            tc = ev.get("tool_call")
                            if isinstance(tc, dict) and tc.get("name"):
                                tool_events.append({
                                    "kind": "call",
                                    "name": tc.get("name"),
                                    "arguments": tc.get("arguments"),
                                })
                            tr = ev.get("tool_result")
                            if isinstance(tr, dict) and tr.get("name"):
                                row = {
                                    "kind": "result",
                                    "name": tr.get("name"),
                                    "ok": tr.get("ok"),
                                    "content": tr.get("content"),
                                }
                                if isinstance(tr.get("media"), list) and tr["media"]:
                                    row["media"] = tr["media"]
                                if isinstance(tr.get("canvas"), dict) and tr["canvas"]:
                                    row["canvas"] = tr["canvas"]
                                tool_events.append(row)
                                ap = _appr.from_tool_result(
                                    str(tr.get("name") or ""),
                                    tr.get("content") if isinstance(tr.get("content"), str) else None,
                                    ok=bool(tr.get("ok", True)),
                                )
                                if ap:
                                    approval_events.append(ap)
                                    _emit({"approval": ap})
                            ca = ev.get("child_agent")
                            if isinstance(ca, dict) and ca.get("span_id"):
                                child_by_span[str(ca["span_id"])] = ca
                            _emit(ev)
                    else:
                        from . import llm
                        import time as _time
                        chunks: list[str] = []
                        think_chunks: list[str] = []
                        t_first = None
                        chars = 0
                        for ev in llm.chat_stream(CFG, messages):
                            if cancel_ev.is_set():
                                cancelled = True
                                break
                            if "thinking_delta" in ev and ev["thinking_delta"]:
                                think_chunks.append(ev["thinking_delta"])
                                _emit({"thinking_delta": ev["thinking_delta"]})
                            if "delta" in ev:
                                d = ev["delta"]
                                chunks.append(d)
                                chars += len(d)
                                now = _time.monotonic()
                                if t_first is None:
                                    t_first = now
                                    _emit({"delta": d})
                                elif now > t_first:
                                    tok = max(1, chars // 4)
                                    live = {
                                        "source": "live",
                                        "completion_tokens": tok,
                                        "decode_tps": round(tok / (now - t_first), 2),
                                    }
                                    _emit({"delta": d, "llm_stats": live})
                                else:
                                    _emit({"delta": d})
                            elif "usage" in ev and isinstance(ev["usage"], dict):
                                _emit({"llm_stats": ev["usage"]})
                                agent_meta = {**(agent_meta or {}), "llm_stats": ev["usage"]}
                            elif "message" in ev and isinstance(ev["message"], dict):
                                m = ev["message"]
                                if m.get("thinking"):
                                    thinking = m["thinking"]
                        reply = "".join(chunks)
                        if not thinking:
                            thinking = "".join(think_chunks)
                    if cancelled and not (reply or "").strip() and not tool_events and not (thinking or "").strip():
                        # Explicit stop before any tokens — nothing to persist.
                        pass
                    else:
                        if cancelled and (reply or "").strip():
                            reply = (reply or "").rstrip() + "\n\n_(stopped)_"
                        gate = harness.check_reply(CFG, reply)
                        if agent_meta:
                            gate = {**gate, "agent": agent_meta}
                        if cancelled:
                            gate = {**gate, "cancelled": True}
                        children = list(child_by_span.values()) or None
                        # Dedupe approvals by kind+id
                        seen_ap: set[tuple] = set()
                        uniq_ap: list[dict] = []
                        for a in approval_events:
                            key = (a.get("kind"), a.get("id"))
                            if key in seen_ap:
                                continue
                            seen_ap.add(key)
                            uniq_ap.append(a)
                        sessions.append(
                            CFG, sid, "assistant", reply,
                            gate=gate, tools=tool_events or None, children=children,
                            approvals=uniq_ap or None,
                            thinking=thinking or None,
                            thoughts=thoughts or None,
                            blocks=blocks or None,
                        )
                        _emit({"done": True, "session_id": sid, "gate": gate, "approvals": uniq_ap})
                except Exception as e:
                    try:
                        _emit({"error": str(e)})
                    except Exception:
                        pass
                finally:
                    _chat_run_end(sid, cancel_ev)
                return
        except KeyError as e:
            return self._send_json({"error": str(e), "code": 404}, 404)
        except TaskNotFound:
            return self._send_json({"error": "no such task", "code": 404}, 404)
        except TaskValidation as e:
            return self._send_json({"error": str(e), "code": 400}, 400)
        except ValueError as e:
            return self._send_json({"error": str(e), "code": 400}, 400)
        except Exception as e:
            return self._send_json({"error": f"internal: {type(e).__name__}: {e}", "code": 500}, 500)
        return self._send_json({"error": "not found", "code": 404}, 404)

    def do_DELETE(self) -> None:
        assert CFG is not None
        from . import sessions

        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path.startswith("/api/") and not self._require_auth(q):
            return
        if u.path.split("?")[0] == "/api/session":
            sid = (q.get("id", [""])[0] or "").strip()
            if sessions.delete(CFG, sid):
                return self._send_json({"ok": True})
            return self._send_json({"error": "no such session", "code": 404}, 404)
        if u.path.split("?")[0] == "/api/agent":
            from . import agents as _agents
            from .errors import StoreError as _SE
            aid = (q.get("id", [""])[0] or "").strip()
            if not aid:
                return self._send_json({"error": "missing ?id=", "code": 400}, 400)
            try:
                spec = _agents.archive_agent(CFG, aid, actor="user")
                return self._send_json({"ok": True, "agent": spec})
            except KeyError:
                return self._send_json({"error": "no such agent", "code": 404}, 404)
            except _SE as e:
                return self._send_json({"error": str(e), "code": 400}, 400)
        return self._send_json({"error": "not found", "code": 404}, 404)

    def log_message(self, *a) -> None:
        pass

    def handle_error(self, request, client_address) -> None:
        import sys
        exc = sys.exception()
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def _watch_config():
    """Hot reload: poll super.config.json mtime, reload CFG in-place."""
    import threading as _th
    import pathlib as _pl

    def _loop():
        last = 0.0
        while True:
            try:
                path = CFG.get("_config_path") if CFG else None
                if path and os.path.isfile(path):
                    mt = os.path.getmtime(path)
                    if mt != last and last != 0:
                        try:
                            from . import config as _cfg
                            reloaded = _cfg.load(path)
                            if not reloaded["server"]["token"]:
                                reloaded["server"]["token"] = CFG["server"]["token"]
                            CFG.clear()
                            CFG.update(reloaded)
                            print(f"[hot-reload] config reloaded from {path}")
                        except Exception as e:
                            print(f"[hot-reload] failed: {e}")
                    last = mt
                # also watch .super/tasks.json and sessions for external edits — no action, just keep mtime
            except Exception:
                pass
            time.sleep(2)

    t = _th.Thread(target=_loop, daemon=True)
    t.start()


def _lan_urls(port: int) -> list[str]:
    """Best-effort LAN IPv4 URLs for the startup banner."""
    urls: list[str] = []
    seen: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
            ip = info[4][0]
            if ip.startswith("127.") or ip in seen:
                continue
            seen.add(ip)
            urls.append(f"http://{ip}:{port}/")
    except OSError:
        pass
    if not urls:
        # Fallback: UDP connect trick to discover the primary outbound IP.
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127."):
                    urls.append(f"http://{ip}:{port}/")
            finally:
                s.close()
        except OSError:
            pass
    return urls


def serve(cfg: dict) -> None:
    global CFG
    CFG = cfg
    host, port = cfg["server"]["host"], cfg["server"]["port"]
    _watch_config()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"SUPER 1.0.0 dashboard on http://{host}:{port}/")
    print(f"  local:  http://127.0.0.1:{port}/")
    for u in _lan_urls(port):
        print(f"  lan:    {u}")
    print("API: /api/tree /api/job?id= /api/report /api/ledger /api/metrics /api/agents /api/capabilities /api/intelligence /api/spans /api/memory /api/fs/pick")
    httpd.serve_forever()
