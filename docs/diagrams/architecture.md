# Architecture — SUPER Harness

```mermaid
flowchart TB
    subgraph INTENT["Intent"]
        REQ[Request] --> AMB{Spec-compilable?}
        AMB -- no --> CLAR[Clarify]
        CLAR --> REQ
        AMB -- yes --> AC[Ambition Contract<br/>quality ladder]
        AC --> SP[Spec Pinner<br/>failing tests = spec]
    end

    subgraph PLAN["Plan: task graph on disk"]
        SP --> TG[Task graph<br/>parent/child, depends-on, proof]
        TG --> LEAF[One leaf to model<br/>what/why/done/needs]
    end

    subgraph CTX["Context per step"]
        LEAF --> CC[Compiler<br/>working set only]
        CS[Claim store<br/>source x verif x validity x taint] --- CC
        SG[Symbol graph] --- CC
        DOC[Version-pinned docs<br/>tainted] --- CC
    end

    subgraph EXEC["Execute"]
        CC --> W[Worker: one microtask<br/>Best-of-N samples]
        SB[Disposable sandbox] --- W
        W --> GATES[Ground, docs,<br/>dup, budgets]
    end

    subgraph VERIFY["Verify + Adversarial"]
        GATES --> VL[Ladder: lint, subset,<br/>full + N-run, mutation]
        VL --> ADV[Reviewer, auditor,<br/>drift probe on diffs]
        ADV --> CG[Composition gate<br/>merged artifact]
    end

    subgraph HUMAN["Human + Trust"]
        CG --> RISK{Blast radius + trust?}
        RISK -- low + proven --> AUTO[Auto-pass, logged]
        RISK -- high or new --> HG[Human: critic evidence]
        AUTO --> SHIP[Ship + scorecard]
        HG --> SHIP
    end

    subgraph SUB["Substrates"]
        TAINT[Taint + capabilities<br/>bounds every call]
        SINK[Sink audit<br/>net-out + secrets]
        IL[Issue ledger<br/>blocks done]
        GA[Gate accounting<br/>pass + reject]
    end

    subgraph META["Meta loop"]
        REPLAY[Replay corpus] --> MINE[Miner] --> EVO[Evolver<br/>add OR delete]
        EVO -. held-out eval .-> REPLAY
        EVO -. distill traces .-> W
    end

    GATES -.-> GA
    VL -.-> GA
    ADV -.-> IL
    IL -. blocks .-> SHIP
    GA -. catch-rate .-> EVO
```

- Harness holds the forest (graph); model holds one leaf (F10 fix).
- Gates dispose; model proposes. Every gate logs to earn its keep or be deleted.
- Security + ledger touch every layer; meta loop evolves everything except the grader.
