# Agent Instructions for knowledge-base

This repository is maintained with the help of AI coding agents (Claude, Antigravity, Cursor, etc.).

## Overview
File-based agent memory store with seven memory types — semantic, episodic,
procedural, working, retrieval, parametric, prospective — one folder per type
under `memory/`.

## Key Rules
- **Read [`memory/AGENT.md`](memory/AGENT.md) first.** It is the authoritative
  contract for this repo, whichever agent or framework you are: the taxonomy,
  the confidence rubric, the `authority` field, and the check to run before
  adding an entry. `.claude/CLAUDE.md` is a summary of it, not a second source
  of truth.
- Storage is portable Markdown with YAML frontmatter. JSON appears only in
  machine-readable config under `.kb/` and in the generated `site/` bundle —
  never as an entry format.
- Workspace-wide multi-agent coexistence rules live in the workspace meta-repo
  [`jvanheerikhuize/repos`](https://github.com/jvanheerikhuize/repos), which
  holds this repository as a git submodule. That repo, not a path on any one
  machine, is where `AGENTS.md`, `CLAUDE.md` and `INTEGRATION.md` for the
  workspace are kept.
