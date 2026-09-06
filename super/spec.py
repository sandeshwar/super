"""Spec pinning + drift probe (doc 03 §4, doc 02 §§1/5).

No task starts building until failing acceptance tests exist — the spec is
executable, not prose. While the worker runs, an isolated probe compares the
spec against the worker's actual diff and tool calls (never its self-report).
Mismatch files a ledger entry and forces re-plan, even when every local
check is green. The terminal evaluator diffs the final diff against the spec.
"""

from __future__ import annotations

import difflib
import re

from . import ledger
from .errors import SpecError

GATE_ID = "spec"
DRIFT_GATE = "drift"

_FILE = "specs.json"
_SCHEMA = 1


def _path(cfg: dict) -> str:
    return f"{cfg['state_dir']}/{_FILE}"


def _blank() -> dict:
    return {"schema": _SCHEMA, "specs": {}}


def _load(cfg: dict) -> dict:
    from . import store
    data = store.load_json(_path(cfg), _blank())
    if not isinstance(data, dict) or not isinstance(data.get("specs"), dict):
        return _blank()
    return data


def _save(cfg: dict, data: dict) -> None:
    from . import store
    store.save_json(_path(cfg), data)


def get_spec(cfg: dict, task_id: str) -> dict | None:
    """Return the pinned spec for `task_id`, or None when never pinned."""
    return _load(cfg)["specs"].get(str(task_id))


def list_specs(cfg: dict) -> list[dict]:
    """All pinned specs, sorted by task id."""
    specs = _load(cfg)["specs"]
    return [specs[k] for k in sorted(specs, key=lambda x: int(x) if x.isdigit() else x)]


def pin_spec(cfg: dict, task: dict, acceptance: list[str]) -> dict:
    """Attach executable acceptance criteria to a task.

    Raises SpecError when intent cannot compile to a testable check — the
    task is rejected back for clarification with concrete options.
    Persists to <state_dir>/specs.json so /api/spec serves the contract.
    """
    clean = [a.strip() for a in (acceptance or []) if a and a.strip()]
    if not clean:
        raise SpecError(
            "no testable acceptance criteria — clarify first. Options: "
            "(1) name the failing test file, (2) describe observable behavior, "
            "(3) split the task until each leaf is checkable."
        )
    spec = {"task_id": task.get("id"), "acceptance": clean, "pinned": True,
            "pinned_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S")}
    ledger.log_gate(cfg, GATE_ID, "F2b", "pass",
                    detail=f"spec pinned for {task.get('id')}: {len(clean)} checks")
    try:
        data = _load(cfg)
        data["specs"][str(task.get("id"))] = spec
        _save(cfg, data)
    except Exception:
        pass
    return spec


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z_][\w]*", text.lower())) - {
        "the", "and", "with", "from", "that", "this", "into", "have", "will",
    }


def drift_score(spec_text: str, diff_text: str) -> float:
    """Token-overlap between spec and diff in [0, 1]. Low overlap = drift."""
    st, dt = _tokens(spec_text), _tokens(diff_text)
    if not st:
        return 1.0
    if not dt:
        return 0.0
    return len(st & dt) / len(st)


def probe(cfg: dict, spec: dict, diff_text: str, tool_calls: list | None = None,
          threshold: float = 0.25) -> tuple[bool, str]:
    """Isolated drift probe grounded in diff/tool calls, not self-report.

    Returns (on_track, evidence). Off-track writes a ledger entry.
    """
    if not cfg.get("gates", {}).get("drift", True):
        return True, "drift gate disabled"
    spec_text = "\n".join(spec.get("acceptance", []))
    evidence = diff_text + "\n" + "\n".join(tool_calls or [])
    score = drift_score(spec_text, evidence)
    if score < threshold:
        ledger.log_gate(cfg, DRIFT_GATE, "F2b", "reject",
                        detail=f"drift score {score:.2f} < {threshold} for {spec.get('task_id')}")
        ledger.add_issue(cfg, "major", "drift",
                         f"task {spec.get('task_id')} drifting from spec (score {score:.2f})")
        return False, f"drift detected (overlap {score:.2f}) — re-plan against the spec"
    ledger.log_gate(cfg, DRIFT_GATE, "F2b", "pass", detail=f"on-track {score:.2f}")
    return True, f"on-track (overlap {score:.2f})"


def evaluate_final(cfg: dict, spec: dict, final_diff: str) -> tuple[bool, str]:
    """Terminal evaluator: final diff vs. pinned spec, with unified-diff evidence."""
    ok, msg = probe(cfg, spec, final_diff)
    if not ok:
        return False, msg
    evidence = "\n".join(difflib.unified_diff(
        spec.get("acceptance", []), final_diff.splitlines(), lineterm="",
    )[:20])
    ledger.log_gate(cfg, "evaluator", "F3", "pass",
                    detail=f"final diff matches spec for {spec.get('task_id')}")
    return True, f"spec satisfied. Evidence:\n{evidence}"
