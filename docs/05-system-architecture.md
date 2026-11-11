# System architecture

The room model and the catalog are the two sources of truth; every design flows through the solver and must pass the verifier before it reaches the phone.

```mermaid
flowchart LR
  subgraph Phone["On the phone"]
    CAP["Room capture<br/>any phone camera"]
    BRF["Brief and chat<br/>what she wants"]
    EDT["3D editor, AR<br/>drag, swap, buy"]
  end
  subgraph Cloud["Cloud design pipeline"]
    RM["Room model<br/>walls in metres"] --> BP["Brief parser<br/>small LLM to JSON"] --> RT["Retrieval<br/>filter and match"] --> LS["Layout solver<br/>rules, no LLM"] --> VF["Verifier<br/>fit, budget, stock"]
  end
  subgraph Data["Data and learning"]
    CAT["Catalog<br/>size, price, 3D"]
    RK["Learned ranker<br/>taste, not fit"]
    EV["Event log<br/>every action"]
  end
  CAP -- "video, tape check" --> RM
  BRF -- "brief, messages" --> BP
  VF -- "3 designs" --> EDT
  CAT -- "real products" --> RT
  RK -- "scores" --> LS
  EDT -- "edits, clicks" --> EV
  EV -- "nightly retrain, eval gate" --> RK
```

Learning changes ranking only. Hard rules and the verifier stay fixed.

Read it left to right, then down: the phone captures the room and the brief, the cloud pipeline builds and checks three designs, and every action she takes in the editor feeds the nightly ranker training. The LLM appears in exactly one box.
