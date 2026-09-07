"""Optional LangGraph ToolNode loop. Falls back to stdlib runtime when absent."""

from __future__ import annotations

from typing import Any, Iterator


def should_use_langgraph(cfg: dict) -> bool:
    runtime = ((cfg.get("tools") or {}).get("runtime") or "auto").lower()
    if runtime == "stdlib":
        return False
    if runtime == "langgraph":
        return True
    # auto
    try:
        from .langchain_bridge import langgraph_available
        return langgraph_available()
    except Exception:
        return False


def run_agent_langgraph(
    cfg: dict,
    messages: list[dict],
    *,
    on_event=None,
) -> tuple[str, list[dict], dict]:
    """LangGraph prebuilt create_react_agent over SUPER's callable tools.

    Still uses SUPER execute_tool so gates/truncation/activation apply.
    """
    from langchain_core.tools import StructuredTool
    from langgraph.prebuilt import create_react_agent

    from .. import llm
    from .discovery import schemas_for_llm
    from .runtime import execute_tool

    # Build LC tools that proxy back into SUPER (respects activation)
    schemas = schemas_for_llm(cfg)
    lc_tools = []
    for sch in schemas:
        fn = sch.get("function") or {}
        name = fn.get("name")
        if not name:
            continue
        desc = fn.get("description") or name
        params = fn.get("parameters") or {"type": "object", "properties": {}}

        def _make(n: str):
            def _run(**kwargs: Any) -> str:
                r = execute_tool(cfg, n, kwargs)
                return r.content
            return _run

        try:
            lc_tools.append(
                StructuredTool.from_function(
                    func=_make(name),
                    name=name,
                    description=desc,
                    # args schema optional — from_function infers poorly; pass kwargs freely
                )
            )
        except Exception:
            # minimal tool without pydantic model
            t = StructuredTool.from_function(func=_make(name), name=name, description=desc)
            lc_tools.append(t)

    # Custom chat model adapter: wrap SUPER llm.chat_message as a tiny Runnable
    # Prefer binding via a simple loop if no ChatOllama — keep dependency light.
    # Many local setups use Ollama; try ChatOllama, else degrade to stdlib.
    try:
        from langchain_community.chat_models import ChatOllama
        endpoint = cfg["llm"]["endpoint"].rstrip("/")
        # ChatOllama wants base_url without /api
        base = endpoint.replace("/api", "") if endpoint.endswith("/api") else endpoint
        model = ChatOllama(model=cfg["llm"]["model"], base_url=base, temperature=0)
        agent = create_react_agent(model, lc_tools)
        # Convert messages
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
        lc_msgs = []
        for m in messages:
            role, content = m.get("role"), m.get("content") or ""
            if role == "system":
                lc_msgs.append(SystemMessage(content=content))
            elif role == "user":
                lc_msgs.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_msgs.append(AIMessage(content=content))
            elif role == "tool":
                lc_msgs.append(ToolMessage(content=content, tool_call_id=m.get("tool_call_id") or "t"))
        result = agent.invoke({"messages": lc_msgs})
        out_msgs = result.get("messages") or []
        reply = ""
        tool_trace = []
        for m in out_msgs:
            if isinstance(m, AIMessage):
                reply = m.content if isinstance(m.content, str) else str(m.content)
            if getattr(m, "type", "") == "tool" or isinstance(m, ToolMessage):
                tool_trace.append({"name": getattr(m, "name", "tool"), "ok": True})
                if on_event:
                    on_event({"type": "tool_result", "name": getattr(m, "name", "tool"), "content": str(m.content)[:2000]})
        messages.extend([{"role": "assistant", "content": reply}])
        return reply, messages, {"steps": len(tool_trace), "tools": tool_trace, "runtime": "langgraph"}
    except Exception:
        # Fall back to the stdlib loop directly — do NOT call run_agent(),
        # which would re-enter this langgraph path and blow the stack.
        from .runtime import run_agent_stdlib
        reply, messages, meta = run_agent_stdlib(cfg, messages, on_event=on_event)
        meta = {**meta, "runtime": "stdlib_fallback"}
        return reply, messages, meta
