"""Typed memory + claim store + per-step context compiler (doc 02 §3).

Memory is a cache, not ground truth: every claim carries source,
verification state, validity interval, and taint. Disconfirming execution
retires a claim the way a new docs version supersedes it (Event Evolution
Graph supersession queries). The per-step compiler assembles only the
load-bearing claims for the current leaf, keeping small contexts viable.
"""

from __future__ import annotations

import time

from . import store
from .errors import StoreError

_FILE = "claims.json"
_SCHEMA = 1
TRUSTED_SOURCES = ("local-exec", "pinned-docs", "test", "human")


def _path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{_FILE}"


def _blank() -> dict:
    return {"schema": _SCHEMA, "claims": []}


def remember(cfg: dict, text: str, source: str = "local-exec",
             taint: str = "local-exec", valid_until: str = "",
             task_id: str = "", verification: str = "unverified") -> dict:
    """Store one claim. Text is mandatory; sources are recorded verbatim."""
    text = (text or "").strip()
    if not text:
        raise StoreError("claim text must be non-empty")
    if verification not in ("unverified", "verified", "human", "retired", "superseded"):
        raise StoreError(f"invalid verification state {verification}")
    claim = {
        "text": text[:2000],
        "source": source,
        "verification": verification,
        "valid_from": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "valid_until": valid_until,
        "taint": taint,
        "task_id": task_id,
        "superseded_by": "",
    }
    data = store.load_json(_path(cfg), _blank())
    data["claims"].append(claim)
    store.save_json(_path(cfg), data)
    return claim


def confirm(cfg: dict, index: int, verification: str = "verified") -> dict:
    data = store.load_json(_path(cfg), _blank())
    if index < 0 or index >= len(data["claims"]):
        raise StoreError(f"no claim at index {index}")
    data["claims"][index]["verification"] = verification
    store.save_json(_path(cfg), data)
    return data["claims"][index]


def supersede(cfg: dict, index: int, replacement: str) -> dict:
    """Retire claim `index`, replaced by `replacement` (EEG supersession)."""
    data = store.load_json(_path(cfg), _blank())
    if index < 0 or index >= len(data["claims"]):
        raise StoreError(f"no claim at index {index}")
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    data["claims"][index]["valid_until"] = now
    data["claims"][index]["superseded_by"] = replacement[:500]
    data["claims"][index]["verification"] = "superseded"
    store.save_json(_path(cfg), data)
    return data["claims"][index]


def _live(claims: list, now: str) -> list:
    out = []
    for c in claims:
        if c.get("verification") == "superseded":
            continue
        if c.get("verification") == "retired":
            continue
        vu = c.get("valid_until", "")
        if vu and now > vu:
            continue
        out.append(c)
    return out


def compile_context(cfg: dict, task: dict | None, limit: int = 12) -> str:
    """Per-step working set: verified-first live claims scoped to the leaf.

    Ordering: task-scoped verified > verified > human > unverified. Taint and
    source ride along so dispatch can bound authority.
    """
    data = store.load_json(_path(cfg), _blank())
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    live = _live(data["claims"], now)
    tid = (task or {}).get("id", "")

    def rank(c: dict) -> tuple:
        scoped = 0 if (tid and c.get("task_id") == tid) else 1
        ver = {"verified": 0, "human": 1, "unverified": 2}.get(c.get("verification", "unverified"), 3)
        trusted = 0 if c.get("source") in TRUSTED_SOURCES else 1
        return (scoped, ver, trusted)

    live.sort(key=rank)
    lines = []
    for c in live[:limit]:
        lines.append(f"- [{c.get('verification')}/{c.get('taint')}] {c.get('text')} (src: {c.get('source')})")
    if not lines:
        return "(no stored claims — grounded in repo only)"
    return "\n".join(lines)


def retire_disconfirmed(cfg: dict, text_fragment: str) -> int:
    """Retire claims disconfirmed by execution. Returns count retired."""
    data = store.load_json(_path(cfg), _blank())
    n = 0
    for c in data["claims"]:
        if text_fragment.lower() in c.get("text", "").lower() and c.get("verification") != "retired":
            c["verification"] = "retired"
            n += 1
    if n:
        store.save_json(_path(cfg), data)
    return n


# ── SQLite graph mirror (optional, stdlib sqlite3) ──
def _sqlite_path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/claims.db"


def _ensure_sqlite(cfg: dict):
    """Mirror JSON claims into sqlite for graph queries. Best-effort, no hard dep."""
    try:
        import sqlite3
        import os as _os
        path = _sqlite_path(cfg)
        _os.makedirs(_os.path.dirname(_os.path.abspath(path)), exist_ok=True)
        con = sqlite3.connect(path)
        cur = con.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS claims (id INTEGER PRIMARY KEY, text TEXT, source TEXT, verification TEXT, taint TEXT, task_id TEXT, valid_from TEXT, valid_until TEXT)")
        # sync from JSON if sqlite empty
        cur.execute("SELECT COUNT(*) FROM claims")
        if cur.fetchone()[0] == 0:
            data = store.load_json(_path(cfg), _blank())
            for i, c in enumerate(data["claims"]):
                cur.execute("INSERT INTO claims (id, text, source, verification, taint, task_id, valid_from, valid_until) VALUES (?,?,?,?,?,?,?,?)",
                            (i, c.get("text",""), c.get("source",""), c.get("verification",""), c.get("taint",""), c.get("task_id",""), c.get("valid_from",""), c.get("valid_until","")))
            con.commit()
        con.close()
        return True
    except Exception:
        return False


def query_graph(cfg: dict, task_id: str = "", taint: str = "", limit: int = 20) -> list[dict]:
    """Graph query: live claims filtered by task_id/taint, ordered by trust. Uses sqlite if available else JSON."""
    try:
        import sqlite3
        if _ensure_sqlite(cfg):
            con = sqlite3.connect(_sqlite_path(cfg))
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            q = "SELECT * FROM claims WHERE verification NOT IN ('superseded','retired') "
            params: list = []
            if task_id:
                q += "AND task_id=? "
                params.append(task_id)
            if taint:
                q += "AND taint=? "
                params.append(taint)
            q += "ORDER BY CASE verification WHEN 'verified' THEN 0 WHEN 'human' THEN 1 ELSE 2 END, task_id DESC LIMIT ?"
            params.append(limit)
            cur.execute(q, params)
            rows = [dict(r) for r in cur.fetchall()]
            con.close()
            return rows
    except Exception:
        pass
    # fallback to JSON scan
    data = store.load_json(_path(cfg), _blank())
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    live = _live(data["claims"], now)
    out = [c for c in live if (not task_id or c.get("task_id")==task_id) and (not taint or c.get("taint")==taint)]
    # rank as in compile_context
    def rank(c: dict) -> tuple:
        scoped = 0 if (task_id and c.get("task_id")==task_id) else 1
        ver = {"verified":0,"human":1,"unverified":2}.get(c.get("verification","unverified"),3)
        trusted = 0 if c.get("source") in TRUSTED_SOURCES else 1
        return (scoped, ver, trusted)
    out.sort(key=rank)
    return out[:limit]


def parse_with_treesitter(source: str, language: str = "python") -> dict:
    """Tree-sitter stub: try tree-sitter, fallback to ast. Returns {type, symbols, tree}."""
    # Try real tree-sitter if installed
    try:
        import importlib as _il
        ts = _il.import_module("tree_sitter")
        # placeholder — if available, parse and extract func names via TS query
        # Fallback for now: use ast
        raise ImportError
    except Exception:
        pass
    # Fallback: ast for python, regex for others
    symbols: list[str] = []
    try:
        import ast as _ast
        import re as _re
        if language in ("py","python"):
            tree = _ast.parse(source)
            for n in _ast.walk(tree):
                if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                    symbols.append(n.name)
        else:
            symbols = _re.findall(r"[A-Za-z_]\w*", source)[:50]
        return {"language": language, "symbols": symbols[:50], "engine": "ast-fallback"}
    except Exception as e:
        return {"language": language, "symbols": [], "engine": "error", "error": str(e)}
