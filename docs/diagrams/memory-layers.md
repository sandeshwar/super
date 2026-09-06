# Knowledge & Memory Layers — typed memory + temporal reasoning

```mermaid
flowchart LR
    subgraph SOURCES["Evidence Sources"]
        M[Model prior<br/>frozen weights]
        W[Web / search<br/>tainted: data only]
        D[Version-pinned docs]
        S[Session evidence<br/>tests, execution]
    end

    subgraph CLAIMSTORE["Claim Store"]
        C1["Claim: 'lib X fn Y takes Z'<br/>source: docs v2.3<br/>valid: t0 -> t1<br/>confidence: 0.9"]
        C2["Claim: 'same fn takes W'<br/>source: docs v2.9<br/>valid: t1 -> now<br/>confidence: 0.95"]
    end

    subgraph EEG["Event Evolution Graph"]
        N1[v2.3 signature] -->|superseded by<br/>breaking change in 2.9| N2[v2.9 signature]
    end

    subgraph CONTEXT["Per-Step Context Compilation"]
        WS[Working Set<br/>only load-bearing claims<br/>attention-bounded]
    end

    M --> C1
    D --> C1
    D --> C2
    S --> C2
    C1 --> N1
    C2 --> N2
    N1 --> WS
    N2 --> WS
    WS --> AG[Agent sees belief HISTORY,<br/>reasons over supersession]

    subgraph REFRESH["Contract Refresh Job (scheduled)"]
        R1[New releases / deprecations / CVEs] -->|delta injected| EEG
    end
```

Key property: outdated and current facts are **not competing booleans** in
context; they are one queryable object with validity intervals, so "old answer
vs new answer" becomes a supersession query instead of a conflict that causes
hallucination.

The same supersession applies downward: procedural-store entries ("in this
repo, migrations need `--dry-run`") are **decaying priors** — an executed
contradiction retires a memory exactly as a newer docs version supersedes a
claim. Memory is a cache; disconfirming evidence is its invalidation signal.
