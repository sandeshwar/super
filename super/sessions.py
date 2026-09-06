"""Durable chat sessions with provenance.

Each session is an ordered message log; assistant messages carry the gate
verdict that accompanied them, so chat evidence feeds the same catch-rate
accounting as the write path. Storage is a single locked JSON document with
atomic saves; history windows keep model context bounded.
"""

from __future__ import annotations

import time
import uuid

from . import store
from .errors import StoreError

FILE = "sessions.json"
MAX_MESSAGE_CHARS = 20000
MAX_MESSAGES_PER_SESSION = 500


def _path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{FILE}"


def _load(cfg: dict) -> dict:
    data = store.load_json(_path(cfg), {"sessions": {}})
    if not isinstance(data, dict) or not isinstance(data.get("sessions"), dict):
        raise StoreError("sessions store is malformed")
    return data


def _save(cfg: dict, data: dict) -> None:
    store.save_json(_path(cfg), data)


def create(cfg: dict, title: str = "New chat") -> str:
    title = (title or "New chat").strip()[:120] or "New chat"
    sid = uuid.uuid4().hex[:12]
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    data = _load(cfg)
    data["sessions"][sid] = {"id": sid, "title": title, "created": now,
                             "updated": now, "messages": []}
    _save(cfg, data)
    return sid


def get(cfg: dict, sid: str) -> dict | None:
    return _load(cfg)["sessions"].get(sid)


def list_all(cfg: dict) -> list:
    data = _load(cfg)
    out = [{"id": s["id"], "title": s["title"], "updated": s["updated"],
            "n": len(s["messages"])} for s in data["sessions"].values()]
    out.sort(key=lambda s: s["updated"], reverse=True)
    return out


def append(cfg: dict, sid: str, role: str, content: str, gate: dict | None = None) -> dict:
    if role not in ("user", "assistant", "system"):
        raise StoreError(f"invalid role {role}")
    content = (content or "")[:MAX_MESSAGE_CHARS]
    if role == "user" and not content.strip():
        raise StoreError("user message must be non-empty")
    data = _load(cfg)
    s = data["sessions"].get(sid)
    if not s:
        raise KeyError(f"no session {sid}")
    if len(s["messages"]) >= MAX_MESSAGES_PER_SESSION:
        # Compact: drop oldest user/assistant pair, keep provenance.
        s["messages"] = s["messages"][2:]
    msg = {"role": role, "content": content, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if gate is not None:
        msg["gate"] = gate
    s["messages"].append(msg)
    s["updated"] = msg["ts"]
    if len(s["messages"]) == 1 and role == "user" and s["title"] == "New chat":
        s["title"] = content[:40]
    _save(cfg, data)
    return msg


def history(cfg: dict, sid: str, limit: int = 20) -> list:
    s = get(cfg, sid)
    if not s:
        raise KeyError(f"no session {sid}")
    return s["messages"][-max(1, limit):]


def delete(cfg: dict, sid: str) -> bool:
    data = _load(cfg)
    if sid not in data["sessions"]:
        return False
    del data["sessions"][sid]
    _save(cfg, data)
    return True


def rename(cfg: dict, sid: str, title: str) -> dict:
    title = (title or "").strip()[:60] or "New chat"
    if len(title) < 2:
        raise StoreError("title must be at least 2 characters")
    data = _load(cfg)
    s = data["sessions"].get(sid)
    if not s:
        raise KeyError(f"no session {sid}")
    s["title"] = title
    s["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _save(cfg, data)
    return s


def branch(cfg: dict, source_sid: str, up_to: int, title: str | None = None) -> str:
    """Fork session at message index up_to (inclusive). Returns new sid."""
    data = _load(cfg)
    src = data["sessions"].get(source_sid)
    if not src:
        raise KeyError(f"no session {source_sid}")
    msgs = src.get("messages", [])
    if up_to < 0 or up_to >= len(msgs):
        up_to = len(msgs) - 1
    new_title = (title or f"Branch of {src.get('title','')}")[:60] or "Branched chat"
    sid = create(cfg, new_title)
    # copy history slice
    data = _load(cfg)  # reload after create
    dst = data["sessions"][sid]
    dst["messages"] = [dict(m) for m in msgs[: up_to + 1]]
    dst["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _save(cfg, data)
    return sid


def edit_message(cfg: dict, sid: str, idx: int, new_content: str) -> dict:
    """Edit user message at idx, truncate after, mark session. Returns session."""
    new_content = (new_content or "").strip()[:MAX_MESSAGE_CHARS]
    if not new_content:
        raise StoreError("new content must be non-empty")
    data = _load(cfg)
    s = data["sessions"].get(sid)
    if not s:
        raise KeyError(f"no session {sid}")
    msgs = s.get("messages", [])
    if idx < 0 or idx >= len(msgs):
        raise StoreError("message index out of range")
    if msgs[idx].get("role") != "user":
        raise StoreError("only user messages can be edited")
    msgs[idx]["content"] = new_content
    msgs[idx]["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    # drop everything after edited message (will regenerate)
    s["messages"] = msgs[: idx + 1]
    s["updated"] = msgs[idx]["ts"]
    _save(cfg, data)
    return s


_TITLE_STOPWORDS = frozenset(
    "a an the and or but with from that this into have will would could should "
    "there their what when where which while about into over under again once "
    "here how why for are was were been has had not you your our out can just "
    "please help need want know think make take show tell give than then them they "
    "its also very much many some any all each".split()
)


def _extractive_title(text: str, max_len: int = 48) -> str:
    """Keyword-frequency extractive title: top informative words in first-seen
    order, 3-6 words. No model needed; used when the LLM summarizer is down."""
    import re as _re
    words = [w for w in _re.findall(r"[A-Za-z][A-Za-z0-9'\-]*", text.lower())
             if w not in _TITLE_STOPWORDS and len(w) > 2]
    if not words:
        return ""
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    ranked: list[str] = []
    for w in words:  # first-seen order, deduped, frequent first on ties
        if w not in ranked:
            ranked.append(w)
    ranked.sort(key=lambda w: freq[w], reverse=True)
    # keep narrative order for readability: reorder top picks by first position
    first_pos = {w: words.index(w) for w in ranked[:8]}
    picks = sorted(ranked[:6], key=lambda w: first_pos[w])[:6]
    while len(picks) > 3 and sum(len(p) + 1 for p in picks) - 1 > max_len:
        # drop lowest-frequency tail word until it fits
        tail = min(picks, key=lambda w: (freq[w], -first_pos[w]))
        picks.remove(tail)
    title = " ".join(picks).strip().capitalize()[:max_len]
    return title if len(title) >= 3 else ""


def summarize_title(cfg: dict, sid: str, max_len: int = 48) -> str:
    """Generate a 3-6 word title: LLM summary first, extractive keywords next,
    first user message as the last resort."""
    s = get(cfg, sid)
    if not s:
        raise KeyError(f"no session {sid}")
    msgs = s.get("messages", [])[:12]
    if not msgs:
        return s.get("title", "New chat")[:max_len]
    # Build prompt: concise title
    convo = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in msgs if m["role"] in ("user", "assistant"))[:2000]
    prompt = f"Summarize this chat in 3-6 words as a title, no quotes, no punctuation prefix. Chat:\n{convo}\nTitle:"
    try:
        from . import llm as _llm
        raw = _llm.chat(cfg, [{"role": "user", "content": prompt}])
        # take first line, strip
        title = raw.strip().splitlines()[0].strip().strip('"').strip("'").strip()[:max_len]
        # remove trailing period
        title = title.rstrip(".")
        if len(title) >= 3 and len(title.split()) <= 8:
            return title
    except Exception:
        pass
    # extractive fallback: keyword title from the conversation
    try:
        extractive = _extractive_title(convo, max_len)
        if extractive:
            return extractive
    except Exception:
        pass
    # fallback: first user message
    for m in msgs:
        if m["role"] == "user" and m["content"].strip():
            return m["content"].strip().splitlines()[0][:max_len]
    return s.get("title", "New chat")[:max_len]
