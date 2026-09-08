"""ReAct-style agent loop with on-demand tool activation (LangGraph-shaped, stdlib).

Flow: system prompt + discovery tools → model may search/activate → call tools →
append tool results → repeat until text reply or max_steps.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Iterator

from .base import ToolResult
from .catalog import get_tool
from .discovery import is_callable, schemas_for_llm


Emit = Callable[[dict], None]


def _media_payload(result: ToolResult) -> list[dict]:
    raw = (result.data or {}).get("media") or []
    if not raw:
        return []
    try:
        from ..media import public_part
        return [public_part(p) for p in raw if isinstance(p, dict)]
    except Exception:
        return [p for p in raw if isinstance(p, dict) and p.get("src")]


def _canvas_payload(result: ToolResult) -> dict | None:
    raw = (result.data or {}).get("canvas")
    if not isinstance(raw, dict):
        return None
    try:
        from ..canvas import public_part
        return public_part(raw)
    except Exception:
        return raw if raw.get("id") else None


def tools_system_addon(cfg: dict) -> str:
    t = cfg.get("tools") or {}
    if not t.get("enabled", True):
        return ""
    try:
        from .langchain_bridge import ensure_bridge
        ensure_bridge(cfg)
    except Exception:
        pass
    if t.get("discovery", True):
        return (
            "\n\nTools: Discover and use tools on demand (built-in and third-party share one catalog). "
            "Workflow:\n"
            "1) search_tools (keywords) or list_tool_groups (categories) — summaries only\n"
            "2) describe_tool for 1–3 candidates you might use — full schema\n"
            "3) activate_tools with those names, then call them\n"
            "Do NOT call tools for greetings, thanks, acknowledgments, opinions, or short chat — "
            "answer those in plain text. Never invent tool names. "
            "For current events / the live web, prefer a search tool over guessing. "
            "For repo questions, prefer read/search tools over guessing. "
            "Specialists: list_agents / create_agent / run_agent when a scoped helper helps; "
            "children inherit your tools, gates, and budgets (can only tighten). "
            "Capability forge: propose_capability to invent a composite (or http) tool from "
            "existing tools; list_capabilities / test_capability / install_capability; "
            "low-risk composites auto-install, others need human approve in chat. "
            "MCP: list_mcp_servers / add_mcp_server / set_mcp_server / remove_mcp_server / "
            "reload_mcp to manage servers; tools appear as mcp_<server>__<tool> "
            "(search_tools / activate_tools; results are untrusted). "
            "Intelligence: self_reflect refreshes the autonomous agenda; list_agenda / "
            "pursue_agenda / dismiss_agenda — pursue high/critical gaps without waiting. "
            "Memory: memory_search before re-deriving known facts; memory_add for durable "
            "claims worth recalling (prefer short atomic facts). memory_confirm after you "
            "verify a claim. Auto-stored search/prove claims show up under Verified context. "
            "Canvas: when the user benefits from a standalone visual (web page, image, video, "
            "markdown/HTML doc), search_tools query=canvas then activate canvas_present "
            "(kinds: url|image|video|markdown|html|file|doc). Use canvas_update to refresh, "
            "canvas_close to collapse. Prefer canvas over dumping long HTML/tables in chat. "
            "Keep tool results focused — use offsets/limits."
        )
    return (
        "\n\nTools: Enabled tools are available. Prefer tools over guessing for live or workspace facts. "
        "Do NOT call tools for simple conversational replies. "
        "Keep arguments tight; large outputs are truncated."
    )


def execute_tool(cfg: dict, name: str, arguments: dict | str) -> ToolResult:
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            return ToolResult(False, f"invalid JSON arguments for {name}")
    if not isinstance(arguments, dict):
        arguments = {}
    spec = get_tool(name)
    if not spec:
        return ToolResult(False, f"unknown tool: {name}")
    if not is_callable(cfg, name):
        hint = "search_tools then activate_tools first" if (cfg.get("tools") or {}).get("discovery", True) else "enable group in settings"
        try:
            from .. import agents as _agents
            ok, why = _agents.can_call_tool(cfg, name)
            if not ok and why:
                hint = why
        except Exception:
            pass
        return ToolResult(False, f"tool not callable: {name} ({hint})")
    try:
        result = spec.handler(cfg, arguments)
    except Exception as e:
        return ToolResult(False, f"{type(e).__name__}: {e}")
    if not isinstance(result, ToolResult):
        result = ToolResult(True, str(result))
    try:
        from .. import media as _media
        result = _media.enrich_tool_result(cfg, result, tool_name=name)
    except Exception:
        pass
    try:
        from .. import memory as _mem
        _mem.maybe_auto_from_tool(cfg, name, arguments, result)
    except Exception:
        pass
    limit = int((cfg.get("tools") or {}).get("max_result_chars", 8000))
    return result.truncated(limit)


def _execute_tool_with_child_stream(
    cfg: dict, name: str, arguments: dict | str,
) -> Iterator[tuple[str, Any]]:
    """Run a tool; for run_agent, yield ('ev', sse_dict) live then ('result', ToolResult).

    Child agents are blocking; we run them on a worker thread so the parent SSE
    loop can flush child_agent oneliners while the specialist works.
    """
    if name != "run_agent":
        yield ("result", execute_tool(cfg, name, arguments))
        return

    import queue
    import threading

    q: queue.Queue = queue.Queue()
    prev_emit = cfg.get("_emit")

    def emit(ev: dict) -> None:
        q.put(("ev", ev))
        if callable(prev_emit):
            try:
                prev_emit(ev)
            except Exception:
                pass

    cfg["_emit"] = emit
    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["result"] = execute_tool(cfg, name, arguments)
        except Exception as e:
            box["error"] = e
        finally:
            q.put(("done", None))

    t = threading.Thread(target=worker, daemon=True, name="super-run-agent")
    t.start()
    try:
        while True:
            kind, payload = q.get()
            if kind == "ev" and isinstance(payload, dict):
                yield ("ev", payload)
            elif kind == "done":
                break
    finally:
        t.join(timeout=2.0)
        if prev_emit is None:
            cfg.pop("_emit", None)
        else:
            cfg["_emit"] = prev_emit
    if "error" in box:
        raise box["error"]
    yield ("result", box["result"])


def _parse_tool_calls(message: dict) -> list[dict]:
    """Normalize Ollama / OpenAI-style tool_calls."""
    raw = message.get("tool_calls") or []
    out = []
    for i, tc in enumerate(raw):
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        name = fn.get("name") or tc.get("name") or ""
        args = fn.get("arguments", tc.get("arguments", {}))
        tid = tc.get("id") or f"call_{i}_{name}"
        if not name:
            continue
        out.append({"id": tid, "name": name, "arguments": args})
    return out


def run_agent_stdlib(
    cfg: dict,
    messages: list[dict],
    *,
    on_event: Emit | None = None,
) -> tuple[str, list[dict], dict]:
    """Stdlib ReAct loop (no LangGraph). Used directly and as langgraph fallback."""
    from .. import llm

    cfg.pop("_tool_session", None)  # fresh activation set per turn
    max_steps = max(1, int(cfg.get("envelope", {}).get("max_steps_per_task", 20)))
    eff = cfg.get("_agent_effective") if isinstance(cfg.get("_agent_effective"), dict) else None
    if eff and eff.get("max_steps"):
        max_steps = max(1, min(max_steps, int(eff["max_steps"])))
    tool_trace: list[dict] = []
    tool_events: list[dict] = []  # UI-shaped {kind, name, ...}
    usage_steps: list[dict] = []
    thinking_parts: list[str] = []
    text_parts: list[str] = []
    blocks: list[dict] = []
    reply = ""

    for step in range(max_steps):
        tools = schemas_for_llm(cfg)
        msg, usage = llm.chat_message(cfg, messages, tools=tools or None)
        if usage:
            usage_steps.append({**usage, "step": step})
            if on_event:
                on_event({"type": "llm_stats", "step": step, "stats": usage})
        content = (msg.get("content") or "") if isinstance(msg, dict) else str(msg)
        th = (msg.get("thinking") or "") if isinstance(msg, dict) else ""
        if th:
            thinking_parts.append(th)
            blocks.append({"kind": "thinking", "text": th, "step": step})
            if on_event:
                on_event({"type": "thinking_step", "step": step, "index": len(thinking_parts) - 1, "content": th})
                on_event({"type": "thinking", "step": step, "content": th})
        if content:
            text_parts.append(content)
            blocks.append({"kind": "text", "text": content, "step": step})
        tool_calls = _parse_tool_calls(msg if isinstance(msg, dict) else {})
        if not tool_calls:
            reply = "\n\n".join(t for t in text_parts if t) or content or ""
            messages.append({"role": "assistant", "content": content or reply})
            break
        # Keep assistant tool_call turn for protocol fidelity
        messages.append({
            "role": "assistant",
            "content": content or "",
            "tool_calls": msg.get("tool_calls"),
        })
        if on_event:
            on_event({"type": "assistant_tool_calls", "step": step, "calls": tool_calls, "content": content})
        for call in tool_calls:
            tool_events.append({
                "kind": "call",
                "name": call["name"],
                "arguments": call.get("arguments"),
            })
            if on_event:
                on_event({"type": "tool_call", "step": step, "id": call["id"], "name": call["name"], "arguments": call["arguments"]})
            result = execute_tool(cfg, call["name"], call["arguments"])
            tool_trace.append({"name": call["name"], "ok": result.ok, "taint": result.taint})
            payload = result.content
            media = _media_payload(result)
            canvas = _canvas_payload(result)
            tool_events.append({
                "kind": "result",
                "name": call["name"],
                "ok": result.ok,
                "content": payload[:2000] if isinstance(payload, str) else str(payload)[:2000],
                **({"media": media} if media else {}),
                **({"canvas": canvas} if canvas else {}),
            })
            if media:
                blocks.append({"kind": "media", "media": media, "step": step, "tool": call["name"]})
            if canvas:
                blocks.append({"kind": "canvas", "canvas": canvas, "step": step, "tool": call["name"]})
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "name": call["name"],
                "content": payload,
            })
            if on_event:
                ev_tr: dict[str, Any] = {
                    "type": "tool_result",
                    "step": step,
                    "id": call["id"],
                    "name": call["name"],
                    "ok": result.ok,
                    "content": payload[:2000],
                    "taint": result.taint,
                }
                if media:
                    ev_tr["media"] = media
                if canvas:
                    ev_tr["canvas"] = canvas
                on_event(ev_tr)
    else:
        reply = reply or "(stopped: max tool steps reached)"
        text_parts.append(reply)
        blocks.append({"kind": "text", "text": reply, "step": max_steps})
        messages.append({"role": "assistant", "content": reply})

    meta = {
        "steps": len(tool_trace),
        "tools": tool_trace,
        "events": tool_events,
        "runtime": "stdlib",
        "llm_stats": usage_steps[-1] if usage_steps else None,
        "llm_stats_steps": usage_steps,
        "thinking": "\n\n".join(thinking_parts) if thinking_parts else "",
        "thoughts": list(thinking_parts),
        "blocks": list(blocks),
    }
    return reply, messages, meta


def run_agent(
    cfg: dict,
    messages: list[dict],
    *,
    on_event: Emit | None = None,
) -> tuple[str, list[dict], dict]:
    """Non-streaming multi-step tool loop. Returns (reply, messages, meta)."""
    try:
        from .langgraph_runtime import run_agent_langgraph, should_use_langgraph
        if should_use_langgraph(cfg):
            return run_agent_langgraph(cfg, messages, on_event=on_event)
    except Exception:
        pass

    return run_agent_stdlib(cfg, messages, on_event=on_event)


def run_agent_stream(
    cfg: dict,
    messages: list[dict],
) -> Iterator[dict[str, Any]]:
    """Yield SSE-shaped events with live token deltas (tools-on path).

    Uses streaming completions so the UI sees tokens as they arrive. Tool-call
    rounds still stream any preamble text, then emit tool_call/tool_result.

    Emits a chronological ``blocks`` timeline (thinking / text / media) so the UI
    can render think→chat→think→chat instead of stacking all thoughts first.
    """
    from .. import llm

    try:
        from .langchain_bridge import ensure_bridge
        ensure_bridge(cfg)
    except Exception:
        pass

    cfg.pop("_tool_session", None)
    max_steps = max(1, int(cfg.get("envelope", {}).get("max_steps_per_task", 20)))
    eff = cfg.get("_agent_effective") if isinstance(cfg.get("_agent_effective"), dict) else None
    if eff and eff.get("max_steps"):
        max_steps = max(1, min(max_steps, int(eff["max_steps"])))
    tool_trace: list[dict] = []
    usage_steps: list[dict] = []
    thinking_parts: list[str] = []
    text_parts: list[str] = []
    blocks: list[dict[str, Any]] = []

    def _meta(reply: str) -> dict[str, Any]:
        thinking = "\n\n".join(thinking_parts) if thinking_parts else ""
        return {
            "agent_meta": {
                "steps": len(tool_trace),
                "tools": tool_trace,
                "llm_stats": usage_steps[-1] if usage_steps else None,
                "llm_stats_steps": usage_steps,
                "thinking": thinking,
                "thoughts": list(thinking_parts),
                "blocks": list(blocks),
            },
            "reply": reply,
            "thinking": thinking,
            "thoughts": list(thinking_parts),
            "blocks": list(blocks),
        }

    def _close_step(step: int, step_thinking: str, content: str) -> Iterator[dict[str, Any]]:
        if step_thinking:
            thinking_parts.append(step_thinking)
            blocks.append({"kind": "thinking", "text": step_thinking, "step": step})
            yield {
                "thinking_step": {
                    "step": step,
                    "index": len(thinking_parts) - 1,
                    "content": step_thinking,
                }
            }
        if content:
            text_parts.append(content)
            blocks.append({"kind": "text", "text": content, "step": step})
            yield {"text_step": {"step": step, "content": content}}

    for step in range(max_steps):
        tools = schemas_for_llm(cfg)
        content = ""
        step_thinking = ""
        tool_calls: list[dict] = []
        raw_tool_calls = None
        usage = None
        streamed_any = False
        stream_ok = False

        try:
            t0 = time.monotonic()
            t_first: float | None = None
            chars = 0
            for ev in llm.chat_stream(cfg, messages, tools=tools or None):
                if "thinking_delta" in ev and ev["thinking_delta"]:
                    streamed_any = True
                    step_thinking += ev["thinking_delta"]
                    now = time.monotonic()
                    live = {
                        "source": "live",
                        "step": step,
                        "prompt_ms": round((now - t0) * 1000, 1),
                    }
                    yield {"thinking_delta": ev["thinking_delta"], "step": step, "llm_stats": live}
                if "delta" in ev and ev["delta"]:
                    streamed_any = True
                    d = ev["delta"]
                    content += d
                    chars += len(d)
                    now = time.monotonic()
                    tok = max(1, chars // 4)
                    if t_first is None:
                        t_first = now
                        live = {
                            "source": "live",
                            "step": step,
                            "completion_tokens": tok,
                            "prompt_ms": round((t_first - t0) * 1000, 1),
                            "total_ms": round((now - t0) * 1000, 1),
                        }
                    else:
                        elapsed = max(1e-3, now - t_first)
                        live = {
                            "source": "live",
                            "step": step,
                            "completion_tokens": tok,
                            "decode_tps": round(tok / elapsed, 2),
                            "prompt_ms": round((t_first - t0) * 1000, 1),
                            "eval_ms": round(elapsed * 1000, 1),
                            "total_ms": round((now - t0) * 1000, 1),
                        }
                    yield {"delta": d, "step": step, "llm_stats": live}
                if "tool_calls" in ev and isinstance(ev["tool_calls"], list):
                    raw_tool_calls = ev["tool_calls"]
                    tool_calls = _parse_tool_calls({"tool_calls": ev["tool_calls"]})
                if "message" in ev and isinstance(ev["message"], dict):
                    msg = ev["message"]
                    content = msg.get("content") or content
                    if msg.get("thinking"):
                        step_thinking = msg.get("thinking") or step_thinking
                    if msg.get("tool_calls"):
                        raw_tool_calls = msg.get("tool_calls")
                        tool_calls = _parse_tool_calls(msg)
                    stream_ok = True
                if "usage" in ev and isinstance(ev["usage"], dict):
                    usage = ev["usage"]
            if not stream_ok and not content and not tool_calls and not step_thinking:
                raise RuntimeError("empty stream completion")
        except Exception:
            # Provider may not support tools+stream — fall back to blocking turn.
            msg, usage = llm.chat_message(cfg, messages, tools=tools or None)
            content = (msg.get("content") or "") if isinstance(msg, dict) else str(msg)
            step_thinking = (msg.get("thinking") or "") if isinstance(msg, dict) else ""
            raw_tool_calls = msg.get("tool_calls") if isinstance(msg, dict) else None
            tool_calls = _parse_tool_calls(msg if isinstance(msg, dict) else {})
            if step_thinking and not streamed_any:
                chunk = 48
                for i in range(0, len(step_thinking), chunk):
                    yield {"thinking_delta": step_thinking[i : i + chunk], "step": step}
            if content and not streamed_any:
                chunk = 24
                for i in range(0, len(content), chunk):
                    yield {"delta": content[i : i + chunk], "step": step}
                streamed_any = True

        yield from _close_step(step, step_thinking, content)

        if usage:
            row = {**usage, "step": step}
            usage_steps.append(row)
            yield {"llm_stats": row}

        if not tool_calls:
            reply = "\n\n".join(t for t in text_parts if t) or content or ""
            messages.append({"role": "assistant", "content": content or reply})
            yield _meta(reply)
            return

        # Tool round: keep assistant tool_call turn for protocol fidelity
        messages.append({
            "role": "assistant",
            "content": content or "",
            "tool_calls": raw_tool_calls or [
                {
                    "id": c["id"],
                    "type": "function",
                    "function": {
                        "name": c["name"],
                        "arguments": c["arguments"] if isinstance(c["arguments"], str)
                        else json.dumps(c["arguments"] or {}),
                    },
                }
                for c in tool_calls
            ],
        })
        for call in tool_calls:
            yield {
                "tool_call": {
                    "step": step,
                    "id": call["id"],
                    "name": call["name"],
                    "arguments": call["arguments"],
                }
            }
            result = None
            for kind, payload in _execute_tool_with_child_stream(cfg, call["name"], call["arguments"]):
                if kind == "ev" and isinstance(payload, dict):
                    yield payload
                elif kind == "result":
                    result = payload
            if result is None:
                result = ToolResult(False, "tool produced no result")
            tool_trace.append({"name": call["name"], "ok": result.ok, "taint": result.taint})
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "name": call["name"],
                "content": result.content,
            })
            media = _media_payload(result)
            canvas = _canvas_payload(result)
            if media:
                blocks.append({"kind": "media", "media": media, "step": step, "tool": call["name"]})
            if canvas:
                blocks.append({"kind": "canvas", "canvas": canvas, "step": step, "tool": call["name"]})
            yield {
                "tool_result": {
                    "step": step,
                    "id": call["id"],
                    "name": call["name"],
                    "ok": result.ok,
                    "content": result.content[:4000],
                    "taint": result.taint,
                    **({"media": media} if media else {}),
                    **({"canvas": canvas} if canvas else {}),
                }
            }
            if canvas:
                yield {"canvas": canvas}

    reply = "(stopped: max tool steps reached)"
    text_parts.append(reply)
    blocks.append({"kind": "text", "text": reply, "step": max_steps})
    messages.append({"role": "assistant", "content": reply})
    yield {"delta": reply, "step": max_steps}
    yield _meta(reply)
