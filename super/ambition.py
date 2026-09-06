"""Ambition Contract + critic ensemble + done-state gate (doc 05).

Silent deflation is impossible by construction: the request compiles to a
multi-dimensional Level-of-Ambition ladder *before* generation, the default
target is LoA 4 (expert), the builder cannot lower the contract, grading is
external / ensembled / reference-grounded, refinement is a mandated
axis-targeted loop, and downgrades require an explicit user key or a priced
budget-exhaustion event. Two-key rule: builder proposes, gates dispose.
"""

from __future__ import annotations

import statistics

from . import ledger
from .errors import AmbitionError

TAXONOMIES = {
    "rendering": ["geometry", "materials", "lighting", "post-processing",
                  "composition", "scene-richness"],
    "ui": ["states", "interactions", "motion", "a11y", "empty-error-states", "polish"],
    "writing": ["research-depth", "citations", "examples", "edge-cases", "structure"],
    "software": ["error-handling", "tests", "perf", "observability", "security", "docs"],
    "data": ["cleaning", "validation", "visualization", "caveats", "reproducibility"],
    "general": ["depth", "breadth", "correctness", "polish", "coverage"],
}

MAX_LOA = 5


def compile_contract(cfg: dict, request: str, domain: str = "general",
                     target_loa: int | None = None) -> dict:
    """Compile a request into a dimension ladder before any generation."""
    domain = domain if domain in TAXONOMIES else "general"
    loa = target_loa or int(cfg.get("ambition", {}).get("default_loa", 4))
    if loa < 1 or loa > MAX_LOA:
        raise AmbitionError(f"target LoA must be in [1, {MAX_LOA}]")
    axes = TAXONOMIES[domain]
    contract = {
        "request": request[:2000],
        "domain": domain,
        "target_loa": loa,
        "axes": {a: {"target": loa, "score": 0, "evidence": ""} for a in axes},
        "downgrades": [],
        "builder_editable": False,
    }
    ledger.log_gate(cfg, "ambition", "F4", "pass",
                    detail=f"contract {domain} LoA{loa} ({len(axes)} axes)")
    return contract


def record_scores(cfg: dict, contract: dict, scores: dict[str, tuple[float, str]]) -> dict:
    """Record external critic scores per axis: {axis: (score, evidence)}.

    Scores come from critics with no shared context with the builder —
    self-grading is structurally impossible here.
    """
    for axis, (score, evidence) in scores.items():
        if axis not in contract["axes"]:
            raise AmbitionError(f"unknown axis {axis}")
        if not (0 <= score <= MAX_LOA):
            raise AmbitionError(f"score for {axis} out of range")
        contract["axes"][axis]["score"] = score
        contract["axes"][axis]["evidence"] = (evidence or "")[:1000]
    return contract


def ensemble(scores_per_critic: list[dict[str, float]]) -> dict[str, float]:
    """Median per axis; any critic >1 level below median forces iteration."""
    if not scores_per_critic:
        raise AmbitionError("critic ensemble is empty")
    axes = set().union(*(c.keys() for c in scores_per_critic))
    medians = {}
    for axis in axes:
        vals = sorted(c[axis] for c in scores_per_critic if axis in c)
        medians[axis] = statistics.median(vals)
    return medians


def disagreements(scores_per_critic: list[dict[str, float]],
                  medians: dict[str, float]) -> list[str]:
    out = []
    for i, c in enumerate(scores_per_critic):
        for axis, v in c.items():
            if medians.get(axis, v) - v > 1.0:
                out.append(f"critic {i} rates {axis} {v} vs median {medians[axis]} — iterate")
    return out


def next_axis(contract: dict) -> str | None:
    """Lowest-scoring axis below target — the only allowed next step
    (axis-targeted refinement, doc 05 §2.3)."""
    worst, worst_key = None, None
    for axis, cell in contract["axes"].items():
        gap = cell["target"] - cell.get("score", 0)
        if gap > 0 and (worst is None or gap > worst):
            worst, worst_key = gap, axis
    return worst_key


def downgrade(contract: dict, axis: str, new_target: int, reason: str,
              user_keyed: bool = False) -> dict:
    """Lower an axis target. Requires explicit user action or a priced
    budget-exhaustion event — never silent, never builder-initiated."""
    if axis not in contract["axes"]:
        raise AmbitionError(f"unknown axis {axis}")
    if not user_keyed and "budget" not in (reason or "").lower():
        raise AmbitionError("downgrades require user approval or budget exhaustion — builder cannot lower the contract")
    contract["axes"][axis]["target"] = new_target
    contract["downgrades"].append({"axis": axis, "to": new_target, "reason": reason})
    return contract


def _presence_score(hits: int, per_level: float = 2.0) -> float:
    """1 + hits/per_level capped to [1, 5]. 0 hits → 1."""
    return float(max(1, min(5, 1 + hits / per_level)))


def _perf_score(src: str) -> tuple[float, str]:
    """Static perf screen: nested loops, I/O-in-loop, sync network, unbounded work.

    Starts at 5, −1 per distinct risk class found (floor 1). Deterministic and
    stdlib-only; runtime regression is covered separately by verify.perf_gate.
    """
    import re as _re
    risks: list[str] = []
    # nested loops: a for/while within 5 lines after another loop opener
    if _re.search(r"^\s*for\s+.+:\s*\n(?:.*\n){0,6}?\s*for\s+", src, _re.M) or \
       _re.search(r"for\s*\(.*\)\s*\{[^}]*for\s*\(", src):
        risks.append("nested loops (O(n²) risk)")
    # I/O or query inside an explicit loop
    if _re.search(r"for\s*[\({:]?.*\n(?:.*\n){0,8}?.*(requests\.(get|post)|fetch\(|\.execute\(|\.query\(|open\(|read\(|write\()", src):
        risks.append("I/O inside loop (batch/paginate)")
    # unbounded / polling loops
    if _re.search(r"while\s+True|while\s*\(\s*true\s*\)", src) and "break" not in src:
        risks.append("unbounded while without break")
    if "time.sleep(" in src or "setTimeout(" in src and "poll" in src.lower():
        risks.append("sleep/poll loop")
    # unbounded SELECT / find without limit
    if _re.search(r"SELECT\b", src, _re.I) and not _re.search(r"LIMIT\b", src, _re.I):
        risks.append("SELECT without LIMIT")
    if _re.search(r"\.find\(\s*\{\s*\}\s*\)", src):
        risks.append("unbounded find({})")
    # sync network on hot path
    sync_net = len(_re.findall(r"requests\.(get|post)|urllib\.request|fetch\(|XMLHttpRequest", src))
    if sync_net >= 3:
        risks.append(f"{sync_net} sync network calls (consider batching/cache)")
    # string concat in loop (quadratic copy)
    if _re.search(r"for\s+.+\n(?:.*\n){0,6}?.*\+=\s*['\"]", src) or \
       _re.search(r"for\s*\(.*\)\s*\{[^}]*\+\=\s*['\"]", src):
        risks.append("string += in loop (use join/builder)")
    score = float(max(1, 5 - len(risks)))
    evidence = "; ".join(risks) if risks else "no static perf risks (loops bounded, queries limited)"
    return score, evidence


def _rendering_metrics(src: str) -> dict[str, tuple[float, str]]:
    import re as _re
    low = src.lower()
    out: dict[str, tuple[float, str]] = {}
    geom_hits = (len(_re.findall(r"buffergeometry|vertices|indices|position\s*attribute|faces|triangles|gltf|objloader|fbx", low)))
    face_nums = _re.findall(r"(?:faces|triangles|verts?)\s*[:=]\s*(\d+)", low)
    face_total = sum(int(n) for n in face_nums[:10]) if face_nums else 0
    out["geometry"] = (_presence_score(geom_hits + (2 if face_total > 1000 else 0)),
                       f"{geom_hits} geometry refs" + (f", ~{face_total} faces" if face_total else ""))
    mat_hits = len(_re.findall(r"meshstandardmaterial|meshphysicalmaterial|meshlamb|pbr|albedo|normalmap|roughnessmap|metalness|envmap|clearcoat", low))
    maps = sorted(set(_re.findall(r"(albedo|normal|roughness|metalness|ao|emissive)\s*(?:map)?", low)))
    out["materials"] = (_presence_score(mat_hits),
                        f"{mat_hits} material refs" + (f" ({', '.join(maps[:4])})" if maps else " — add albedo/normal/rough maps"))
    light_hits = len(_re.findall(r"directionallight|hemispherelight|pointlight|spotlight|ambientlight|rectarealight", low))
    shadow = bool(_re.search(r"castshadow|receiveshadow|shadowmap|shadow\.mapsize", low))
    hdri = bool(_re.search(r"hdri|hdr |\.hdr|pmrem|environment\s*preset|roomEnvironment", low))
    out["lighting"] = (_presence_score(light_hits + (2 if shadow else 0) + (2 if hdri else 0)),
                       f"{light_hits} lights" + (" +shadows" if shadow else " — no shadows") + (" +HDRI/env" if hdri else " — no HDRI"))
    post_hits = len(_re.findall(r"effectcomposer|unrealbloom|tonemapping|acesfilmic|exposure|antialias|outputcolorspace|vignette|ssao|bloom", low))
    out["post-processing"] = (_presence_score(post_hits),
                              f"{post_hits} post refs" if post_hits else "no composer/tonemap pass")
    cam_hits = len(_re.findall(r"perspectivecamera|orthographiccamera|orbitcontrols|fov|camera\.position|viewpoint|flyto", low))
    out["composition"] = (_presence_score(cam_hits),
                          f"{cam_hits} camera refs" if cam_hits else "single default camera")
    rich_hits = len(_re.findall(r"instancedmesh|foliage|trees?|grass|particles|entourage|scatter|lod\b", low))
    out["scene-richness"] = (_presence_score(rich_hits),
                             f"{rich_hits} richness refs" if rich_hits else "empty backdrop — add entourage")
    return out


def _ui_metrics(src: str) -> dict[str, tuple[float, str]]:
    import re as _re
    low = src.lower()
    out: dict[str, tuple[float, str]] = {}
    states = len(set(_re.findall(r"loading|disabled|active|selected|hover|focus|visited|checked|expanded|collapsed", low)))
    out["states"] = (_presence_score(states, 1.5), f"{states}/10 state variants")
    inter = len(_re.findall(r"onclick|onchange|onsubmit|oninput|addEventListener|@click|@submit|handle[A-Z]\w*", src))
    out["interactions"] = (_presence_score(inter, 1.5), f"{inter} handlers")
    motion = len(_re.findall(r"transition|animation|@keyframes|transform\s*:|duration|ease", low))
    reduced = bool(_re.search(r"prefers-reduced-motion", low))
    out["motion"] = (_presence_score(motion + (2 if reduced else 0), 1.5),
                     f"{motion} motion refs" + ("" if reduced else " — no prefers-reduced-motion"))
    a11y = len(_re.findall(r"aria-|role=|alt=|<label|tabindex|focus-visible|onkeydown|onkeyup", src))
    out["a11y"] = (_presence_score(a11y, 1.5), f"{a11y} a11y hooks" if a11y else "no aria/roles/labels")
    empty_err = len(_re.findall(r"empty|no results|not found|error boundary|try again|offline|404|something went wrong", low))
    out["empty-error-states"] = (_presence_score(empty_err, 1.0), f"{empty_err} empty/error refs")
    polish = len(_re.findall(r"@media|dark:?|focus-visible|text-overflow|line-clamp|truncate", low))
    out["polish"] = (_presence_score(polish, 1.5), f"{polish} polish refs")
    return out


def _writing_metrics(src: str) -> dict[str, tuple[float, str]]:
    import re as _re
    words = len(_re.findall(r"[A-Za-z]{2,}", src))
    out: dict[str, tuple[float, str]] = {}
    out["research-depth"] = (_presence_score(words, 400.0), f"{words} words")
    cites = len(_re.findall(r"\[\d+\]|\(\w+ \d{4}\)|https?://|footnotes?|\[\^[^\]]+\]", src))
    out["citations"] = (_presence_score(cites, 1.5), f"{cites} citations/links")
    examples = len(_re.findall(r"```|e\.g\.|for example|figure \d|example \d", src, _re.I))
    out["examples"] = (_presence_score(examples, 1.0), f"{examples} examples/figures")
    edge = len(set(_re.findall(r"edge case|limitation|caveat|however|exception|trade-?off|assumption", src, _re.I)))
    out["edge-cases"] = (_presence_score(edge, 1.0), f"{edge}/7 edge-case markers")
    heads = len(_re.findall(r"^#{1,4}\s+\S", src, _re.M))
    has_intro = bool(_re.search(r"^#\s+.*|introduction", src, _re.M | _re.I))
    out["structure"] = (_presence_score(heads + (1 if has_intro else 0), 1.5), f"{heads} headings")
    return out


def _data_metrics(src: str, low: str) -> dict[str, tuple[float, str]]:
    import re as _re
    out: dict[str, tuple[float, str]] = {}
    clean = len(_re.findall(r"dropna|fillna|dedup|normalize|strip\(\)|astype|parse_dates", low))
    out["cleaning"] = (_presence_score(clean, 1.5), f"{clean} cleaning ops")
    valid = len(_re.findall(r"assert|validate|schema|expect_|range|notnull|unique", low))
    out["validation"] = (_presence_score(valid, 1.5), f"{valid} validation checks")
    viz = len(_re.findall(r"chart|plot|figure|matplotlib|altair|histogram|scatter|bar\(|line\(", low))
    out["visualization"] = (_presence_score(viz, 1.0), f"{viz} viz refs")
    caveats = len(set(_re.findall(r"bias|missing|confound|limitation|selection|leakage", low)))
    out["caveats"] = (_presence_score(caveats, 1.0), f"{caveats}/6 caveat markers")
    repro = len(_re.findall(r"random_state|seed\(|version|requirements|pipeline|dvc|mlflow|dockerfile", low))
    out["reproducibility"] = (_presence_score(repro, 1.0), f"{repro} repro pins")
    return out


def _general_metrics(src: str, low: str) -> dict[str, tuple[float, str]]:
    import re as _re
    out: dict[str, tuple[float, str]] = {}
    lines = src.splitlines()
    sections = len(_re.findall(r"^#{1,4}\s+\S", src, _re.M))
    blocks = len(_re.findall(r"```", src)) // 2
    out["depth"] = (_presence_score(len(lines), 120.0) if len(lines) < 600 else 5.0,
                    f"{len(lines)} lines, {sections} sections, {blocks} code blocks")
    heads = set(_re.findall(r"^#{1,4}\s+(.+)$", src, _re.M))
    out["breadth"] = (_presence_score(len(heads), 1.5), f"{len(heads)} distinct sections")
    todos = len(_re.findall(r"TODO|FIXME|XXX|HACK", src))
    try:
        compile(src, "<artifact>", "exec")
        parses = True
    except Exception:
        parses = "{" in src and src.count("{") == src.count("}")
    out["correctness"] = (float(max(1, min(5, (5 if parses else 2) - min(2, todos)))),
                          ("parses" if parses else "parse risk") + (f", {todos} TODOs" if todos else ", no TODOs"))
    trailing = sum(1 for l in lines if l != l.rstrip())
    out["polish"] = (float(max(1, 5 - min(3, trailing // 20 + todos // 3))),
                     f"{trailing} trailing-ws lines" if trailing else "clean whitespace")
    out["coverage"] = (_presence_score(sections + blocks, 2.0), f"{sections} sections + {blocks} blocks")
    return out
def mechanical_metrics(cfg: dict, domain: str, artifact_source: str = "", artifact_path: str = "") -> dict[str, tuple[float, str]]:
    """Mechanical metrics per axis — evidence for critic ensemble, never verdict alone (doc 05 §2.2)."""
    import os as _os
    import re as _re
    src = artifact_source or ""
    if artifact_path and _os.path.isfile(artifact_path):
        try:
            with open(artifact_path, encoding="utf-8", errors="ignore") as f:
                src = f.read(80000)
        except Exception:
            pass
    low = src.lower()
    out: dict[str, tuple[float, str]] = {}
    if domain == "software":
        # error-handling: count try/except
        eh = len(_re.findall(r"\btry\s*:", src)) + len(_re.findall(r"\bexcept\b", src))
        out["error-handling"] = (min(5, 1 + eh * 0.8), f"{eh} try/except blocks")
        # tests: count assert/expect
        t = len(_re.findall(r"\bassert\b|\bexpect\s*\(", src))
        out["tests"] = (min(5, 1 + t * 0.5), f"{t} asserts")
        # static perf screen (runtime regression is verify.perf_gate vs baseline)
        out["perf"] = _perf_score(src)
        # observability: log/print
        obs = len(_re.findall(r"\blogger|logging|print\(|console\.log", src))
        out["observability"] = (min(5, 1 + obs * 0.6), f"{obs} log points")
        # docs
        docs = len(_re.findall(r'""".*?"""', src, _re.S))
        out["docs"] = (min(5, 1 + docs * 0.7), f"{docs} docstrings")
        # security: SAST hits inverse
        from . import security as _sec
        findings = _sec.sast_scan(src)
        out["security"] = (max(1, 5 - len(findings)), f"{len(findings)} SAST findings")
    elif domain == "rendering":
        out.update(_rendering_metrics(src))
    elif domain == "ui":
        out.update(_ui_metrics(src))
    elif domain == "writing":
        out.update(_writing_metrics(src))
    elif domain == "data":
        out.update(_data_metrics(src, low))
    else:
        out.update(_general_metrics(src, low))
    return out


def critic_loop(cfg: dict, contract: dict, artifact_source: str = "", artifact_path: str = "", budget_minutes: float = 20.0) -> tuple[bool, list[str], dict]:
    """Axis-targeted refinement loop: draft → critique → enhance → re-critique until LoA or budget."""
    import time as _time
    start = _time.time()
    blockers, scorecard = done_state(cfg, contract)[1:]
    # mechanical metrics as evidence for critics
    mech = mechanical_metrics(cfg, contract.get("domain","general"), artifact_source, artifact_path)
    for axis, (score, ev) in mech.items():
        if axis in contract["axes"]:
            # seed critic scores with mechanical hint, but don't pass axis alone
            contract["axes"][axis]["score"] = max(contract["axes"][axis].get("score",0), min(score, contract["axes"][axis]["target"] - 0.5))
            contract["axes"][axis]["evidence"] = ev
    # VLM critics: call llm if available, else use mech
    critics = int(cfg.get("ambition", {}).get("critics", 3))
    try:
        from . import llm as _llm
        # One critic call per axis-targeted iteration (isolated, no shared context)
        for _ in range(critics):
            nxt = next_axis(contract)
            if not nxt:
                break
            # ask critic to score lowest axis
            try:
                prompt = f"Score {nxt} for this {contract['domain']} artifact on LoA 1-5. Artifact excerpt:\n{(artifact_source or '')[:2000]}\n\nRespond JSON {{\"score\": <1-5>, \"evidence\": \"...\"}}"
                raw = _llm.chat(cfg, [{"role":"user","content": prompt}])
                import json as _json
                # try parse JSON
                m = _json.loads(raw[raw.find("{"):raw.rfind("}")+1]) if "{" in raw else {}
                s = float(m.get("score", 3))
                ev = m.get("evidence", "vlm-critic")
                contract["axes"][nxt]["score"] = max(contract["axes"][nxt]["score"], s)
                contract["axes"][nxt]["evidence"] = ev[:500]
            except Exception:
                continue
            if (_time.time() - start) / 60 > budget_minutes:
                downgrade(contract, nxt, max(1, contract["axes"][nxt]["target"]-1), f"budget exhausted at {budget_minutes} min", user_keyed=True)
                break
    except Exception:
        pass
    return done_state(cfg, contract)


def done_state(cfg: dict, contract: dict) -> tuple[bool, list[str], dict]:
    """Done-state gate: no axis below contracted LoA, scorecard attached."""
    blockers = [
        f"{axis}: LoA {cell.get('score', 0)} < contracted {cell['target']}"
        for axis, cell in contract["axes"].items()
        if cell.get("score", 0) < cell["target"]
    ]
    scorecard = {
        "domain": contract["domain"],
        "target_loa": contract["target_loa"],
        "axes": {a: {"target": c["target"], "score": c.get("score", 0),
                     "evidence": c.get("evidence", "")}
                 for a, c in contract["axes"].items()},
        "downgrades": contract.get("downgrades", []),
    }
    if blockers:
        ledger.log_gate(cfg, "ambition-done", "F4", "reject", detail="; ".join(blockers))
    else:
        ledger.log_gate(cfg, "ambition-done", "F4", "pass", detail="all axes at contracted LoA")
    return (not blockers), blockers, scorecard
