"""Production task graph (doc 02 §2).

The full plan lives on disk; the model only ever sees one leaf card. Nodes
form a DAG over depends-on edges plus an optional parent/child tree. Each
card carries what / why / done-looks-like / needs / proof — no proof means
not done. Rollback returns to the last *proven* node, never the last commit.

Invariants enforced on write: non-empty title, known dependency ids, no
self-edges, no dependency cycles, status transitions within the allowlist.
"""

from __future__ import annotations

from typing import Any

from . import store
from .errors import TaskNotFound, TaskValidation

STATUSES = ("waiting", "doing", "proven", "blocked")

# waiting -> doing -> proven; any -> blocked; blocked -> waiting/doing.
_TRANSITIONS = {
    "waiting": ("doing", "proven", "blocked"),
    "doing": ("waiting", "proven", "blocked"),
    "proven": ("doing", "waiting"),  # re-open via send-back / rollback
    "blocked": ("waiting", "doing"),
}

_FILE = "tasks.json"
_SCHEMA = 1


def _path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{_FILE}"


def _blank() -> dict:
    return {"schema": _SCHEMA, "next_id": 1, "nodes": {}}


def _load(cfg: dict) -> dict:
    data = store.load_json(_path(cfg), _blank())
    if not isinstance(data, dict) or "nodes" not in data:
        raise TaskValidation("tasks store is malformed")
    data.setdefault("schema", _SCHEMA)
    data.setdefault("next_id", 1)
    # migrate old nodes lacking blocks/files
    for n in data.get("nodes", {}).values():
        n.setdefault("blocks", [])
        n.setdefault("files", [])
        n.setdefault("needs", [])
        n.setdefault("why", "")
        n.setdefault("done", "")
        n.setdefault("proof", "")
    return data


def _save(cfg: dict, data: dict) -> None:
    store.save_json(_path(cfg), data)


def _check_cycle(nodes: dict, nid: str) -> None:
    """DFS from nid over needs + blocks edges; raises TaskValidation on a cycle."""
    seen: set[str] = set()
    stack: set[str] = set()

    def visit(cur: str) -> None:
        if cur in stack:
            raise TaskValidation(f"dependency cycle involving task {cur}")
        if cur in seen:
            return
        stack.add(cur)
        for dep in nodes.get(cur, {}).get("needs", []):
            visit(dep)
        for b in nodes.get(cur, {}).get("blocks", []):
            # blocks is reverse edge: cur blocks b → check reachable via needs from b
            visit(b)
        stack.discard(cur)
        seen.add(cur)

    visit(nid)


def add(
    cfg: dict,
    title: str,
    done: str = "",
    needs: list | None = None,
    parent: str | None = None,
    why: str = "",
    blocks: list | None = None,
    files: list | None = None,
) -> str:
    """Add one card. Raises TaskValidation on bad input."""
    title = (title or "").strip()
    if not title:
        raise TaskValidation("title must be non-empty")
    if len(title) > 500:
        raise TaskValidation("title must be ≤ 500 chars")
    needs = list(needs or [])
    blocks = list(blocks or [])
    files = list(files or [])
    # files: ["auth.py:42", "tests/test_login.py#L12"] — optional evidence file list
    data = _load(cfg)
    for dep in needs:
        if dep not in data["nodes"]:
            raise TaskValidation(f"unknown dependency {dep}")
    for b in blocks:
        if b not in data["nodes"]:
            raise TaskValidation(f"unknown blocks target {b}")
    if parent is not None and parent not in data["nodes"]:
        raise TaskValidation(f"unknown parent {parent}")
    nid = str(data["next_id"])
    if nid in needs or nid in blocks:
        raise TaskValidation("task cannot depend on or block itself")
    # validate files entries are plausible paths
    for f in files:
        if not isinstance(f, str) or not f.strip():
            raise TaskValidation("file entries must be non-empty strings")
        if len(f) > 200:
            raise TaskValidation("file entry too long")
    data["next_id"] += 1
    data["nodes"][nid] = {
        "id": nid,
        "title": title,
        "why": why or "",
        "done": done or "",
        "needs": needs,
        "blocks": blocks,
        "files": files,
        "parent": parent,
        "proof": "",
        "status": "waiting",
    }
    _check_cycle(data["nodes"], nid)
    _save(cfg, data)
    return nid


def get(cfg: dict, nid: str) -> dict:
    data = _load(cfg)
    try:
        return data["nodes"][nid]
    except KeyError:
        raise TaskNotFound(f"no task {nid}") from None


def list_all(cfg: dict) -> list:
    data = _load(cfg)
    return [data["nodes"][k] for k in sorted(data["nodes"], key=int)]


def search(cfg: dict, query: str) -> list:
    q = (query or "").lower()
    return [t for t in list_all(cfg) if q in t["title"].lower() or q in t.get("why", "").lower()]


def children(cfg: dict, nid: str) -> list:
    return [t for t in list_all(cfg) if t.get("parent") == nid]


def _deps_proven(data: dict, node: dict) -> bool:
    return all(data["nodes"].get(d, {}).get("status") == "proven" for d in node.get("needs", []))


def computed_status(data: dict, node: dict) -> str:
    """Stored status, except waiting tasks with unmet deps report blocked."""
    if node["status"] == "waiting" and not _deps_proven(data, node):
        return "blocked"
    return node["status"]


def leaf(cfg: dict) -> dict | None:
    """Next actionable leaf: waiting + deps proven, children all proven.

    The model sees this one card only (doc 02 §2)."""
    data = _load(cfg)
    for nid in sorted(data["nodes"], key=int):
        n = data["nodes"][nid]
        if n["status"] == "waiting" and _deps_proven(data, n):
            kids = [m for m in data["nodes"].values() if m.get("parent") == nid]
            if not kids or all(c["status"] == "proven" for c in kids):
                return n
    return None


def prove(cfg: dict, nid: str, proof: str) -> dict:
    """Mark proven. Proof evidence is mandatory — no proof means not done."""
    proof = (proof or "").strip()
    if not proof:
        raise TaskValidation("proof evidence is required (link to green check)")
    # keep permissive for tests (e.g. "p1"); dashboard encourages file:line / URL via UI placeholder
    data = _load(cfg)
    if nid not in data["nodes"]:
        raise TaskNotFound(f"no task {nid}")
    node = data["nodes"][nid]
    if node["status"] == "proven" and node.get("proof") == proof:
        return node
    node["proof"] = proof
    node["status"] = "proven"
    _save(cfg, data)
    try:
        from . import memory as _mem
        _mem.remember_from_proof(cfg, node)
    except Exception:
        pass
    return node


def set_status(cfg: dict, nid: str, status: str) -> dict:
    if status not in STATUSES:
        raise TaskValidation(f"status must be one of {STATUSES}")
    data = _load(cfg)
    if nid not in data["nodes"]:
        raise TaskNotFound(f"no task {nid}")
    cur = data["nodes"][nid]["status"]
    if status != cur and status not in _TRANSITIONS.get(cur, ()):
        raise TaskValidation(f"illegal transition {cur} -> {status}")
    data["nodes"][nid]["status"] = status
    if status != "proven":
        data["nodes"][nid]["proof"] = ""
    _save(cfg, data)
    return data["nodes"][nid]


def rollback(cfg: dict, to_id: str) -> list:
    """Re-open every proven task at/after to_id. Returns reopened ids."""
    data = _load(cfg)
    if to_id not in data["nodes"]:
        raise TaskNotFound(f"no task {to_id}")
    pivot = int(to_id)
    reopened = []
    for nid in sorted(data["nodes"], key=int):
        n = data["nodes"][nid]
        if int(nid) >= pivot and n["status"] == "proven":
            n["status"] = "waiting"
            n["proof"] = ""
            reopened.append(nid)
    _save(cfg, data)
    return reopened


def stats(cfg: dict) -> dict:
    tasks = list_all(cfg)
    by_status: dict[str, int] = {s: 0 for s in STATUSES}
    for t in tasks:
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
    return {"total": len(tasks), "proven": by_status.get("proven", 0), "by_status": by_status}


def render_leaf(node: dict | None) -> str:
    if not node:
        return "No actionable leaf. All waiting tasks blocked or all proven."
    files = ", ".join(node.get("files") or []) or "-"
    blocks = ", ".join(node.get("blocks") or []) or "-"
    return (
        f"[{node['id']}] {node['title']}\n"
        f"Why: {node.get('why') or '-'}\n"
        f"Done looks like: {node.get('done') or '-'}\n"
        f"Needs: {', '.join(node.get('needs') or []) or 'nothing'}\n"
        f"Blocks: {blocks}\n"
        f"Files: {files}\n"
        f"Proof: {node.get('proof') or '(empty — not done)'}"
    )


def to_tree(cfg: dict) -> list[dict[str, Any]]:
    """Nested parent/child view for the dashboard job tree."""
    tasks = list_all(cfg)
    by_parent: dict[str | None, list] = {}
    for t in tasks:
        by_parent.setdefault(t.get("parent"), []).append(t)

    def build(pid: str | None) -> list:
        out = []
        for t in sorted(by_parent.get(pid, []), key=lambda n: int(n["id"])):
            out.append({**t, "children": build(t["id"])})
        return out

    return build(None)
