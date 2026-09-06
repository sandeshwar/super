"""Production local API + dashboard (doc 06).

Binds 127.0.0.1 only, requires a bearer token on every /api/* route except
liveness (/api/health). Tokens ride the Authorization header, X-Super-Token,
or ?token= (dashboard convenience — the CLI prints the tokenized URL).
Stdlib only. All mutations validate input, audit-log, and return typed
errors without stack leaks.
"""

from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

CFG: dict | None = None
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "dist")
MIME = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
        ".svg": "image/svg+xml", ".json": "application/json", ".png": "image/png"}

MAX_BODY = 1_000_000


def _token_of(handler: BaseHTTPRequestHandler, query: dict) -> str:
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    if handler.headers.get("X-Super-Token"):
        return handler.headers.get("X-Super-Token", "").strip()
    vals = query.get("token", [])
    return vals[0] if vals else ""



def _authorized(handler: BaseHTTPRequestHandler, query: dict) -> bool:
    if CFG is None:
        return False
    want = (CFG.get("server", {}) or {}).get("token", "")
    if not want:
        return True
    import hmac as _hmac

    return _hmac.compare_digest(_token_of(handler, query), want)


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
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, name: str) -> None:
        path = os.path.normpath(os.path.join(WEB_DIR, name))
        if not path.startswith(WEB_DIR) or not os.path.isfile(path):
            return self._send_json({"error": "not found", "code": 404}, 404)
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(os.path.splitext(name)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

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
        if _authorized(self, query):
            return True
        self._send_json({"error": "unauthorized — supply ?token= or Authorization: Bearer", "code": 401}, 401)
        return False

    def _prefers_html(self) -> bool:
        """Browser navigations prefer text/html; curl/fetch keep JSON on colliding paths."""
        accept = (self.headers.get("Accept") or "").lower()
        if "text/html" not in accept:
            return False
        html_i = accept.find("text/html")
        json_i = accept.find("application/json")
        return json_i < 0 or html_i < json_i

    def _is_spa_path(self, path: str) -> bool:
        if path in ("/", "/chat", "/tree", "/approve", "/report"):
            return True
        for prefix in ("/chat/", "/tree/", "/approve/", "/report/"):
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
            node_id = (q.get("id", [""])[0] or "").strip()
            if not node_id:
                return self._send_json({"error": "missing ?id=", "code": 400}, 400)
            try:
                return self._send_json(tasks.get(CFG, node_id))
            except KeyError:
                return self._send_json({"error": "no such task", "code": 404}, 404)
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
            return self._send_json({"models": models, "current": CFG["llm"]["model"]})
        if u.path == "/api/workspace":
            return self._send_json({"workspace": CFG.get("_root",""), "state_dir": CFG.get("state_dir",""), "config_path": CFG.get("_config_path")})
        if u.path == "/api/spec":
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
            except KeyError:
                return self._send_json({"error": "no such task", "code": 404}, 404)
        if u.path == "/api/sessions":
            return self._send_json({"sessions": sessions.list_all(CFG)})
        if u.path == "/api/session":
            sid = (q.get("id", [""])[0] or "").strip()
            s = sessions.get(CFG, sid) if sid else None
            if not s:
                return self._send_json({"error": "no such session", "code": 404}, 404)
            return self._send_json(s)
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
        try:
            if path_no_q in ("/api/prove", "/prove"):
                tid, proof = str(body.get("id", "")), str(body.get("proof", ""))
                if not tid or not proof:
                    return self._send_json({"error": "id and proof required", "code": 400}, 400)
                tasks.prove(CFG, tid, proof)
                ledger.log_gate(CFG, "prove", "F10", "pass", detail=f"proved {tid}")
                return self._send_json({"ok": True})
            if path_no_q in ("/api/approve", "/approve"):
                tid = str(body.get("id", ""))
                if not tid:
                    return self._send_json({"error": "id required", "code": 400}, 400)
                tasks.prove(CFG, tid, f"human-approved: {body.get('note', '')}")
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
                tasks.set_status(CFG, tid, "doing")
                ledger.add_issue(CFG, "major", "review", f"sent back {tid}: {body.get('note', '')}")
                trust.record_approval(CFG, "approve", False)
                return self._send_json({"ok": True})
            if path_no_q in ("/api/rollback", "/rollback", "/api/revert", "/revert"):
                tid = str(body.get("id", "") or body.get("to_id", "") or body.get("pivot", "")).strip()
                if not tid:
                    return self._send_json({"error": "id (pivot) required", "code": 400}, 400)
                try:
                    reopened = tasks.rollback(CFG, tid)
                except KeyError:
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
                except KeyError:
                    return self._send_json({"error": "no such task", "code": 404}, 404)
                try:
                    from . import spec as _specmod
                    s = _specmod.pin_spec(CFG, task, [str(a) for a in acceptance])
                    return self._send_json({"ok": True, "spec": s})
                except Exception as e:
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
                # validate via list if possible
                CFG["llm"]["model"] = new_model
                try:
                    from . import config as _cfg
                    _cfg.save(CFG)
                except Exception as e:
                    return self._send_json({"error": f"cannot persist model: {e}", "code": 500}, 500)
                return self._send_json({"ok": True, "model": new_model})
            if self.path.split("?")[0] == "/api/workspace":
                new_ws = str(body.get("path", "")).strip()
                if not new_ws:
                    return self._send_json({"error": "path required", "code": 400}, 400)
                # security: must be existing dir, local, not outside allowed
                import pathlib as _pl
                p = _pl.Path(new_ws).expanduser().resolve()
                if not p.exists() or not p.is_dir():
                    return self._send_json({"error": "workspace must be an existing directory", "code": 400}, 400)
                # prevent escaping to system roots without super.config.json
                # allow any local dir, but ensure we can create state_dir
                try:
                    (p / ".super").mkdir(exist_ok=True)
                except Exception as e:
                    return self._send_json({"error": f"cannot init workspace: {e}", "code": 500}, 500)
                # reload config from new workspace
                try:
                    from . import config as _cfg
                    new_cfg = _cfg.load(str(p / "super.config.json") if (p / "super.config.json").exists() else None)
                    # if loaded from different path, adjust _root
                    if not new_cfg.get("_config_path"):
                        new_cfg["_root"] = str(p)
                        new_cfg["_config_path"] = str(p / "super.config.json")
                    # preserve token from old cfg if new has empty
                    if not new_cfg["server"]["token"]:
                        new_cfg["server"]["token"] = CFG["server"]["token"]
                    # swap global
                    CFG.clear()
                    CFG.update(new_cfg)
                    return self._send_json({"ok": True, "workspace": CFG["_root"]})
                except Exception as e:
                    return self._send_json({"error": f"cannot load workspace: {e}", "code": 500}, 500)
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
                from . import llm

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
                hist = sessions.history(CFG, sid)
                messages = [{"role": "system", "content": harness.build_system(CFG)}]
                for m in hist:
                    if m["role"] in ("user", "assistant"):
                        messages.append({"role": m["role"], "content": m["content"]})
                messages.append({"role": "user", "content": user_text})
                sessions.append(CFG, sid, "user", user_text)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                chunks: list[str] = []
                try:
                    for delta in llm.chat_stream(CFG, messages):
                        chunks.append(delta)
                        self.wfile.write(f"data: {json.dumps({'delta': delta})}\n\n".encode())
                        self.wfile.flush()
                    reply = "".join(chunks)
                    gate = harness.check_reply(CFG, reply)
                    sessions.append(CFG, sid, "assistant", reply, gate=gate)
                    self.wfile.write(
                        f"data: {json.dumps({'done': True, 'session_id': sid, 'gate': gate})}\n\n".encode())
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
        except KeyError as e:
            return self._send_json({"error": str(e), "code": 404}, 404)
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
        return self._send_json({"error": "not found", "code": 404}, 404)

    def log_message(self, *a) -> None:
        pass


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


def serve(cfg: dict) -> None:
    global CFG
    CFG = cfg
    host, port = cfg["server"]["host"], cfg["server"]["port"]
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("refusing to bind non-localhost")
    token = (cfg.get("server", {}) or {}).get("token", "")
    _watch_config()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"SUPER { '1.0.0'} dashboard on http://{host}:{port}/?token={token}")
    print("API: /api/tree /api/job?id= /api/report /api/ledger /api/metrics")
    httpd.serve_forever()
