# Taint–Capability Flow — fetched content reduces what the agent may do

```mermaid
flowchart LR
    subgraph IN["Ingress (all retrieval paths)"]
        WEB[Web page / search hit]
        DOC[Version-pinned docs]
        ISS[Issue / PR text]
        TOOLD[Tool descriptions<br/>MCP, skills]
    end

    subgraph LABEL["Taint Labeling"]
        L1[Untrusted origin<br/>taint = high]
        L2[Pinned official docs<br/>taint = medium-low]
        L3[Executed local output<br/>taint = low]
    end

    subgraph CTX["Agent Context"]
        C[Content rendered as DATA<br/>'from X' provenance frame<br/>never a directive]
    end

    subgraph DISPATCH["Tool Middleware"]
        REQ[Tool call requested]
        BOUND{"call authority <=<br/>min task authority,<br/>1 - taint of producing context ?"}
        OK[Execute with<br/>scoped capability token]
        DENY[Denied: tainted context<br/>may not cause this call]
    end

    WEB --> L1
    DOC --> L2
    ISS --> L1
    TOOLD --> L1
    L1 --> C
    L2 --> C
    L3 --> C

    C -->|context that produced the call| BOUND
    REQ --> BOUND
    BOUND -- yes --> OK
    BOUND -- no --> DENY
    DENY -->|issue ledger entry| IL[Issue: injection attempt<br/>or agent confusion]
```

The specific pattern this kills: a poisoned page (taint high) instructing the
agent to read `.aws/credentials` and POST it somewhere — the exfiltration-
shaped call requires authority the tainted context cannot grant. The rule is
mechanical and lives in tool dispatch; "the web page said it was fine" is
inadmissible by construction.
