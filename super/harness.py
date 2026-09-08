"""Harness chat pipeline: task context + memory + grounding on every reply.

The model receives exactly one leaf card plus compiled memory claims and a
repo overview — the harness holds the forest, the model holds one leaf.
Replies pass symbol extraction and the grounding registry; chat warns via
the returned gate verdict while the file write path blocks. Best-of-N
sampling with verifier selection and early abort on stall multiplies small
models (doc 02 §4): tokens buy search, selection buys quality.
"""

from __future__ import annotations

import os
import re

STOPWORDS = {
    "import", "from", "return", "for", "while", "with", "if", "else", "elif",
    "try", "except", "True", "False", "None", "and", "or", "not", "in", "is",
    "the", "a", "an",
}

MAX_SYMBOLS_CHECKED = 20


def repo_overview(cfg: dict, limit: int = 60) -> str:
    """Top-level repo listing so the model knows what exists without dumping files."""
    root = cfg["_root"]
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return "(unreadable root)"
    shown = [n for n in names if not n.startswith(".super")][:limit]
    return ", ".join(shown) or "(empty)"


def build_system(cfg: dict) -> str:
    from . import memory, tasks
    from .tools.runtime import tools_system_addon

    # Heartbeat: refresh agenda + auto-forge/seed before the model thinks.
    briefing = ""
    try:
        from . import intelligence as intel
        if intel.enabled(cfg):
            intel.tick(cfg, force=False)
            briefing = intel.compile_briefing(cfg)
    except Exception:
        briefing = ""

    leaf = tasks.leaf(cfg)
    leaf_txt = tasks.render_leaf(leaf)
    try:
        mem_txt = memory.compile_context(cfg, leaf)
    except Exception:
        mem_txt = "(memory unavailable)"
    return (
        "You are SUPER — a self-extending intelligence: tools, memory, specialists, "
        "capability forge, and an autonomous agenda. You do not wait to be told what "
        "to improve. You notice gaps, invent missing skills, plan work, and act. "
        "Match the user's language. Be direct; don't over-tool simple chat.\n\n"
        "When you claim facts about this workspace (files, symbols, APIs, commands, configs): "
        "only state what you have evidence for from tools or the context below; "
        "prefer listed repo symbols over memory; put code symbols in backticks; "
        "if unsure something exists, say so instead of inventing it.\n\n"
        "Autonomy loop (every substantive turn):\n"
        "1) Read the Intelligence agenda below — pursue high/critical items without being asked\n"
        "2) search_tools first; if a reusable combo is missing, propose_capability (risk=low)\n"
        "3) add_task for real work with clear done-looks-like; prove nothing you cannot evidence\n"
        "4) create_agent / run_agent for scoped specialists (children only tighten rights)\n"
        "5) memory_add short durable claims; memory_confirm after verification\n"
        "6) self_reflect when stuck; pursue_agenda / dismiss_agenda as you close gaps\n"
        "Never invent tool names; never claim you can eval arbitrary code as a tool.\n\n"
        f"Current task card (if any — not every turn is about this):\n{leaf_txt}\n\n"
        f"Verified context:\n{mem_txt}\n\n"
        f"Working directory: {cfg.get('_root', '.')}\n"
        f"Top level: {repo_overview(cfg)}\n"
        "File/shell tools default to the working directory; absolute paths and ~ work anywhere on this machine."
        f"{briefing}"
        f"{tools_system_addon(cfg)}"
    )


def extract_symbols(text: str) -> list[str]:
    """Candidate code symbols: backticked, imports, dotted names, file-like paths."""
    found: list[str] = []
    found += re.findall(r"`([^`\s][^`]{0,80})`", text)
    found += re.findall(r"^\s*(?:from|import)\s+([\w\.]+)", text, re.M)
    found += re.findall(r"\b([a-zA-Z_][\w]*\.[\w\.]+)\b", text)
    found += re.findall(r"\b([\w\-./]+\.(?:py|js|ts|tsx|go|rs|java|md|json))\b", text)
    seen, out = set(), []
    for s in found:
        s = s.strip().strip(".,:;()[]")
        base = s.split(".")[0].split("/")[0]
        if not s or base in STOPWORDS or len(s) > 120:
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out[:MAX_SYMBOLS_CHECKED]


def check_reply(cfg: dict, reply: str) -> dict:
    """Grounding post-check. Returns {'ok': bool, 'missing': [...], 'checked': n}."""
    from . import gates

    if not cfg.get("gates", {}).get("grounding", True):
        return {"ok": True, "missing": [], "checked": 0, "skipped": True}
    symbols = extract_symbols(reply)
    if not symbols:
        return {"ok": True, "missing": [], "checked": 0}
    ok, missing = gates.check(cfg, symbols)
    return {"ok": ok, "missing": missing, "checked": len(symbols)}


def _score_reply(cfg: dict, reply: str) -> tuple[float, dict]:
    """Verifier score for Best-of-N selection: groundedness first."""
    gate = check_reply(cfg, reply)
    score = 1.0
    if gate["checked"]:
        score = 1.0 if gate["ok"] else 0.0
    # Prefer replies sized within the competence envelope.
    if len(reply.splitlines()) > cfg.get("envelope", {}).get("max_microtask_lines", 50) * 4:
        score -= 0.1
    return score, gate


def answer(cfg: dict, session_id: str, user_text: str) -> tuple[str, dict]:
    """Full pipeline: context -> (tools) model -> grounding check -> persist."""
    from . import llm, sessions

    if not (user_text or "").strip():
        raise ValueError("message must be non-empty")
    hist = sessions.history(cfg, session_id)
    messages = [{"role": "system", "content": build_system(cfg)}]
    for m in hist:
        if m["role"] in ("user", "assistant"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_text})
    sessions.append(cfg, session_id, "user", user_text)

    tools_on = bool((cfg.get("tools") or {}).get("enabled", True))
    if tools_on:
        from .tools.runtime import run_agent
        import uuid as _uuid
        run_cfg = cfg
        # Tag session so spawned specialists appear under this chat.
        if not cfg.get("_session_id"):
            run_cfg = {**cfg, "_session_id": session_id}
            run_cfg["_agent"] = {**(cfg.get("_agent") or {}), "id": "main", "run_id": _uuid.uuid4().hex[:12]}
        reply, _, meta = run_agent(run_cfg, messages)
        gate = check_reply(cfg, reply)
        if isinstance(gate, dict):
            gate = {**gate, "agent": {k: v for k, v in meta.items() if k != "events"}}
        # Persist UI tool trace (same shape as /api/chat/stream)
        events = meta.get("events") if isinstance(meta, dict) else None
        children = None
        try:
            from . import agents as _agents
            children = _agents.list_spans(cfg, session_id=session_id, limit=12)
            # Only attach spans touched this turn if we can filter by run_id
            rid = (run_cfg.get("_agent") or {}).get("run_id")
            if rid and children:
                children = [c for c in children if c.get("run_id") == rid] or children[:4]
        except Exception:
            children = None
        approvals = []
        try:
            from . import approvals as _appr
            for ev in events or []:
                if not isinstance(ev, dict) or ev.get("kind") != "result":
                    continue
                ap = _appr.from_tool_result(
                    str(ev.get("name") or ""),
                    ev.get("content") if isinstance(ev.get("content"), str) else None,
                    ok=bool(ev.get("ok", True)),
                )
                if ap:
                    approvals.append(ap)
        except Exception:
            approvals = []
        sessions.append(
            cfg, session_id, "assistant", reply,
            gate=gate, tools=events or None, children=children,
            approvals=approvals or None,
            thinking=(meta.get("thinking") if isinstance(meta, dict) else None) or None,
            thoughts=(meta.get("thoughts") if isinstance(meta, dict) else None) or None,
            blocks=(meta.get("blocks") if isinstance(meta, dict) else None) or None,
        )
        return reply, gate

    n = max(1, int(cfg.get("envelope", {}).get("best_of_n", 1)))
    stall = max(1, int(cfg.get("envelope", {}).get("early_abort_stall", 3)))
    best_reply, best_gate, best_score = "", {"ok": True, "missing": [], "checked": 0}, -1.0
    misses = 0
    tries = 1 if n <= 1 else n  # N=1 fast path: single call, still verified
    for idx in range(tries):
        try:
            reply = llm.chat(cfg, messages)
        except Exception:
            # transient LLM failure — treat as miss, try next sample unless last
            misses += 1
            if misses >= stall or idx == tries - 1:
                # surface last error if no successful reply yet
                if not best_reply:
                    raise
                break
            continue
        score, gate = _score_reply(cfg, reply)
        if score > best_score:
            best_reply, best_gate, best_score = reply, gate, score
        if gate.get("ok"):
            break
        misses += 1
        if misses >= stall:
            break  # early abort: pass-rate stalled, don't burn steps going nowhere
    sessions.append(cfg, session_id, "assistant", best_reply, gate=best_gate)
    return best_reply, best_gate
