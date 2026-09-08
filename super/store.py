"""Atomic JSON store with advisory file locking.

Every persistent collection (sessions, claims, ledger indexes) goes
through this module so concurrent CLI + server writers cannot interleave
partial JSON. Writes are tmp-file + fsync + os.replace. Reads take a shared
lock. Corrupt files are quarantined to *.corrupt-<ts> and surfaced as
StoreError instead of silently reset.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from typing import Any, Callable

try:
    import fcntl  # POSIX (macOS/Linux)

    _HAS_FCNTL = True
except ImportError:  # Windows fallback
    _HAS_FCNTL = False

from .errors import StoreError


@contextmanager
def _locked(path: str, exclusive: bool):
    """Advisory lock on a sidecar lockfile so the data file itself stays clean."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    lock_path = path + ".lock"
    fh = open(lock_path, "a+")
    try:
        if _HAS_FCNTL:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        try:
            if _HAS_FCNTL:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def load_json(path: str, default: Any) -> Any:
    """Load JSON under a shared lock. Returns a deep copy of `default` on miss."""
    if not os.path.exists(path):
        return json.loads(json.dumps(default))
    with _locked(path, False):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            bad = f"{path}.corrupt-{time.strftime('%Y%m%dT%H%M%S')}"
            try:
                os.replace(path, bad)
            except OSError:
                pass
            raise StoreError(f"corrupt store {path} quarantined to {bad}: {e}") from e
        except OSError as e:
            raise StoreError(f"cannot read {path}: {e}") from e


def save_json(path: str, data: Any) -> None:
    """Atomic save under an exclusive lock."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with _locked(path, True):
        tmp = f"{path}.tmp-{os.getpid()}"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, path)
        except OSError as e:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            raise StoreError(f"cannot write {path}: {e}") from e


def update_json(path: str, default: Any, fn: Callable[[Any], Any]) -> Any:
    """Load-modify-store under one exclusive lock. Returns the new value."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with _locked(path, True):
        if not os.path.exists(path):
            data = json.loads(json.dumps(default))
        else:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                bad = f"{path}.corrupt-{time.strftime('%Y%m%dT%H%M%S')}"
                try:
                    os.replace(path, bad)
                except OSError:
                    pass
                raise StoreError(f"corrupt store {path} quarantined to {bad}: {e}") from e
        result = fn(data)
        tmp = f"{path}.tmp-{os.getpid()}"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, path)
        except OSError as e:
            raise StoreError(f"cannot write {path}: {e}") from e
        return result


def append_jsonl(path: str, record: dict) -> None:
    """Append one JSON line (lock-protected). Adds ts when absent."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    rec = dict(record)
    rec.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
    line = json.dumps(rec) + "\n"
    with _locked(path, True):
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
        except OSError as e:
            raise StoreError(f"cannot append {path}: {e}") from e


def read_jsonl(path: str) -> list:
    """Read all JSON lines (lock-protected, skips blank lines)."""
    if not os.path.exists(path):
        return []
    with _locked(path, False):
        out = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        out.append(json.loads(line))
        except OSError as e:
            raise StoreError(f"cannot read {path}: {e}") from e
        return out
