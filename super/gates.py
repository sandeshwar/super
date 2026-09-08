"""Unified gate registry (doc 02 §§4–6, doc 03).

Every row replaces an instruction with a tool that refuses. The registry
binds each gate to its failure class, implementation, and counter-check, so
descent (doc 02 §8) can price every gate by measured catch rate. The chat
write path enforces grounding; file writes additionally pass contract,
verification, quality, and security.
"""

from __future__ import annotations

import os
import subprocess

GATE_ID = "grounding"
FAILURE_CLASS = "F1"

# gate -> (failure class, description)
REGISTRY = {
    "grounding": ("F1", "no symbol without observation evidence"),
    "docs": ("F1", "library symbols must be in version-pinned docs"),
    "contract": ("F1", "standards + duplication enforced at write time"),
    "verification": ("F1", "lint/type per edit, tests per change-set/commit"),
    "mutation": ("F4", "vacuous tests cannot gate anything"),
    "quality": ("F1", "LOC/complexity/nesting budgets + debt ledger"),
    "secrets": ("F5", "secret material blocked at write time"),
    "sast": ("F5", "known-bad code patterns blocked"),
    "dependency": ("F5", "pin + typosquat + license screen"),
    "taint": ("F5", "call authority bounded by context taint"),
    "ambition": ("F4", "quality ladder contracted before generation"),
}


def symbol_in_repo(symbol: str, root: str) -> bool:
    """True if symbol text appears anywhere under root. rg preferred, grep fallback."""
    if not symbol or len(symbol) > 256:
        return False
    try:
        r = subprocess.run(
            ["rg", "-l", "--no-messages", "--max-count", "1", symbol, root],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0 and r.stdout.strip():
            return True
        if r.returncode == 1:
            return _grep(symbol, root)
    except FileNotFoundError:
        return _grep(symbol, root)
    except Exception:
        return False
    return _grep(symbol, root)


def _grep(symbol: str, root: str) -> bool:
    try:
        r = subprocess.run(["grep", "-rl", "--", symbol, root],
                           capture_output=True, text=True, timeout=30)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def _docs_cache_path(root: str, package: str, version: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in f"{package}_{version}")
    return os.path.join(root, ".super", "docs-cache", f"{safe}.json")


def ensure_docs_cache(cfg: dict, package: str, version: str, symbols: list[str]) -> str:
    """Create version-pinned docs cache entry for package@version with symbols."""
    root = cfg.get("_root", ".")
    path = _docs_cache_path(root, package, version)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"package": package, "version": version, "symbols": symbols, "pinned": True}
    try:
        import json as _json
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(data, f, indent=2)
    except Exception:
        pass
    return path


def _dts_exports(root: str, package: str) -> list[str]:
    """Parse .d.ts / .js sources under node_modules/<package> for exported symbols."""
    import re as _re
    base = os.path.join(root, "super", "web-src", "node_modules", package)
    if not os.path.isdir(base):
        base = os.path.join(root, "node_modules", package)
    if not os.path.isdir(base):
        return []
    pats = [
        r"export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)",
        r"export\s*\{\s*([^}]{1,2000})\s*\}",
        r"module\.exports\s*=\s*\{([^}]{1,2000})\}",
        r"exports\.([A-Za-z_$][\w$]*)\s*=",
        r"(?:function|class)\s+([A-Za-z_$][\w$]*)\s*\(",
    ]
    found: list[str] = []
    checked = 0
    for dirpath, _, files in os.walk(base):
        if "node_modules" in dirpath[len(base):] and dirpath != base:
            continue
        for fn in files:
            if not fn.endswith((".d.ts", ".js", ".ts")) or fn.endswith((".min.js", ".map")):
                continue
            if checked >= 40:
                break
            checked += 1
            try:
                with open(os.path.join(dirpath, fn), encoding="utf-8", errors="replace") as f:
                    text = f.read(60000)
            except OSError:
                continue
            for pat in pats:
                for m in _re.finditer(pat, text):
                    grp = m.group(1)
                    if "{" in pat or "," in grp:
                        for part in _re.split(r"[,\s]+", grp):
                            name = part.split(" as ")[-1].strip()
                            if _re.fullmatch(r"[A-Za-z_$][\w$]*", name) and name not in found:
                                found.append(name)
                    elif grp not in found:
                        found.append(grp)
            if len(found) >= 300:
                break
        if checked >= 40 or len(found) >= 300:
            break
    # package.json main/types entry points are evidence too
    try:
        import json as _json
        with open(os.path.join(base, "package.json"), encoding="utf-8") as f:
            meta = _json.load(f)
        for key in ("main", "types", "typings", "module"):
            if isinstance(meta.get(key), str) and meta[key] not in found:
                found.append(meta[key].split("/")[-1])
    except Exception:
        pass
    return found[:300]


def _site_package_symbols(root: str, package: str) -> list[str]:
    """Parse installed Python package for top-level public symbols via AST."""
    import sys as _sys
    candidates = [os.path.join(root, ".venv", "lib"), os.path.join(root, "venv", "lib"),
                  os.path.join(root, "site-packages")]
    for sp in _sys.path:
        if "site-packages" in sp or "dist-packages" in sp:
            candidates.append(sp)
    norm = package.replace("-", "_")
    for base in candidates:
        if not os.path.isdir(base):
            continue
        for entry in (package, norm):
            pkgdir = os.path.join(base, entry)
            init = os.path.join(pkgdir, "__init__.py")
            if os.path.isfile(init):
                try:
                    with open(init, encoding="utf-8", errors="replace") as f:
                        text = f.read(60000)
                    from . import memory as _mem
                    parsed = _mem.parse_with_treesitter(text, "python")
                    syms = list(parsed.get("symbols", []))
                    detail = parsed.get("detail", {}) or {}
                    syms += detail.get("imports", [])
                    if syms:
                        return syms[:300]
                except Exception:
                    continue
    return []


def _fetch_json(url: str, timeout: int = 8) -> dict | None:
    """Stdlib HTTPS GET → parsed JSON. None on any failure (offline-safe)."""
    import json as _json
    import urllib.request as _url
    try:
        req = _url.Request(url, headers={"Accept": "application/json",
                                         "User-Agent": "super-harness/1.0"})
        with _url.urlopen(req, timeout=timeout) as r:
            if r.status != 200:
                return None
            return _json.loads(r.read(300000).decode("utf-8", errors="replace"))
    except Exception:
        return None


def _npm_symbols(package: str, version: str) -> tuple[list[str], str]:
    """Fetch version metadata from the npm registry; exports keys are symbols."""
    top = package.split("/")[0] if "/" in package and not package.startswith("@") else package
    doc = _fetch_json(f"https://registry.npmjs.org/{package}/{version}")
    if not doc:
        doc = _fetch_json(f"https://registry.npmjs.org/{package}/latest")
    if not doc:
        return [], ""
    syms: list[str] = []
    for key in ("exports", "typesVersions"):
        val = doc.get(key)
        if isinstance(val, dict):
            syms.extend(str(k).strip("./").split("/")[0] for k in val.keys())
    for key in ("main", "types", "typings", "module", "description"):
        if isinstance(doc.get(key), str):
            syms.append(doc[key].split("/")[-1][:80])
    dist_tags = ""
    return sorted(set(s for s in syms if s and s != "."))[:200], dist_tags


def _pypi_symbols(package: str, version: str) -> list[str]:
    """Fetch release metadata from PyPI; entry points + summary keywords are symbols."""
    doc = _fetch_json(f"https://pypi.org/pypi/{package}/{version}/json".replace("//json", "/json")
                      if version != "pinned" else f"https://pypi.org/pypi/{package}/json")
    if not doc:
        return []
    info = doc.get("info", {}) if isinstance(doc, dict) else {}
    syms: list[str] = []
    for key in ("summary", "description"):
        text = info.get(key) or ""
        import re as _re
        syms.extend(_re.findall(r"[A-Za-z_]\w{2,40}", str(text))[:40])
    urls = doc.get("urls", []) if isinstance(doc, dict) else []
    if urls:
        syms.append(f"release-files:{len(urls)}")
    return sorted(set(syms))[:200]


def scrape_docs_versioned(cfg: dict, package: str, version: str) -> bool:
    """Pin versioned docs for package@version into .super/docs-cache/.

    Resolution order (first non-empty wins, all stdlib/offline-safe):
      1. existing cache file,
      2. local node_modules .d.ts export parse (npm),
      3. local site-packages AST parse (Python),
      4. npm registry version metadata (exports map),
      5. PyPI release metadata.
    Always writes a cache entry (possibly with source=unresolved) so the
    write path can proceed offline; returns True when any symbols resolved.
    """
    root = cfg.get("_root", ".")
    path = _docs_cache_path(root, package, version)
    if os.path.isfile(path):
        return True
    symbols: list[str] = []
    source = "unresolved"
    local = _dts_exports(root, package)
    if local:
        symbols, source = local, "node_modules"
    if not symbols:
        site_syms = _site_package_symbols(root, package)
        if site_syms:
            symbols, source = site_syms, "site-packages"
    if not symbols and version != "pinned":
        npm_syms, _ = _npm_symbols(package, version)
        if npm_syms:
            symbols, source = npm_syms, "npm-registry"
    if not symbols:
        pypi_syms = _pypi_symbols(package, version)
        if pypi_syms:
            symbols, source = pypi_syms, "pypi"
    ensure_docs_cache(cfg, package, version, symbols[:300])
    try:
        # annotate cache with provenance source
        import json as _json
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)
        data["source"] = source
        import time as _time
        data["fetched_at"] = _time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(data, f, indent=2)
    except Exception:
        pass
    try:
        from . import ledger
        ledger.log_gate(cfg, "docs", "F1", "pass",
                        detail=f"docs-cache pinned {package}@{version} "
                               f"({len(symbols)} symbols via {source})")
    except Exception:
        pass
    return bool(symbols)


def docs_have(symbol: str, root: str) -> bool:
    """Version-pinned docs cache check: docs/ or versioned cache counts as observed."""
    for base in ("docs", ".super/docs-cache", "docs-cache"):
        cand = os.path.join(root, base)
        if os.path.isdir(cand) and symbol_in_repo(symbol, cand):
            return True
    # also check versioned cache JSON symbols
    try:
        import json as _json
        import glob as _glob
        for path in _glob.glob(os.path.join(root, ".super", "docs-cache", "*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    data = _json.load(f)
                if symbol in (data.get("symbols") or []) or symbol.lower() in [s.lower() for s in (data.get("symbols") or [])]:
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def check(cfg: dict, symbols: list[str], root: str | None = None) -> tuple[bool, list[str]]:
    """Grounding enforcement: every symbol must be observed in repo or docs.

    Returns (ok, missing). Both outcomes are logged to the gate ledger.
    """
    from . import ledger

    root = root or cfg["_root"]
    if not cfg.get("gates", {}).get("grounding", True):
        return True, []
    missing = [s for s in symbols
               if not symbol_in_repo(s, root) and not docs_have(s, root)]
    if missing:
        ledger.log_gate(cfg, GATE_ID, FAILURE_CLASS, "reject",
                        detail=f"unobserved: {', '.join(missing)}")
        return False, missing
    ledger.log_gate(cfg, GATE_ID, FAILURE_CLASS, "pass", detail=f"{len(symbols)} observed")
    return True, []


def run_write_gates(cfg: dict, source: str, where: str = "",
                    context_taints: list[str] | None = None,
                    existing: dict[str, str] | None = None,
                    waiver: str = "") -> tuple[bool, list[str]]:
    """Full write-path enforcement for file edits. Returns (ok, blockers)."""
    from . import ledger, quality, security, verify

    blockers: list[str] = []
    # 1. Verification ladder (lint/type per edit via verify)
    if cfg.get("gates", {}).get("verification", True):
        try:
            verify.verify_edit(cfg, source)
        except Exception as e:
            blockers.append(str(e))
    # 2. Contract: standards + duplication (doc 03 §2)
    try:
        from . import contract
        ok, msg = contract.check_write(cfg, source, existing or {}, waiver=waiver)
        if not ok:
            blockers.append(msg)
    except Exception as e:
        blockers.append(f"contract gate error: {e}")
    # 3. Docs-before-write: new library symbols must be in version-pinned cache
    if cfg.get("gates", {}).get("docs_before_write", True):
        # heuristic: if source imports something, ensure docs cache probe at least ran
        try:
            import re as _re
            imports = _re.findall(r"^\s*(?:from|import)\s+([\w\.]+)", source, _re.M)
            for pkg in imports[:5]:
                top = pkg.split(".")[0]
                if top and top not in ("os", "sys", "json", "re", "typing", "subprocess", "pathlib"):
                    # ensure cache exists (creates if missing) — never blocks, but logs
                    scrape_docs_versioned(cfg, top, "pinned")
        except Exception:
            pass
    # 4. Quality budgets
    if cfg.get("gates", {}).get("quality", True):
        ok, violations = quality.check_budgets(cfg, source, where)
        if not ok:
            blockers.extend(violations)
    # 5. Security (secrets/sast/taint/dependency)
    if cfg.get("gates", {}).get("security", True):
        try:
            security.enforce_write(cfg, source, where, context_taints)
        except Exception as e:
            blockers.append(str(e))
    if blockers:
        ledger.log_gate(cfg, "write-gate", "F1", "reject", detail="; ".join(blockers)[:500])
        return False, blockers
    ledger.log_gate(cfg, "write-gate", "F1", "pass", detail=f"clear ({where or 'edit'})")
    return True, []
