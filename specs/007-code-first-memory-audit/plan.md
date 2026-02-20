# Spec 007 Plan: Prompt-First Simplification (No Overengineering)

## Summary

This plan is intentionally minimal.

Target workflow:
1. DSPy (`dspy.RLM`) gets transcript and extracts memory candidates.
2. Lead agent does retrieval by delegating to parallel read-only subagents using Claude SDK `Task`.
3. Lead agent decides `add|update|no-op`.
4. Lead agent writes memory.
5. Cold jobs stay in `maintain`.
6. Dashboard stays as UI only (read-only).

Design rule:
- Do in prompt whenever possible.
- Do not add new Python frameworks/modules.
- Remove extra runtime layers.

Reference:
- Claude subagents and parallel `Task`: https://docs.anthropic.com/en/docs/claude-code/sub-agents

Hard constraints from product direction:
- Keep Cursor integration.
- Keep dashboard for UI.
- Keep only one user-facing Acreta skill for agent usage guidance.

## Final Design

### Lead agent

Lead agent is the only decider and writer.

- Input: extracted candidates + retrieval results.
- Output: final action per candidate (`add|update|no-op`).
- Writes: canonical memory + sidecars only from lead path.

### Retrieval behavior

No hard-coded “one explorer per folder” logic in Python.

- Lead prompt says:
  - use parallel explorer subagents;
  - choose fan-out dynamically (by candidate count and search need);
  - search across primitive folders (`decisions`, `learnings`, `conventions`, `context`) project-first then global fallback;
  - return evidence with file paths/lines.
- This stays prompt-driven through Claude SDK `Task`.

### DSPy boundary

DSPy does extraction only.

- Input: transcript/archive.
- Output: candidate memories.
- No retrieval in DSPy.
- No write decision in DSPy.

### No wikilink

Remove wikilink usage entirely.

- No `[[...]]` in prompts.
- No wikilink parser dependency.
- `related` uses explicit ids/slugs only.

## What to Remove

This plan removes complexity, not adds it.

1. Remove custom subagent orchestration patterns that duplicate Claude SDK behavior.
2. Remove guardrails layer from the runtime path.
3. Remove lane-specific subagent wiring when prompt delegation already handles it.
4. Remove wikilink generation/parsing logic.
5. Remove hot-path heavy work (vector/index/graph rebuild calls in sync/extract hot flows).
6. Remove extra Acreta-specific skills that are not needed in the simplified architecture.

### File Deletion List (explicit)

Delete these files as part of simplification:

1. `/Users/kargarisaac/codes/personal/acreta/acreta/runtime/guardrails.py`
2. `/Users/kargarisaac/codes/personal/acreta/acreta/runtime/subagents.py` (if no required SDK callsite dependency remains)
3. `/Users/kargarisaac/codes/personal/acreta/acreta/extract/metrics.py`
4. `/Users/kargarisaac/codes/personal/acreta/acreta/extract/orchestrator.py` (replace with minimal DSPy pipeline integration path)
5. `/Users/kargarisaac/codes/personal/acreta/acreta/memory/graph.py`
6. `/Users/kargarisaac/codes/personal/acreta/acreta/memory/index.py`
7. `/Users/kargarisaac/codes/personal/acreta/acreta/memory/vector.py`
8. `/Users/kargarisaac/codes/personal/acreta/acreta/adapters/cline.py`
9. `/Users/kargarisaac/codes/personal/acreta/acreta/config/paths.py`
10. `/Users/kargarisaac/codes/personal/acreta/acreta/__main__.py`
11. `/Users/kargarisaac/codes/personal/acreta/acreta/README.md`
12. `/Users/kargarisaac/codes/personal/acreta/acreta/adapters/README.md`
13. `/Users/kargarisaac/codes/personal/acreta/acreta/app/README.md`
14. `/Users/kargarisaac/codes/personal/acreta/acreta/config/README.md`
15. `/Users/kargarisaac/codes/personal/acreta/acreta/extract/README.md`
16. `/Users/kargarisaac/codes/personal/acreta/acreta/memory/README.md`
17. `/Users/kargarisaac/codes/personal/acreta/acreta/runtime/README.md`
18. `/Users/kargarisaac/codes/personal/acreta/acreta/sessions/README.md`

Do not delete these (explicit keep constraints):

1. `/Users/kargarisaac/codes/personal/acreta/acreta/app/dashboard.py` (keep as read-only UI dashboard)
2. `/Users/kargarisaac/codes/personal/acreta/acreta/adapters/cursor.py` (keep Cursor integration)
3. `/Users/kargarisaac/codes/personal/acreta/acreta/sessions/queue.py` (queue behavior must remain intact; if merged, keep public compatibility path)

## File-Level Changes (Minimal, Direct)

### `/Users/kargarisaac/codes/personal/acreta/acreta/runtime/agent.py`

- Keep Claude SDK `Task` usage.
- Simplify system/task prompts to enforce:
  - parallel explorer delegation,
  - dynamic fan-out,
  - read-only exploration,
  - evidence-first output.
- Remove wiring for custom guardrail hooks.

### `/Users/kargarisaac/codes/personal/acreta/acreta/runtime/guardrails.py`

- Remove from active runtime path (and delete if fully unused after cleanup).

### `/Users/kargarisaac/codes/personal/acreta/acreta/runtime/subagents.py`

- Simplify to minimal definitions only if absolutely required by SDK call site.
- No folder-by-folder hard-coded orchestration logic.

### `/Users/kargarisaac/codes/personal/acreta/acreta/extract/orchestrator.py`

- Use DSPy extraction output as candidate source.
- Replace local non-agentic neighbor retrieval with lead prompt delegation to parallel explorers.
- Keep final action decision in lead code path.
- Remove wikilink insertion.
- Remove hot-path cold operations from extract flow.

### `/Users/kargarisaac/codes/personal/acreta/acreta/memory/search.py`

- Make retrieval prompt-driven through lead + explorer subagents.
- Keep optional FTS/vector/graph as enrichers only when enabled.
- No hidden backend use when disabled.

### `/Users/kargarisaac/codes/personal/acreta/acreta/memory/models.py`
### `/Users/kargarisaac/codes/personal/acreta/acreta/memory/graph.py`
### `/Users/kargarisaac/codes/personal/acreta/acreta/memory/maintenance.py`
### `/Users/kargarisaac/codes/personal/acreta/acreta/app/cli.py`

- Remove wikilink-specific code and prompt text.
- Keep explicit `related` references only.
- Ensure CLI text does not mention wikilinks.

### `/Users/kargarisaac/codes/personal/acreta/acreta/app/daemon.py`

- Keep `sync` hot path lightweight.
- Remove vector/index/graph rebuild calls from hot path.
- Keep these in `maintain` cold path only.

### `/Users/kargarisaac/codes/personal/acreta/acreta/app/dashboard.py`

- Keep as UI dashboard.
- Keep read-only behavior.
- Keep it out of hot-path and extraction decision logic.

### `/Users/kargarisaac/codes/personal/acreta/acreta/adapters/cursor.py`

- Keep Cursor integration.
- Keep registry wiring for Cursor in the connected-platform flow.

### `/Users/kargarisaac/codes/personal/acreta/.claude/skills/`

- Keep one user-facing skill:
  - `/Users/kargarisaac/codes/personal/acreta/.claude/skills/acreta/SKILL.md`
- Keep its reference:
  - `/Users/kargarisaac/codes/personal/acreta/.claude/skills/acreta/cli-reference.md`
- Remove/deprecate extra Acreta-specific skills after migration:
  - `/Users/kargarisaac/codes/personal/acreta/.claude/skills/acreta-evidence-policy/SKILL.md`
  - `/Users/kargarisaac/codes/personal/acreta/.claude/skills/acreta-memory-taxonomy/SKILL.md`
  - `/Users/kargarisaac/codes/personal/acreta/.claude/skills/acreta-retention-policy/SKILL.md`
  - `/Users/kargarisaac/codes/personal/acreta/.claude/skills/acreta-internal-runtime/` (entire folder)

## Implementation Steps

1. Strip guardrails from runtime call path (`agent.py`) and clean dead references.
2. Simplify subagent wiring so SDK prompt drives parallel explorer use.
3. Update extraction flow: DSPy extraction -> lead retrieval delegation -> lead decision -> write.
4. Update search flow to same retrieval style (prompt + explorer delegation).
5. Delete wikilink code paths from extractor, model, graph, maintenance, CLI.
6. Remove hot-path cold-task leakage in daemon/extract.
7. Keep dashboard UI path intact and read-only.
8. Keep Cursor adapter and registry integration intact.
9. Merge skill guidance into one user-facing Acreta skill and remove/deprecate extra Acreta-specific skills.
10. Run full test suite and docs updates, then remove dead code/files left by simplification.

## Tests and Acceptance

This section is mandatory and blocking for merge.

### Unit tests (pytest)

1. Run unit suite:
   - `scripts/run_tests.sh unit`
2. Add/adjust unit tests for:
   - DSPy extraction boundary (extract only, no write/no retrieval in DSPy module).
   - Lead final decision authority (`add|update|no-op`).
   - Prompt contract includes parallel explorer delegation.
   - Backend toggle strictness (disabled backend never executes).
   - No wikilink handling in memory/extract paths.

### Integration tests (pytest)

1. Run integration suite:
   - `ACRETA_INTEGRATION=1 pytest tests/test_e2e_real.py`
2. Add/adjust integration tests for:
   - `sync` hot path (no cold jobs triggered).
   - `maintain` cold path (consolidate/decay/rebuild jobs only here).
   - Sessions queue lifecycle (enqueue/claim/heartbeat/complete/fail).
   - Cursor ingestion still functional end-to-end.

### E2E tests (pytest)

1. Add/adjust E2E coverage for:
   - Transcript -> DSPy extract -> parallel explorer retrieval -> lead decision -> write.
   - Query path retrieval with dynamic explorer fan-out via SDK `Task`.
   - Dashboard read-only UI endpoints (status, runs, queue snapshots) still functional.
2. Validate both scopes:
   - project-first
   - global fallback

### Regression checks

1. No writes from explorer subagents.
2. No hidden FTS/vector/graph calls when toggles are disabled.
3. No wikilink tokens (`[[...]]`) emitted by prompts or stored as required syntax.
4. Queue counts and service run summaries remain correct.

### Documentation updates (required)

1. Update `/Users/kargarisaac/codes/personal/acreta/README.md`:
   - new simple architecture, DSPy boundary, parallel explorer retrieval.
2. Update `/Users/kargarisaac/codes/personal/acreta/docs/architecture.md`:
   - hot vs cold lane contract and lead authority.
3. Update `/Users/kargarisaac/codes/personal/acreta/.claude/skills/acreta/cli-reference.md`:
   - command behavior after simplification.
4. Update `/Users/kargarisaac/codes/personal/acreta/.claude/skills/acreta/SKILL.md`:
   - single-source instructions for how agents should use Acreta in the simplified flow.
5. Remove or deprecate extra Acreta-specific skill docs under `/Users/kargarisaac/codes/personal/acreta/.claude/skills/`.
6. Update package docs that remain under `acreta/*/README.md` to match removed/kept modules.

### Acceptance criteria

1. All unit, integration, and E2E tests pass.
2. Dashboard remains available as read-only UI.
3. Cursor integration remains supported.
4. Queue behavior remains intact.
5. Only one user-facing Acreta skill remains active.
6. Simplification goals achieved without introducing new orchestration frameworks.

## Assumptions

- “No python code” means no new overengineered runtime framework/modules; only minimal edits/removals and prompt-centered behavior.
- Claude SDK `Task` is the orchestration mechanism; no custom parallel engine is added.
