# 02 — Solution Architecture (SUPER Harness)

Principle: **no unverifiable fact and no ungated edit reaches the write path — and every gate must earn its keep with a measured catch rate.**

SUPER = five rules the whole design obeys:

- **S — Small steps.** Never ask for more than the model's competence envelope. One turn = one verifiable outcome.
- **U — Ungated writes impossible.** Grounding, docs, standards, and tests are locked doors, not advice.
- **P — Provenance × verification logged.** Where a claim came from and whether it's true are separate columns. Passes and rejects both logged.
- **E — Evolution with descent.** Every gate carries its failure class + catch rate per model version. Zero catch across N versions → deleted.
- **R — Risk-calibrated freedom.** Authority scales with blast radius and track record, not uniform gating.

Words we use (plain meaning): **provenance** = where a fact came from; **descent** = deleting rules that stop catching bugs; **blast radius** = how much a change could break; **taint** = mark for unsafe internet text; **SBOM** = list of all packages in the build; **SAST** = auto-checker for known bad code patterns; **AST** = code as tree structure, for finding copies; **LSP** = tool that knows where symbols live; **supersession** = new fact replaces old fact with dates; **Best-of-N** = try N times, keep the best verified one.

Diagram: [diagrams/architecture.md](diagrams/architecture.md)

## 1. Intent layer (what "done" means)

Ambiguity gate → Ambition Contract (doc 05) → acceptance checks (failing tests / observables). If intent can't compile to a testable check, clarify with 2–3 concrete options. No check, no build.

## 2. Planning surface (attacks F10, F2)

Long work is steered by an **intelligence agenda** (gaps, priorities) plus chat tools — not a separate DAG UI. The model plans with tools and memory; the harness enforces gates on writes. Context stays small: verified claims + repo overview + the current turn.

## 3. Context layer (attacks F2a, staleness, F10)

Per-step compiler assembles a small working set from: claim store (source, verification, validity interval, taint), symbol/usage graph, version-pinned docs, Event Evolution Graph (facts carry validity intervals; old vs. new is a supersession query, not a conflict). Memory is a cache: disconfirming execution retires a memory the way a new docs version supersedes a claim.

## 4. Execution layer (attacks F1)

Diff-only patches in a disposable sandbox (pinned deps, session-0 env probe). Structured tools (AST search, LSP, exec) made faster than guessing. Output space constrained (schema-validated tool calls, templates for common changes).

Small-model multiplier: sample Best-of-N (5–10 cheap tries) per step; verifiers pick the winner. Tokens spent on search, quality from selection. Early abort when pass-rate stalls — don't burn 50 steps going nowhere.

## 5. Verification + adversarial layer (attacks F2, F3, F4)

Ladder: lint/type per edit → focused tests → full suite + N-run flaky quarantine per commit → acceptance + mutation screen (a new test that stays green under mutation is vacuous and can't gate anything) → property/fuzz for generated logic → perf/resource diff + SAST/secret/license + docs-API co-evolution check.

Writer ≠ reviewer ≠ auditor ≠ evaluator. Reviewer blocks only with a failing-test reproducer. Drift probes are grounded in the actual diff/tool calls vs. the acceptance check — never the worker's self-report. Composition gate checks the merged artifact; the integrator owns seam defects.

## 6. Security substrate (attacks F5)

Capability tokens per call + taint labels on all fetched content (untrusted / pinned-docs / local-exec) + explicit declassification. Authority of a call is bounded by the taint of the context that produced it — enforced in tool dispatch, not a prompt request to "be careful." Dedicated sink log (every network-out + secret-read joined to taint) + dependency-introduction gate (pin + CVE + license + typosquat + SBOM update).

Diagram: [diagrams/taint-capability.md](diagrams/taint-capability.md)

## 7. Human + trust layer (attacks F7)

The human has a finite budget, modeled like one: fatigue detection (approval rate per prompt type; ≥95% approve → promote to trusted or remove — a waved-through gate launders risk), critic-first evidence (human sees the strongest objection + blast radius, never the builder's summary), attention budget, blast-radius routing (small + track record → auto-pass logged; big/new/auth/billing/crypto → mandatory human + full CI), trust tiers per agent per repo area from gate-accounting history. Product surface: inline chat approvals for agents, capabilities, and memory confirms.

## 8. Meta loop (attacks F3, F8, F9)

Replay corpus of failed sessions (the falsifier) + live gate-accounting log (passes and rejects, per model version) → trajectory miner → harness evolver that may add *or delete* gates. Held-out search suite + separate eval suite, always — gains on the search benchmark don't count. Grader/verifiers/permissions need human sign-off; the evaluated agent never edits its grader. Verified traces also feed SLM fine-tuning (distillation flywheel), which widens the competence envelope from §4.

Diagram: [diagrams/gate-decay.md](diagrams/gate-decay.md)

## Component → failure map

| Failure | Intent | Plan/agenda | Context | Execution+Best-of-N | Verif+Adversarial | Security | Human+Trust | Meta+Descent |
|---|---|---|---|---|---|---|---|---|
| F1 bad writes | ○ | | | ● | ○ | | | |
| F2a rot | | ○ | ● | | ○ | | | |
| F2b drift | ● | ○ | | | ● | | | |
| F3 self-grade | | | | | ● | | | ● |
| F4 gaming | | | | | ● | | ○ | ● |
| F5 injection | | | ○ | | | ● | | |
| F6 seams | | | | | ● | | | |
| F7 human | | | | | | | ● | |
| F8 rot | | | | | | | | ● |
| F10 context+flat plan | | ● | ● | ○ | | | | |
| Ambition (doc 05) | ● | | | ○ | ● | | ○ | |

● primary, ○ secondary.

Live product UI: **Chat + Settings** (+ canvas). See [06 — Local Interface](06-local-interface.md).
