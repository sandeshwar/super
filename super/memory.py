"""Typed memory + claim store + per-step context compiler (doc 02 §3).

Memory is a cache, not ground truth: every claim carries source,
verification state, validity interval, and taint. Disconfirming execution
retires a claim the way a new docs version supersedes it (Event Evolution
Graph supersession queries). The per-step compiler assembles only the
load-bearing claims for the current leaf, keeping small contexts viable.
"""

from __future__ import annotations

import re
import time
from typing import Any

from . import store
from .errors import StoreError

_FILE = "claims.json"
_SCHEMA = 2
TRUSTED_SOURCES = ("local-exec", "pinned-docs", "test", "human", "prove")
_VER_STATES = ("unverified", "verified", "human", "retired", "superseded")
# Tool results worth auto-caching as unverified claims (query + snippet).
_AUTO_TOOLS = {
    "duckduckgo_search": "web-search",
    "wikipedia": "wikipedia",
    "arxiv": "arxiv",
}


def _path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{_FILE}"


def _blank() -> dict:
    return {"schema": _SCHEMA, "next_id": 1, "claims": []}


def _migrate(data: dict) -> dict:
    """Ensure stable claim ids + next_id (schema 2)."""
    if not isinstance(data, dict):
        data = _blank()
    claims = data.get("claims")
    if not isinstance(claims, list):
        claims = []
        data["claims"] = claims
    next_id = int(data.get("next_id") or 1)
    for c in claims:
        if not isinstance(c, dict):
            continue
        if "id" not in c:
            c["id"] = next_id
            next_id += 1
        else:
            try:
                next_id = max(next_id, int(c["id"]) + 1)
            except (TypeError, ValueError):
                c["id"] = next_id
                next_id += 1
    data["next_id"] = next_id
    data["schema"] = max(int(data.get("schema") or 1), _SCHEMA)
    return data


def _load(cfg: dict) -> dict:
    return _migrate(store.load_json(_path(cfg), _blank()))


def _save(cfg: dict, data: dict) -> None:
    store.save_json(_path(cfg), data)
    _sync_sqlite(cfg, data)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9][a-z0-9\-_.]{1,}", (text or "").lower()))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


def _find_dup(claims: list[dict], text: str, *, min_jaccard: float = 0.72) -> dict | None:
    nt = _norm(text)
    tt = _tokens(text)
    for c in claims:
        if c.get("verification") in ("superseded", "retired"):
            continue
        ct = c.get("text") or ""
        if _norm(ct) == nt:
            return c
        if _jaccard(tt, _tokens(ct)) >= min_jaccard:
            return c
    return None


def _resolve_index(data: dict, index: int | None = None, claim_id: int | None = None) -> int:
    claims = data["claims"]
    if claim_id is not None:
        for i, c in enumerate(claims):
            try:
                if int(c.get("id")) == int(claim_id):
                    return i
            except (TypeError, ValueError):
                continue
        raise StoreError(f"no claim with id {claim_id}")
    if index is None:
        raise StoreError("index or id required")
    if index < 0 or index >= len(claims):
        raise StoreError(f"no claim at index {index}")
    return index


def remember(cfg: dict, text: str, source: str = "local-exec",
             taint: str = "local-exec", valid_until: str = "",
             task_id: str = "", verification: str = "unverified",
             *, dedupe: bool = True) -> dict:
    """Store one claim. Text is mandatory; sources are recorded verbatim.

    When dedupe=True, near-duplicate live claims are returned as-is (or
    upgraded verification) instead of inserting another row.
    """
    text = (text or "").strip()
    if not text:
        raise StoreError("claim text must be non-empty")
    if verification not in _VER_STATES:
        raise StoreError(f"invalid verification state {verification}")
    data = _load(cfg)
    if dedupe:
        dup = _find_dup(data["claims"], text)
        if dup is not None:
            rank = {"unverified": 0, "verified": 1, "human": 2}
            if rank.get(verification, 0) > rank.get(str(dup.get("verification")), 0):
                dup["verification"] = verification
            if task_id and not dup.get("task_id"):
                dup["task_id"] = task_id
            if source and source != dup.get("source"):
                dup["source"] = source
            _save(cfg, data)
            return dup
    cid = int(data.get("next_id") or 1)
    claim = {
        "id": cid,
        "text": text[:2000],
        "source": source,
        "verification": verification,
        "valid_from": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "valid_until": valid_until,
        "taint": taint,
        "task_id": str(task_id or ""),
        "superseded_by": "",
    }
    data["claims"].append(claim)
    data["next_id"] = cid + 1
    _save(cfg, data)
    return claim


def confirm(cfg: dict, index: int | None = None, verification: str = "verified",
            *, claim_id: int | None = None) -> dict:
    if verification not in _VER_STATES:
        raise StoreError(f"invalid verification state {verification}")
    data = _load(cfg)
    i = _resolve_index(data, index, claim_id)
    data["claims"][i]["verification"] = verification
    _save(cfg, data)
    return data["claims"][i]


def supersede(cfg: dict, index: int | None = None, replacement: str = "",
              *, claim_id: int | None = None) -> dict:
    """Retire claim, replaced by `replacement` (EEG supersession).

    If `replacement` is non-empty, also inserts it as a new live claim
    (inherits task_id; verification=human when source was human-facing).
    """
    data = _load(cfg)
    i = _resolve_index(data, index, claim_id)
    old = data["claims"][i]
    old_ver = str(old.get("verification") or "")
    old_source = str(old.get("source") or "human")
    old_taint = str(old.get("taint") or "local-exec")
    old_task = str(old.get("task_id") or "")
    old_text = str(old.get("text") or "")
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    repl = (replacement or "").strip()
    data["claims"][i]["valid_until"] = now
    data["claims"][i]["superseded_by"] = repl[:500]
    data["claims"][i]["verification"] = "superseded"
    _save(cfg, data)
    if repl and _norm(repl) != _norm(old_text):
        remember(
            cfg, repl,
            source=old_source,
            taint=old_taint,
            task_id=old_task,
            verification="human" if old_ver in ("human", "verified") else "unverified",
            dedupe=True,
        )
    return data["claims"][i]


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


def list_claims(cfg: dict, *, include_dead: bool = False, limit: int = 200,
                offset: int = 0) -> dict:
    data = _load(cfg)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    claims = data["claims"] if include_dead else _live(data["claims"], now)
    claims = list(reversed(claims))
    total = len(claims)
    slice_ = claims[max(0, offset): max(0, offset) + max(1, min(limit, 500))]
    return {"claims": slice_, "total": total, "offset": offset, "limit": limit}


def search(cfg: dict, query: str = "", *, task_id: str = "", taint: str = "",
           limit: int = 20, include_dead: bool = False) -> list[dict]:
    """Ranked claim retrieval: token overlap + substring + verification boost."""
    data = _load(cfg)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    pool = data["claims"] if include_dead else _live(data["claims"], now)
    if task_id:
        pool = [c for c in pool if c.get("task_id") == task_id]
    if taint:
        pool = [c for c in pool if c.get("taint") == taint]
    q = (query or "").strip()
    if not q:
        def rank(c: dict) -> tuple:
            ver = {"verified": 0, "human": 1, "unverified": 2}.get(c.get("verification", "unverified"), 3)
            trusted = 0 if c.get("source") in TRUSTED_SOURCES else 1
            return (ver, trusted, -int(c.get("id") or 0))
        return sorted(pool, key=rank)[:limit]

    qt = _tokens(q)
    ql = q.lower()
    scored: list[tuple[float, dict]] = []
    for c in pool:
        text = c.get("text") or ""
        ct = _tokens(text)
        overlap = (len(qt & ct) / len(qt)) if qt else 0.0
        if ql in text.lower():
            overlap = max(overlap, 0.65)
        if overlap <= 0 and qt and (qt & ct):
            overlap = 0.25 * (len(qt & ct) / len(qt))
        if overlap <= 0:
            continue
        ver_boost = {"verified": 0.35, "human": 0.3, "unverified": 0.05}.get(
            c.get("verification", "unverified"), 0.0)
        trusted = 0.1 if c.get("source") in TRUSTED_SOURCES else 0.0
        scored.append((overlap + ver_boost + trusted, c))
    scored.sort(key=lambda x: (-x[0], -int(x[1].get("id") or 0)))
    return [c for _, c in scored[:limit]]


def compile_context(cfg: dict, task: dict | None, limit: int = 12) -> str:
    """Per-step working set: verified-first live claims scoped to the leaf."""
    data = _load(cfg)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    live = _live(data["claims"], now)
    tid = (task or {}).get("id", "")
    title = (task or {}).get("title") or ""

    def rank(c: dict) -> tuple:
        scoped = 0 if (tid and c.get("task_id") == tid) else 1
        ver = {"verified": 0, "human": 1, "unverified": 2}.get(c.get("verification", "unverified"), 3)
        trusted = 0 if c.get("source") in TRUSTED_SOURCES else 1
        return (scoped, ver, trusted)

    if title:
        hits = search(cfg, title, task_id=str(tid or ""), limit=limit)
        if hits:
            seen = {int(c.get("id") or -1) for c in hits}
            rest = [c for c in sorted(live, key=rank) if int(c.get("id") or -1) not in seen]
            live = hits + rest
        else:
            live.sort(key=rank)
    else:
        live.sort(key=rank)

    lines = []
    for c in live[:limit]:
        lines.append(
            f"- [{c.get('verification')}/{c.get('taint')}] {c.get('text')} "
            f"(src: {c.get('source')}, id: {c.get('id')})"
        )
    if not lines:
        return "(no stored claims — grounded in repo only)"
    return "\n".join(lines)


def retire_disconfirmed(cfg: dict, text_fragment: str) -> int:
    """Retire claims disconfirmed by execution. Returns count retired."""
    data = _load(cfg)
    n = 0
    frag = (text_fragment or "").lower()
    if not frag:
        return 0
    for c in data["claims"]:
        if frag in c.get("text", "").lower() and c.get("verification") != "retired":
            c["verification"] = "retired"
            n += 1
    if n:
        _save(cfg, data)
    return n


def remember_from_proof(cfg: dict, node: dict) -> dict | None:
    """Auto-store a verified claim when a task is proven."""
    if not node:
        return None
    tid = str(node.get("id") or "")
    title = (node.get("title") or "").strip() or f"task {tid}"
    proof = (node.get("proof") or "").strip()
    text = f"Done: {title}" + (f" — proof: {proof}" if proof else "")
    return remember(
        cfg, text,
        source="prove",
        taint="local-exec",
        task_id=tid,
        verification="verified",
        dedupe=True,
    )


def maybe_auto_from_tool(cfg: dict, name: str, arguments: dict, result: Any) -> dict | None:
    """Cache high-signal tool outcomes as unverified claims (deduped)."""
    src = _AUTO_TOOLS.get(name)
    if not src:
        return None
    ok = getattr(result, "ok", None)
    content = getattr(result, "content", None)
    if ok is False or not content:
        return None
    text = str(content).strip()
    if len(text) < 40:
        return None
    args = arguments if isinstance(arguments, dict) else {}
    q = str(args.get("query") or args.get("input") or args.get("q") or "").strip()
    snippet = re.sub(r"\s+", " ", text)[:420]
    claim_text = f"{q}: {snippet}" if q else snippet
    taint = "web" if src in ("web-search", "wikipedia", "arxiv") else "tool"
    try:
        return remember(
            cfg, claim_text,
            source=src,
            taint=taint,
            verification="unverified",
            dedupe=True,
        )
    except StoreError:
        return None


# ── SQLite graph mirror (optional, stdlib sqlite3) ──
def _sqlite_path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/claims.db"


def _sync_sqlite(cfg: dict, data: dict | None = None) -> bool:
    """Always mirror JSON → sqlite after mutations. Best-effort."""
    try:
        import os as _os
        import sqlite3
        path = _sqlite_path(cfg)
        _os.makedirs(_os.path.dirname(_os.path.abspath(path)) or ".", exist_ok=True)
        if data is None:
            data = _load(cfg)
        con = sqlite3.connect(path)
        cur = con.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS claims ("
            "id INTEGER PRIMARY KEY, text TEXT, source TEXT, verification TEXT, "
            "taint TEXT, task_id TEXT, valid_from TEXT, valid_until TEXT, superseded_by TEXT)"
        )
        try:
            cur.execute("ALTER TABLE claims ADD COLUMN superseded_by TEXT")
        except sqlite3.OperationalError:
            pass
        cur.execute("DELETE FROM claims")
        for c in data.get("claims") or []:
            try:
                cid = int(c.get("id"))
            except (TypeError, ValueError):
                continue
            cur.execute(
                "INSERT INTO claims (id, text, source, verification, taint, task_id, "
                "valid_from, valid_until, superseded_by) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    cid,
                    c.get("text", ""),
                    c.get("source", ""),
                    c.get("verification", ""),
                    c.get("taint", ""),
                    c.get("task_id", ""),
                    c.get("valid_from", ""),
                    c.get("valid_until", ""),
                    c.get("superseded_by", ""),
                ),
            )
        con.commit()
        con.close()
        return True
    except Exception:
        return False


def _ensure_sqlite(cfg: dict) -> bool:
    return _sync_sqlite(cfg)


def query_graph(cfg: dict, task_id: str = "", taint: str = "", limit: int = 20) -> list[dict]:
    """Graph query: live claims filtered by task_id/taint, ordered by trust."""
    return search(cfg, "", task_id=task_id, taint=taint, limit=limit)


_TS_QUERIES = {
    "python": "(function_definition name: (identifier) @fn) (class_definition name: (identifier) @cls)",
    "javascript": "(function_declaration name: (identifier) @fn) (class_declaration name: (identifier) @cls)",
    "typescript": "(function_declaration name: (identifier) @fn) (class_declaration name: (identifier) @cls)",
}


def _ts_parse(source: str, language: str) -> dict | None:
    """Real tree-sitter parse when the package + grammar are installed.

    Supports both the new (0.21+: Parser(Language(...))) and old
    (Parser(); set_language()) APIs, plus optional per-language grammar
    packages (tree_sitter_python, tree_sitter_javascript, ...). Stdlib-only
    installs return None so callers fall through to the AST/regex parsers.
    """
    try:
        import importlib as _il
        ts = _il.import_module("tree_sitter")
    except ImportError:
        return None
    lang = (language or "python").lower()
    if lang == "py":
        lang = "python"
    if lang == "js":
        lang = "javascript"
    grammar_mod = {
        "python": "tree_sitter_python",
        "javascript": "tree_sitter_javascript",
        "typescript": "tree_sitter_typescript",
        "go": "tree_sitter_go",
        "rust": "tree_sitter_rust",
    }.get(lang)
    try:
        Language = getattr(ts, "Language", None)
        Parser = getattr(ts, "Parser", None)
        Query = getattr(ts, "Query", None)
        if Language is None or Parser is None:
            return None
        language_obj = None
        if grammar_mod is not None:
            try:
                gmod = _il.import_module(grammar_mod)
                if hasattr(gmod, "language"):
                    language_obj = gmod.language()
            except ImportError:
                language_obj = None
        if language_obj is None:
            return None  # grammar not installed — caller uses fallback
        # New API: Parser(Language(obj)); Old API: Parser(); set_language(obj)
        try:
            parser = Parser(Language(language_obj))
        except Exception:
            parser = Parser()
            parser.set_language(language_obj)
        tree = parser.parse(bytes(source, "utf-8", errors="replace"))
        root = tree.root_node
        symbols: list[str] = []
        try:
            if Query is not None:
                q = Query(language_obj, _TS_QUERIES.get(lang, _TS_QUERIES["python"]))
                for _node, capture in q.captures(root):
                    if isinstance(capture, str) and capture in ("fn", "cls"):
                        symbols.append(_node.text.decode("utf-8", errors="replace")[:120])
                    elif hasattr(_node, "text"):
                        symbols.append(_node.text.decode("utf-8", errors="replace")[:120])
        except Exception:
            pass
        if not symbols:
            # Walk for named definition nodes as a query-independent path.
            def _walk(n):
                if n.type in ("function_definition", "function_declaration",
                              "class_definition", "class_declaration",
                              "method_definition"):
                    for ch in n.children:
                        if ch.type == "identifier":
                            symbols.append(ch.text.decode("utf-8", errors="replace")[:120])
                            break
                for ch in n.children:
                    _walk(ch)
            try:
                _walk(root)
            except RecursionError:
                pass
        return {
            "language": language,
            "symbols": symbols[:100],
            "engine": "tree-sitter",
            "tree": root.sexp()[:4000],
            "node_count": root.descendant_count if hasattr(root, "descendant_count") else 0,
        }
    except Exception:
        return None


def _parse_python_detail(source: str) -> dict:
    """Full AST parse: qualified names, imports, decorators, docstrings."""
    import ast as _ast
    tree = _ast.parse(source)
    functions: list[str] = []
    classes: list[str] = []
    imports: list[str] = []
    decorated = 0
    docstrings = 0
    for node in _ast.walk(tree):
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            functions.append(node.name)
            if node.decorator_list:
                decorated += 1
            if _ast.get_docstring(node):
                docstrings += 1
        elif isinstance(node, _ast.ClassDef):
            classes.append(node.name)
            if node.decorator_list:
                decorated += 1
            if _ast.get_docstring(node):
                docstrings += 1
        elif isinstance(node, _ast.Import):
            imports.extend(a.asname or a.name.split(".")[0] for a in node.names)
        elif isinstance(node, _ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])
    # qualified Class.method names
    qualified: list[str] = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    qualified.append(f"{node.name}.{sub.name}")
    symbols = classes + qualified + [f for f in functions if "." not in f]
    return {
        "symbols": symbols[:100],
        "detail": {
            "functions": functions[:100],
            "classes": classes[:100],
            "methods": qualified[:100],
            "imports": sorted(set(imports))[:50],
            "decorated": decorated,
            "docstrings": docstrings,
        },
        "tree": _ast.dump(tree)[:4000],
        "node_count": sum(1 for _ in _ast.walk(tree)),
    }


_JS_PATTERNS = [
    r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)",
    r"(?:export\s+)?class\s+([A-Za-z_$][\w$]*)",
    r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(",
    r"(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
    r"([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{",  # methods
    r"export\s+(?:const|function|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)",
    r"interface\s+([A-Za-z_$][\w$]*)",
    r"type\s+([A-Za-z_$][\w$]*)\s*=",
]

_OTHER_PATTERNS = {
    "go": [r"func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)", r"type\s+([A-Za-z_]\w*)\s+struct"],
    "rust": [r"fn\s+([A-Za-z_]\w*)", r"(?:struct|enum|trait)\s+([A-Za-z_]\w*)"],
    "java": [r"(?:public|private|protected)?\s*(?:static\s+)?(?:class|interface|enum)\s+([A-Za-z_]\w*)",
             r"(?:public|private|protected)?\s*[\w<>\[\]]+\s+([A-Za-z_]\w*)\s*\("],
    "ruby": [r"def\s+([A-Za-z_]\w*[?!]?)", r"class\s+([A-Za-z_]\w*)"],
}


def _parse_regex_detail(source: str, language: str) -> dict:
    import re as _re
    pats = _JS_PATTERNS if language in ("javascript", "typescript", "js", "ts", "jsx", "tsx") \
        else _OTHER_PATTERNS.get(language, [r"(?:def|function|class)\s+([A-Za-z_]\w*)"])
    seen: list[str] = []
    for pat in pats:
        for m in _re.finditer(pat, source):
            name = m.group(1)
            if name not in ("if", "for", "while", "switch", "catch") and name not in seen:
                seen.append(name)
    imports: list[str] = []
    for pat in (r"^\s*import\s+(?:.*?\s+from\s+)?['\"]([^'\"]+)['\"]",
                r"require\(\s*['\"]([^'\"]+)['\"]\s*\)",
                r"^\s*(?:from|import)\s+([\w\.]+)"):
        imports.extend(_re.findall(pat, source, _re.M))
    return {
        "symbols": seen[:100],
        "detail": {"imports": sorted(set(imports))[:50]},
        "tree": "",
        "node_count": len(seen),
    }


def parse_with_treesitter(source: str, language: str = "python") -> dict:
    """Parse `source` and extract defined symbols.

    Prefers real tree-sitter (query + full sexp tree) when the package and
    grammar are installed; otherwise uses a per-language parser — AST with
    qualified names/imports for Python, export-aware regexes for JS/TS and
    other languages. Never raises; always returns
    {language, symbols, engine, ...}.
    """
    lang = (language or "python").lower()
    if lang in ("py", "js", "ts"):
        lang = {"py": "python", "js": "javascript", "ts": "typescript"}[lang]
    hit = _ts_parse(source, lang)
    if hit is not None:
        return hit
    if lang == "python":
        try:
            detail = _parse_python_detail(source)
            return {"language": language, "symbols": detail["symbols"],
                    "engine": "ast", **{k: v for k, v in detail.items() if k != "symbols"}}
        except SyntaxError as e:
            return {"language": language, "symbols": [], "engine": "error",
                    "error": f"syntax error: {e}"}
        except Exception as e:
            return {"language": language, "symbols": [], "engine": "error", "error": str(e)}
    try:
        detail = _parse_regex_detail(source, lang)
        engine = "regex-ts" if lang in ("javascript", "typescript", "jsx", "tsx") else "regex"
        return {"language": language, "symbols": detail["symbols"],
                "engine": engine, **{k: v for k, v in detail.items() if k != "symbols"}}
    except Exception as e:
        return {"language": language, "symbols": [], "engine": "error", "error": str(e)}
