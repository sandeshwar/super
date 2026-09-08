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


def create(
    cfg: dict,
    title: str = "New chat",
    *,
    parent: str | None = None,
    span_id: str | None = None,
    agent_id: str | None = None,
    kind: str = "chat",
) -> str:
    title = (title or "New chat").strip()[:120] or "New chat"
    sid = uuid.uuid4().hex[:12]
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    data = _load(cfg)
    row: dict = {
        "id": sid, "title": title, "created": now,
        "updated": now, "messages": [], "kind": kind or "chat",
    }
    if parent:
        row["parent"] = str(parent)
        row["kind"] = kind or "agent"
    if span_id:
        row["span_id"] = str(span_id)
    if agent_id:
        row["agent_id"] = str(agent_id)
    data["sessions"][sid] = row
    _save(cfg, data)
    return sid


def get(cfg: dict, sid: str) -> dict | None:
    return _load(cfg)["sessions"].get(sid)


def list_all(cfg: dict) -> list:
    """Top-level chats only (agent child sessions nest under parent.spans)."""
    from . import agents as _agents
    data = _load(cfg)
    by_sid = _agents.spans_by_session(cfg)
    out = []
    for s in data["sessions"].values():
        if s.get("parent"):
            continue  # child agent transcripts — opened via span click
        out.append({
            "id": s["id"],
            "title": s["title"],
            "updated": s["updated"],
            "n": len(s["messages"]),
            "kind": s.get("kind") or "chat",
            "spans": by_sid.get(s["id"], []),
        })
    out.sort(key=lambda s: s["updated"], reverse=True)
    return out


def append(
    cfg: dict,
    sid: str,
    role: str,
    content: str,
    gate: dict | None = None,
    tools: list | None = None,
    children: list | None = None,
    approvals: list | None = None,
    thinking: str | None = None,
    media: list | None = None,
    thoughts: list | None = None,
    blocks: list | None = None,
) -> dict:
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

    clean_tools = None
    if tools:
        clean_tools = []
        for t in tools[:80]:
            if not isinstance(t, dict):
                continue
            row = {
                "kind": t.get("kind"),
                "name": str(t.get("name") or "")[:80],
            }
            if "ok" in t:
                row["ok"] = bool(t.get("ok"))
            if t.get("arguments") is not None:
                row["arguments"] = t.get("arguments")
            content_t = t.get("content")
            if isinstance(content_t, str) and content_t:
                row["content"] = content_t[:2000]
            media_t = t.get("media")
            if isinstance(media_t, list) and media_t:
                try:
                    from . import media as _media
                    row["media"] = [
                        _media.public_part(p) for p in media_t[:12] if isinstance(p, dict)
                    ]
                except Exception:
                    row["media"] = [p for p in media_t[:12] if isinstance(p, dict) and p.get("src")]
            canvas_t = t.get("canvas")
            if isinstance(canvas_t, dict):
                try:
                    from . import canvas as _canvas
                    pub = _canvas.public_part(canvas_t)
                    if pub:
                        row["canvas"] = pub
                except Exception:
                    if canvas_t.get("id"):
                        row["canvas"] = canvas_t
            clean_tools.append(row)

    msg_media = list(media) if isinstance(media, list) else []
    if role == "assistant":
        try:
            from . import media as _media
            content, collected = _media.collect_message_media(
                cfg, content=content, tools=clean_tools, extra=msg_media,
            )
            content = content[:MAX_MESSAGE_CHARS]
            msg_media = collected
        except Exception:
            pass

    msg = {"role": role, "content": content, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    clean_thoughts: list[str] = []
    clean_blocks: list[dict] = []
    if role == "assistant":
        if isinstance(blocks, list):
            for b in blocks[:80]:
                if not isinstance(b, dict):
                    continue
                kind = str(b.get("kind") or "")
                if kind == "thinking":
                    text = str(b.get("text") or "")[:MAX_MESSAGE_CHARS]
                    if not text.strip():
                        continue
                    clean_blocks.append({
                        "kind": "thinking",
                        "text": text,
                        **({"step": b["step"]} if isinstance(b.get("step"), int) else {}),
                    })
                    clean_thoughts.append(text)
                elif kind == "text":
                    text = str(b.get("text") or "")[:MAX_MESSAGE_CHARS]
                    if not text.strip():
                        continue
                    clean_blocks.append({
                        "kind": "text",
                        "text": text,
                        **({"step": b["step"]} if isinstance(b.get("step"), int) else {}),
                    })
                elif kind == "media":
                    media_b = b.get("media")
                    if not isinstance(media_b, list) or not media_b:
                        continue
                    try:
                        from . import media as _media
                        parts = [_media.public_part(p) for p in media_b[:12] if isinstance(p, dict)]
                    except Exception:
                        parts = [p for p in media_b[:12] if isinstance(p, dict) and p.get("src")]
                    if parts:
                        row_b: dict = {"kind": "media", "media": parts}
                        if isinstance(b.get("step"), int):
                            row_b["step"] = b["step"]
                        if isinstance(b.get("tool"), str) and b["tool"]:
                            row_b["tool"] = b["tool"][:80]
                        clean_blocks.append(row_b)
                elif kind == "canvas":
                    canvas_b = b.get("canvas")
                    if not isinstance(canvas_b, dict):
                        continue
                    try:
                        from . import canvas as _canvas
                        pub = _canvas.public_part(canvas_b)
                    except Exception:
                        pub = canvas_b if canvas_b.get("id") else None
                    if pub:
                        row_b = {"kind": "canvas", "canvas": pub}
                        if isinstance(b.get("step"), int):
                            row_b["step"] = b["step"]
                        if isinstance(b.get("tool"), str) and b["tool"]:
                            row_b["tool"] = b["tool"][:80]
                        clean_blocks.append(row_b)
        if isinstance(thoughts, list) and not clean_thoughts:
            for t in thoughts[:40]:
                if isinstance(t, str) and t.strip():
                    clean_thoughts.append(t[:MAX_MESSAGE_CHARS])
        if not clean_thoughts and thinking:
            clean_thoughts = [thinking[:MAX_MESSAGE_CHARS]]
        if clean_blocks:
            msg["blocks"] = clean_blocks
            # Prefer joined text blocks as content when caller only sent final reply
            joined_text = "\n\n".join(
                str(b.get("text") or "") for b in clean_blocks if b.get("kind") == "text"
            ).strip()
            if joined_text:
                msg["content"] = joined_text[:MAX_MESSAGE_CHARS]
                content = msg["content"]
        if clean_thoughts:
            msg["thoughts"] = clean_thoughts
            msg["thinking"] = "\n\n".join(clean_thoughts)[:MAX_MESSAGE_CHARS]
        elif thinking:
            msg["thinking"] = str(thinking)[:MAX_MESSAGE_CHARS]
    if msg_media and role == "assistant":
        try:
            from . import media as _media
            msg["media"] = [_media.public_part(p) for p in msg_media[:24] if isinstance(p, dict)]
        except Exception:
            msg["media"] = [p for p in msg_media[:24] if isinstance(p, dict) and p.get("src")]
    if role == "assistant":
        # Aggregate canvas artifacts from blocks + tools onto the message.
        canvas_by_id: dict[str, dict] = {}
        for b in clean_blocks:
            if b.get("kind") == "canvas" and isinstance(b.get("canvas"), dict):
                c = b["canvas"]
                cid = str(c.get("id") or "")
                if cid:
                    canvas_by_id[cid] = c
        if clean_tools:
            for t in clean_tools:
                c = t.get("canvas") if isinstance(t, dict) else None
                if isinstance(c, dict) and c.get("id"):
                    canvas_by_id[str(c["id"])] = c
        if canvas_by_id:
            msg["canvas"] = list(canvas_by_id.values())[:24]
    if gate is not None:
        msg["gate"] = gate
    if clean_tools:
        msg["tools"] = clean_tools
    if children:
        clean_c = []
        for c in children[:20]:
            if not isinstance(c, dict) or not c.get("span_id"):
                continue
            clean_c.append({
                "span_id": str(c.get("span_id"))[:24],
                "agent_id": str(c.get("agent_id") or "")[:40],
                "agent_name": str(c.get("agent_name") or "")[:80],
                "role": str(c.get("role") or "")[:32],
                "status": str(c.get("status") or "done")[:16],
                "summary": str(c.get("summary") or "")[:160],
                "goal": str(c.get("goal") or "")[:200],
                "steps": c.get("steps"),
                "child_session_id": str(c.get("child_session_id") or "")[:24] or None,
            })
        if clean_c:
            msg["children"] = clean_c
    if approvals:
        clean_a = []
        for a in approvals[:20]:
            if not isinstance(a, dict) or not a.get("kind") or a.get("id") is None:
                continue
            clean_a.append({
                "kind": str(a.get("kind"))[:24],
                "id": a.get("id") if isinstance(a.get("id"), int) else str(a.get("id"))[:40],
                "title": str(a.get("title") or "")[:160],
                "detail": str(a.get("detail") or "")[:240],
                "status": str(a.get("status") or "pending")[:16],
                "meta": a.get("meta") if isinstance(a.get("meta"), dict) else {},
            })
        if clean_a:
            msg["approvals"] = clean_a
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
    # Cascade: remove nested agent child sessions
    drop = [sid] + [
        k for k, v in data["sessions"].items()
        if isinstance(v, dict) and v.get("parent") == sid
    ]
    for k in drop:
        data["sessions"].pop(k, None)
    _save(cfg, data)
    return True


def write_agent_transcript(
    cfg: dict,
    sid: str,
    llm_messages: list,
    *,
    gate: dict | None = None,
    tool_events: list | None = None,
) -> dict:
    """Replace a child agent session with a UI transcript from the ReAct run."""
    data = _load(cfg)
    s = data["sessions"].get(sid)
    if not s:
        raise KeyError(f"no session {sid}")
    ui: list[dict] = []
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    i = 0
    msgs = [m for m in (llm_messages or []) if isinstance(m, dict)]
    while i < len(msgs):
        m = msgs[i]
        role = m.get("role")
        if role == "system":
            i += 1
            continue
        if role == "user":
            content = str(m.get("content") or "")[:MAX_MESSAGE_CHARS]
            if content.strip():
                ui.append({"role": "user", "content": content, "ts": now})
            i += 1
            continue
        if role == "assistant":
            content = str(m.get("content") or "")
            tools_ui: list[dict] = []
            raw_tcs = m.get("tool_calls") or []
            call_meta: list[tuple[str, str, object]] = []
            if isinstance(raw_tcs, list):
                for tc in raw_tcs:
                    if not isinstance(tc, dict):
                        continue
                    fn = tc.get("function") or {}
                    name = str(fn.get("name") or tc.get("name") or "")
                    tid = str(tc.get("id") or "")
                    args = fn.get("arguments", tc.get("arguments"))
                    if name:
                        call_meta.append((tid, name, args))
                        tools_ui.append({"kind": "call", "name": name, "arguments": args})
            i += 1
            # Consume following tool role messages as results
            results_left = list(call_meta)
            while i < len(msgs) and msgs[i].get("role") == "tool":
                tr = msgs[i]
                name = str(tr.get("name") or (results_left[0][1] if results_left else "tool"))
                if results_left:
                    results_left.pop(0)
                body = str(tr.get("content") or "")[:2000]
                tools_ui.append({"kind": "result", "name": name, "ok": True, "content": body})
                i += 1
            row: dict = {
                "role": "assistant",
                "content": content[:MAX_MESSAGE_CHARS],
                "ts": now,
            }
            if tools_ui:
                row["tools"] = tools_ui
            # Attach gate only on the final text-only assistant turn
            if gate is not None and not call_meta:
                row["gate"] = gate
                gate = None  # only once
            ui.append(row)
            continue
        i += 1
    # If we have leftover tool_events and no tools on messages, attach to last assistant
    if tool_events and ui:
        last = ui[-1]
        if last.get("role") == "assistant" and not last.get("tools"):
            clean = []
            for t in tool_events[:40]:
                if isinstance(t, dict) and t.get("name"):
                    clean.append(t)
            if clean:
                last["tools"] = clean
    if gate is not None and ui and ui[-1].get("role") == "assistant" and "gate" not in ui[-1]:
        ui[-1]["gate"] = gate
    s["messages"] = ui
    s["updated"] = now
    _save(cfg, data)
    return s


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
