# Purpose

**Problem:** AI agents need persistent memory but no single taxonomy of memory types (episodic, semantic, procedural, parametric) exists with clear storage patterns and automated maintenance.

**Audience:** AI researchers, agent builders, and systems that need reliable long-term memory for learned facts, patterns, and experiences without external databases.

**Key constraints:** Must be file-based (portable, no database server), support 7+ memory types with distinct formats, include automated staleness audits, and integrate with wikilinks for knowledge graphs.

**Success metric:** An agent can write to and query its memory system, retrieve relevant facts at inference time, detect stale knowledge, and regenerate indices without manual intervention.
