# Working Memory

Working memory is everything currently in the model's context window. It
is not persisted here — persisting it would defeat the purpose of a
context window and duplicate what the agent already has.

This folder holds only `distill.template.md`: a checklist an agent runs
through at the end of a session to decide what — if anything — is worth
promoting to `episodic/`, `semantic/`, or `prospective/` before the
context is lost.
