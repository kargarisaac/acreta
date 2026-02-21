# 011 — Agentic Maintenance Rewrite

## Goal

Add an agent-driven maintenance flow (merge, dedupe, forget, consolidate) to AcretaAgent, reorganize all prompts into a dedicated folder, and simplify the agent's public API.

## Approach

The maintenance flow reuses the existing AcretaAgent and its internal SDK plumbing (`_run_sdk_sync`). A new `maintain()` method builds a comprehensive prompt that instructs the agent to scan existing memories, use explore subagents for analysis, merge duplicates, archive stale/low-value memories, and report results. All maintenance logic lives in the prompt — no programmatic merge/decay code. The daemon and CLI are simplified by removing the step-dispatch machinery. All prompts (system, sync, maintain, chat) move from inline strings to a `prompts/` package with triple-quoted strings.

## Files

### New files

- `[NEW] acreta/runtime/prompts/__init__.py` — package init, re-exports the 4 builder functions
- `[NEW] acreta/runtime/prompts/system.py` — `build_system_prompt(skills)`, moved from `_build_system_prompt` in agent.py
- `[NEW] acreta/runtime/prompts/sync.py` — `build_sync_prompt(...)`, moved from `_build_memory_write_prompt` in agent.py
- `[NEW] acreta/runtime/prompts/maintain.py` — `build_maintain_prompt(memory_root, run_folder, artifact_paths)`, new
- `[NEW] acreta/runtime/prompts/chat.py` — `build_chat_prompt(question, hits, context_docs)`, moved from `_build_chat_prompt` in cli.py

### Modified files

- `[MODIFY] acreta/runtime/agent.py` — Remove inline prompts. Rename methods: `run_sync` → `chat`, `run` → `sync`, add `maintain(memory_root, workspace_root)`. Import prompt builders from `prompts/`. Both `sync` and `maintain` share the same internal plumbing, hooks, and artifact pattern.
- `[MODIFY] acreta/app/daemon.py` — Simplify `run_maintain_once`: remove step dispatch (`maintain_default_steps`, `resolve_maintain_steps`, `_run_maintain_step`), replace with single `agent.maintain()` call. Update `run_sync_once` to call `agent.sync()`. Update `run_daemon_once` accordingly.
- `[MODIFY] acreta/app/cli.py` — Update `_cmd_chat` to call `agent.chat()`. Remove `_build_chat_prompt` (moved to prompts/). Update `_cmd_maintain` to remove `--steps` flag. Update imports.
- `[MODIFY] tests/test_maintain_command.py` — Rewrite for new maintain behavior (no steps).
- `[MODIFY] tests/test_daemon_sync_maintain.py` — Update `agent.run` → `agent.sync`, rewrite maintain test.
- `[MODIFY] tests/test_runtime_agent_contract.py` — Update `agent.run` → `agent.sync`.
- `[MODIFY] tests/test_agent_memory_write_flow.py` — Update `agent.run` → `agent.sync`.
- `[MODIFY] tests/test_agent_memory_write_integration.py` — Update `agent.run` → `agent.sync`.
- `[MODIFY] tests/test_agent_memory_write_modes_e2e.py` — Update `agent.run` → `agent.sync`.
- `[MODIFY] tests/test_cli.py` — Update `run_sync` → `chat`.
- `[MODIFY] tests/test_context_layers_e2e.py` — Update `run_sync` → `chat`.

### Deleted files

- `[DELETE] acreta/memory/maintenance.py` — dead stub (15 lines, zero functions, nothing imports it)

## Key Decisions

1. **One agent run for all maintenance** (not separate steps). The LLM handles reasoning about what to merge/forget — splitting into programmatic steps would mean reimplementing logic that belongs in the prompt.
2. **Soft-delete via Bash `mv`** to `memory_root/archived/{decisions,learnings}/`. AGENTS.md requires soft-delete-first. Bash mv bypasses Write/Edit hooks (which is fine — we're moving, not creating memory files). Archive stays inside memory_root.
3. **Same PreToolUse hooks** for maintain as sync. Boundary enforcement and frontmatter normalization apply equally. When the agent merges two memories into one updated file, the Write hook normalizes the result.
4. **Workspace folder for intermediate results**. The maintain prompt tells the agent it can save intermediate analysis files in the run folder to manage context. Signature: `maintain(memory_root, workspace_root)`.
5. **Rename public methods**: `run_sync` → `chat`, `run` → `sync`, new `maintain`. All callers updated.
6. **Remove step dispatch** from daemon.py. Functions removed: `maintain_default_steps`, `resolve_maintain_steps`, `_run_maintain_step`. `--steps` CLI flag removed. Single agent run replaces granular steps.
7. **`build_extract_report` stays** in `extract_pipeline.py`. Dashboard still uses it independently. Just no longer called from the maintain flow.
8. **Triple-quoted strings** for all prompts.

## LLM/Framework vs. Custom Code

| What | Handled By | Notes |
|------|-----------|-------|
| Memory analysis (scan, compare) | LLM + explore subagents | Agent reads files, delegates explore subagents for similarity matching |
| Merge decisions | LLM prompt | Prompt defines merge criteria (similar topic, overlapping content) |
| Forget decisions | LLM prompt | Prompt defines forget criteria (low confidence, outdated, superseded) |
| Consolidation | LLM prompt | Prompt instructs combining related small memories |
| File writes/moves | Agent tools (Write, Edit, Bash) | Agent executes, hooks guard boundaries |
| Boundary enforcement | PreToolUse hooks (code) | Same hooks as sync — validated file paths, frontmatter normalization |
| Artifact validation | Custom code (agent.py) | Post-run checks that report exists and paths are valid |
| Report generation | LLM prompt | Agent writes structured JSON report of actions taken |

## Dependencies

No new dependencies. All existing: `claude_agent_sdk`, `python-frontmatter`, DSPy.

## Out of Scope

- Confidence decay over time (could be added to the prompt later)
- Cross-project memory deduplication (maintain only operates on one memory_root)
- Scheduling infrastructure (cron job setup is user's responsibility; daemon loop already exists)
- Vector/embedding-based similarity (maintain uses agent's Read/Grep/Glob — file-first retrieval)
- Dashboard integration for maintain results (dashboard can read the report JSON from workspace)

## Implementation Steps

- [ ] **Step 1: Create `acreta/runtime/prompts/` package** — `__init__.py` + `system.py` + `sync.py` + `chat.py` with moved prompts (triple-quoted strings). Verify imports work.
- [ ] **Step 2: Create `acreta/runtime/prompts/maintain.py`** — the maintenance prompt builder. Core new content.
- [ ] **Step 3: Refactor `agent.py`** — Remove inline prompts (import from prompts/). Rename `run_sync` → `chat`, `run` → `sync`. Add `maintain()` method.
- [ ] **Step 4: Simplify `daemon.py`** — Remove step dispatch functions. Rewrite `run_maintain_once` to call `agent.maintain()`. Update `run_sync_once` and `run_daemon_once` for renamed methods.
- [ ] **Step 5: Update `cli.py`** — Remove `_build_chat_prompt` (import from prompts/). Remove `--steps` flag. Update method calls.
- [ ] **Step 6: Delete `acreta/memory/maintenance.py`** — dead stub.
- [ ] **Step 7: Update all tests** — method renames, maintain test rewrite.
- [ ] **Step 8: Run tests** — `scripts/run_tests.sh unit` to verify nothing broke.
