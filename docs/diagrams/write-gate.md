# Write-Gate Flow — one leaf at a time

```mermaid
flowchart TD
    LEAF[Leaf card: what/why/done/needs] --> S[Best-of-N samples<br/>cheap tries]
    S --> G1{Symbol observed?<br/>grep/LSP/type evidence}
    G1 -- no --> R1[REJECT: observe first]
    R1 --> S
    G1 -- yes --> G2{Lib symbol in<br/>version-pinned docs?}
    G2 -- no --> R2[REJECT: fetch docs first]
    R2 --> S
    G2 -- yes --> G3{Near-duplicate of<br/>existing helper?}
    G3 -- yes --> R3[BLOCK: return existing<br/>or sign waiver]
    G3 -- no --> G4{Budgets pass?<br/>size/complexity}
    G4 -- no --> R4[REJECT with report]
    G4 -- yes --> V1[Type + lint per edit]
    V1 -- fail --> IL1[Ledger entry, fix now]
    IL1 --> S
    V1 -- pass --> PICK[Pick best sample]
    PICK --> DP{Drift probe:<br/>diff vs spec?}
    DP -- mismatch --> IL2[Ledger entry<br/>even if green]
    DP -- aligned --> L2[Subset per subtask]
    L2 --> L3[Full suite per commit<br/>N-run flaky quarantine]
    L3 --> SPEC{Acceptance green?}
    SPEC -- no --> S
    SPEC -- yes --> MUT{Vacuous?<br/>green under mutation}
    MUT -- yes --> REJ[Rejected as check]
    MUT -- no --> PROOF[Proof linked<br/>leaf closable]
```

- Rejection names the missing tool call; the gate teaches.
- Done needs: spec green + non-vacuous tests + no open criticals + proof link.
- No budget/progress → early abort: re-plan or escalate, don't burn steps.
