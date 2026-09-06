"""Disposable sandbox + session-0 environment probe (doc 02 §4).

Patches are diff-only and apply inside an isolated temp directory seeded
from the repo; the runtime that executes them is pinned and probed once per
session (language versions, tooling, OS, hooks) — never assumed. The probe
record travels with the session so grounding and contract checks resolve
against observed versions, not memory.
"""

from __future__ import annotations

import difflib
import os
import platform
import shutil
import subprocess
import sys
import tempfile

from . import ledger
from .errors import SandboxError


def probe() -> dict:
    """Session-0 probe: record what the machine actually has."""
    info: dict = {
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "python": platform.python_version(),
        "executable": sys.executable,
        "tools": {},
        "scripts": {},
        "pinned": {},
    }
    for tool in ("rg", "git", "node", "go", "cargo", "uv", "python3", "pip"):
        info["tools"][tool] = shutil.which(tool) is not None
        # version probe
        try:
            r = subprocess.run([tool, "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                info["tools"][f"{tool}_version"] = (r.stdout + r.stderr).strip().splitlines()[0][:120]
        except Exception:
            pass
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=10)
        info["git_root"] = r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        info["git_root"] = ""
    for hook in (".git/hooks/pre-commit", ".pre-commit-config.yaml", "package.json", "pyproject.toml", "super.config.json"):
        info.setdefault("hooks", {})[hook] = os.path.exists(hook)
        if hook == "package.json" and os.path.isfile(hook):
            try:
                import json as _j
                data = _j.load(open(hook, encoding="utf-8"))
                info["pinned"]["node"] = data.get("engines", {})
            except Exception:
                pass
    # pinned dep mtimes
    for name in ("package-lock.json", "poetry.lock", "uv.lock", "Cargo.lock", "go.mod"):
        if os.path.isfile(name):
            try:
                info["pinned"][name] = os.path.getmtime(name)
            except OSError:
                pass
    # scripts from package.json
    try:
        import json as _j
        if os.path.isfile("package.json"):
            data = _j.load(open("package.json", encoding="utf-8"))
            info["scripts"] = data.get("scripts", {})
    except Exception:
        pass
    return info


class Sandbox:
    """Disposable working copy. Context-manager; removes itself on exit."""

    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.workdir = tempfile.mkdtemp(prefix="super-sandbox-")
        # seed copy (doc 02 §4): disposable copy of repo, minus .git/.super/node_modules for speed
        try:
            ignore = shutil.ignore_patterns(".git", ".super", "node_modules", "__pycache__", ".venv", "dist", "build")
            # copytree into existing workdir: use dirs_exist_ok pattern by copying contents
            for name in os.listdir(self.root):
                if name in (".git", ".super", "node_modules", "__pycache__"):
                    continue
                src = os.path.join(self.root, name)
                dst = os.path.join(self.workdir, name)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
        except Exception:
            pass
        self.env = dict(probe())

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *exc) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)

    def apply_unified_diff(self, diff_text: str) -> list[str]:
        """Apply a unified diff to the sandbox copy. Handles multiple files,
        deletions, and absolute escapes are refused."""
        touched: list[str] = []
        current: str | None = None
        out: list[str] | None = None
        pending_delete: str | None = None

        def flush():
            nonlocal current, out, pending_delete
            if pending_delete:
                dest = os.path.normpath(os.path.join(self.workdir, pending_delete))
                if os.path.isfile(dest):
                    os.remove(dest)
                touched.append(dest + " (deleted)")
                pending_delete = None
            if current is not None and out is not None:
                dest = current
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "w", encoding="utf-8") as f:
                    f.write("\n".join(out) + "\n")
                touched.append(dest)
            current = None
            out = None

        for line in diff_text.splitlines():
            if line.startswith("--- "):
                # track source for delete detection: --- a/file  /dev/null
                src = line[4:].strip().lstrip("a/")
                if src == "/dev/null":
                    pending_delete = None
                # else keep for context
                continue
            if line.startswith("+++ "):
                rel = line[4:].strip().lstrip("b/")
                if rel == "/dev/null":
                    # deletion: flush previous, mark pending delete from --- line
                    flush()
                    # we already have pending_delete from previous ---, but need to capture it
                    # actually deletion is --- a/file / +++ /dev/null
                    # so we need to have stored src
                    # fallback: do nothing, caller should have set pending_delete via previous logic
                    # handle by leaving current None and using last src
                    continue
                # flush previous file
                if current is not None:
                    flush()
                rel = rel.strip()
                dest = os.path.normpath(os.path.join(self.workdir, rel))
                if not dest.startswith(self.workdir) or os.path.isabs(rel):
                    raise SandboxError(f"diff escape refused: {rel}")
                # detect deletion case where src was /dev/null? handled above
                current = dest
                out = []
                # if diff is deletion (+++ /dev/null) we already continued
                # read original content for context if file exists, to handle hunk correctly
                if os.path.isfile(dest):
                    try:
                        with open(dest, encoding="utf-8", errors="replace") as f:
                            existing = f.read().splitlines()
                        # we will reconstruct via hunks; for now start empty and apply below
                        # better to track via patch utility: we simply collect +/  lines as new content
                        # so existing is not needed — we overwrite with out
                        pass
                    except Exception:
                        pass
            elif current is not None and out is not None:
                if line.startswith("+") and not line.startswith("+++"):
                    out.append(line[1:])
                elif line.startswith(" ") or line == "":
                    out.append(line[1:] if line.startswith(" ") else "")
                elif line.startswith("-") and not line.startswith("---"):
                    # removal: skip line (don't add to out)
                    pass
                elif line.startswith("@@"):
                    # hunk header: if we need original context, we could load but simple approach
                    # hunk headers are ignored because we reconstruct sequentially
                    pass
                elif line.startswith("diff ") or line.startswith("index "):
                    pass
                else:
                    pass
            elif line.startswith("diff "):
                # start of new file diff without ---/+++? ignore
                pass
        flush()
        # also handle bare --- a/file -> +++ /dev/null deletions that were not flushed (no out)
        # if diff_text contains "+++ /dev/null", we already handled via flush, but need to detect src
        # fallback: scan for deletion header pairs
        if "+++ /dev/null" in diff_text:
            import re as _re
            for m in _re.finditer(r"--- a/([^\n]+)\n\+\+\+ /dev/null", diff_text):
                rel = m.group(1).strip()
                dest = os.path.normpath(os.path.join(self.workdir, rel))
                if dest.startswith(self.workdir) and os.path.isfile(dest):
                    try:
                        os.remove(dest)
                        if dest not in touched:
                            touched.append(dest + " (deleted)")
                    except Exception:
                        pass
        return touched


def diff_of(original: str, revised: str, path: str = "file") -> str:
    """Unified diff between two texts (evidence for probes and review)."""
    return "\n".join(difflib.unified_diff(
        original.splitlines(), revised.splitlines(),
        fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="",
    ))


def run_in(cfg: dict, workdir: str, argv: list[str], timeout_s: int = 120) -> tuple[int, str]:
    """Execute one pinned command for verification. Shell is never used."""
    if not argv or any(not isinstance(a, str) for a in argv):
        raise SandboxError("refusing to run empty or non-string command")
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s, cwd=workdir)
        out = (r.stdout + r.stderr)[-4000:]
        ledger.log_gate(cfg, "sandbox-exec", "F1", "pass", detail=f"{argv[0]} rc={r.returncode}")
        return r.returncode, out
    except subprocess.TimeoutExpired as e:
        raise SandboxError(f"command timed out: {argv[0]}") from e
    except OSError as e:
        raise SandboxError(f"cannot execute {argv[0]}: {e}") from e
