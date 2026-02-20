# Plan: Cross-Session Memory + Cursor Adapter Hardening

**Feature Branch**: `[002-cross-platform-learning]`  
**Date**: 2026-01-29  
**Spec**: `/specs/002-cross-platform-learning/spec.md`

## Summary

Add a deterministic memory prefilter using the learning FTS index, wire connected platform paths into indexing, verify Cursor session ingestion, and document adapter contributions. Update Phase 2 docs to defer learning transfer and feedback loop to advanced features.

## Technical Context (repo scan)

- **Stack**: Python 3.12, SQLite (FTS5), CLI + Textual TUI.
- **Key modules/files**:
  - `acreta/agent/prompts.py` (memory/briefing prompts)
  - `acreta/memory/query/fts.py`, `acreta/memory/store/file_store.py`
  - `acreta/core/search/indexer.py`
  - `acreta/core/platforms.py`
  - `acreta/core/ingestion/cursor.py`, `acreta/core/api/session_viewer.py`
  - Docs: `docs/phases/phase-2-cross-platform.md`, `docs/phases/phase-2-tasks.md`, `docs/phases/advanced-features.md`, `README.md`

## Approach (mapped to primary user flow)

1. Build a local memory query engine that indexes learnings, filters by project + confidence, and ranks by FTS relevance.
2. Use the prefiltered results to build query/briefing prompts (agent still formats response).
3. Honor connected platform paths during indexing (cursor/cline/custom paths).
4. Update docs and add adapter contribution guide.

## Interfaces / APIs

- **New module**: `acreta/memory/query/engine.py`
  - `query_learnings(question, project_root, project_name, min_confidence=0.7, limit=20, memory_dir=None, memory_db_path=None) -> list[MemoryHit]`
  - `format_learning_context(hits: list[MemoryHit]) -> str`
- **Prompt changes**: `build_query_prompt(..., prefiltered: str | None = None)` and `build_briefing_prompt(..., prefiltered: str | None = None)`
- **Indexer change**: `index_new_sessions()` passes connected paths to parsers via `_collect_trace_runs(..., agent_paths=...)`.

## Data Model / Migrations (if any)

- No schema changes. Reuse `~/.acreta/memory/index.sqlite3` for FTS queries.

## Security / Privacy (if any)

- No new external calls; all memory prefiltering stays local.

## Observability

- No new logging required; keep existing behavior.

## Test Strategy (map to acceptance scenarios)

- Scenario P1.1/P1.2: new unit tests for `query_learnings` filtering/ranking.
- Scenario P1.3: test empty results path.
- Scenario P1 Cursor: add unit test showing indexing uses connected cursor path.
- Prompt tests updated for new `prefiltered` parameter.

## Rollout Plan (if user-facing)

- None (local CLI behavior change only).

## Risks + Mitigations

- **Risk**: FTS query errors on special characters → **Mitigation**: sanitize query tokens, fallback to confidence sort.
- **Risk**: Connected paths ignored by indexer → **Mitigation**: explicit agent path map + unit test.

## Assumptions (if needed)

- Agent response formatting remains acceptable when prefiltered learnings are provided.
