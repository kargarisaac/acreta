# Plan: Agent-Led Memory Write Flow (Claude SDK)

**Feature Branch**: `008-agent-led-memory-write-flow`  
**Date**: 2026-02-20  
**Spec**: Assumption: no `spec.md` yet; this plan is derived from user request + current code scan.

## Summary
This plan simplifies memory writing around one lead agent flow driven by `trace_path`, not raw trace content in prompt context.

Core direction:
- lead receives `trace_path`
- lead creates todos with `TodoWrite`
- lead runs DSPy pipelines via CLI using file path and saves outputs to workspace artifacts
- lead uses read-only explorer subagents to inspect memory files and decide `add|update|no-op`
- lead writes markdown+YAML frontmatter memory files
- summary is always written to `.acreta/memory/summaries/`

Hard constraints from request:
- no versioning
- no migrations/backfill
- no legacy paths in new flow

## Technical Context (repo scan)
- **Stack**: Python 3.12, Claude Agent SDK, DSPy, markdown file store.
- **Lead runtime**: `/Users/kargarisaac/codes/personal/acreta/acreta/runtime/agent.py`
- **Extraction pipeline**: `/Users/kargarisaac/codes/personal/acreta/acreta/memory/extract_pipeline.py`
- **Summarization pipeline**: `/Users/kargarisaac/codes/personal/acreta/acreta/memory/summarization_pipeline.py`
- **Models**: `/Users/kargarisaac/codes/personal/acreta/acreta/memory/models.py`
- **Layout**: `/Users/kargarisaac/codes/personal/acreta/acreta/memory/layout.py`
- **Store**: `/Users/kargarisaac/codes/personal/acreta/acreta/memory/store.py`
- **Current issue**: `agent.py` sets `permission_mode="bypassPermissions"` and passes `extra_args={"no-session-persistence": None}`.

Code facts relevant to your flow:
- pipelines already support direct file-path entry points:
  - `extract_memories_from_session_file(session_file_path=...)`
  - `summarize_trace_from_session_file(session_file_path=...)`
- this enables strict `trace_path` flow without loading trace text into lead prompt.

## Approach (mapped to primary user flow)
1. **Input contract**
- Lead input becomes:
  - `trace_path` (required)
  - `memory_root` (default: `<repo>/.acreta/memory`)
  - `workspace_root` (default: `<repo>/.acreta/workspace`)
  - `run_mode` (`hot|cold|sync`) for observability grouping
- Lead does `Path(trace_path).exists()` and fails fast on missing files.

2. **Per-run workspace folder (always)**
- For every run, create:
  - `.acreta/workspace/<run_mode>-<YYYYMMDD-HHMMSS>-<shortid>/`
- Keep run folder flat (no Acreta-managed nested subfolders).
- Write intermediate outputs as flat files in that folder:
  - `extract.json`
  - `summary.json`
  - `memory_actions.json`
  - `agent.log`
  - `subagents.log`
  - `session.log` (optional session/transcript pointer data)
- Lead and subagents persist intermediate state to this run folder, not in-context memory.

3. **Todo-first orchestration**
- Lead writes explicit todo list via `TodoWrite`:
  - validate inputs
  - run extract pipeline
  - run summary pipeline
  - run explorer checks
  - decide add/update/no-op
  - write memory files
  - write run decision report

4. **Run pipelines with `trace_path`, save artifacts**
- Prompt includes exact CLI calls (path mode):
  - extract command writes `extract.json`
  - summary command writes `summary.json`
- Lead can use `Read` on artifact files for downstream decisioning.
- Lead never requests full raw trace dump into conversation.

5. **Explorer subagents: built-in first**
- Use built-in `Explore` subagents for read-only candidate matching.
- Do not define custom subagents in phase 1 unless output format proves unstable.
- Fan-out 1-3 explorers based on candidate count.
- Explorer output schema: `candidate_id`, `action_hint`, `matched_file`, `evidence`.

6. **Lead-only write decision**
- For each non-summary candidate:
  - `add` when no strong match
  - `update` when same intent and overlap above threshold
  - `no-op` when duplicate/no delta
- Summary is always episodic and always `add` to `summaries`.

7. **Write markdown files**
- Lead writes memory files under configured memory root only.
- Summary always targets `.acreta/memory/summaries/`.
- If action is `update`, modify matched file in-place; no duplicate new file.

## Interfaces / APIs (contract)
1. **Central memory registry (single source)**
- Add canonical module (example: `acreta/memory/types.py`) with:
  - `MemoryType` enum
  - per-type definition text
  - folder mapping
  - example snippets for prompts/docstrings
- `extract_pipeline.py`, `summarization_pipeline.py`, and `models.py` all import this registry.

2. **Minimal taxonomy option (recommended)**
- Reduce active long-term types to:
  - `decision`
  - `learning`
  - `summary` (episodic only, dedicated folder)
- Represent `context` and `convention` as `learning` subtypes/tags, not separate folders.

3. **Agent runtime API**
- Keep one simple lead entry:
  - `run(trace_path, memory_root=None, workspace_root=None, run_mode="sync")`
- Return payload:
  - artifact paths
  - created/updated/no-op counts
  - written memory paths
  - summary path
  - run folder path

## Data Model / Migrations
- Add folder: `.acreta/memory/summaries/`.
- Add workspace folder: `.acreta/workspace/`.
- Keep file format: markdown with YAML frontmatter.
- No migration plan. No version fields. No backfill of existing memory files.

Summary frontmatter baseline:
- `id`, `title`, `description`, `date`, `time`, `coding_agent`, `raw_trace_path`, `run_id`, `repo_name`, `related`, `created`, `updated`

## Security / Privacy
Mandatory controls:
- remove `bypassPermissions` for this path
- keep lead toolset minimal: `Read`, `Grep`, `Glob`, `Task`, `TodoWrite`, `Bash`, `Write`, `Edit`
- explorer subagents read-only only: `Read`, `Grep`, `Glob`
- set `cwd` to repo root and `add_dirs` to explicit allowed roots
- add `PreToolUse` hook to deny `Write|Edit` outside:
  - `memory_root`
  - run `workspace_root` subfolder

Session persistence location strategy:
- current code disables session persistence (`--no-session-persistence`)
- for this project SDK flow only, to persist locally in workspace:
  - remove that flag for this SDK invocation
  - set `CLAUDE_CONFIG_DIR` via SDK `env` on this process only
- do not change global/default Claude Code log locations outside this project SDK flow
- keep this toggleable (`persist_sessions_in_workspace=true|false`)

## Observability
Write per-run artifacts:
- `extract.json`
- `summary.json`
- `memory_actions.json`
- `agent.log`
- `subagents.log`
- `session.log` (optional)

Metrics per run:
- candidate count
- summary count
- add/update/no-op count
- denied write attempts by hooks
- explorer fan-out and elapsed time
- total run duration

## Test Strategy (mapped to acceptance scenarios)
Acceptance Scenario A: Lead takes only `trace_path` and does not pull full trace into prompt.
- Verification: prompt template contains path-based pipeline commands; no trace payload injection.

Acceptance Scenario B: Todos are explicitly tracked.
- Verification: `TodoWrite` lifecycle shows pending/in_progress/completed states.

Acceptance Scenario C: Pipelines produce file artifacts.
- Verification: `extract.json` and `summary.json` exist and parse.

Acceptance Scenario D: Summary always goes to `summaries`.
- Verification: one new file under `.acreta/memory/summaries/` per run.

Acceptance Scenario E: Update does not duplicate.
- Verification: update edits existing memory file; memory count for that intent unchanged.

Acceptance Scenario F: Write boundary enforced.
- Verification: out-of-root `Write|Edit` attempts are denied by hook.

Acceptance Scenario G: Central registry drives type usage.
- Verification: `extract_pipeline`, `summarization_pipeline`, and `models` read types/definitions from one module.

Acceptance Scenario H: Workspace run folder is complete.
- Verification: one flat run folder contains expected output files without date/time nesting.

## Rollout Plan
- Phase 1: implement behind flag `agent_memory_write_v2`.
- Phase 2: enable for manual sync path.
- Phase 3: enable default daemon hot/cold/sync paths.
- Phase 4: remove deprecated memory-type branches after burn-in.

## Risks + Mitigations
- **Risk 1**: Built-in Explore output not structured enough.
- **Mitigation**: strict response format in Task prompt; fallback parser; introduce one custom explorer only if needed.

- **Risk 2**: Session persistence path behavior varies by runtime.
- **Mitigation**: integration test with `CLAUDE_CONFIG_DIR` in SDK `env`; keep fallback to disabled persistence.

- **Risk 3**: Taxonomy reduction loses nuance.
- **Mitigation**: keep `memory_subtype` and tags so meaning survives without extra folders.

- **Risk 4**: Pipeline artifact writing adds file noise.
- **Mitigation**: rotate/prune by date and keep only latest N runs per mode.

- **Risk 5**: Lead still writes outside boundary due prompt drift.
- **Mitigation**: enforce hook deny as hard gate, not prompt-only guidance.

## Assumptions
- Assumption: this artifact update is plan-only, no code implementation now.
- Assumption: user preference is minimal taxonomy and minimal branching logic.
- Assumption: no package rename (`acreta` -> `src`) in this feature; that is a separate packaging refactor.

## Todo List (Phased)
Phase 1: Core Contract + Inputs
- [ ] Define final lead contract with required `trace_path` and optional `memory_root`, `workspace_root`, `run_mode`.
- [ ] Remove any path that loads full trace content into lead-agent prompt context.
- [ ] Keep one minimal orchestration entrypoint in runtime (no duplicate wrappers).
- [ ] Ensure no fallback/legacy code paths remain in the new flow.

Phase 2: Central Memory Type Registry
- [ ] Add one canonical memory type module as single source for types and definitions.
- [ ] Reduce taxonomy to `decision`, `learning`, `summary`.
- [ ] Move `context` and `convention` semantics into `learning` tags/subtypes.
- [ ] Update pipelines and models to import from central registry only (remove duplicated literals).
- [ ] Delete dead/legacy type-handling branches.

Phase 3: Workspace Run Folder + Artifacts
- [ ] Implement one flat per-run folder: `.acreta/workspace/<run_mode>-<YYYYMMDD-HHMMSS>-<shortid>/`.
- [ ] Write flat run files: `extract.json`, `summary.json`, `memory_actions.json`, `agent.log`, `subagents.log`, optional `session.log`.
- [ ] Ensure intermediate state is file-based in run folder, not prompt-memory based.
- [ ] Keep implementation minimal (no extra folder trees, no optional complexity by default).

Phase 4: Lead Orchestration (Minimal Claude SDK)
- [ ] Add/confirm `TodoWrite` usage with fixed checklist lifecycle.
- [ ] Run extraction and summarization pipelines by `trace_path` CLI calls and save outputs to files.
- [ ] Use built-in Explore subagents first for read-only matching.
- [ ] Keep write authority in lead only (subagents read-only).
- [ ] Implement deterministic `add|update|no-op` decision logic.
- [ ] Enforce summary always writes to `.acreta/memory/summaries/`.

Phase 5: Security + Session Scope
- [ ] Remove `bypassPermissions` for this flow.
- [ ] Add `PreToolUse` hook deny rules for writes outside `memory_root` and current run folder.
- [ ] Keep SDK toolsets minimal for lead and stricter for subagents.
- [ ] Keep session persistence behavior scoped to this project SDK flow only.
- [ ] If enabled, set `CLAUDE_CONFIG_DIR` only in this SDK process env; do not alter global Claude defaults.

Phase 6: Simplification + Cleanup
- [ ] Remove dead code paths created by taxonomy reduction and flow simplification.
- [ ] Remove legacy migration/version branches related to this flow.
- [ ] Remove package fallbacks/try-except fallbacks where package absence should raise.
- [ ] Consolidate duplicated helpers/functions; keep minimal number of functions and lines.
- [ ] Run static search for stale references and delete unreachable code.

Phase 7: Documentation Updates
- [ ] Update architecture docs in `/Users/kargarisaac/codes/personal/acreta/docs/`.
- [ ] Update root `/Users/kargarisaac/codes/personal/acreta/README.md`.
- [ ] Update root `/Users/kargarisaac/codes/personal/acreta/AGENTS.md`.
- [ ] Update all folder-level README files touched by boundary/flow changes.
- [ ] Document new memory taxonomy, workspace run folder format, and lead/subagent responsibilities.

Phase 8: Testing (Required)
- [ ] Unit tests: add/update tests for central types, path-only orchestration, summary routing, decision logic.
- [ ] Unit tests: add/update tests for hook-based path enforcement and no-trace-in-context behavior.
- [ ] Integration tests: run real pipeline path using trace files and verify artifact outputs + memory writes.
- [ ] Integration tests: verify project-scoped session persistence toggle behavior.
- [ ] E2E tests: run full hot/cold/sync flow and verify add/update/no-op + summaries + run folder outputs.
- [ ] Execute test suites:
  - `scripts/run_tests.sh unit`
  - `scripts/run_tests.sh integration`
  - `scripts/run_tests.sh e2e`
  - optional full sweep: `scripts/run_tests.sh all`
- [ ] Verify acceptance scenarios A-H all pass and map each to concrete test evidence.

Phase 9: Final Quality Gate
- [ ] Confirm no dead code, no legacy code, no fallback code remains for this feature path.
- [ ] Confirm code is minimal and readable with updated docstrings where needed.
- [ ] Confirm docs and tests are in sync with final behavior.
- [ ] Prepare concise change summary with risks, mitigations, and follow-up items.
