# 04 — Implementation Roadmap (SUPER order)

Build order = evidence-per-effort: nothing ships before the measurement exists that could kill it.

## Phase 0: replay + envelope — the standing falsifier

1. Production event ledger (tool traces, gate passes + rejects, session outcomes).
2. Collect 30–50 failed sessions; label failure class (doc 01 F1–F10); mark which hypothetical gate would have caught each at which step.
3. Measure competence envelope: largest edit the target (small) model does reliably with full context — sets max microtask size and default Best-of-N depth.
4. Output: catch-rate matrix = build list *and* falsifier. If hypothesized gates catch < threshold, the thesis is wrong for this corpus — change the docs.

Phase 0 never ends; it becomes the live accounting + descent input.

## Core enforcement: grounding + spec + verification

1. Grounding gate (doc 03 §1) — unobserved symbol → reject.
2. Task graph (doc 02 §2) — parent/child + depends-on + proof link; model sees one leaf only.
3. Spec pinning + drift probe (doc 03 §4) — failing acceptance tests required; isolated probe per subtask grounded in diffs.
4. Ladder + mutation (doc 03 §3) — local type/lint per edit, subset per subtask, full + N-run per commit; vacuous tests rejected.

Metrics: acceptance rate ↑, first-pass ↑, session length ↓, hallucinated-import → 0, vacuous-catch rate, drift hits/session.

## Phase 2 (weeks 6–11): contract + debt + security substrate

Contract compiler + docs-before-write + duplication block with waiver (doc 03 §§1–2); session-0 probe + disposable sandbox; ledger with expiry blocking done-state (doc 03 §5); taint rule + capability tokens + sink audit + dependency/secret/license gates (doc 02 §6); Best-of-N + early abort tuned from envelope data.

## Phase 3 (weeks 12–19): memory + human + trust

Typed memory + EEG validity intervals + per-step compilation (doc 02 §3); quality budgets + reviewer-checklist mining; differential repair; blast-radius routing + trust tiers + fatigue detection + critic-first UI + attention budget (doc 02 §7); perf/resource/docs-co-evolution gates.

## Phase 4 (research): ambition + self-evolution + distillation

Ambition Contract + critic ensemble after the linchpin test (can critics discriminate? — doc 05 §2.2); composition gate + full adversarial topology; evolver (add *or delete*, held-out search / separate eval, grader off-limits) + SLM distillation from verified traces.

## Stack (opinionated, swappable)

tree-sitter + clone detection; native type/lint per language; mutation scoped to changed lines; coverage-based test-impact; version-pinned docs scrapers; Firecracker/containerd + Nix; sqlite/graph claim store (source, verification, validity, taint); append-only gate log joined to outcomes; offline LLM trajectory miner.

## Evaluation

Phase-0 replay on every gate proposal + model upgrade; held-out evolution protocol (search gains don't count); track acceptance rate, first-pass, session length, found-at-step vs. found-at-end, vacuous-catch, drift-hit, per-gate catch per model, sink-audit clean, approval-rate per prompt type.

## Honest limits

Model limits persist; pressure relocates to gate-gaming (bounded, not removed). Perf/taste/architecture stay human-partnered. Phase 4 is a research bet with a wide interval; Phases 0–2 are engineering with measurable payoff.
