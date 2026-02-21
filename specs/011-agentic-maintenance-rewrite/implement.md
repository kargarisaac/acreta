# Implementation Prompt: Agentic Maintenance Rewrite

Read `specs/011-agentic-maintenance-rewrite/plan.md` first for full context. Then implement the steps below IN ORDER. After each step, run `scripts/run_tests.sh unit` and fix any breakage before moving on.

Read AGENTS.md for project rules. Key rules:
- All files need a docstring at top explaining what the file does.
- All functions need docstrings.
- Use `"""` triple-quoted strings, never `"" + ""` concatenation for multi-line strings.
- Each file should have `if __name__ == "__main__":` self-test when possible.
- No dead code, no commented-out code, no fallbacks, no try/except for packages.
- Minimum code, maximum reliance on LLM prompts.

---

## Step 1: Create `acreta/runtime/prompts/` package

Create the folder `acreta/runtime/prompts/` with these files:

### `__init__.py`

```python
"""Prompt builders for AcretaAgent flows (system, sync, maintain, chat)."""
```

Just re-export the builder functions from the submodules:
- `build_system_prompt` from `.system`
- `build_sync_prompt` from `.sync`
- `build_maintain_prompt` from `.maintain`
- `build_chat_prompt` from `.chat`

### `system.py`

Move `_build_system_prompt` from `acreta/runtime/agent.py:43-58` here. Rename to `build_system_prompt`. Convert the concatenated string to a single triple-quoted f-string. Same logic, same content. Signature: `build_system_prompt(skills: list[str] | None = None) -> str`.

### `sync.py`

Move `_build_memory_write_prompt` from `acreta/runtime/agent.py:403-468` here. Rename to `build_sync_prompt`. Convert the concatenated string to a single triple-quoted f-string. Same signature, same content. It imports `memory_write_schema_prompt` from `acreta.memory.memory_record` (same as current). Signature stays the same (takes trace_file, memory_root, run_folder, artifact_paths, metadata).

### `chat.py`

Move `_build_chat_prompt` from `acreta/app/cli.py:353-392` here. Rename to `build_chat_prompt`. Convert the concatenated string to a triple-quoted f-string. Also move `_looks_like_auth_error` from `cli.py:395-404` here since it's chat-related. Same logic, same content. Signature: `build_chat_prompt(question: str, hits: list[dict[str, Any]], context_docs: list[dict[str, Any]]) -> str`.

### `maintain.py`

New file. Create `build_maintain_prompt`. This is the core new content. Signature:

```python
def build_maintain_prompt(
    *,
    memory_root: Path,
    run_folder: Path,
    artifact_paths: dict[str, Path],
) -> str:
```

The prompt must instruct the agent to do this in one run:

```
You are running Acreta memory maintenance — an offline refinement pass over existing memories.
This mimics how human memory works: consolidate, strengthen important memories, forget noise.

Inputs:
- memory_root: {memory_root}
- run_folder: {run_folder} (use this for intermediate files to manage your context)
- artifact_paths: {artifact_paths as json}

Checklist (use TodoWrite, move pending -> in_progress -> completed):
- scan_memories
- analyze_duplicates
- merge_similar
- archive_low_value
- consolidate_related
- write_report

Instructions:

1. SCAN: Use Task with Explore subagents to read all memory files in memory_root/decisions/ and memory_root/learnings/. Parse their frontmatter (id, title, confidence, tags, created, updated) and body content. Save a summary to run_folder for reference if the list is large.

2. ANALYZE DUPLICATES: Identify memories that cover the same topic or have substantially overlapping content. Group them by similarity.

3. MERGE: For memories with overlapping content about the same topic:
   - Keep the most comprehensive version as the primary.
   - Merge unique details from the secondary into the primary using Edit.
   - Update the primary's "updated" timestamp to now.
   - Archive the secondary by moving it: use Bash to run `mkdir -p {memory_root}/archived/{folder}/ && mv {old_path} {memory_root}/archived/{folder}/` where folder is "decisions" or "learnings".

4. ARCHIVE LOW-VALUE: Archive memories that are:
   - Very low confidence (< 0.3)
   - Trivial or obvious (e.g., "installed package X", "ran command Y" with no insight)
   - Superseded by a more complete memory covering the same ground
   Use the same Bash mv pattern to move them to archived/.

5. CONSOLIDATE: When you find 3+ small related memories about the same broader topic, consider combining them into one comprehensive memory file. Write the new consolidated memory via Write tool. Archive the originals.

6. REPORT: Write a JSON report to {artifact_paths['maintain_actions']} with keys:
   - run_id: the run folder name
   - actions: list of {{action, source_path, target_path, reason}} dicts
   - counts: {{merged, archived, consolidated, unchanged}}
   - All file paths must be absolute.

Rules:
- You are the only writer. Explore subagents are read-only.
- Memory files use YAML frontmatter between --- delimiters.
- {include memory_write_schema_prompt() output here}
- When writing new/updated memory files, follow the same frontmatter schema.
- Do NOT touch memory_root/summaries/ — summaries are managed by the pipeline only.
- Do NOT delete files. Always archive (soft-delete via mv to archived/).
- Be conservative: when unsure whether to merge or archive, leave it unchanged.
- Quality over quantity: fewer good memories are better than many noisy ones.

Return one short plain-text completion line.
```

Use `memory_write_schema_prompt()` from `acreta.memory.memory_record` to inject schema rules (same as sync prompt does).

The artifact_paths for maintain are simpler than sync. Define a helper in agent.py (or in this file) that builds them:

```python
{
    "maintain_actions": run_folder / "maintain_actions.json",
    "agent_log": run_folder / "agent.log",
    "subagents_log": run_folder / "subagents.log",
}
```

---

## Step 2: Refactor `acreta/runtime/agent.py`

### Remove inline prompts
- Delete `_build_system_prompt` function (moved to prompts/system.py).
- Delete `_build_memory_write_prompt` method (moved to prompts/sync.py).
- Import builders: `from acreta.runtime.prompts import build_system_prompt, build_sync_prompt, build_maintain_prompt`.
- In `__init__`, change `self.system_prompt = _build_system_prompt(self.skills)` to `self.system_prompt = build_system_prompt(self.skills)`.

### Rename methods
- `run_sync` → `chat`. Update docstring. Same logic.
- `run` → `sync`. Update docstring. Same logic.

### Change `_default_run_folder_name` to accept a prefix
Currently hardcoded to `sync-`. Make it `_default_run_folder_name(prefix: str = "sync")` so maintain can use `maintain-` prefix. One-line change.

### Add `maintain()` method

```python
def maintain(
    self,
    memory_root: str | Path | None = None,
    workspace_root: str | Path | None = None,
) -> dict[str, Any]:
```

This method follows the same pattern as `sync()` but simpler:
1. Resolve memory_root (default: `repo_root/.acreta/memory`).
2. Resolve workspace_root (default: `repo_root/.acreta/workspace`).
3. Create run_folder with `maintain-` prefix via `_default_run_folder_name("maintain")`.
4. Build artifact_paths (maintain-specific: `maintain_actions`, `agent_log`, `subagents_log`). Define a small `_build_maintain_artifact_paths(run_folder)` helper next to the existing `_build_artifact_paths`.
5. Build prompt via `build_maintain_prompt(memory_root=..., run_folder=..., artifact_paths=...)`.
6. Build PreToolUse hooks via `self._build_pretool_hooks((resolved_memory_root, run_folder), memory_root=resolved_memory_root)`. Note: no `metadata` dict needed since maintain doesn't have a trace_path or run_id for frontmatter source field — pass `metadata={"run_id": run_folder.name}`.
7. Set up tools = `MEMORY_WRITE_TOOLS` (same as sync).
8. Define `explore-reader` AgentDefinition (same as sync).
9. Call `self._run_sdk_sync(...)` with the prompt, tools, hooks, agents.
10. Write agent response to `agent_log`.
11. Validate `maintain_actions.json` exists.
12. Read and parse `maintain_actions.json`, extract counts.
13. Return result dict with: `memory_root`, `workspace_root`, `run_folder`, `artifacts`, `counts`.

The validation is lighter than sync — no summary_path check, no extract.json check. Just verify `maintain_actions.json` exists and is valid JSON with a `counts` dict.

### Update self-test

Update the `if __name__ == "__main__":` block to test the new names (`chat` not `run_sync`, `sync` not `run`). Also add a basic test that `build_maintain_prompt` produces a valid prompt string.

---

## Step 3: Simplify `acreta/app/daemon.py`

### Remove these functions entirely:
- `maintain_default_steps()` (line 251)
- `resolve_maintain_steps()` (line 256)
- `_run_maintain_step()` (line 273)

### Rewrite `run_maintain_once()`

Remove the parameters: `steps_raw`, `parse_csv`. Remove `parse_agent_filter` (not needed without steps).

New simplified signature:

```python
def run_maintain_once(
    *,
    force: bool,
    dry_run: bool,
) -> tuple[int, dict]:
```

New logic:
1. Acquire writer lock (unless dry_run).
2. If dry_run, return early with `{"dry_run": True}`.
3. Create `AcretaAgent(skills=["acreta"], default_cwd=str(Path.cwd()))`.
4. Call `agent.maintain()`.
5. Record service_run with result.
6. Release lock.
7. Return `(EXIT_OK, result)` or `(EXIT_FATAL, {"error": str(exc)})` on failure.

The window/since/until parameters are removed — the maintenance agent scans all existing memories, not a time window.

### Update `run_sync_once()`

Change `lead_agent.run(Path(session_path))` (line 431) to `lead_agent.sync(Path(session_path))`.

### Update `run_daemon_once()`

Update the `run_maintain_once(...)` call to use the new simplified signature (remove steps_raw, parse_csv, parse_agent_filter, window args).

### Update self-test

The self-test at the bottom tests `resolve_maintain_steps`. Remove that test since the function is deleted. Replace with a basic smoke test (e.g., assert `run_maintain_once` is callable or similar minimal check).

---

## Step 4: Update `acreta/app/cli.py`

### Remove `_build_chat_prompt` and `_looks_like_auth_error`
These moved to `acreta/runtime/prompts/chat.py`. Import them:
```python
from acreta.runtime.prompts.chat import build_chat_prompt, looks_like_auth_error
```
(Rename `_looks_like_auth_error` to `looks_like_auth_error` since it's now a public module function.)

### Update `_cmd_chat`
Change `agent.run_sync(prompt, cwd=...)` to `agent.chat(prompt, cwd=...)`.
Change `_build_chat_prompt(...)` to `build_chat_prompt(...)`.
Change `_looks_like_auth_error(...)` to `looks_like_auth_error(...)`.

### Update `_cmd_maintain`
Remove `steps_raw=args.steps` from the `run_maintain_once()` call. Remove all the parameters that were removed from `run_maintain_once` (window, since, until, agent, parse_*). Just pass `force=args.force, dry_run=args.dry_run`.

### Update maintain parser (line 539-547)
Remove: `--steps`, `--window`, `--since`, `--until`, `--agent`.
Keep: `--force`, `--dry-run`, `--json`.
The maintain parser becomes very simple.

### Update imports
- Remove `resolve_window_bounds` from daemon import if only used by sync (check — it IS used by `_cmd_sync` too, so keep it).
- Remove `parse_csv` from arg_utils import if no longer needed in cli.py (check — it may be used elsewhere in cli.py).

---

## Step 5: Delete `acreta/memory/maintenance.py`

Delete the file. It's a 15-line dead stub. Nothing imports it.

---

## Step 6: Update tests

### `tests/test_maintain_command.py`
Rewrite both tests. The old tests check `maintain_default_steps()` and step ordering — those concepts no longer exist. New tests should:
- `test_maintain_dry_run()`: Call `run_cli_json(["maintain", "--dry-run", "--json"])`, assert code == 0 and `dry_run` is True in payload.
- Remove the step ordering test entirely.

### `tests/test_daemon_sync_maintain.py`
- `test_sync_does_not_run_vector_rebuild`: Change the monkeypatch from `"acreta.runtime.agent.AcretaAgent.run"` to `"acreta.runtime.agent.AcretaAgent.sync"`.
- `test_maintain_runs_requested_steps`: This test patches `_run_maintain_step` which no longer exists. Rewrite to patch `AcretaAgent.maintain` instead and verify `run_maintain_once` calls it. Something like:
  ```python
  def test_maintain_calls_agent(monkeypatch, tmp_path):
      _setup(tmp_path, monkeypatch)
      called = []
      monkeypatch.setattr(
          "acreta.runtime.agent.AcretaAgent.maintain",
          lambda self, **kw: (called.append(True), {"counts": {"merged": 0, "archived": 0, "consolidated": 0, "unchanged": 0}})[1],
      )
      code, payload = daemon.run_maintain_once(force=False, dry_run=False)
      assert code == daemon.EXIT_OK
      assert len(called) == 1
  ```

### `tests/test_runtime_agent_contract.py`
- Change `agent.run(trace_path)` to `agent.sync(trace_path)` (line 124).
- Change `agent.run(tmp_path / "missing.jsonl")` to `agent.sync(tmp_path / "missing.jsonl")` (line 135).

### `tests/test_agent_memory_write_flow.py`
- Change all `agent.run(trace_path)` to `agent.sync(trace_path)` (lines 133, 167, 168).

### `tests/test_agent_memory_write_integration.py`
- Change `agent.run(trace_path)` to `agent.sync(trace_path)` (line 101).

### `tests/test_agent_memory_write_modes_e2e.py`
- Change `agent.run(trace_path)` to `agent.sync(trace_path)` (line 122).

### `tests/test_cli.py`
- Change mock `run_sync` method to `chat` (line 97).

### `tests/test_context_layers_e2e.py`
- Change mock `run_sync` method to `chat` (line 27).

---

## Step 7: Run tests

```bash
scripts/run_tests.sh unit
```

Fix any failures. Then run:

```bash
python -m acreta.runtime.prompts.system
python -m acreta.runtime.prompts.sync
python -m acreta.runtime.prompts.maintain
python -m acreta.runtime.prompts.chat
python -m acreta.runtime.agent
```

to verify self-tests pass.

---

## Critical Rules

- **No dead code.** After moving a function, delete it from the original location. After removing step dispatch, delete those functions.
- **No overengineering.** The maintain() method should follow the same pattern as sync() but simpler. Don't add abstractions.
- **Triple-quoted strings.** All prompts use `"""..."""` f-strings, not `"line1\n" + "line2\n"` concatenation.
- **Docstrings on everything.** Every file, every function.
- **Self-tests.** Each new prompt file gets a minimal `if __name__ == "__main__":` that asserts the builder returns a non-empty string containing expected keywords.
- **Match existing code style.** Look at how agent.py is written — imports, typing, naming — and match it exactly.
- **Do not change** `_run_sdk_once`, `_run_sdk_sync`, `_run_coroutine_sync`, `_build_pretool_hooks`, or any of the hook/boundary logic. These are shared infrastructure.
- **Do not change** `build_extract_report` in `extract_pipeline.py`. Dashboard uses it independently.
- **Do not add new dependencies.**
