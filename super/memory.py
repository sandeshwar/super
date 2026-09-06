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
