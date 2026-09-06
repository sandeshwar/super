# Ambition Ladder — Progressive Elaboration Loop

```mermaid
flowchart TD
    REQ[User request:<br/>'3D rendered villa'] --> AC[Ambition Contract Compiler<br/>domain taxonomy + per-axis LoA ladder]
    AC --> DEF["Default target: LoA 4 (expert)<br/>ambiguity resolves TOWARD THE TOP"]
    DEF --> SHOW[One-screen scorecard shown to user<br/>adjust sliders, not spec]
    SHOW --> BUILD[Builder agent: draft pass]

    BUILD --> CRIT{Critic Ensemble<br/>no shared context with builder}
    subgraph CRITICS["External, reference-grounded grading"]
        M1[Mechanical metrics<br/>poly count, texture res,<br/>render passes present]
        M2[N model critics, median score<br/>anchored to fetched exemplars]
        M3{Disagreement > 1 level?<br/>=> force iteration}
    end
    CRIT --> CRITICS
    CRITICS -->|all axes >= LoA 4<br/>+ coverage complete| GATE[Done-State Gate<br/>per-axis scorecard delivered]
    GATE --> SHIP[Deliver]

    CRITICS -->|lowest axis named:<br/>'no normal maps, hard shadows,<br/>no pool reflections'| TARGET[Targeted enhancement pass<br/>ONLY allowed to improve named axis]
    subgraph R7["Anti-checkbox rule (gate compliance)"]
        MET[Mechanical metrics<br/>feed critics as evidence<br/>never pass an axis alone]
    end
    MET --> CRITICS
    TARGET --> BUD{Within LoA cost envelope?}
    BUD -- yes --> BUILD
    BUD -- no --> PRICE["Visible, priced downgrade request:<br/>'LoA 3 achieved, LoA 4 = +40 render-min<br/>accept or extend?'"]
    PRICE -->|user key| SHIP
    PRICE -->|user extends| BUILD

    GATE -.->|user corrections<br/>'too flat', 'go deeper'| MINE[Trajectory Miner<br/>asymmetric: raises levels<br/>never lowers the bar]
    GATE -.->|'this is enough'<br/>-> price observation| BUD
    MINE -.-> AC

    BUILD x-.->|BUILDER CANNOT:<br/>lower contract, edit critic,<br/>move goalposts| FORBIDDEN[FORBIDDEN]
```

Invariants:

1. Builder proposes; only gates dispose.
2. Default LoA = expert; drafts must be *requested* downward.
3. Every iteration targets a named, observable deficiency.
4. Deflation = user-keyed + priced; never silent.
5. Taxonomy grows from real user corrections (mined, not hand-written) —
   asymmetrically: complaints raise the bar, acceptance only reprices it.
6. Mechanical metrics are evidence for critics, never an axis verdict alone
   (checkbox realism is the gate-compliance failure to design against).
