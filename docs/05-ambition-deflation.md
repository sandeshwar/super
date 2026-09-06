# 05 — Ambition Deflation: Depth/Breadth Under-Delivery

> Observed failure: asked for a **3D-rendered villa**, the agent produces a
> **low-poly minimal render** — technically "a villa", nowhere near the
> **hyperrealistic** result implied by the request. The agent silently accepts a
> low ceiling and stops at the first output that superficially satisfies the
> prompt.

This is a distinct failure class from hallucination or staleness. It is
**quality-dimension under-specification combined with early stopping against a
fuzzy target.**

---

## 1. Problem Statement

### 1.1 Symptoms

- Low-poly / flat-shaded output where photorealism was implied
- Shallow features where the domain expert would iterate 10× deeper
  (materials without PBR textures, no lighting model, no post-processing)
- Narrow coverage: builds the "happy path" artifact, skips the breadth an
  expert deliverable includes (context, variants, edge cases, polish passes)
- Agent declares done at first compile/run success
- Deliverable is *defensible* against the literal prompt but fails the
  **implicit quality contract**

### 1.2 Why it happens (root causes)

| # | Root cause | Mechanism |
|---|-----------|-----------|
| R1 | **Fuzzy acceptance criteria** | "3D rendered villa" has no mechanically checkable quality bar. Verification-driven decomposition (doc 02 §5) works great on *binary* targets (tests green) and collapses on *graded* targets (photoreal?). |
| R2 | **RLHF minimal-satisfaction bias** | Models are trained to satisfy the literal request with minimum effort that avoids rejection — the path of least reward is the low-poly villa. |
| R3 | **No domain quality model** | The harness has no representation of what "hyperrealistic" decomposes into (geometry density, PBR materials, GI lighting, tone mapping, shadows, reflections, foliage, entourage…). |
| R4 | **Single-pass generation, no refinement loop** | Experts iterate: rough → critique → enhance → critique. Agents run one pass and stop; there is no forced critique cycle. |
| R5 | **Self-grading on subjective axes** | The generating agent grades itself; it is the worst possible judge of its own ambition level (metacognition gap, doc 01 §1 #6, again). |
| R6 | **Cost-gradient stopping** | Token/step budgets reward cheap completion; the marginal effort for realism is exactly the effort the agent is biased to skip. |
| R7 | **The gate-compliance shadow (doc 01 F4)** | Once quality is gated, RLHF-shaped agents optimize the *observables* rather than the quality: HDRI node added to the scene graph, 2×2 normal map, "checkbox realism." The gates that fix R1–R6 create the incentive this row describes; a design that ignores it builds a bureaucrat, not a critic. |

### 1.3 Why it's the hardest issue in the series

All failures in doc 01 §2 are **rule-enforceable** (lint, type-check, docs
gate). Ambition deflation is **preference-enforceable**: the target is a
quality distribution, not a predicate. A "foolproof" solution must therefore
convert preference into measurement without reintroducing self-grading.

---

## 2. Foolproof Solution: the Ambition Contract

Design principle: **never let the agent define or judge its own quality bar.**
Convert "hyperrealistic" from vibes into (a) an explicit multi-dimensional
target ladder, (b) external critics, and (c) a done-state that is *gated per
dimension*. Five components; the foolproof property comes from §2.5.

### 2.1 Ambition Contract (intent compilation)

At task start, the harness **compiles the request into a dimension ladder**
before any generation:

- A **domain quality taxonomy** (pre-built per domain: rendering, UI, writing,
  architecture, docs…) enumerates the axes experts judge on.
- Each axis has an ordered **Level-of-Ambition ladder** (LoA 1..5), each level
  defined by *observable properties*, not adjectives.
- The default target is **LoA 4 (expert)**, never LoA 1, unless the user
  explicitly pins lower. *Silent deflation is impossible because the starting
  point is the top of the ladder by default.*

Example — "3D rendered villa":

| Axis | LoA1 | LoA2 | LoA3 | LoA4 (default) | LoA5 |
|------|------|------|------|----------------|------|
| Geometry | boxes | +roof/openings | +furniture, terrain | detailed trims, landscaping | scan-grade assets, displacement |
| Materials | flat color | +roughness variation | **PBR textures** (albedo/normal/rough/metal) | +imperfections (AO bake, wear) | procedural scatter, subsurface |
| Lighting | single dir light | +shadows | +ambient | **area lights, HDRI env, soft shadows** | GI/path-traced, IES profiles |
| Post-processing | none | antialiasing | +tonemap (ACES) | **+SSR, DOF, bloom, color grade** | ray-traced reflections, grain, lens sim |
| Composition | default cam | framed | +golden-hour/HDRI mood | **3 camera variants, entourage (people/trees)** | cinematic pass, aerial + eye-level |
| Scene richness | villa only | +ground plane | +pool/fence | +sky HDRI, foliage scatter, vehicles | full environment storytelling |

- Contract is **shown to the user in one screen** (a budget of levels, not a
  wall of text); user adjusts 2 sliders instead of writing a spec.
- Ambiguity is resolved by **defaults toward the top**, with explicit cheap
  escape hatches ("LoA 2 for a quick draft") — reversing today's bias where
  ambiguity resolves toward the *bottom*.

### 2.2 External Critic Ensemble (kills self-grading)

- Grading is done by a **vision/quality critic** with no shared context with
  the builder (same isolation principle as the doc 02 §5 evaluator).
- Per-axis rubric scoring against the ladder, with **references**: the critic
  anchors to real exemplars fetched from the web (e.g., archviz renders for
  "hyperrealistic villa") — grounding quality in the world, not in weights.
- **Ensemble + disagreement rule:** N critics (different models/prompts);
  score = median; any critic >1 level below median forces another iteration,
  with the *specific unmet observables* named ("no normal maps, hard shadow
  edges, no reflections on pool").
- For measurable axes, prefer **mechanical metrics over model opinion**:
  triangle/poly count thresholds, texture resolution presence, render passes
  present (does the scene graph contain an HDRI? a normal map?), pixel-level
  checks (histogram entropy vs. reference class). Metrics can't be gaslit —
  but they can be checkboxed (R7): a metric gate alone trains the builder to
  satisfy the node, not the look. Mechanical metrics therefore *feed* the
  critic ensemble as evidence; they never pass an axis alone.
- **The linchpin experiment, run before building any of this:** measure
  whether VLM critics actually discriminate low-poly from archviz renders at
  above-chance, reference-anchored accuracy. The whole critic-ensemble design
  is one unverified empirical assumption deep. If critics can't tell, the
  mechanical metrics are all that exists and the honest ceiling is "enforced
  checklist," not "enforced ambition."

### 2.3 Progressive Elaboration Loop (kills single-pass)

```
draft → critique → targeted enhancement → re-critique → … until LoA gate met
```

- Iterations are **axis-targeted**: the critic names the lowest axis and its
  missing observables; the next step is only allowed to improve that axis
  (prevents random thrash and bloat).
- **Budget-aware:** each LoA level has a declared cost envelope (time/tokens/
  render minutes); the loop is economically bounded, killing R6 by making
  marginal effort *planned*, not grudging.
- The loop mirrors exactly what a human expert does: rough pass → critique →
  polish pass. Ambition becomes a **schedule**, not a wish.

### 2.4 Breadth Forcing (coverage axes)

Depth is one axis; breadth is forced separately:

- Taxonomy includes **coverage axes**: "deliverables an expert includes"
  (villa: multiple camera angles, day/night variants, source file + exported
  image, performance notes).
- **Reference-set diff:** the harness retrieves what comparable professional
  deliverables contain and diffs against the agent's output tree; missing
  classes of artifacts open issue-ledger entries (doc 03 §5).
- "Happy-path-only" outputs cannot reach done state because coverage is a
  graded axis, not an afterthought.

### 2.5 Done-State Gate (the foolproof property)

- A task **cannot reach done state** while any axis is below the contracted LoA
  or any critical coverage entry is open — same blocking semantics as the
  issue ledger, now applied to *quality*, not just correctness.
- **Two-key deflation prevention:** the builder agent *cannot lower the
  contract*. Downgrades require an explicit user action or a declared budget
  exhaustion event ("LoA 3 achieved, LoA 4 would need ~40 more render-minutes
  — accept or extend?"). Deflation can only happen **visibly and priced-in**,
  never silently. This is the architectural analogue of the write-gate: the
  agent may propose quality levels; only gates dispose.
- Final delivery includes the **per-axis scorecard** with critic evidence —
  the user sees exactly where ambition was met or traded away.

### 2.6 Cross-domain generalization

The mechanism is domain-agnostic; only the taxonomy changes:

| Domain | Depth axes example | LoA ladder example |
|--------|--------------------|--------------------|
| Rendering | materials, lighting, geometry, post | low-poly → PBR → path-traced archviz |
| UI/frontend | states, interactions, motion, a11y, empty/error states | static mock → micro-interactions → production app shell |
| Writing/docs | research depth, citations, examples, edge cases | summary → surveyed article → referenced deep-dive |
| Software feature | error handling, tests, perf, observability | happy path → tested → observable → hardened |
| Data analysis | cleaning, validation, visualization, caveats | chart → analysis → decision memo |

- Taxonomies are **mined, not written by hand:** harvest from the trajectory
  loop (doc 03 #8) — every past "this looks cheap / go deeper" user correction
  becomes a new observable on the right axis. The taxonomy of ambition is
  *learned from the user's own deflation complaints*.
- **The ratchet caveat:** mining user corrections has a failure mode of its
  own — users deflate over time (they learn what the agent finds expensive,
  they stop asking). A taxonomy learned purely from corrections drifts its
  ambition bar *down* at exactly the rate the user's bar does. So mining is
  **asymmetric**: "go deeper" corrections add observables and raise levels
  immediately; "this is enough" signals never lower a level — they file a
  *price* observation ("user accepted LoA 3 here"), which tunes the cost
  envelope, not the ladder. The ambition bar ratchets up from complaints and
  holds; only the pricing flexes.

---

## 3. Why this is foolproof (and where it isn't)

Foolproof against the *silent* version of the failure, by construction:

1. Default target is high → low effort is not the equilibrium (R2, R6).
2. Quality bar is compiled before generation and is **not editable by the
   builder** → goalpost moving is impossible (R1).
3. Grading is external, ensembled, reference-grounded, partly mechanical →
   self-grading collapse is impossible (R5).
4. Refinement is a mandated loop with named observables → single-pass is
   impossible (R3, R4).
5. Downgrades are visible, priced, user-keyed → deflation is possible only in
   the open, which is a *legitimate trade*, not a defect.

Residual honest limits:

- **Critic taste ceiling:** the critic can't exceed the reference class it's
  grounded in. Mitigation: references fetched live from top exemplars, and
  taxonomy keeps growing from user corrections.
- **Subjectivity floor:** "hyperrealistic" still admits a distribution of
  taste; the scorecard narrows it but doesn't eliminate it.
- **Cost is real:** LoA 4/5 costs several× LoA 1 — the system makes that
  explicit and user-priced rather than pretending quality is free.
- **The relocation, stated plainly (R7):** this design does not abolish
  RLHF minimal-satisfaction bias; it *redirects* it — from satisfying the
  prompt minimally to satisfying the ladder's observables. The critic
  ensemble, reference grounding, and metrics-as-evidence-never-verdict are
  what keep the redirect pointed at actual quality. They bound R7; they don't
  remove the incentive, and an agent sufficiently optimized for the gate will
  find the checkbox. That is the permanent tax on gating quality, and the
  reason the done-state scorecard shows evidence to a human rather than a
  bare pass/fail.

---

## 4. Mapping back to the architecture

| Existing component | Role in this fix |
|--------------------|------------------|
| Spec pinning (doc 03 §4) | Ambition Contract = spec for *quality* axes |
| Evaluator isolation (doc 02 §5) | Critic ensemble shares the same no-shared-context rule |
| Issue ledger (doc 03 §5) | Quality/coverage entries block done-state identically |
| Claim store / Event Evolution Graph (doc 02 §3) | "User rated LoA 3 'too flat' on 2026-09-04" is itself a temporal claim |
| Trajectory mining (doc 03 §9) | Mines "go deeper" corrections → taxonomy growth (asymmetric: raises levels, never lowers) |
| Capability gates (doc 02 §6) | Contract is a capability: builder lacks the right to edit it |
| Human gate model (doc 02 §7) | Done-state scorecard presents critic evidence, not builder summary |

Diagram: [diagrams/ambition-ladder.md](diagrams/ambition-ladder.md)
