# Gate Decay — the descent operator on the enforcement layer

```mermaid
flowchart TD
    G[Gate created<br/>records: failure class it catches] --> LOG[Gate accounting<br/>logs passes AND rejects<br/>per session outcome]
    LOG --> CR[Per model version:<br/>catch rate from live log<br/>+ Phase-0 replay matrix]
    CR --> Q{Caught anything<br/>across N model versions?}
    Q -- yes --> KEEP[Keep — cost justified<br/>continue logging]
    Q -- no --> FLAG[Flagged for removal<br/>cost vs. zero benefit]
    FLAG --> H{Human review<br/>safety-critical gate?}
    H -- no --> DELETE[Gate deleted<br/>mutation versioned,<br/>rollback-able]
    H -- yes --> SIG[Human sign-off<br/>required to delete]

    MU[Model upgrade] -.expires assumptions<br/>about what model cannot do.-> CR

    style DELETE fill:#2d2,stroke:#333
    style MU fill:#f96,stroke:#333
```

The failure this prevents (doc 01 F8): gates encode assumptions about model
weaknesses; model updates expire the weaknesses; without descent, the harness
acretes brakes — cost and capability-tax paid to defend failures that no
longer occur.

Invariants:

1. No gate exists without a recorded justifying failure class.
2. Catch rate is computed over both logged outcomes (live) and the replay
   suite (counterfactual), per model version.
3. Zero catch rate across N versions ⇒ flagged; non-safety gates are deleted
   by the evolution agent, safety gates only with sign-off.
4. The evolution loop rewards deletion as much as addition — descent is
   evolution, not erosion.
