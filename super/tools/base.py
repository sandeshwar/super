"""Tool primitives: specs, results, truncation, path safety."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable


Handler = Callable[[dict, dict], "ToolResult"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    group: str
    summary: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object
    handler: Handler
    risk: str = "low"  # low | medium | high
    discovery: bool = False  # meta-tools always exposed when discovery on
    lazy_pack: str | None = None  # unloadable until activate/describe loads pack
    keywords: str = ""  # extra search tokens (aliases, categories)

    def openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {"type": "object", "properties": {}},
            },
        }

    @property
    def is_lazy(self) -> bool:
        return bool(self.lazy_pack)


@dataclass
class ToolResult:
    ok: bool
    content: str
    data: dict[str, Any] = field(default_factory=dict)
    taint: str = "local-exec"

    def truncated(self, limit: int) -> "ToolResult":
        if limit <= 0 or len(self.content) <= limit:
            return self
        head = max(200, limit - 80)
        note = f"\n…[truncated {len(self.content) - head} chars; use a narrower query]"
        return ToolResult(ok=self.ok, content=self.content[:head] + note, data=self.data, taint=self.taint)


def dump_json(obj: Any, limit: int = 12000) -> str:
    try:
        text = json.dumps(obj, indent=2, default=str)
    except Exception:
        text = str(obj)
    if len(text) > limit:
        return text[: limit - 40] + "\n…[truncated]"
    return text


def safe_path(cfg: dict, rel: str) -> str:
    """Resolve path under workspace root; refuse escapes."""
    root = os.path.abspath(cfg.get("_root") or os.getcwd())
    rel = (rel or "").strip() or "."
    if os.path.isabs(rel):
        cand = os.path.abspath(rel)
    else:
        cand = os.path.abspath(os.path.join(root, rel))
    try:
        if os.path.commonpath([root, cand]) != root:
            raise ValueError(f"path escapes workspace: {rel}")
    except ValueError:
        raise ValueError(f"path escapes workspace: {rel}") from None
    return cand


def rel_display(cfg: dict, abs_path: str) -> str:
    root = os.path.abspath(cfg.get("_root") or os.getcwd())
    try:
        return os.path.relpath(abs_path, root)
    except ValueError:
        return abs_path
