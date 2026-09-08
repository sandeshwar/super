# 01 — Problem Statement

Two layers fail: the **model** and the **harness** (the layer between model and real world: session, sandbox, tools, context, permissions, trace, eval).

## 1. Model limits

Per *On the Fundamental Limits of LLMs at Scale* (arXiv 2511.12869), plus observed gaps:

| # | Limit | Why it matters for coding |
|---|-------|---------------------------|
| 1 | Hallucination | Invents APIs, params, facts. Rises with capability. |
| 2 | Context rot | Effective window far smaller than advertised; recall degrades non-linearly. Small models rot faster. |
| 3 | Reasoning degradation | Worse the longer it runs; steep on hard problems. |
| 4 | Retrieval fragility | RAG breaks on multi-hop / nuanced queries. |
| 5 | Frozen knowledge | Cutoff lags release by months; no temporal reasoning; edits don't scale (ripple effects). |
| 6 | Metacognition gap | Cannot reliably report why it failed; confidence diverges from reliability. Only outcome rates (pass/fail) are trustworthy. |

Smaller models show every row worse — which is why the harness must carry more weight for them, not less.

## 2. Field issues (what users actually see)

Every item below is reported against coding agents daily:

outdated syntax; library/language version mismatch; ignoring coding standards / AGENTS.md / CONTRIBUTING.md; duplication; reinventing in-repo utilities; bloated files; no reusability / maintainability / efficiency / performance / security / reliability focus; not using latest versions; lack of environment knowledge; memory-over-docs; not using tools (grep, linters, type-checkers, tests); issues pile up silently; no depth or breadth (low-poly villa — see doc 05); context overflow on long runs; shallow todos that lose priority and proof.

Root cause in one sentence:

> **The agent trusts parametric memory when ground truth is one tool call away — and nothing refuses the bad write.**

Caveat: true for knowledge in repo/docs (styles, versions, symbols). False for knowledge only in an expert's head (architecture judgment, algorithmic cleverness). Gates verify the former; they cannot manufacture the latter.

## 3. Harness failure classes (F1–F10)

| ID | Class | Description |
|----|-------|-------------|
| F1 | Ungated bad writes | §2 symptoms. Instructions ignored under pressure; no write-path refusal. |
| F2a | Mechanical rot | Lost state, stale assumptions flushed from window. |
| F2b | Semantic drift | Answers a different question while every local check passes. Needs goal-probe, not code-gate. |
| F3 | Self-graded homework | Worker judges itself; extends to evolving harnesses on the same benchmark they report on. |
| F4 | Goodhart at gates | Checks become targets: vacuous tests, checkbox realism, cherry-picked evidence. Assume gaming. |
| F5 | Harness as attack surface | Every retrieval path (repos, issues, pages, MCP tools, skills) is a write into behavior. Needs taint, not just scoping. |
| F6 | Seam loss | Writer / reviewer / evaluator isolated but composition unowned: each part excellent, merge broken. |
| F7 | Unmodeled human | Approval fatigue (40 prompts/hr, 98% approve) + cherry-picked builder summaries launder risk as consent. |
| F8 | Co-evolution rot | Gates encode "model cannot do X"; models update; gates never deleted. All brakes, no steering. |
| F9 | Attribution blindness | Logs record errors, not passes. Can't say which layer failed → can't evolve, can't price gates. |
| F10 | Small context + flat plan | Context is accumulated flat until it rots; plan is a shallow todo with no priority, no durable steering, no proof of what closed a goal. Long runs fail structurally. |

F10 is load-bearing for small models: the harness must keep context compiled and small, and steer long work with an agenda + tools — not dump the whole plan into the prompt.

## 4. What this system is not

- Does not eliminate model limits. It moves where they bind: from "model misbehaves" to "agent games the gate." F4 is permanent; gates bound it.
- Efficiency / taste / architecture judgment are only partially enforceable without domain oracles. Gates verify repo/docs knowledge; the rest stays human-partnered.
