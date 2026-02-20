# Plan: Acretia Core Simplification (Memory Extraction + Search)

**Feature Folder**: `/Users/isaackargar/codes/personal/acreta/specs/003-acretia-core-simplification`  
**Date**: 2026-02-14  
**Owner**: Isaac  
**Goal**: Keep only the core product path: connect agent traces -> extract memory -> store/index -> search memory, with a clean hot/cold pipeline.

## Summary

This plan removes product-surface complexity that is not core to Acretia.  
Core scope after cleanup:

1. Ingest sessions from connector paths.
2. Queue each new session for processing.
3. Extract semantic/procedural/episodic memory using tool-first bounded reads.
4. Store memory and raw markdown artifacts.
5. Index for full-text + vector search.
6. Query memory reliably.
7. Run daily consolidation/forgetting as a separate cold lane.

## Clarifications (from current code)

`cases` and `enrichment` today are separate artifacts:
- `Case` = structured session outcome record (goal, actions, outcome, files, commands, errors), in `/Users/isaackargar/codes/personal/acreta/acreta/memory/store/models.py`.
- `EnrichmentDoc` = generated context docs (repo overview, module summaries, session digest), also in `/Users/isaackargar/codes/personal/acreta/acreta/memory/store/models.py`.

Why this matters:
- They add extra storage types and indexing branches.
- They are also injected into default query context in `/Users/isaackargar/codes/personal/acreta/acreta/search/pipeline.py`.
- For a simpler product surface, we should fold needed value into core memory types (especially episodic session summary) and remove extra runtime branches.

## Current-State Findings To Act On

- [x] Fix sync extraction loss bug in `/Users/isaackargar/codes/personal/acreta/acreta/cli/commands/lanes.py` (`run_sync_once` truncates newly indexed run IDs, which can skip extraction forever for overflow sessions).
- [x] Replace daemon trigger queue-only model in `/Users/isaackargar/codes/personal/acreta/acreta/service/daemon.py` with durable per-session job queue for hot-path processing.
- [x] Remove query-time index mutation in `/Users/isaackargar/codes/personal/acreta/acreta/search/memory/search.py` and `/Users/isaackargar/codes/personal/acreta/acreta/search/pipeline.py` (`index.sync_from_store(...)` inside query path).
- [x] Resolve two graph systems:
  Retrieval graph writes `graph_edges` in `/Users/isaackargar/codes/personal/acreta/acreta/search/pipeline.py` and `/Users/isaackargar/codes/personal/acreta/acreta/search/memory/graph.py`.
  Dashboard graph separately derives nodes/edges from file store in `/Users/isaackargar/codes/personal/acreta/acreta/web/graph_service.py`.
- [x] Remove runtime evaluation surface from CLI and runtime evaluation modules, as requested.
- [x] Remove dead command handlers not wired in parser:
  `/Users/isaackargar/codes/personal/acreta/acreta/cli/main.py` (`_cmd_collect`, `_cmd_readiness`, `_cmd_runs`, `_cmd_serve`).
- [x] Remove dead/legacy runtime paths:
  `run_background_pipeline()` in `/Users/isaackargar/codes/personal/acreta/acreta/search/pipeline.py`, and legacy `learning_runs` path in `/Users/isaackargar/codes/personal/acreta/acreta/sessions/storage.py` if not used by active flow/tests.

## Decision: Two Graph Systems

Recommendation:
- Keep one canonical graph source for runtime retrieval.
- Dashboard graph must read from canonical graph/index artifacts, not rebuild separate logic/scoring from raw files.

Reason:
- Two independently computed graphs drift.
- Retrieval and visualization can disagree, reducing trust.
- One graph engine lowers maintenance and test surface.

Execution choice for this phase:
- Keep retrieval graph semantics.
- Refactor dashboard graph endpoint to adapt canonical graph output (projection/filter only), not recompute relationships.

## Target Simplified Architecture

Hot path (near real-time):
1. Connector discovers new session (`run_id`).
2. Session queued in durable `session_jobs`.
3. Worker pulls job, runs tool-first extraction.
4. Writes:
   - raw archived markdown/trace
   - memory records (semantic/procedural/episodic)
   - FTS index rows
   - vector rows
   - canonical graph updates (or deferred incremental mark for maintain rebuild)
5. Marks job done/failed with retries and error details.

Cold path (daily):
1. Consolidate duplicate/overlapping memories.
2. Decay/forget stale memories.
3. Rebuild/validate global graph and vectors if needed.
4. Produce maintenance report only.

Query path:
- Strict read-only: no indexing writes, no schema building, no store sync side effects.

## Implementation Tasks

### Phase 0 — Freeze Scope and Safety
- [x] Create branch `codex/003-core-simplification`.
- [x] Capture baseline `pytest -q` and CLI smoke (`sync`, `maintain`, `chat`, `memory search`).
- [x] Add migration/rollback notes for any DB schema changes before touching runtime.

#### Migration / Rollback Notes (before schema edits)

- Planned schema change: add durable `session_jobs` table in `sessions.sqlite3` for hot-path extraction queue.
- Planned schema cleanup: stop creating/using legacy `learning_runs` table in active runtime path.
- Forward migration strategy:
  - Use `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` only (additive, safe on existing DBs).
  - Keep existing refine/service tables untouched.
  - Keep old data files in memory store unchanged.
- Rollback strategy:
  - Runtime rollback is code-level: switch back to previous commit; old tables still readable.
  - Data rollback is non-destructive: optional manual drop of `session_jobs` only if needed.
  - No destructive migration on existing learning/session rows in this phase.

### Phase 1 — Remove Non-Core Runtime Surface
- [x] Remove runtime evaluation CLI command tree in `/Users/isaackargar/codes/personal/acreta/acreta/cli/main.py`.
- [x] Remove eval task specs (`EVAL_DATASET_GENERATE`, `EVAL_ANSWER`) from `/Users/isaackargar/codes/personal/acreta/acreta/agents/engine/task_specs.py` if no remaining runtime consumer.
- [x] Remove runtime evaluation package usage and clean imports.
- [x] Update CLI docs and README references to eval command removal.
- [x] Keep internal validation as tests/scripts only (non-runtime path).

### Phase 2 — Reduce Memory Model Complexity
- [x] Decide and implement one model for episodic session memory (replace separate case/enrichment query-context default usage).
- [x] Remove case/enrichment as default query context layers from `/Users/isaackargar/codes/personal/acreta/acreta/search/pipeline.py`.
- [x] Keep optional offline generation only if needed; otherwise remove case/enrichment runtime ingestion/indexing branches.
- [x] Ensure semantic/procedural/episodic are all persisted in one consistent retrieval surface.

### Phase 3 — Queue-Centered Hot Path
- [x] Introduce durable session job table/queue (status, retries, timestamps, run_id uniqueness).
- [x] Enqueue every newly indexed session immediately.
- [x] Refactor `run_sync_once` in `/Users/isaackargar/codes/personal/acreta/acreta/cli/commands/lanes.py` to process from queue, not sliced in-memory list.
- [x] Fix overflow behavior so no newly indexed session can be dropped from extraction.
- [x] Add retry/backoff and dead-letter behavior for failed session extraction jobs.

### Phase 4 — Tool-First Extraction Hardening
- [x] Enforce bounded tool-first evidence retrieval in extraction flows (no full session dump into prompt context).
- [x] Add explicit guardrails/tests that extraction prompts include archive path + bounded read strategy.
- [x] Keep one primary SDK worker path for extraction/search orchestration.

### Phase 5 — Read-Only Query Path
- [x] Remove `index.sync_from_store(...)` from query-time flows in:
  `/Users/isaackargar/codes/personal/acreta/acreta/search/memory/search.py` and
  `/Users/isaackargar/codes/personal/acreta/acreta/search/pipeline.py`.
- [x] Move all index writes to ingestion/maintain stages only.
- [x] Add tests proving query commands do not mutate index state.

### Phase 6 — Graph Unification
- [x] Keep one canonical graph relation model for retrieval.
- [x] Refactor `/Users/isaackargar/codes/personal/acreta/acreta/web/graph_service.py` to consume canonical graph outputs.
- [x] Remove duplicate edge construction/scoring paths from dashboard service.
- [x] Add parity tests: dashboard graph view must reflect retrieval graph relationships for same memory set.

### Phase 7 — Dead Code and Unused Code Removal
- [x] Delete dead handlers in `/Users/isaackargar/codes/personal/acreta/acreta/cli/main.py` (`_cmd_collect`, `_cmd_readiness`, `_cmd_runs`, `_cmd_serve`).
- [x] Remove `run_background_pipeline()` from `/Users/isaackargar/codes/personal/acreta/acreta/search/pipeline.py` if unreferenced.
- [x] Remove legacy `learning_runs` runtime path from `/Users/isaackargar/codes/personal/acreta/acreta/sessions/storage.py` if no active caller.
- [x] Run static dead-code sweep and remove findings:
  - `ruff check . --select F401,F841`
  - `vulture acreta` (if available; otherwise document skip).
- [x] Clean unused imports and unreachable branches across touched files.

Dead-code sweep notes:
- `ruff check . --select F401,F841`: pass after cleanup.
- Removed dead runtime branches/folders tied to non-core memory artifacts:
  - `/Users/isaackargar/codes/personal/acreta/acreta/refine/enrichment/`
  - `/Users/isaackargar/codes/personal/acreta/acreta/memory/store/case_store.py`
  - `/Users/isaackargar/codes/personal/acreta/acreta/memory/store/enrichment_store.py`
- Additional repo-wide dead-code cleanup completed:
  - removed remaining unreferenced functions/constants/tests tied to removed runtime surfaces.
  - added explicit `vulture` whitelist file for dynamic-framework false positives (Pydantic fields, `row_factory`, HTTP handler dispatch methods).
  - verification command now: `vulture acreta tests vulture_whitelist.py` (passes with no findings).

### Phase 8 — Maintain Lane Separation
- [x] Keep maintain as explicit daily cold lane for consolidation/decay/report.
- [x] Ensure hot lane does immediate extraction + indexing only.
- [x] Confirm maintain does not re-do hot-lane core extraction work.
- [x] Verify schedule defaults and docs match actual behavior.

### Phase 9 — Tests and Verification
- [x] Add/adjust unit tests for queue lifecycle, sync no-drop guarantee, and query read-only guarantees.
- [x] Add regression test for previously dropped run IDs in sync overflow condition.
- [x] Add tests for unified graph behavior (retrieval vs dashboard parity).
- [x] Run targeted unit tests for changed modules.
- [x] Run full unit suite via `scripts/run_tests.sh unit`.
- [x] Record any integration/e2e suggestions, but do not run without explicit confirmation.

Integration/E2E suggestions (not run in this pass):
- `ACRETA_INTEGRATION=1 pytest tests/test_runner.py -k Integration`
- Daemon trigger + queue durability smoke: run `acreta daemon` + `acreta daemon --trigger sync --wait` with synthetic sessions.
- Dashboard graph API smoke against canonical graph: `/api/memory-graph/query` + `/api/memory-graph/expand` on sample memory corpus.

### Phase 10 — Docs and Handoff
- [x] Update `/Users/isaackargar/codes/personal/acreta/README.md` for simplified scope and removed runtime surfaces.
- [x] Update `/Users/isaackargar/codes/personal/acreta/.claude/skills/acreta/cli-reference.md` to match real commands only.
- [x] Update architecture docs to describe queue-first hot path and maintain-only cold path responsibilities.
- [x] Update folder-level READMEs for changed domain boundaries.
- [x] Mark completed checklist items in this plan file during implementation.

## Acceptance Criteria

- [x] No runtime evaluation command remains in CLI surface.
- [x] No dead handlers/functions remain for removed surfaces.
- [x] New sessions are never silently dropped from extraction due to list slicing.
- [x] Query path performs no write/index sync side effects.
- [x] Memory retrieval core supports semantic/procedural/episodic output.
- [x] Dashboard graph is a view over canonical graph data, not a second graph engine.
- [x] Unit tests pass for all changed behavior.

## Out of Scope (for this phase)

- Multi-agent analysis system.
- Team memory sharing product features.
- New frontend/dashboard redesign beyond graph data-path simplification.

## Notes For Implementer

- Keep edits small and reviewable.
- Prefer removal over deprecation when code is clearly dead and not in active tests.
- If a removal impacts public CLI docs, update docs in the same change.
- If any ambiguity appears about keeping `cases/enrichment` as runtime artifacts, prioritize minimal core path and ask one short decision question before implementing irreversible schema deletions.
