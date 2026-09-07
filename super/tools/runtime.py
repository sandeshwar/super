"""ReAct-style agent loop with on-demand tool activation (LangGraph-shaped, stdlib).

Flow: system prompt + discovery tools → model may search/activate → call tools →
append tool results → repeat until text reply or max_steps.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Iterator

from .base import ToolResult
from .catalog import get_tool
from .discovery import is_callable, schemas_for_llm


Emit = Callable[[dict], None]


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
            "\n\nTools: You can discover tools on demand (built-in and third-party share one catalog). "
            "Workflow:\n"
            "1) search_tools (keywords) or list_tool_groups (categories) — summaries only\n"
            "2) describe_tool for 1–3 candidates you might use — full schema\n"
            "3) activate_tools with those names, then call them\n"
            "Do NOT call tools for simple greetings, yes/no, or short conversational replies — "
            "answer those in plain text. Never invent tool names. Prefer search/read over guessing. "
            "Keep tool results focused — use offsets/limits."
        )
    return (
        "\n\nTools: Enabled project tools are available. Prefer reading/searching before editing. "
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
        return ToolResult(False, f"tool not callable: {name} ({hint})")
    try:
        result = spec.handler(cfg, arguments)
    except Exception as e:
        return ToolResult(False, f"{type(e).__name__}: {e}")
    if not isinstance(result, ToolResult):
        return ToolResult(True, str(result))
    limit = int((cfg.get("tools") or {}).get("max_result_chars", 8000))
    return result.truncated(limit)


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
    tool_trace: list[dict] = []
    tool_events: list[dict] = []  # UI-shaped {kind, name, ...}
    usage_steps: list[dict] = []
    reply = ""

    for step in range(max_steps):
        tools = schemas_for_llm(cfg)
        msg, usage = llm.chat_message(cfg, messages, tools=tools or None)
        if usage:
            usage_steps.append({**usage, "step": step})
            if on_event:
                on_event({"type": "llm_stats", "step": step, "stats": usage})
        content = (msg.get("content") or "") if isinstance(msg, dict) else str(msg)
        tool_calls = _parse_tool_calls(msg if isinstance(msg, dict) else {})
        if not tool_calls:
            reply = content or ""
            messages.append({"role": "assistant", "content": reply})
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
            tool_events.append({
                "kind": "result",
                "name": call["name"],
                "ok": result.ok,
                "content": payload[:2000] if isinstance(payload, str) else str(payload)[:2000],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "name": call["name"],
                "content": payload,
            })
            if on_event:
                on_event({
                    "type": "tool_result",
                    "step": step,
                    "id": call["id"],
                    "name": call["name"],
                    "ok": result.ok,
                    "content": payload[:2000],
                    "taint": result.taint,
                })
    else:
        reply = reply or "(stopped: max tool steps reached)"
        messages.append({"role": "assistant", "content": reply})

    meta = {
        "steps": len(tool_trace),
        "tools": tool_trace,
        "events": tool_events,
        "runtime": "stdlib",
        "llm_stats": usage_steps[-1] if usage_steps else None,
        "llm_stats_steps": usage_steps,
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
    """Yield SSE-shaped events: tool_call, tool_result, llm_stats, delta, done-meta."""
    from .. import llm

    try:
        from .langchain_bridge import ensure_bridge
        ensure_bridge(cfg)
    except Exception:
        pass

    cfg.pop("_tool_session", None)
    max_steps = max(1, int(cfg.get("envelope", {}).get("max_steps_per_task", 20)))
    tool_trace: list[dict] = []
    usage_steps: list[dict] = []
    reply = ""

    for step in range(max_steps):
        tools = schemas_for_llm(cfg)
        # Prefer non-stream for tool rounds (need full message with tool_calls).
        msg, usage = llm.chat_message(cfg, messages, tools=tools or None)
        if usage:
            row = {**usage, "step": step}
            usage_steps.append(row)
            yield {"llm_stats": row}
        content = (msg.get("content") or "") if isinstance(msg, dict) else str(msg)
        tool_calls = _parse_tool_calls(msg if isinstance(msg, dict) else {})

        if not tool_calls:
            reply = content or ""
            messages.append({"role": "assistant", "content": reply})
            if reply:
                chunk = 48
                for i in range(0, len(reply), chunk):
                    yield {"delta": reply[i : i + chunk]}
            yield {
                "agent_meta": {
                    "steps": len(tool_trace),
                    "tools": tool_trace,
                    "llm_stats": usage_steps[-1] if usage_steps else None,
                    "llm_stats_steps": usage_steps,
                },
                "reply": reply,
            }
            return

        messages.append({
            "role": "assistant",
            "content": content or "",
            "tool_calls": msg.get("tool_calls"),
        })
        if content:
            yield {"delta": content + "\n"}
        for call in tool_calls:
            yield {"tool_call": {"step": step, "id": call["id"], "name": call["name"], "arguments": call["arguments"]}}
            result = execute_tool(cfg, call["name"], call["arguments"])
            tool_trace.append({"name": call["name"], "ok": result.ok, "taint": result.taint})
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "name": call["name"],
                "content": result.content,
            })
            yield {
                "tool_result": {
                    "step": step,
                    "id": call["id"],
                    "name": call["name"],
                    "ok": result.ok,
                    "content": result.content[:4000],
                    "taint": result.taint,
                }
            }

    reply = "(stopped: max tool steps reached)"
    messages.append({"role": "assistant", "content": reply})
    yield {"delta": reply}
    yield {
        "agent_meta": {
            "steps": len(tool_trace),
            "tools": tool_trace,
            "llm_stats": usage_steps[-1] if usage_steps else None,
            "llm_stats_steps": usage_steps,
        },
        "reply": reply,
    }
