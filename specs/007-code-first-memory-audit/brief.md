# 007 Code-First Memory Audit Brief

## Summary

This brief is for the next agent.

Goal:
- Inspect Acreta by reading the actual code paths, not docs.
- Verify how memory hot path, cold path, retrieval, and update logic currently work.
- Compare current behavior vs the desired system below.

## Desired system (from Isaac)

### 1) File-first and agentic retrieval

- Retrieval must be file-first.
- Primary retrieval should use agent tools such as `Read`, `Grep`, `Glob`, and optional `Bash` (`rg`).
- Optional backends (`fts`, `vector`, `graph`) are accelerators that can be enabled or disabled by user config.
- If a backend is disabled, it must not be used anywhere, including merge/update decisions.

### 2) No wiki-link dependency

- Do not depend on `[[wikilink]]` syntax.
- Graph should work from explicit references in canonical fields (for example `related` with IDs/slugs).
- If any wikilink behavior exists, treat it as legacy and flag for removal or compatibility-only mode.

### 3) DSPy boundary

- Use DSPy for extraction and recommendation only.
- DSPy can classify candidate memories and recommend `add|update|no-op`.
- Retrieval itself must stay tool-backed and file-first, and be executed by the lead agent (or its read-only explorer subagent).
- Final action authority stays with the lead agent and deterministic runtime policy, not DSPy.

### 4) Lead agent and explorer subagent

- One lead orchestrator agent should control CRUD flow.
- One explorer/search subagent can be used for read-only retrieval and candidate gathering.
- Explorer does not write memory.
- Lead is the only writer/deleter and the only final decider for `add|update|no-op|delete`.

### 5) CRUD behavior

- Create: extract -> retrieve similar -> dedupe check -> write canonical memory + sidecars.
- Read: retrieve from project-first scope with global fallback, based on configured scope mode.
- Update: extract delta -> retrieve neighbors -> deterministic merge/update write.
- Delete: explicit policy path (soft-first preferred, hard delete only explicit).

### 6) Scope and storage

- Project-first `.acreta/` with global fallback `~/.acreta/`.
- Canonical files in primitive folders:
  - `memory/decisions`
  - `memory/learnings`
  - `memory/conventions`
  - `memory/context`
- Operational metadata in sidecars:
  - `meta/state`
  - `meta/evidence`

### 7) Hot path vs cold path contract

- Keep hot path lightweight and deterministic:
  - ingest session
  - extract candidate primitives
  - retrieve similar memories (file-first)
  - decide `add|update|no-op`
  - write canonical files + sidecars
- Keep heavy/background tasks in cold path:
  - consolidation
  - decay/retention
  - full index rebuilds
  - graph rebuild/audit jobs
  - cleanup/reporting jobs
- Query path is read-only and separate from mutation paths.
- If a backend is disabled, neither hot nor cold path should silently use it.

## What must be audited in code

- `acreta/app/daemon.py`
- `acreta/extract/orchestrator.py`
- `acreta/extract/parser.py`
- `acreta/runtime/agent.py`
- `acreta/runtime/subagents.py`
- `acreta/runtime/guardrails.py`
- `acreta/memory/search.py`
- `acreta/memory/store.py`
- `acreta/memory/models.py`
- `acreta/memory/maintenance.py`
- `acreta/memory/graph.py`
- `acreta/config/settings.py`
- `acreta/config/project_scope.py`
- `acreta/sessions/catalog.py`
- `acreta/app/cli.py`

## Required audit output

- A code-grounded architecture map of current flow:
  - ingest -> queue -> extract -> write -> search -> maintain
- A gap list: current behavior vs desired behavior above.
- Severity-ranked issues and risks.
- Concrete implementation plan with exact file targets and ordered steps.
- Explicit callouts for:
  - non-agentic retrieval paths
  - wiki-link dependencies
  - hidden/implicit vector usage
  - places where DSPy is missing but required by target design
  - hot path doing cold-path work (or cold path missing required maintenance)
