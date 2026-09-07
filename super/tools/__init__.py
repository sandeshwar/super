"""Agent tools: registry, discovery, builtins, and ReAct-style runtime.

Designed like a LangGraph tool node without the dependency: the model only
sees discovery meta-tools (+ any activated tools), searches the catalog on
demand, then calls concrete tools. Context stays small; Settings toggles
groups/individuals.
"""

from .catalog import GROUPS, TOOLS, catalog_public, get_tool, search_tools
from .runtime import run_agent, run_agent_stream

__all__ = [
    "GROUPS",
    "TOOLS",
    "catalog_public",
    "get_tool",
    "search_tools",
    "run_agent",
    "run_agent_stream",
]
