# Code Review Prompt: Agentic Maintenance Rewrite (Spec 011)

Read `specs/011-agentic-maintenance-rewrite/plan.md` for what was implemented. Then review every changed and new file with a critical eye. You are a senior reviewer who values minimalism, simplicity, and security. Your job is to find problems, not to praise.

---

## Files to Review

Read each file fully before reviewing. Do not skim.

### New files
- `acreta/runtime/prompts/__init__.py`
- `acreta/runtime/prompts/system.py`
- `acreta/runtime/prompts/sync.py`
- `acreta/runtime/prompts/maintain.py`
- `acreta/runtime/prompts/chat.py`

### Modified files
- `acreta/runtime/agent.py`
- `acreta/app/daemon.py`
- `acreta/app/cli.py`
- `acreta/memory/memory_repo.py`
- `acreta/memory/summarization_pipeline.py`

### Modified tests
- `tests/test_maintain_command.py`
- `tests/test_daemon_sync_maintain.py`
- `tests/test_runtime_agent_contract.py`
- `tests/test_agent_memory_write_flow.py`
- `tests/test_agent_memory_write_integration.py`
- `tests/test_agent_memory_write_modes_e2e.py`
- `tests/test_cli.py`
- `tests/test_context_layers_e2e.py`

### Deleted files (confirm deleted)
- `acreta/memory/maintenance.py`

---

## Review Criteria

For each file, evaluate against ALL of the following. Be specific — cite line numbers and code snippets when flagging issues.

### 1. Simplicity and Minimalism

- Can any function be removed entirely? Is it called? Is it needed?
- Can any function be shortened? Are there unnecessary intermediate variables, redundant checks, or verbose patterns?
- Are there abstractions that serve only one caller? If so, inline them.
- Are there parameters that are always passed the same value? If so, hardcode them.
- Are there if/else branches that can never be reached?
- Is there any code that exists "just in case" or "for future flexibility"?
- Could any logic be replaced with a simpler standard library call?
- Is there any copy-paste duplication between `sync()` and `maintain()` in agent.py that should be extracted into a shared helper? Conversely, is there a shared helper that makes things MORE complex than just having the code inline?

### 2. Overengineering

- Are there wrapper functions that just call another function with the same args?
- Are there utility functions that are used exactly once and add no clarity?
- Is the `build_maintain_artifact_paths` helper justified, or should it be inline in `maintain()`?
- Is the prompt builder separation (4 files) justified, or would fewer files be simpler? Would 1 file with 4 functions be cleaner?
- Are there type hints that add no value (e.g., obvious from context)?
- Are there docstrings that just restate the function name without adding information?
- Is the `__init__.py` re-export necessary, or do callers import directly from submodules anyway?

### 3. Security

- **Boundary enforcement**: Does `maintain()` properly restrict writes to `memory_root` and `run_folder` only? Check the `_build_pretool_hooks` call — are the allowed_roots correct?
- **Path traversal**: Can the maintenance prompt trick the agent into writing outside allowed roots? Check if the hooks cover all Write/Edit paths.
- **Archive path**: When the agent uses `Bash mv` to move files to `archived/`, the PreToolUse hooks do NOT guard Bash commands. Is this a security risk? Could the agent be prompted to `mv` files to arbitrary locations? What mitigations exist (cwd restriction, add_dirs)?
- **Frontmatter injection**: Could malformed frontmatter in existing memory files cause issues when the maintenance agent reads and re-writes them?
- **File extension checks**: Does the maintain flow enforce the same `.md`-only restriction for memory writes as the sync flow?
- **Workspace artifacts**: Can the agent write arbitrary file types to the run_folder? Is this acceptable?
- **Sensitive data**: Could the maintenance agent accidentally expose memory contents in its report JSON?

### 4. Prompt Quality

- **Maintain prompt**: Is it clear and unambiguous? Could the agent misinterpret any instruction?
- **Maintain prompt**: Does it cover all edge cases? What happens when:
  - memory_root has 0 files?
  - memory_root has 1 file (nothing to merge)?
  - All memories are high quality (nothing to archive)?
  - Two memories have identical content?
  - A memory file has malformed frontmatter?
- **Maintain prompt**: Is it too long? Could it be shorter without losing clarity?
- **Maintain prompt**: Does it give the agent enough freedom to make good decisions, or is it too prescriptive?
- **Maintain prompt**: Does it contradict any rule in the system prompt?
- **Sync prompt**: Was anything lost or changed when moving from inline to the prompts file? Compare the original logic in the plan against what's in `sync.py` now.
- **System prompt**: Is it still generic enough for all flows (chat, sync, maintain)?
- **Chat prompt**: Was anything lost when moving from cli.py?

### 5. Correctness

- Does `maintain()` return the right structure? Check callers in daemon.py — do they expect the right keys?
- Does `run_maintain_once()` in daemon.py handle errors correctly? What if `agent.maintain()` throws?
- Does the daemon still record `service_run` audit entries for maintain?
- Does the CLI `_cmd_maintain` format the output correctly for both `--json` and plain text?
- Are all imports correct? No circular imports? No missing imports?
- Does `_default_run_folder_name("maintain")` produce `maintain-YYYYMMDD-HHMMSS-hex` format? Check the implementation.
- Do the PreToolUse hooks work correctly for the maintain flow? The hooks use `metadata` for the `source` field in frontmatter — does maintain pass a valid metadata dict?
- Summary path structure: `write_summary_markdown` now writes to `summaries/YYYYMMDD/HHMMSS/{slug}.md`. Do any callers or validators assume the old flat structure?

### 6. Test Quality

- Do the tests actually test meaningful behavior, or are they trivial pass-through checks?
- Is the maintain flow adequately tested? What's NOT tested that should be?
- Are there tests that mock so aggressively they don't test anything real?
- Are there missing edge case tests (e.g., maintain with empty memory_root, maintain with lock contention)?
- Do the test mocks for summary paths match the new `YYYYMMDD/HHMMSS/{slug}.md` structure?

### 7. Code Style and Conventions

- Do all files have a top-level docstring?
- Do all functions have docstrings?
- Are triple-quoted strings used consistently (no `"line\n" + "line\n"` concatenation for prompts)?
- Does the code match the existing codebase style (imports, naming, formatting)?
- Are there any `# TODO`, `# FIXME`, or commented-out code blocks?
- Are there any print statements that should be logging?
- Self-tests: does every new file have `if __name__ == "__main__":`?

### 8. Dead Code and Orphans

- Search for any remaining references to deleted functions: `maintain_default_steps`, `resolve_maintain_steps`, `_run_maintain_step`, `_build_system_prompt`, `_build_memory_write_prompt`, `_build_chat_prompt`, `_looks_like_auth_error`, `run_sync` (as method), `.run(` on agent.
- Search for any imports of `acreta.memory.maintenance`.
- Search for any reference to `--steps` in CLI code or tests.
- Are there any unused imports in any changed file?
- Are there any functions defined but never called?

---

## Output Format

For each file, produce:

```
### filename.py

**Verdict**: CLEAN | MINOR ISSUES | NEEDS CHANGES

**Issues:**
1. [severity: critical/major/minor] Line XX: description of issue. Suggested fix.
2. ...

**Simplification opportunities:**
1. Line XX: description. How to simplify.
2. ...
```

Then produce a summary table:

```
| File | Verdict | Critical | Major | Minor | Simplifications |
|------|---------|----------|-------|-------|-----------------|
| ...  | ...     | ...      | ...   | ...   | ...             |
```

End with:
- **Top 3 most important changes** to make (if any)
- **Security concerns** that need addressing (if any)
- **Overall assessment**: Is this implementation minimal and clean, or does it need another pass?
