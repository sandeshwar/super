"""Agent presentation canvas — structured artifacts for the side panel.

Kinds: url | image | video | markdown | html | file | doc

Large html/markdown bodies are written under ``{state_dir}/canvas/`` and
served at ``/api/canvas/<id>`` so SSE/session payloads stay small.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from typing import Any

from .tools.base import ToolResult, dump_json, resolve_path

KINDS = ("url", "image", "video", "markdown", "html", "file", "doc")
MAX_INLINE_CHARS = 12_000
MAX_TITLE = 120
MAX_CONTENT_STORE = 2_000_000


def _canvas_dir(cfg: dict) -> str:
    d = os.path.join(cfg.get("state_dir") or ".super", "canvas")
    os.makedirs(d, exist_ok=True)
    return d


def _session_store(cfg: dict) -> dict[str, dict]:
    store = cfg.setdefault("_canvas_artifacts", {})
    if not isinstance(store, dict):
        store = {}
        cfg["_canvas_artifacts"] = store
    return store


def public_part(part: dict | None) -> dict | None:
    """Sanitize a canvas artifact for SSE / session JSON."""
    if not isinstance(part, dict):
        return None
    kind = str(part.get("kind") or "").strip().lower()
    if kind not in KINDS:
        return None
    action = str(part.get("action") or "present").strip().lower()
    if action not in ("present", "update", "close"):
        action = "present"
    out: dict[str, Any] = {
        "id": str(part.get("id") or "")[:64] or uuid.uuid4().hex[:12],
        "action": action,
        "kind": kind,
        "title": str(part.get("title") or "Canvas")[:MAX_TITLE],
        "open": bool(part.get("open", action != "close")),
        "detachable": bool(part.get("detachable", True)),
    }
    for key in ("src", "mime", "path", "alt"):
        val = part.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()[:8000 if key == "src" else 500]
    content = part.get("content")
    if isinstance(content, str) and content:
        out["content"] = content[:MAX_INLINE_CHARS]
        if len(content) > MAX_INLINE_CHARS:
            out["content_truncated"] = True
    if isinstance(part.get("bytes"), int) and part["bytes"] >= 0:
        out["bytes"] = int(part["bytes"])
    if "embeddable" in part:
        out["embeddable"] = bool(part.get("embeddable"))
    note = part.get("embed_note")
    if isinstance(note, str) and note.strip():
        out["embed_note"] = note.strip()[:400]
    return out


def probe_url_embeddable(url: str, *, timeout: float = 8.0) -> tuple[bool, str]:
    """Return (embeddable, note) based on X-Frame-Options / CSP frame-ancestors."""
    import urllib.error
    import urllib.parse
    import urllib.request

    from . import net as _net

    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return False, "URL must be http(s)"

    host = (urllib.parse.urlparse(url).hostname or "").lower()
    # Sites that reliably refuse iframe embeds (even when probe is blocked by a proxy).
    hard_block = (
        "google.com", "www.google.com", "accounts.google.com",
        "youtube.com", "www.youtube.com",
        "facebook.com", "www.facebook.com",
        "twitter.com", "x.com", "www.x.com",
        "instagram.com", "www.instagram.com",
        "linkedin.com", "www.linkedin.com",
        "github.com", "www.github.com",
    )
    if host in hard_block or any(host.endswith("." + h) for h in ("google.com", "youtube.com", "facebook.com")):
        return False, f"{host} blocks iframe embedding"

    headers = {
        "User-Agent": "super-harness/1.0 (canvas-embed-probe)",
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    # Prefer HEAD; some sites 405 — fall back to GET with tiny read.
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers=headers)
            with _net.urlopen(req, timeout=timeout) as resp:
                xfo = (resp.headers.get("X-Frame-Options") or "").strip().lower()
                csp = (resp.headers.get("Content-Security-Policy") or "").strip().lower()
                if method == "GET":
                    try:
                        resp.read(64)
                    except Exception:
                        pass
            if xfo in ("deny", "sameorigin"):
                return False, f"Blocked by X-Frame-Options: {xfo}"
            if "frame-ancestors" in csp:
                fa = csp.split("frame-ancestors", 1)[1]
                fa = fa.split(";", 1)[0].strip()
                if "'none'" in fa or fa == "none":
                    return False, "Blocked by CSP frame-ancestors 'none'"
                if "'self'" in fa and "*" not in fa and "http" not in fa:
                    return False, "Blocked by CSP frame-ancestors 'self'"
            return True, ""
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (403, 405, 501):
                continue
            if e.code in (401, 403):
                xfo = (e.headers.get("X-Frame-Options") or "").strip().lower() if e.headers else ""
                if xfo in ("deny", "sameorigin"):
                    return False, f"Blocked by X-Frame-Options: {xfo}"
            return True, f"Probe HTTP {e.code}; embedding may fail"
        except Exception as e:
            if method == "HEAD":
                continue
            return True, f"Probe failed ({type(e).__name__}); embedding may fail"
    return True, "Probe inconclusive; embedding may fail"


def resolve_canvas_file(cfg: dict, cid: str) -> tuple[str, str] | None:
    """Return (path, mime) for a stored canvas body, or None."""
    cid = (cid or "").strip()
    if not cid or "/" in cid or ".." in cid or "\\" in cid:
        return None
    base = _canvas_dir(cfg)
    for name in os.listdir(base):
        if name.startswith(cid + ".") or name == cid:
            path = os.path.join(base, name)
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(name)[1].lower()
            mime = {
                ".html": "text/html; charset=utf-8",
                ".md": "text/markdown; charset=utf-8",
                ".txt": "text/plain; charset=utf-8",
                ".json": "application/json",
            }.get(ext, "text/plain; charset=utf-8")
            return path, mime
    return None


def _store_text(cfg: dict, text: str, *, ext: str, hint: str = "body") -> dict:
    raw = (text or "")[:MAX_CONTENT_STORE].encode("utf-8", errors="replace")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    cid = f"{hint[:24]}_{digest}" if hint else digest
    safe_ext = ext if ext.startswith(".") else f".{ext}"
    path = os.path.join(_canvas_dir(cfg), f"{cid}{safe_ext}")
    if not os.path.isfile(path):
        with open(path, "wb") as f:
            f.write(raw)
    mime = {
        ".html": "text/html; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
    }.get(safe_ext, "text/plain; charset=utf-8")
    return {
        "id": cid,
        "src": f"/api/canvas/{cid}",
        "mime": mime,
        "bytes": len(raw),
    }


def _guess_kind_from_path(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}:
        return "image"
    if ext in {".mp4", ".webm", ".mov", ".m4v", ".ogg"}:
        return "video"
    if ext in {".md", ".markdown", ".txt", ".rst"}:
        return "markdown"
    if ext in {".html", ".htm"}:
        return "html"
    if ext in {".pdf", ".doc", ".docx", ".ppt", ".pptx"}:
        return "doc"
    return "file"


def _normalize_src(cfg: dict, kind: str, args: dict) -> dict[str, Any]:
    """Resolve src / content / path into a public-ready fragment."""
    out: dict[str, Any] = {}
    src = (args.get("src") or "").strip() if isinstance(args.get("src"), str) else ""
    content = args.get("content") if isinstance(args.get("content"), str) else None
    path_arg = (args.get("path") or "").strip() if isinstance(args.get("path"), str) else ""

    if path_arg:
        full = resolve_path(cfg, path_arg)
        if not os.path.exists(full):
            raise FileNotFoundError(f"path not found: {path_arg}")
        out["path"] = full
        if kind in ("image", "video", "file", "doc") or not src:
            # Prefer media API for images so sessions stay consistent
            if kind == "image" or (kind == "file" and _guess_kind_from_path(full) == "image"):
                try:
                    from . import media as _media
                    with open(full, "rb") as f:
                        raw = f.read()
                    part = _media.store_bytes(
                        cfg, raw, mime=None, hint=os.path.basename(full),
                    )
                    out["src"] = part["src"]
                    out["mime"] = part.get("mime")
                    out["bytes"] = part.get("bytes")
                    if kind == "file":
                        out["kind"] = "image"
                    return out
                except Exception:
                    pass
            if kind in ("markdown", "html") or _guess_kind_from_path(full) in ("markdown", "html"):
                with open(full, encoding="utf-8", errors="replace") as f:
                    text = f.read()
                guessed = _guess_kind_from_path(full)
                use_kind = kind if kind in ("markdown", "html") else guessed
                stored = _store_text(
                    cfg, text,
                    ext=".md" if use_kind == "markdown" else ".html",
                    hint=os.path.splitext(os.path.basename(full))[0] or "doc",
                )
                out.update(stored)
                if "content" not in out and len(text) <= MAX_INLINE_CHARS:
                    out["content"] = text
                if kind == "file":
                    out["kind"] = use_kind
                return out
            # Generic file — expose path hint (browser can't open file://)
            out["src"] = f"file:{full}"
            out["alt"] = os.path.basename(full)
            try:
                out["bytes"] = os.path.getsize(full)
            except OSError as e:
                raise FileNotFoundError(str(e)) from e
            return out

    if src:
        out["src"] = src
        return out

    if content is not None:
        if kind in ("html", "markdown", "doc") and len(content) > MAX_INLINE_CHARS:
            stored = _store_text(
                cfg, content,
                ext=".html" if kind == "html" else ".md",
                hint=kind,
            )
            out.update(stored)
            out["content"] = content[:MAX_INLINE_CHARS]
            out["content_truncated"] = True
        else:
            out["content"] = content
        return out

    return out


def _artifact_from_args(cfg: dict, args: dict, *, action: str) -> dict:
    kind = str(args.get("kind") or "markdown").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    aid = str(args.get("id") or "").strip() or uuid.uuid4().hex[:12]
    title = str(args.get("title") or "Canvas").strip()[:MAX_TITLE] or "Canvas"
    open_flag = args.get("open")
    if open_flag is None:
        open_flag = action != "close"
    frag = _normalize_src(cfg, kind, args)
    if frag.get("kind") in KINDS:
        kind = frag.pop("kind")
    art: dict[str, Any] = {
        "id": aid,
        "action": action,
        "kind": kind,
        "title": title,
        "open": bool(open_flag),
        "detachable": bool(args.get("detachable", True)),
        "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        **frag,
    }
    if kind == "url" and art.get("src") and action != "close":
        ok, note = probe_url_embeddable(str(art["src"]))
        art["embeddable"] = ok
        if note:
            art["embed_note"] = note
        if not ok and not note:
            art["embed_note"] = "This site blocks iframe embedding"
    if action != "close":
        if kind == "url" and not art.get("src"):
            raise ValueError("url kind requires src")
        if kind in ("image", "video") and not art.get("src"):
            raise ValueError(f"{kind} kind requires src or path")
        if kind in ("markdown", "html", "doc") and not (art.get("content") or art.get("src") or art.get("path")):
            raise ValueError(f"{kind} kind requires content, src, or path")
        if kind == "file" and not (art.get("src") or art.get("path")):
            raise ValueError("file kind requires src or path")
    return art


def handle_present(cfg: dict, args: dict) -> ToolResult:
    """Open or replace a canvas artifact in the chat side panel."""
    try:
        art = _artifact_from_args(cfg, args, action="present")
    except (ValueError, FileNotFoundError, OSError) as e:
        return ToolResult(False, str(e))
    store = _session_store(cfg)
    store[art["id"]] = art
    pub = public_part(art)
    return ToolResult(
        True,
        f"Canvas presented: {art['title']} ({art['kind']}, id={art['id']})",
        {"canvas": pub},
    )


def handle_update(cfg: dict, args: dict) -> ToolResult:
    """Patch an existing canvas artifact (same id)."""
    aid = str(args.get("id") or "").strip()
    if not aid:
        return ToolResult(False, "id is required for canvas_update")
    store = _session_store(cfg)
    prev = store.get(aid) or {"id": aid, "kind": args.get("kind") or "markdown", "title": "Canvas"}
    merged = {**prev, **{k: v for k, v in args.items() if v is not None}}
    merged["id"] = aid
    try:
        art = _artifact_from_args(cfg, merged, action="update")
    except (ValueError, FileNotFoundError, OSError) as e:
        return ToolResult(False, str(e))
    store[aid] = art
    pub = public_part(art)
    return ToolResult(
        True,
        f"Canvas updated: {art['title']} ({art['kind']}, id={art['id']})",
        {"canvas": pub},
    )


def handle_close(cfg: dict, args: dict) -> ToolResult:
    """Collapse the canvas panel (optionally clear one id)."""
    aid = str(args.get("id") or "").strip()
    store = _session_store(cfg)
    if aid and aid in store:
        art = {**store[aid], "action": "close", "open": False}
        store[aid] = art
    else:
        art = {
            "id": aid or "canvas",
            "action": "close",
            "kind": "markdown",
            "title": "Canvas",
            "open": False,
            "detachable": True,
        }
        if aid:
            store[aid] = art
    pub = public_part(art)
    return ToolResult(True, f"Canvas closed{f' ({aid})' if aid else ''}", {"canvas": pub})


def handle_list(cfg: dict, args: dict) -> ToolResult:
    """List artifacts currently tracked for this agent turn."""
    store = _session_store(cfg)
    items = [public_part(v) for v in store.values()]
    items = [x for x in items if x]
    return ToolResult(True, dump_json(items), {"canvases": items})
