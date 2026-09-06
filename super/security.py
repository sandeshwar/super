"""Security substrate (doc 02 §6, doc 03 §§6/8).

Capability tokens bound every tool call; taint labels mark all fetched
content (untrusted / pinned-docs / local-exec) with explicit
declassification; a call's authority is bounded by the taint of the context
that produced it — enforced in dispatch, never by asking the model to "be
careful". Dedicated sink log joins every network-out and secret-read to its
taint. Dependency introduction requires pin + CVE screen + license check +
typosquat screen + SBOM update.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time

from . import ledger, store
from .errors import SecurityViolation

TAINTS = ("untrusted", "pinned-docs", "local-exec")
# Authority rank: a call may only use context at or below its capability.
_RANK = {"untrusted": 0, "pinned-docs": 1, "local-exec": 2}

SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9]{16,}", "api-key"),
    (r"xox[bap]-[A-Za-z0-9\-]{8,}", "slack-token"),
    (r"gh[pousr]_[A-Za-z0-9]{20,}", "github-token"),
    (r"AKIA[0-9A-Z]{16}", "aws-key"),
    (r"(?i)password\s*[:=]\s*['\"][^'\"]{4,}['\"]", "password"),
    (r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----", "private-key"),
    (r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{16,}", "bearer-token"),
]

SAST_RULES = [
    (r"\beval\s*\(", "code-injection: eval()"),
    (r"\bexec\s*\(", "code-injection: exec()"),
    (r"subprocess\.(?:call|run|Popen)\s*\([^)]*shell\s*=\s*True", "shell-injection: shell=True"),
    (r"SELECT.*%s.*%[^s]|\.format\(.*SELECT|SELECT.*\+", "sql-injection: string-built query"),
    (r"innerHTML\s*=", "xss: innerHTML assignment"),
    (r"dangerouslySetInnerHTML", "xss: dangerouslySetInnerHTML"),
    (r"Math\.random\(\)", "weak-random: Math.random for security use"),
    (r"hashlib\.(md5|sha1)\(", "weak-hash"),
    (r"verify\s*=\s*False|CERT_NONE|check_hostname\s*=\s*False", "tls-verification-disabled"),
]

APPROVED_LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC",
                     "Python-2.0", "PSF", "Unlicense", "CC0-1.0", "MPL-2.0", "LGPL-3.0"}
KNOWN_PACKAGES = {"react", "react-dom", "vite", "typescript", "pytest", "requests",
                  "numpy", "pandas", "flask", "django", "fastapi", "express"}
# Offline CVE fallback pins (live OSV is authoritative when online).
# Thresholds last synced from OSV affected ranges: requests <2.33.0 still
# matches GHSA-9hjg-9r4m-mvj7 (fix 2.32.4), GHSA-9wx4-h78v-vm56 (fix 2.32.0),
# GHSA-gc5v-m9x4-r6x2 (fix 2.33.0).
VULN_DB: dict[str, list[str]] = {
    "lodash": ["<4.17.21"],
    "minimist": ["<1.2.8"],
    "requests": ["<2.33.0"],
    "pillow": ["<9.5.0"],
}

_SINK_LOG = "sink.log.jsonl"


def taint(text: str, source: str) -> str:
    """Label fetched content. Web/MCP/issue content is untrusted by default;
    version-pinned docs cache is pinned-docs; local repo/exec is local-exec."""
    s = (source or "").lower()
    if any(k in s for k in (" веб", "http", "mcp", "issue", "web", "fetch")):
        return "untrusted"
    if "docs-cache" in s or "pinned" in s:
        return "pinned-docs"
    return "local-exec"


def check_authority(capability: str, context_taints: list[str]) -> tuple[bool, str]:
    """A call's authority is bounded by the taint of its producing context."""
    cap = _RANK.get(capability, 0)
    worst = min((_RANK.get(t, 0) for t in context_taints), default=_RANK["local-exec"])
    # Untrusted context may only drive untrusted-capability calls.
    if worst == 0 and cap > 0:
        return False, f"untrusted context cannot drive {capability} calls — declassify first"
    return True, "authority ok"


def mint_capability(secret: str, scope: str, ttl_s: int = 600) -> str:
    """HMAC capability token: scope + expiry, verifiable without storage."""
    exp = int(time.time()) + ttl_s
    body = f"{scope}.{exp}.{secrets.token_hex(8)}"
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_capability(secret: str, token: str) -> str | None:
    """Returns the scope when valid and unexpired, else None."""
    try:
        scope, exp, _nonce, sig = token.rsplit(".", 3)
        body = f"{scope}.{exp}.{_nonce}"
    except ValueError:
        return None
    expect = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return None
    if int(exp) < int(time.time()):
        return None
    return scope


def scan_secrets(text: str) -> list[tuple[str, str]]:
    """Returns [(kind, redacted_match)] for every secret pattern hit."""
    hits = []
    for pat, kind in SECRET_PATTERNS:
        for m in re.finditer(pat, text):
            hits.append((kind, m.group(0)[:12] + "…[redacted]"))
    return hits


def sast_scan(source: str) -> list[str]:
    """Static pattern screen. Returns finding descriptions."""
    return [desc for pat, desc in SAST_RULES if re.search(pat, source)]


def log_sink(cfg: dict, kind: str, target: str, taint_label: str, allowed: bool) -> None:
    """Every network-out + secret-read joined to taint (doc 02 §6)."""
    store.append_jsonl(f"{cfg['state_dir']}/{_SINK_LOG}", {
        "kind": kind, "target": target, "taint": taint_label,
        "allowed": allowed,
    })


def gate_secrets(cfg: dict, text: str, where: str = "") -> tuple[bool, str]:
    if not cfg.get("security", {}).get("block_secrets", True):
        return True, "secret gate disabled"
    hits = scan_secrets(text)
    if hits:
        kinds = ", ".join(sorted({k for k, _ in hits}))
        ledger.log_gate(cfg, "secrets", "F5", "reject", detail=f"{kinds} in {where}")
        ledger.add_issue(cfg, "critical", "security", f"secret material ({kinds}) in {where or 'content'}")
        return False, f"secret material blocked ({kinds}) — remove before writing"
    return True, "no secrets"


def gate_sast(cfg: dict, source: str, where: str = "") -> tuple[bool, list[str]]:
    if not cfg.get("security", {}).get("sast", True):
        return True, []
    findings = sast_scan(source)
    for f in findings:
        ledger.add_issue(cfg, "major", "security", f"SAST {f} in {where or 'edit'}")
    ledger.log_gate(cfg, "sast", "F5", "pass" if not findings else "reject",
                    detail=f"{len(findings)} findings in {where or 'edit'}")
    return (not findings), findings


def _typosquat(name: str) -> str | None:
    n = name.lower()
    for known in KNOWN_PACKAGES:
        if n != known and n.replace("-", "").replace("_", "") == known.replace("-", ""):
            return known
    return None


def _osv_cache_path(cfg: dict | None, name: str, version: str, ecosystem: str) -> str | None:
    if not cfg or not cfg.get("state_dir"):
        return None
    safe = "".join(c if c.isalnum() else "_" for c in f"{ecosystem}_{name}_{version}")
    return os.path.join(cfg["state_dir"], "osv-cache", f"{safe}.json")


def _osv_query(name: str, version: str, ecosystem: str,
               cfg: dict | None = None, timeout: int = 6) -> list[dict]:
    """Query OSV (covers NVD/GHSA) for package@version. Cached 24h; [] on offline/error.

    Stdlib urllib only. Cache lives in <state_dir>/osv-cache/ so offline runs
    reuse the last verdict instead of failing open silently.
    """
    import json as _json
    import urllib.request as _url
    cache_path = _osv_cache_path(cfg, name, version, ecosystem)
    if cache_path and os.path.isfile(cache_path):
        try:
            if time.time() - os.path.getmtime(cache_path) < 86400:
                with open(cache_path, encoding="utf-8") as f:
                    return _json.load(f).get("vulns", [])
        except Exception:
            pass
    try:
        payload = _json.dumps({"package": {"name": name, "ecosystem": ecosystem},
                               "version": version}).encode()
        req = _url.Request("https://api.osv.dev/v1/query", data=payload,
                           headers={"Content-Type": "application/json",
                                    "User-Agent": "super-harness/1.0"},
                           method="POST")
        with _url.urlopen(req, timeout=timeout) as r:
            body = _json.loads(r.read(500000).decode("utf-8", errors="replace"))
        vulns = body.get("vulns", []) if isinstance(body, dict) else []
        if cache_path:
            try:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    _json.dump({"vulns": vulns,
                                "fetched": time.strftime("%Y-%m-%dT%H:%M:%S")}, f)
            except Exception:
                pass
        return vulns
    except Exception:
        # offline: serve stale cache if any
        if cache_path and os.path.isfile(cache_path):
            try:
                with open(cache_path, encoding="utf-8") as f:
                    return _json.load(f).get("vulns", [])
            except Exception:
                pass
        return []


def _infer_ecosystems(name: str) -> list[str]:
    """Ecosystems to probe on OSV for a bare dependency name."""
    n = name.lower()
    if n.startswith("@") or "-" in n or n in ("react", "react-dom", "vite", "express",
                                              "lodash", "minimist", "typescript"):
        return ["npm"]
    if "_" in n or n in ("requests", "pillow", "numpy", "pandas", "flask",
                         "django", "fastapi", "pytest"):
        return ["PyPI"]
    return ["npm", "PyPI"]  # unknown — probe both, npm first


def _cve_check(name: str, version: str, cfg: dict | None = None,
               ecosystem: str | None = None) -> str | None:
    """Live CVE screen via OSV (NVD/GHSA-backed), VULN_DB as offline fallback.

    Returns an advisory string or None. Never raises and never blocks on
    network failure — offline verdicts fall back to the pinned VULN_DB.
    """
    if not version:
        return None
    ecosystems = [ecosystem] if ecosystem else _infer_ecosystems(name)
    for eco in ecosystems:
        vulns = _osv_query(name, version, eco, cfg)
        if vulns:
            top = vulns[0]
            vid = top.get("id", "OSV")
            sev = ""
            try:
                sev = (top.get("severity") or [{}])[0].get("score", "")
                sev = f" (severity {sev})" if sev else ""
            except Exception:
                pass
            summary = (top.get("summary") or top.get("details") or "")[:160]
            return (f"{name}@{version} has {len(vulns)} known vuln(s) via OSV [{eco}] "
                    f"({vid}{sev}) {summary} — update required".strip())
    # offline fallback: pinned VULN_DB heuristic
    import re as _re
    # normalize version like "1.2.3" -> tuple
    def _parse(v: str) -> tuple[int, ...]:
        v = _re.sub(r"[^0-9.]", ".", v).strip(".")
        parts = [int(p) if p.isdigit() else 0 for p in v.split(".") if p]
        return tuple(parts) if parts else (0,)
    rules = VULN_DB.get(name.lower())
    if not rules:
        return None
    vp = _parse(version)
    for rule in rules:
        m = _re.match(r"<\s*([0-9.]+)", rule)
        if m:
            thr = _parse(m.group(1))
            if vp < thr:
                return f"{name}@{version} has known CVE (fix ≥ {m.group(1)}) — update required"
    return None

def gate_dependency(cfg: dict, name: str, version: str = "",
                    license: str = "", ecosystem: str | None = None) -> tuple[bool, str]:
    """Pin + CVE + typosquat + license screen for every newly introduced dependency."""
    if not cfg.get("security", {}).get("dependency_gate", True):
        return True, "dependency gate disabled"
    if not version:
        ledger.log_gate(cfg, "dependency", "F5", "reject", detail=f"{name} unpinned")
        return False, f"dependency {name} must be version-pinned"
    cve = _cve_check(name, version, cfg, ecosystem)
    if cve:
        ledger.log_gate(cfg, "dependency", "F5", "reject", detail=cve)
        ledger.add_issue(cfg, "critical", "security", cve)
        return False, cve
    squat = _typosquat(name)
    if squat:
        ledger.log_gate(cfg, "dependency", "F5", "reject", detail=f"{name} typosquats {squat}")
        ledger.add_issue(cfg, "critical", "security", f"possible typosquat: {name} (~ {squat})")
        return False, f"{name} looks like a typosquat of {squat}"
    if license and license not in APPROVED_LICENSES:
        ledger.log_gate(cfg, "license", "F5", "reject", detail=f"{name}: {license}")
        ledger.add_issue(cfg, "major", "legal", f"unapproved license {license} for {name}")
        return False, f"license {license} needs legal review"
    ledger.log_gate(cfg, "dependency", "F5", "pass", detail=f"{name}@{version or '?'}")
    return True, "dependency clear"


def sink_audit(cfg: dict) -> dict:
    """Join check: any allowed network-out from untrusted context is a finding."""
    rows = store.read_jsonl(f"{cfg['state_dir']}/{_SINK_LOG}")
    bad = [r for r in rows if r.get("allowed") and r.get("taint") == "untrusted"
           and r.get("kind") in ("network-out", "secret-read")]
    return {"entries": len(rows), "violations": bad, "clean": not bad}


def declassify(cfg: dict, text: str, from_taint: str, to_taint: str, reviewer: str = "human", reason: str = "") -> tuple[bool, str]:
    """Explicit declassification: untrusted → pinned-docs → local-exec. Logged, never implicit."""
    if _RANK.get(from_taint, 0) >= _RANK.get(to_taint, 0):
        return True, "no elevation"
    if from_taint == "untrusted" and to_taint in ("pinned-docs", "local-exec"):
        if not reviewer or not reason:
            return False, "declassification requires reviewer + reason"
        ledger.log_gate(cfg, "declassify", "F5", "pass", detail=f"{from_taint}->{to_taint} by {reviewer}: {reason[:120]}")
        ledger.add_issue(cfg, "minor", "security", f"declassified {from_taint}->{to_taint} by {reviewer}")
        return True, f"declassified to {to_taint}"
    return False, f"illegal declassification {from_taint}->{to_taint}"


def dispatch_tool(cfg: dict, tool: str, capability_token: str, secret: str, context_taints: list[str]) -> tuple[bool, str]:
    """Capability-bound dispatch: token scope must equal tool and taint must allow it."""
    scope = verify_capability(secret, capability_token)
    if not scope:
        ledger.log_gate(cfg, "capability", "F5", "reject", detail=f"invalid token for {tool}")
        return False, "invalid or expired capability token"
    if scope != tool:
        return False, f"token scope {scope} != tool {tool}"
    ok, msg = check_authority(tool, context_taints)
    if not ok:
        ledger.log_gate(cfg, "capability", "F5", "reject", detail=msg)
        return False, msg
    ledger.log_gate(cfg, "capability", "F5", "pass", detail=f"{tool} dispatched")
    return True, "dispatched"


def generate_sbom(cfg: dict, root: str | None = None) -> dict:
    """SBOM from lockfiles: package-lock.json, poetry/uv/Cargo/go/requirements. Stdlib only."""
    root = root or cfg.get("_root", ".")
    sbom: dict[str, list] = {"packages": [], "generated": time.strftime("%Y-%m-%dT%H:%M:%S")}
    # package-lock.json
    for cand in [os.path.join(root, "package-lock.json"), os.path.join(root, "super/web-src/package-lock.json")]:
        if os.path.isfile(cand):
            try:
                with open(cand, encoding="utf-8") as f:
                    data = json.load(f)
                for name, meta in (data.get("packages") or {}).items():
                    if not name or name == "": continue
                    ver = meta.get("version", "")
                    sbom["packages"].append({"name": name.split("node_modules/")[-1], "version": ver, "source": cand})
                for name, meta in (data.get("dependencies") or {}).items():
                    sbom["packages"].append({"name": name, "version": meta.get("version",""), "source": cand})
            except Exception:
                pass
    # requirements.txt / requirements.lock
    for cand in [os.path.join(root, "requirements.txt"), os.path.join(root, "requirements.lock")]:
        if os.path.isfile(cand):
            try:
                for line in open(cand, encoding="utf-8", errors="replace"):
                    line=line.strip()
                    if not line or line.startswith("#"): continue
                    m=re.match(r"([A-Za-z0-9_.\-]+)\s*==\s*([^\s;]+)", line)
                    if m: sbom["packages"].append({"name": m.group(1), "version": m.group(2), "source": cand})
            except Exception:
                pass
    # poetry.lock (toml-ish)
    cand = os.path.join(root, "poetry.lock")
    if os.path.isfile(cand):
        try:
            txt=open(cand, encoding="utf-8", errors="replace").read()
            for m in re.finditer(r'name\s*=\s*"([^"]+)"\s*\nversion\s*=\s*"([^"]+)"', txt):
                sbom["packages"].append({"name": m.group(1), "version": m.group(2), "source": cand})
        except Exception:
            pass
    # uv.lock
    cand = os.path.join(root, "uv.lock")
    if os.path.isfile(cand):
        try:
            txt=open(cand, encoding="utf-8", errors="replace").read()
            for m in re.finditer(r'name\s*=\s*"([^"]+)"\s*\nversion\s*=\s*"([^"]+)"', txt):
                sbom["packages"].append({"name": m.group(1), "version": m.group(2), "source": cand})
        except Exception:
            pass
    # Cargo.lock
    cand = os.path.join(root, "Cargo.lock")
    if os.path.isfile(cand):
        try:
            txt=open(cand, encoding="utf-8", errors="replace").read()
            for m in re.finditer(r'name\s*=\s*"([^"]+)"\s*\nversion\s*=\s*"([^"]+)"', txt):
                sbom["packages"].append({"name": m.group(1), "version": m.group(2), "source": cand})
        except Exception:
            pass
    # go.mod
    cand = os.path.join(root, "go.mod")
    if os.path.isfile(cand):
        try:
            for line in open(cand, encoding="utf-8", errors="replace"):
                m=re.match(r"\s*([A-Za-z0-9_./\-]+)\s+v([0-9.]+[^\s]*)", line)
                if m: sbom["packages"].append({"name": m.group(1), "version": m.group(2), "source": cand})
        except Exception:
            pass
    # pyproject.toml dependencies (best-effort)
    cand = os.path.join(root, "pyproject.toml")
    if os.path.isfile(cand):
        try:
            txt=open(cand, encoding="utf-8", errors="replace").read()
            # dependencies = ["requests==2.31.0", ...]
            for m in re.finditer(r"([A-Za-z0-9_.\-]+)\s*==\s*([0-9.][^\s\",]+)", txt):
                # only if inside dependencies section (heuristic: keep all)
                sbom["packages"].append({"name": m.group(1), "version": m.group(2), "source": cand})
        except Exception:
            pass
    # deduplicate
    seen=set()
    uniq=[]
    for p in sbom["packages"]:
        k=(p["name"], p["version"])
        if k not in seen and p["name"]:
            seen.add(k)
            uniq.append(p)
    sbom["packages"]=sorted(uniq, key=lambda x: x["name"])[:800]
    sbom["count"]=len(sbom["packages"])
    try:
        store.save_json(f"{cfg['state_dir']}/sbom.json", sbom)
    except Exception:
        pass
    ledger.log_gate(cfg, "sbom", "F5", "pass", detail=f"sbom {sbom['count']} packages")
    return sbom


def enforce_write(cfg: dict, source: str, where: str = "",
                  context_taints: list[str] | None = None) -> tuple[bool, list[str]]:
    """Combined write-path security enforcement. Returns (ok, blockers)."""
    blockers: list[str] = []
    ok, msg = gate_secrets(cfg, source, where)
    if not ok:
        blockers.append(msg)
    ok_sast, findings = gate_sast(cfg, source, where)
    if not ok_sast:
        blockers.append(f"SAST: {'; '.join(findings)}")
    if cfg.get("gates", {}).get("taint", True):
        ok_auth, msg_auth = check_authority("local-exec", context_taints or ["local-exec"])
        if not ok_auth:
            blockers.append(msg_auth)
    if blockers:
        raise SecurityViolation("; ".join(blockers))
    return True, []
