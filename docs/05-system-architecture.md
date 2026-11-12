# System architecture

The room model and the catalog are the two sources of truth. Every design flows through the solver and must pass the verifier before it reaches the phone. AI models sit around the solver, never in place of it.

```mermaid
flowchart LR
  subgraph Phone["On the phone (light)"]
    CAP["Capture<br/>video, motion, compass"]
    BRF["Brief<br/>taps, references"]
    UI["Reveal, 3D editor<br/>buy, share"]
  end
  subgraph GPU["GPU workers"]
    REC["Reconstruction<br/>metric 3D"]
    SEG["Segmentation<br/>walls, floor, items"]
    REN["Photo render<br/>her room, redesigned"]
    AST["3D assets<br/>image to 3D"]
  end
  subgraph Engine["Design engine"]
    DES["AI designer<br/>program, picks"]
    SOL["Solver<br/>places items"]
    VER["Verifier<br/>hard rules"]
    JUD["AI judge and taste ranker"]
  end
  subgraph Data["Data"]
    ROOM["Room model<br/>metres, sources"]
    CAT["Curated catalog<br/>sizes, 3D, links"]
    EV["Event log"]
  end
  CAP --> REC --> ROOM
  CAP --> SEG --> ROOM
  BRF --> DES
  ROOM --> DES
  CAT --> DES
  DES --> SOL --> VER
  VER -->|"fail: repair"| DES
  VER --> JUD --> REN --> UI
  AST --> CAT
  UI --> EV
```

- **Phone:** captures video, motion data and compass headings; shows guides, the reveal and the editor. No heavy AI on the device.
- **GPU workers:** scale to zero when idle. Reconstruction, segmentation, photo renders and 3D asset generation.
- **Design engine:** CPU service plus model calls. The AI designer proposes; the solver places; the verifier decides; the judge and taste ranker order what survives.
- **Data:** Postgres with pgvector for rooms, catalog and embeddings; object storage for media; an event log from day one for v2 learning.
- **API:** one Python modular monolith. Separate services only when load proves it necessary.
