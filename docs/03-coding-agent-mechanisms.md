# 03 — Coding Mechanisms (how each issue is blocked)

Rule: **every row replaces an instruction with a tool that refuses.** Every check ships with a counter-check for the lazy way to pass it.

Flow: [diagrams/write-gate.md](diagrams/write-gate.md)

## 1. Grounding gate — outdated syntax, version mismatch, memory-over-docs, env ignorance

Agent may not reference a symbol it has not observed (grep/LSP/type-check evidence). Library symbols must be in the version-pinned docs cache (pinned to lockfile, not "latest"); else rejected with "fetch docs first." Session-0 probe records runtime versions, tooling, OS, scripts, hooks — never assumed. Kills existence-class hallucination; wrong-semantics still needs tests.

## 2. Contract compiler — standards, guidelines, latest versions, duplication, reinventing the wheel

On session start compile: lockfile versions, lint/formatter configs, CI config, AGENTS.md/CONTRIBUTING.md as machine rules, exported symbol/usage graph. Enforced at write time: lint + type + duplication check (AST similarity, threshold tuned per repo from Phase-0 data) must pass before the edit is visible. Near-duplicate helper → blocked and existing symbol returned; deliberate copies (adapters, wrappers, test doubles) via one-line waiver that files a ledger entry for the reviewer. Scheduled refresh injects deltas ("on 2.3, 2.9 exists, breaking: X").

## 3. Verification ladder + mutation + property tests — reliability, vacuous tests, gaming

Per edit: type/lint (local, ms). Per subtask: focused subset via test-impact analysis. Per commit: full suite + N-run flaky quarantine (nondeterministic failures never create fix-work). New acceptance tests face mutation (operator/boundary/statement deletes); green-under-mutation = vacuous = rejected as a check. Generated logic (parsers, authz, math) additionally gets property/fuzz harnesses — example tests are gameable, fuzzers aren't.

## 4. Spec pinning + drift probe — wrong-goal, slow drift (F2b)

Task starts only after failing acceptance tests exist (ambiguity gate first: untestable intent → clarify). Per subtask, an isolated probe diffs the spec against the worker's actual diff/tool calls — never its self-report. Mismatch → ledger entry + re-plan, even when all local checks are green. Terminal evaluator diffs final diff vs. spec.

## 5. Quality budgets + debt ledger — bloat, maintainability, piling issues

Per-edit LOC/complexity/nesting budgets (caught at line 300, not 2000). Differential repair only (transformations on verified code, no wholesale rewrites). Every violation → persistent ledger with severity and expiry; done-state blocked on open criticals; waivers expire and escalate (no permanent bypass). Reviewer checklist mined from the repo's own maintainer rejections, not generic style advice.

## 6. Perf / security / legal gates — efficiency, performance, security, legal

Perf: benchmark harness for hot paths + per-PR CPU/mem/latency/query-count/bundle diff. Partial — cannot invent clever algorithms; flags regressions, doesn't manufacture insight. Security: SAST ruleset + secret scanner + dependency gate (pin + CVE + license + typosquat + SBOM) + sink audit (all network-out/secret-reads joined to taint). Legal: license scan per new dep/file.

## 7. Adversarial review + composition — rubber-stamping, seam loss

Writer ≠ reviewer ≠ auditor. Reviewer blocks only with a reproducer test. Builder summaries never shown at approval; reviewer objection + diff/blast radius shown as-is. Delegation = acceptance contract (vague delegation rejected). Integrator owns the merged artifact; seam defects attributed to composition, never laundered by "each part passed."

## 8. Taint rule + tool ergonomics — injection, "not using tools"

All fetched content rendered as data with source framing, taint-labeled; call authority bounded by producing-context taint in tool dispatch (see doc 02 §6). Exploration tools made faster than guessing: AST search, structured results, chunked outputs.

## 9. Task graph + memory-as-cache — context limits, flat todos, repeated mistakes

Graph (doc 02 §2) + per-step context compilation (only load-bearing claims) + claim/procedural stores with validity intervals where disconfirming execution retires memory. Trajectory miner promotes repeated failures to harness fixes (better tool descriptions, preconditions, templates), constrained to non-grader components under held-out eval.

## 10. Calibration + trust — fatigue, over-trust

Verification pass-rates per task/area tracked; sustained drop inserts "reassess" checkpoint. Per-agent trust tier per repo area from history widens/narrows authority (blast-radius routing in doc 02 §7). Approval rates per prompt type detect rubber-stamping.

## Issue → mechanism map

| Issue | Mechanism |
|---|---|
| Outdated syntax / version mismatch / memory-over-docs | 1, 2 |
| Standards / guidelines ignored | 2 |
| Duplication / reinventing wheel | 2 |
| Latest versions | 1, 2 (refresh) |
| Bloated files | 5 |
| Reusability | 2 (symbol graph) |
| Efficiency / performance | 6 (partial, honestly limited) |
| Maintainability | 5 + 7 |
| Security | 6 + 8 |
| Reliability | 3 + 4 |
| Env knowledge | 1 (probe + sandbox) |
| Tool use | 1 + 8 |
| Issues pile up | 5 (ledger blocks done) |
| Drift / wrong-goal | 4 |
| Vacuous tests / gaming | 3 |
| Injection | 8 |
| Seams | 7 |
| Context / flat-todo | 9 |
| Depth/breadth | doc 05 (Ambition Contract) |

## Build small? Build 1 + 4 + 3 first

Grounding, spec+drift, cheap verification+mutation. They kill hallucination, drift, compounding, and first-order gaming at minimal cost — measurable from day one (acceptance rate, first-pass success, hallucinated-import → 0, vacuous-catch rate, drift hits/session).
