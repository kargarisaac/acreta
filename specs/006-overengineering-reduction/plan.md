# Acreta Plan: Overengineering Reduction (No Feature Loss)

Date: 2026-02-15  
Status: Draft  
Owner: Isaac

## Summary

This plan reduces code complexity without removing existing behavior.

Main target:
1. Keep all current user-facing functionality.
2. Reduce duplicate logic and repeated SQL/parse code.
3. Make runtime flow easier to maintain and test.

## How to use

Use this file as the execution checklist.

- Work phase by phase, in order.
- Do not skip checklist items.
- Mark each task from `[ ]` to `[x]` immediately after it is done.
- If blocked, keep the task unchecked and add a short blocker note under that phase.

## Scope

In scope:
- Refactor and deduplicate existing logic.
- Keep CLI commands and outputs compatible.
- Keep queue hot path and maintain cold path behavior.

Out of scope:
- New product features.
- Removing supported providers/adapters/commands.
- Schema-breaking changes without migration safety.

## Phase 1 - Extract/Sync Path Unification

Goal: one canonical session-processing flow.

- [ ] Document current overlap between `acreta/extract/orchestrator.py` and `acreta/app/daemon.py`.
- [ ] Refactor `run_extract_window` and `run_extract_backfill` into thin wrappers around canonical sync/maintain internals.
- [ ] Remove duplicated status/accounting logic while preserving result payload shape.
- [ ] Keep existing tests passing for extraction and sync behavior.

## Phase 2 - Dashboard Query Decomposition

Goal: reduce SQL duplication in dashboard endpoints.

- [ ] Move reusable session query/filter/pagination logic from `acreta/app/dashboard.py` into `acreta/sessions/catalog.py`.
- [ ] Keep dashboard endpoints as thin request/response handlers.
- [ ] Preserve endpoint paths and response JSON shapes.
- [ ] Add/adjust tests for dashboard query behavior parity.

## Phase 3 - Queue State Transition Simplification

Goal: one internal helper for queue state updates.

- [ ] Introduce a shared internal transition helper in `acreta/sessions/catalog.py`.
- [ ] Refactor `claim_session_jobs`, `heartbeat_session_job`, `complete_session_job`, and `fail_session_job` to use it.
- [ ] Preserve retry/backoff/dead-letter semantics exactly.
- [ ] Confirm queue lifecycle tests still pass.

## Phase 4 - Config Loader Deduplication

Goal: reduce repeated env/TOML parsing code.

- [ ] Create a compact field-spec approach in `acreta/config/settings.py` for repeated parse patterns.
- [ ] Keep same precedence order (explicit env, TOML layers, defaults).
- [ ] Preserve backward compatibility for legacy config paths.
- [ ] Keep current `Config` shape and `get_config()` behavior.

## Phase 5 - Search/FTS Helper Consolidation

Goal: remove duplicate text-query helpers and repeated filtering branches.

- [ ] Extract shared FTS token-to-OR-query helper used by CLI and memory search.
- [ ] Refactor callers in `acreta/app/cli.py` and `acreta/memory/search.py` to use one helper.
- [ ] Remove dead helper code and stale wrappers only if confirmed unused.
- [ ] Keep search ranking behavior and result ordering unchanged.

## Phase 6 - Embedding Runtime Simplification

Goal: keep embedding features with less custom protocol code.

- [ ] Isolate provider-independent embedding runtime path.
- [ ] Reduce custom request/poll parsing logic in `acreta/memory/vector.py` while preserving batch capability.
- [ ] Keep cache behavior and vector metadata compatibility.
- [ ] Confirm vector update/search behavior stays stable.

## Phase 7 - Cleanup and Verification

Goal: finish safely with clear evidence.

- [ ] Remove confirmed dead code paths found during phases.
- [ ] Update affected folder docs (`acreta/*/README.md`) if boundaries changed.
- [ ] Run unit test suite: `scripts/run_tests.sh unit`.
- [ ] Provide final report with changed files, behavior parity notes, and remaining risks.
- [ ] Ask Isaac which extra suite to run next (`integration`, `e2e`, or `quality`).

## Done Criteria

All must be true:

1. Every checklist task is `[x]` or explicitly blocked with reason.
2. No intended user-facing functionality removed.
3. Unit tests pass.
4. Docs reflect the simplified architecture.
