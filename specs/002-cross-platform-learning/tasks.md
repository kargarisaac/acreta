# Tasks: Cross-Session Memory + Cursor Adapter Hardening

**Spec**: `/specs/002-cross-platform-learning/spec.md`  
**Decisions**: `/specs/002-cross-platform-learning/decisions.md`  
**Plan**: `/specs/002-cross-platform-learning/plan.md`

## Instructions

- Group tasks by user story priority (P1, P2, ...).
- Every acceptance scenario must have:
  - At least one implementation task, and
  - At least one verification task (test/manual).
- Include explicit test tasks and a final “Verify all acceptance scenarios” task.
- Tasks should be sized for ~30–90 minutes.

## P1 — Cross-session memory retrieval

### Acceptance Scenario 1
- [x] [Impl] Add `acreta/memory/query/engine.py` with FTS + confidence prefiltering and project scope filtering.
- [x] [Impl] Wire prefiltered context into `build_query_prompt` / `build_briefing_prompt` and CLI (`acreta/core/cli/main.py`).
- [x] [Verify] Add unit tests for `query_learnings` filtering and ranking.

### Acceptance Scenario 2
- [x] [Impl] Ensure query sanitization/fallback for invalid FTS queries.
- [x] [Verify] Add unit test covering low-confidence and wrong-project exclusions.

### Acceptance Scenario 3
- [x] [Verify] Add unit test for empty/no-match query response path.

## P1 — Cursor sessions are ingestible from connected paths

### Acceptance Scenario 1
- [x] [Impl] Respect connected platform paths when collecting sessions in `acreta/core/search/indexer.py` and `acreta/core/platforms.py`.
- [x] [Verify] Add unit test that indexes cursor sessions from a custom connected path.

### Acceptance Scenario 2
- [x] [Verify] Extend platform counting logic test to include Cursor nested `state.vscdb`.

## P2 — Adapter contribution guide

### Acceptance Scenario 1
- [x] [Impl] Write adapter contribution guide doc in `docs/adapter-contribution.md`.
- [x] [Verify] Update Phase 2 docs (remove 2.3/2.4) and move them to advanced features.

## Final Verification

- [x] Verify all acceptance scenarios
