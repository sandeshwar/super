#!/usr/bin/env python3
"""Minimal stdio MCP server for SUPER E2E tests.

Tools:
  ping() -> "pong"
  echo(text) -> text
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("super-e2e-echo")


@mcp.tool()
def ping() -> str:
    """Health check — returns pong."""
    return "pong"


@mcp.tool()
def echo(text: str) -> str:
    """Echo the given text back."""
    return text


if __name__ == "__main__":
    mcp.run(transport="stdio")
