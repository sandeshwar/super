# SUPER Coding Harness — Design Docs

> Core thesis: **the bottleneck moved from the model to the harness.**
> Small model + SUPER harness beats big naked model on grounded repo work.

SUPER rules: **S**mall steps · **U**ngated writes impossible · **P**rovenance × verification logged · **E**volution with descent · **R**isk-calibrated freedom.

## Contents

| Doc | Scope |
|-----|-------|
| [01 — Problem Statement](01-problem-statement.md) | Model limits, full field-issue list, harness failures F1–F10 (incl. small-context + flat-todo) |
| [02 — Solution Architecture](02-solution-architecture.md) | SUPER layers: intent, task graph, context, execution + Best-of-N, verification + adversarial, security, human + trust, meta loop |
| [03 — Coding Mechanisms](03-coding-agent-mechanisms.md) | Which gate blocks which issue; issue → mechanism map; build-small-first set |
| [04 — Implementation Roadmap](04-implementation-roadmap.md) | Phase-0 replay + envelope, core enforcement, contract/security, memory/human, research |
| [05 — Ambition Deflation](05-ambition-deflation.md) | Quality-dimension under-delivery: Ambition Contract, critic ensemble, done-state gate |
| [06 — Local Interface](06-local-interface.md) | CLI + localhost pages: job tree, approve, report card |
| [Diagrams](diagrams/) | Architecture, write-gate, taint-capability, gate-decay, ambition-ladder, memory-layers |

## Summary

Agents fail because they guess from memory with no refusal, rot over long context, drift off-goal while all checks pass, grade themselves, game checks, get poisoned via retrieval, break at agent seams, fatigue the human approver, accrete dead guardrails, and run long tasks off a flat todo that can't hold depth, order, or proof.

SUPER replaces instructions with locked doors: task graph holds the whole plan on disk while the model sees one leaf; every edit passes grounding, docs, standards, duplication, and test gates; sampling (Best-of-N) + verifiers pick winners; isolated probes catch drift; taint bounds authority; humans see critic evidence on risky changes only; every gate logs passes and rejects to earn its keep or be deleted. Quality (doc 05) is a contracted ladder with a done-state the builder can't move.

Key refs: *Fundamental Limits of LLMs at Scale* (2511.12869); AHE harness evolution; *Rethinking Harness Evolution* (held-out protocol); *Long-Horizon Mirage* (compounding); *GitInject* (retrieval as attack surface); Anthropic 2026 context-engineering report.
