"""Built-in tool handlers grouped by capability."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .base import ToolResult, dump_json, rel_display, safe_path


# ── files ──────────────────────────────────────────────────────────────

def list_dir(cfg: dict, args: dict) -> ToolResult:
    path = safe_path(cfg, args.get("path") or ".")
    if not os.path.isdir(path):
        return ToolResult(False, f"not a directory: {rel_display(cfg, path)}")
    entries = []
    try:
        for name in sorted(os.listdir(path)):
            if name.startswith(".super"):
                continue
            full = os.path.join(path, name)
            kind = "dir" if os.path.isdir(full) else "file"
            size = os.path.getsize(full) if kind == "file" else None
            entries.append({"name": name, "kind": kind, "size": size})
    except OSError as e:
        return ToolResult(False, str(e))
    return ToolResult(True, dump_json(entries), {"entries": entries})


def read_file(cfg: dict, args: dict) -> ToolResult:
    from .tool_config import resolve_builtin
    bc = resolve_builtin(cfg, "read_file")
    path = safe_path(cfg, args.get("path") or "")
    if not os.path.isfile(path):
        return ToolResult(False, f"not a file: {rel_display(cfg, path)}")
    offset = max(0, int(args.get("offset") or 0))
    default_limit = int(bc.get("default_limit") or 200)
    limit = int(args.get("limit") or default_limit)
    limit = max(1, min(limit, 500))
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        return ToolResult(False, str(e))
    total = len(lines)
    chunk = lines[offset : offset + limit]
    numbered = "".join(f"{offset + i + 1:>6}|{line}" for i, line in enumerate(chunk))
    header = f"{rel_display(cfg, path)} lines {offset + 1}-{offset + len(chunk)} of {total}\n"
    return ToolResult(True, header + numbered, {"path": rel_display(cfg, path), "total": total})


def write_file(cfg: dict, args: dict) -> ToolResult:
    path = safe_path(cfg, args.get("path") or "")
    content = args.get("content")
    if content is None:
        return ToolResult(False, "content required")
    content = str(content)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        return ToolResult(False, str(e))
    return ToolResult(True, f"wrote {rel_display(cfg, path)} ({len(content)} chars)")


def edit_file(cfg: dict, args: dict) -> ToolResult:
    path = safe_path(cfg, args.get("path") or "")
    old = args.get("old")
    new = args.get("new")
    if old is None or new is None:
        return ToolResult(False, "old and new required")
    old, new = str(old), str(new)
    if not os.path.isfile(path):
        return ToolResult(False, f"not a file: {rel_display(cfg, path)}")
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return ToolResult(False, str(e))
    count = text.count(old)
    if count == 0:
        return ToolResult(False, "old string not found")
    replace_all = bool(args.get("replace_all"))
    if count > 1 and not replace_all:
        return ToolResult(False, f"old string appears {count} times; set replace_all=true or make old unique")
    text = text.replace(old, new) if replace_all else text.replace(old, new, 1)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        return ToolResult(False, str(e))
    return ToolResult(True, f"edited {rel_display(cfg, path)} ({count if replace_all else 1} replacement(s))")


def mkdir_tool(cfg: dict, args: dict) -> ToolResult:
    path = safe_path(cfg, args.get("path") or "")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        return ToolResult(False, str(e))
    return ToolResult(True, f"directory ready: {rel_display(cfg, path)}")


def delete_file(cfg: dict, args: dict) -> ToolResult:
    path = safe_path(cfg, args.get("path") or "")
    if not os.path.exists(path):
        return ToolResult(False, f"missing: {rel_display(cfg, path)}")
    try:
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    except OSError as e:
        return ToolResult(False, str(e))
    return ToolResult(True, f"deleted {rel_display(cfg, path)}")


# ── search ─────────────────────────────────────────────────────────────

def grep_tool(cfg: dict, args: dict) -> ToolResult:
    from .tool_config import resolve_builtin
    bc = resolve_builtin(cfg, "grep")
    pattern = str(args.get("pattern") or "")
    if not pattern:
        return ToolResult(False, "pattern required")
    path = safe_path(cfg, args.get("path") or ".")
    glob = args.get("glob")
    default_hits = int(bc.get("max_hits") or 40)
    max_hits = max(1, min(int(args.get("max_hits") or default_hits), 100))
    root = cfg.get("_root") or os.getcwd()
    rg = shutil.which("rg")
    hits: list[str] = []
    if rg:
        cmd = [rg, "--line-number", "--no-heading", "--color", "never", "-m", str(max_hits), pattern]
        if glob:
            cmd.extend(["--glob", str(glob)])
        cmd.append(path)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=root)
            hits = [ln for ln in (r.stdout or "").splitlines() if ln][:max_hits]
        except Exception as e:
            return ToolResult(False, str(e))
    else:
        try:
            cre = re.compile(pattern)
        except re.error as e:
            return ToolResult(False, f"bad pattern: {e}")
        walk_root = path if os.path.isdir(path) else os.path.dirname(path)
        files = [path] if os.path.isfile(path) else []
        if not files:
            for dirpath, dirnames, filenames in os.walk(walk_root):
                dirnames[:] = [d for d in dirnames if d not in (".git", ".super", "node_modules", "__pycache__", ".venv")]
                for fn in filenames:
                    if glob and not Path(fn).match(str(glob)):
                        continue
                    files.append(os.path.join(dirpath, fn))
                    if len(files) > 2000:
                        break
        for fp in files:
            try:
                with open(fp, encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if cre.search(line):
                            hits.append(f"{rel_display(cfg, fp)}:{i}:{line.rstrip()}")
                            if len(hits) >= max_hits:
                                break
            except OSError:
                continue
            if len(hits) >= max_hits:
                break
    return ToolResult(True, "\n".join(hits) or "(no matches)", {"count": len(hits)})


def glob_files(cfg: dict, args: dict) -> ToolResult:
    pattern = str(args.get("pattern") or "**/*")
    root = Path(safe_path(cfg, args.get("path") or "."))
    matches: list[str] = []
    try:
        for p in root.glob(pattern):
            if any(part in (".git", ".super", "node_modules", "__pycache__", ".venv") for part in p.parts):
                continue
            matches.append(rel_display(cfg, str(p)))
            if len(matches) >= 200:
                break
    except Exception as e:
        return ToolResult(False, str(e))
    return ToolResult(True, "\n".join(matches) or "(no matches)", {"count": len(matches)})


def find_symbol(cfg: dict, args: dict) -> ToolResult:
    name = str(args.get("name") or "").strip()
    if not name:
        return ToolResult(False, "name required")
    # reuse grep with common definition patterns
    patterns = [
        rf"\b(def|class|function|const|let|var|fn|type|interface)\s+{re.escape(name)}\b",
        rf"\b{re.escape(name)}\s*=",
    ]
    combined: list[str] = []
    for pat in patterns:
        r = grep_tool(cfg, {"pattern": pat, "path": args.get("path") or ".", "max_hits": 20})
        if r.ok and r.content != "(no matches)":
            combined.extend(r.content.splitlines())
    # dedupe
    seen, out = set(), []
    for ln in combined:
        if ln not in seen:
            seen.add(ln)
            out.append(ln)
    return ToolResult(True, "\n".join(out[:40]) or "(no matches)", {"count": len(out)})


# ── shell ──────────────────────────────────────────────────────────────

_BLOCKED = re.compile(
    r"\b(rm\s+-rf\s+/|mkfs|dd\s+if=|shutdown|reboot|:(){:|fork\s*\()\b",
    re.I,
)


def run_command(cfg: dict, args: dict) -> ToolResult:
    from .tool_config import resolve_builtin
    bc = resolve_builtin(cfg, "run_command")
    cmd = str(args.get("command") or "").strip()
    if not cmd:
        return ToolResult(False, "command required")
    if _BLOCKED.search(cmd):
        return ToolResult(False, "command blocked by safety filter")
    cwd = safe_path(cfg, args.get("cwd") or ".")
    default_to = int(bc.get("default_timeout_s") or 60)
    timeout = max(1, min(int(args.get("timeout_s") or default_to), 300))
    shell = (bc.get("shell") or "").strip() or None
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=cwd,
            executable=shell,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(False, f"timed out after {timeout}s")
    except OSError as e:
        return ToolResult(False, str(e))
    out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
    return ToolResult(
        r.returncode == 0,
        out.strip() or f"(exit {r.returncode}, empty output)",
        {"exit_code": r.returncode},
    )


# ── git ────────────────────────────────────────────────────────────────

def _git(cfg: dict, argv: list[str], timeout: int = 30) -> ToolResult:
    root = cfg.get("_root") or os.getcwd()
    if not shutil.which("git"):
        return ToolResult(False, "git not installed")
    try:
        r = subprocess.run(["git", *argv], capture_output=True, text=True, timeout=timeout, cwd=root)
    except Exception as e:
        return ToolResult(False, str(e))
    text = (r.stdout or r.stderr or "").strip()
    return ToolResult(r.returncode == 0, text or "(empty)", {"exit_code": r.returncode})


def git_status(cfg: dict, args: dict) -> ToolResult:
    return _git(cfg, ["status", "--short", "--branch"])


def git_diff(cfg: dict, args: dict) -> ToolResult:
    argv = ["diff"]
    if args.get("staged"):
        argv.append("--staged")
    path = args.get("path")
    if path:
        argv.extend(["--", str(path)])
    return _git(cfg, argv)


def git_log(cfg: dict, args: dict) -> ToolResult:
    n = max(1, min(int(args.get("limit") or 10), 50))
    return _git(cfg, ["log", f"-{n}", "--oneline", "--decorate"])


def git_show(cfg: dict, args: dict) -> ToolResult:
    ref = str(args.get("ref") or "HEAD")
    return _git(cfg, ["show", "--stat", ref])


# ── web ────────────────────────────────────────────────────────────────

def fetch_url(cfg: dict, args: dict) -> ToolResult:
    from .tool_config import resolve_builtin
    from .. import net as _net
    bc = resolve_builtin(cfg, "fetch_url")
    url = str(args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return ToolResult(False, "url must be http(s)")
    default_to = int(bc.get("timeout_s") or 15)
    timeout = max(1, min(int(args.get("timeout_s") or default_to), 60))
    max_bytes = max(1000, min(int(bc.get("max_bytes") or 200_000), 2_000_000))
    ua = str(bc.get("user_agent") or "super-harness/1.0")
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        with _net.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes)
            ctype = resp.headers.get("Content-Type", "")
        text = raw.decode("utf-8", errors="replace")
    except Exception as e:
        return ToolResult(False, str(e), taint="untrusted")
    return ToolResult(True, text, {"content_type": ctype}, taint="untrusted")


# ── tasks / memory / project ─────────────────────────────────────────

def list_tasks(cfg: dict, args: dict) -> ToolResult:
    from .. import tasks as T
    try:
        items = T.list_all(cfg)
    except Exception as e:
        return ToolResult(False, str(e))
    status = args.get("status")
    if status:
        items = [t for t in items if isinstance(t, dict) and t.get("status") == status]
    return ToolResult(True, dump_json(items[:100]), {"count": len(items)})


def get_task(cfg: dict, args: dict) -> ToolResult:
    from .. import tasks as T
    tid = str(args.get("id") or "")
    if not tid:
        return ToolResult(False, "id required")
    try:
        t = T.get(cfg, tid)
    except Exception as e:
        return ToolResult(False, str(e))
    if not t:
        return ToolResult(False, f"no task {tid}")
    return ToolResult(True, dump_json(t), {"id": tid})


def add_task(cfg: dict, args: dict) -> ToolResult:
    from .. import tasks as T
    title = str(args.get("title") or "").strip()
    if not title:
        return ToolResult(False, "title required")
    try:
        nid = T.add(
            cfg,
            title,
            done=str(args.get("done_looks_like") or args.get("done") or ""),
            parent=args.get("parent"),
        )
        node = T.get(cfg, nid)
    except Exception as e:
        return ToolResult(False, str(e))
    return ToolResult(True, dump_json(node), {"id": nid})


def memory_search(cfg: dict, args: dict) -> ToolResult:
    from .. import memory
    q = str(args.get("query") or "").strip()
    try:
        hits = memory.search(cfg, q, limit=20)
        if not hits:
            text = memory.compile_context(cfg, {"id": "?", "title": q or "search"}, limit=12)
            return ToolResult(True, text or "(no memory hits)")
    except Exception as e:
        return ToolResult(False, str(e))
    return ToolResult(True, dump_json(hits[:20]))


def memory_add(cfg: dict, args: dict) -> ToolResult:
    from .. import memory
    claim = str(args.get("claim") or "").strip()
    if not claim:
        return ToolResult(False, "claim required")
    ver = str(args.get("verification") or "unverified").strip() or "unverified"
    try:
        stored = memory.remember(
            cfg, claim,
            source=str(args.get("source") or "agent"),
            task_id=str(args.get("task_id") or ""),
            verification=ver if ver in ("unverified", "verified", "human") else "unverified",
        )
    except Exception as e:
        return ToolResult(False, str(e))
    return ToolResult(
        True,
        dump_json({"claim": stored, "note": "Unverified — confirm in chat if you trust it"}),
        data={"id": stored.get("id"), "verification": stored.get("verification")},
    )


def memory_confirm(cfg: dict, args: dict) -> ToolResult:
    from .. import memory
    try:
        cid = args.get("id")
        idx = args.get("index")
        ver = str(args.get("verification") or "verified").strip() or "verified"
        claim = memory.confirm(
            cfg,
            index=int(idx) if idx is not None and str(idx) != "" else None,
            claim_id=int(cid) if cid is not None and str(cid) != "" else None,
            verification=ver,
        )
    except Exception as e:
        return ToolResult(False, str(e))
    return ToolResult(True, dump_json(claim))

def repo_tree(cfg: dict, args: dict) -> ToolResult:
    root = Path(safe_path(cfg, args.get("path") or "."))
    max_depth = max(1, min(int(args.get("depth") or 3), 6))
    lines: list[str] = []

    def walk(p: Path, depth: int, prefix: str = "") -> None:
        if depth > max_depth or len(lines) > 400:
            return
        try:
            kids = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except OSError:
            return
        for i, kid in enumerate(kids):
            if kid.name in (".git", ".super", "node_modules", "__pycache__", ".venv", "dist", "build"):
                continue
            last = i == len(kids) - 1
            branch = "└── " if last else "├── "
            lines.append(f"{prefix}{branch}{kid.name}{'/' if kid.is_dir() else ''}")
            if kid.is_dir():
                walk(kid, depth + 1, prefix + ("    " if last else "│   "))

    lines.append(str(root) + "/")
    walk(root, 1)
    return ToolResult(True, "\n".join(lines), {"lines": len(lines)})


def read_config_tool(cfg: dict, args: dict) -> ToolResult:
    from .. import config as C
    view = C.public_view(cfg)
    section = args.get("section")
    if section:
        return ToolResult(True, dump_json(view.get(str(section), {})))
    # strip large mcp env already gone
    return ToolResult(True, dump_json(view))
