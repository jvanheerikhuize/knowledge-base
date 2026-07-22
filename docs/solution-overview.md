# Solution Overview

## System at a glance

```mermaid
flowchart TB
    subgraph Sources["Raw Sources (immutable)"]
        S1[Docs / transcripts]
        S2[Web pages]
        S3[Prior agent sessions]
    end

    subgraph Ingestion["Ingestion Layer"]
        ING["scripts/kb.py new\n(agent-assisted classification)"]
    end

    subgraph KB["memory/ — the knowledge base"]
        ENTRY["AGENT.md\n(single entry point)"]
        SEM["semantic/"]
        EPI["episodic/"]
        PRO["procedural/"]
        WRK["working/"]
        RET["retrieval/"]
        PAR["parametric/"]
        PRS["prospective/"]
    end

    subgraph Interface["Interaction Interface"]
        CLI["scripts/kb.py\nlist / search / show / lint"]
    end

    subgraph Viz["Visualization Layer"]
        GEN["scripts/visualize.py"]
        GRAPH["memory/_generated/graph.mmd"]
    end

    subgraph Pipeline["Scaffolder / CI"]
        SCAF["scripts/scaffold.sh"]
        GHA[".github/workflows/kb-lint.yml"]
    end

    Sources --> Ingestion --> KB
    ENTRY -.orients.-> SEM & EPI & PRO & WRK & RET & PAR & PRS
    KB --> CLI
    KB --> GEN --> GRAPH
    GHA --> GEN
    GHA --> CLI
    SCAF -. drops memory/+scripts/ into any repo .-> KB
```

## Memory taxonomy → folder mapping

Based on the CoALA framework and the 7-types article:

```mermaid
flowchart LR
    classDef persisted fill:#2e7d32,color:#fff
    classDef ephemeral fill:#8d6e63,color:#fff
    classDef boundary fill:#455a64,color:#fff

    Working["Working\n(in-context)\nfolder: working/"]:::ephemeral
    Semantic["Semantic\nfacts & preferences\nfolder: semantic/"]:::persisted
    Episodic["Episodic\npast events/runs\nfolder: episodic/"]:::persisted
    Procedural["Procedural\nskills & workflows\nfolder: procedural/"]:::persisted
    Retrieval["Retrieval\nfile-based search index\nfolder: retrieval/"]:::persisted
    Parametric["Parametric\nmodel-weight knowledge\nfolder: parametric/ (boundary notes only)"]:::boundary
    Prospective["Prospective\nfuture intentions\nfolder: prospective/"]:::persisted

    Working -- "distilled at session end" --> Episodic
    Episodic -- "repeated pattern promoted" --> Procedural
    Episodic -- "durable fact extracted" --> Semantic
    Semantic -- "indexed for lookup" --> Retrieval
    Prospective -- "fires, becomes" --> Episodic
```

`working/` never stores raw context (that would defeat the purpose of a
context window); it holds only the *template* an agent uses to distill a
session before it ends. `parametric/` is documentation-only: it records the
explicit boundary of what the KB assumes any capable model already knows,
so entries aren't wasted re-stating common knowledge.

## Entry lifecycle (ingestion → fact-check → visualization)

```mermaid
sequenceDiagram
    participant Agent
    participant KB as memory/<type>/*.md
    participant Lint as kb.py lint
    participant Viz as visualize.py

    Agent->>KB: kb.py new --type semantic "fact name"
    Note over KB: writes frontmatter:<br/>confidence, source, last_verified, links
    Agent->>KB: fills in content, sets confidence
    Agent->>Lint: kb.py lint
    Lint-->>Agent: flags stale (>90d unverified),<br/>contradicting entries, orphan links
    Agent->>KB: resolves flags, updates last_verified
    Agent->>Viz: scripts/visualize.py
    Viz->>KB: reads all frontmatter
    Viz-->>KB: writes memory/_generated/graph.mmd
```

## Entry format (all memory types share this shape)

```yaml
---
name: kebab-case-slug
type: semantic|episodic|procedural|working|retrieval|prospective
description: one-line summary
confidence: verified|high|medium|low|unverified
source: where this came from (URL, session, person)
created: YYYY-MM-DD
last_verified: YYYY-MM-DD
links: [other-entry-slug, ...]
---

Body content in markdown.
```

This is deliberately close to the frontmatter convention already used by
static-site generators (Jekyll/Hugo) and note-taking tools (Obsidian) —
familiar to humans, trivially parsable by any agent, and requires no schema
server to validate (a plain JSON Schema file is provided for optional
local validation).

## Single point of entry

`memory/AGENT.md` is the one file every agent reads first. It explains:
- the folder-per-memory-type layout and when to use each
- the confidence-scoring rubric
- how to add an entry (`kb.py new`), search (`kb.py search`), and audit
  (`kb.py lint`)
- links to `docs/plan.md` and `docs/roadmap.md` for the "why"

This mirrors the emerging `AGENTS.md` convention and Karpathy's schema
document pattern, kept solution-agnostic — nothing in it assumes a
particular agent framework or model provider.
