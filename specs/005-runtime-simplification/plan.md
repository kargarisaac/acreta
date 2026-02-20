# Acreta Plan: Runtime Simplification Refactor

Date: 2026-02-15  
Status: Draft  
Owner: Isaac

## Summary

This plan simplifies current Acreta runtime code without removing product behavior.

Target:
1. Keep full feature set.
2. Reduce duplicated logic and cross-module coupling.
3. Make runtime paths easier to reason about and test.

Phase rule:
- One simplification item equals one phase.

## How to use

Use this as the implementation checklist.

- Execute phases in order.
- Keep each phase small and reviewable.
- Run tests for each phase before moving forward.
- After all phases, run full unit tests.
- After full unit pass, ask Isaac which extra suite to run (`integration`, `e2e`, `quality`).

## Scope

In scope:
- Refactor for fewer lines, less duplication, less coupling.
- Keep same CLI behavior and same runtime outputs.

Out of scope:
- New features.
- Product behavior change.
- Removing supported commands from CLI surface.

## Technical context (from review)

Hotspots:
- `acreta/extract/orchestrator.py`
- `acreta/app/daemon.py`
- `acreta/app/cli.py`
- `acreta/app/dashboard.py`
- `acreta/sessions/catalog.py`
- `acreta/memory/search.py`
- `acreta/memory/vector.py`
- `acreta/adapters/*`

Main test anchors:
- `tests/test_cli.py`
- `tests/test_learning_runs.py`
- `tests/test_graph_explorer_frontend.py`
- `tests/test_maintain_command.py`
- `tests/test_context_layers_e2e.py`

## Phases

### [x] Phase 1 - Extract duplicate logic collapse

Goal: remove duplicate metrics and JSON parse logic in extraction path.

Refactor:
- Remove duplicated metrics scanner/helpers from `acreta/extract/orchestrator.py`.
- Reuse `collect_metrics` and helpers from `acreta/extract/metrics.py` as single source.
- Reuse `extract_json_value` from `acreta/extract/parser.py` in window report parse path.

Files:
- `acreta/extract/orchestrator.py`
- `acreta/extract/metrics.py`
- `acreta/extract/parser.py`

Verification:
- Run extraction-focused tests.
- Run unit tests touching report generation and extraction parsing.

### [x] Phase 2 - CLI/daemon boundary cleanup

Goal: stop daemon importing private CLI helper functions.

Refactor:
- Move shared argument parsing helpers to one neutral module (for example `acreta/app/arg_utils.py`).
- Update `acreta/app/cli.py` and `acreta/app/daemon.py` to import from shared module.
- Keep CLI UX and flags unchanged.

Files:
- `acreta/app/cli.py`
- `acreta/app/daemon.py`
- `acreta/app/arg_utils.py` (new)

Verification:
- Run `tests/test_cli.py`.
- Run daemon-related unit tests.

### [x] Phase 3 - MemoryIndex lifecycle simplification

Goal: remove `MemoryIndex.__new__` usage and make DB-open behavior explicit.

Refactor:
- Add explicit constructor/classmethod for read-only use without schema-init side effects.
- Replace `__new__` patterns in chat context and memory search paths.
- Keep search/query behavior identical.

Files:
- `acreta/memory/index.py`
- `acreta/memory/search.py`
- `acreta/app/cli.py`

Verification:
- Run memory search tests and chat-context tests.
- Validate `acreta status --json` still reports memory count.

### [x] Phase 4 - Adapter shared utility consolidation

Goal: reduce repeated helper code across adapters.

Refactor:
- Introduce shared helpers in adapter common module for timestamp parsing, JSONL line loading, file count helpers, and window filtering.
- Replace duplicated helpers in `claude`, `codex`, `cline`, `cursor`, `opencode` where valid.
- Remove unused helper `parse_iso_utc` from `acreta/adapters/base.py` if no caller remains.

Files:
- `acreta/adapters/base.py`
- `acreta/adapters/claude.py`
- `acreta/adapters/codex.py`
- `acreta/adapters/cline.py`
- `acreta/adapters/cursor.py`
- `acreta/adapters/opencode.py`
- `acreta/adapters/common.py` (new)

Verification:
- Run adapter/session indexing tests.
- Run unit tests covering connected platform behavior.

### [x] Phase 5 - Queue API surface unification

Goal: remove confusing dual queue API surface.

Refactor:
- Standardize internal imports to one canonical queue API path.
- Pick one canonical path: keep queue facade as canonical and move queue logic there, or remove shim and import from canonical sessions module consistently.
- Keep backward compatibility for existing internal call sites during migration.

Files:
- `acreta/sessions/catalog.py`
- `acreta/sessions/queue.py`
- `acreta/sessions/__init__.py`
- call sites in `acreta/app/*`

Verification:
- Run `tests/test_learning_runs.py`.
- Run status/dashboard API tests that read queue state.

### [x] Phase 6 - Dashboard decomposition and graph expand efficiency

Goal: simplify monolithic dashboard handler and avoid full graph-query then prune.

Refactor:
- Split `DashboardHandler._handle_api_get` into endpoint-specific handlers.
- Keep route contract unchanged.
- Refactor memory-graph expand flow to build focused graph response directly.
- Remove redundant in-memory filtering passes where possible.

Files:
- `acreta/app/dashboard.py`

Verification:
- Run dashboard and graph explorer tests.
- Validate all current API endpoints and response shapes.

### [x] Phase 7 - Embedding pipeline path consolidation

Goal: simplify embedding path while keeping capabilities.

Refactor:
- Create one embedding execution path used by maintenance/search.
- Keep batch support capability, but hide provider-specific branching behind one helper.
- Remove repeated per-chunk embed/cache/write patterns from callers.
- Remove dead fields/unused members (for example unused vector store members) if safe.

Files:
- `acreta/memory/vector.py`
- `acreta/memory/maintenance.py`
- `acreta/memory/search.py`

Verification:
- Run memory/vector-related tests.
- Validate vector-meta compatibility and query behavior.

### [x] Phase 8 - Session catalog initialization simplification

Goal: reduce repeated DB init and mixed schema/runtime logic in catalog module.

Refactor:
- Centralize schema init/migration bootstrap logic.
- Avoid calling `init_sessions_db()` in every public function when already initialized.
- Keep same migration safety and backward-compatible DB behavior.
- Keep queue lifecycle semantics unchanged.

Files:
- `acreta/sessions/catalog.py`
- optional schema helper module under `acreta/sessions/`

Verification:
- Run `tests/test_learning_runs.py`.
- Run maintain/sync tests and status checks.

## Risks and mitigations

Risk 1: hidden behavior drift during dedupe.
- Mitigation: phase-by-phase tests and no scope mixing.

Risk 2: accidental API response change in dashboard.
- Mitigation: keep endpoint contracts fixed; run existing dashboard tests.

Risk 3: queue lifecycle regressions.
- Mitigation: keep `tests/test_learning_runs.py` as hard gate for related phases.

Risk 4: adapter parsing regressions across platforms.
- Mitigation: keep adapter-specific tests and fixture-based checks.

## Done criteria

All criteria must pass:

1. All 8 phases completed.
2. No intended functionality removed.
3. Unit suite passes: `scripts/run_tests.sh unit`.
4. Docs updated where boundaries changed (`acreta/*/README.md` and relevant docs).
5. Ask Isaac which extra suite to run next (`integration`, `e2e`, or `quality`).
