# Working in knowledge-base

File-based agent memory system with 7-type taxonomy (episodic, semantic, procedural, parametric, and variants). Automated maintenance (staleness audits, regeneration). Integration point with digital-twin and asdlc knowledge systems.

## How to Work Here

**Architecture:**
- `types/` — memory type definitions and storage patterns
- `templates/` — per-type templates for new memories
- `ci/` — automated audits (staleness detection, index regeneration)
- `ingestion/` — how to add new memories programmatically

**Adding a new memory:**
1. Choose type (episodic/semantic/procedural/parametric)
2. Use appropriate template from `templates/<type>/`
3. Follow frontmatter format (name, description, metadata)
4. Maintain wikilinks to related memories
5. Commit with clear message about memory category

**Before committing:**
- Run `python3 ci/lint.py` to validate memory format
- Verify staleness dates are accurate (or omit if always-current)
- Check wikilinks are resolvable
- Test index regeneration

**Index regeneration:** Run `python3 ci/regenerate_graph.py` after adding many memories.

**Never:** Edit auto-generated index files directly — they regenerate on commit.

**Integration:** Keep wikilinks consistent across knowledge-base, knowledge, and digital-twin.
