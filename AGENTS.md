# Acreta

Read global instructions: ~/.codex/AGENTS.md

We are at February 2026. Try to fetch up to date data from the web.

## What this project is

Acreta is a continual memory layer for coding agents and projects.
Read [README.md](README.md) for runtime overview and [docs/architecture.md](docs/architecture.md) for design.
CLI source of truth is [.claude/skills/acreta/cli-reference.md](.claude/skills/acreta/cli-reference.md).
General coding simplification source of truth is [docs/simple-coding-rules.md](docs/simple-coding-rules.md).

## Rules

- Never Never make silent decisions. Always ask Isaac.
- Never commit unless user asked clearly.
- Do not revert unrelated user changes.
- Keep folder docs updated when boundaries change.
- Start folder navigation from `acreta/README.md`.
- All functions should have docstring.
- All files should have a brief explanation on top of them in docstring explaining what the file does and contains.
- Each file should be testable in isolation (at least a minimal direct run/smoke path).
- Module self-tests must run the real path only (no mocking/stubbing in `__main__` self-test flows). 
- Add/update self-tests when possible. one `if __name__ == "__main__":` block and test under it. no separate function
- General rule: Prefer and try to have self-test per file when possible, inline in `if __name__ == "__main__":`.
- Never put fallback for packages. no try/except. if a package is needed and not installed, should raise an error
- Never keep old codes
- Always prefer implementing every feature with minimum number of functions and minimal number of lines and the most simple solution. Do not overengineer.
- Follow [docs/simple-coding-rules.md](docs/simple-coding-rules.md) for general coding style, simplification, strict schemas, and testing expectations.
- Never do normalization for chat traces. feed the raw traces to llm.
- DSPY uses pydantic. no need for separate normalization or check.
- Hard boundary: Acreta memory flow must always use LLM extraction/summarization. Never add `--no-llm`, `no_llm`, mock-summary shortcuts, or any non-LLM bypass path.

## Run locally

- Install: `uv venv && source .venv/bin/activate && uv pip install -e .`
- Scheduler: `python -m acreta daemon` (or `python -m acreta sync` / `python -m acreta maintain`)
- Query: `python -m acreta chat "<question>"`
- Dashboard: `python -m acreta dashboard --host 127.0.0.1 --port 8765`
- Tests (unit): `scripts/run_tests.sh unit`
- Tests (integration): `scripts/run_tests.sh integration`
- Tests (e2e): `scripts/run_tests.sh e2e`
- Tests (full stack): `scripts/run_tests.sh all`

## Memory model (V2)

- Project-first memory root: `<repo>/.acreta/`
- Global fallback memory root: `~/.acreta/`
- Primitive folders: `memory/decisions`, `memory/learnings`, `memory/summaries`
- Archive folders: `memory/archived/decisions`, `memory/archived/learnings`
- Summaries layout: `memory/summaries/YYYYMMDD/HHMMSS/{slug}.md`
- Trace archive: `meta/traces/sessions`
- Run workspace: `workspace/sync-<YYYYMMDD-HHMMSS>-<shortid>/` or `workspace/maintain-<YYYYMMDD-HHMMSS>-<shortid>/`
- Optional indexes: `index/fts.sqlite3`, `index/graph.sqlite3`, `index/vectors.lance/`

## Conventions

- Python 3.12, no heavy framework
- Filesystem is canonical memory store
- Lean frontmatter in memory files
- Graph links are explicit-first via `related` fields and ID/slug references (no wikilink dependency)
- Default search mode is `files`; FTS/vector/graph are toggleable
- `.acreta/` is gitignored by default

## Claude Code + Agent SDK guardrails

This section is the runtime contract for future agents.

### Capability baseline (verified Feb 18, 2026)

- Do not underestimate Claude Agent SDK. It supports production-grade orchestration:
  - Programmatic subagents via `agents` + `Task`.
  - Filesystem subagents via `.claude/agents/*.md`.
  - Separate context per subagent (better context isolation).
  - Parallel subagent execution for multi-branch analysis.
  - Per-subagent tool restrictions and model overrides.
  - MCP tool integration and plugin loading in SDK apps.
  - Strong CLI/terminal execution when `Bash` is allowed (good for `rg`, git inspection, local scripts, and repo ops).
- Current built-ins matter:
  - SDK: built-in `general-purpose` subagent is available when `Task` is allowed.
  - Claude Code: built-in `Explore`, `Plan`, and `general-purpose` subagents exist and are auto-delegated by Claude when relevant.
- Important constraint: subagents cannot spawn subagents (no nested Task trees).
- Skills are filesystem-native capability packs:
  - Project: `.claude/skills/*/SKILL.md`
  - User: `~/.claude/skills/*/SKILL.md`
  - SDK must enable `setting_sources=["user","project"]` and include `"Skill"` in `allowed_tools`.
  - In SDK, `SKILL.md` frontmatter `allowed-tools` is not an enforcement boundary; SDK `allowed_tools` controls runtime access.

If a future design assumes “Claude cannot do X”, verify against current docs first.

### Retrieval model

- File-first is required. Primary retrieval uses agent tools (`Read`, `Grep`, `Glob`, optional `Bash` with `rg`).
- Optional backends are accelerators only:
  - `fts` enabled: allow SQLite FTS candidate generation.
  - `vector` enabled: allow embedding nearest-neighbor candidate generation.
  - `graph` enabled: allow explicit edge expansion.
- If a backend is disabled, it is not used anywhere (including add/update merge decisions).
- No hidden vector fallback when user selected files-only mode.

### Graph model

- Do not require `[[wikilink]]` syntax.
- Canonical graph edges come from frontmatter `related` plus parser-detected explicit references to known memory IDs/slugs.
- Inferred edges are weak fallback only when explicit links are absent.

### Skills and subagents

- Skills are filesystem artifacts (`SKILL.md`), not programmatic SDK objects.
- SDK needs `setting_sources=["user","project"]` plus `allowed_tools` including `"Skill"` to load/use skills.
- `allowed-tools` in `SKILL.md` applies to Claude Code CLI, not SDK runtime policy. In SDK, tool policy is controlled in `allowed_tools`.
- Subagents are invoked through `Task`; use read-only subagents for exploration and keep writes in the lead/orchestrator path.

### DSPy boundary

- Use DSPy for extraction and normalization:
  - transcript/chunk -> primitive candidate(s)
  - quality/noise filtering
  - merge/update recommendation from candidate + retrieved neighbors
- Do not use DSPy as the retrieval engine. Retrieval remains tool-backed (files first, optional FTS/vector/graph per toggles).

### CRUD policy

- `create`: extract -> retrieve similar -> dedupe check -> write primitive file.
- `read`: retrieve with current mode/toggles, project-first then global fallback.
- `update`: extract delta -> retrieve neighbors -> apply merge/update policy -> update primitive file.
- `delete`: soft-delete first (tombstone + archive path), hard-delete only via explicit command/policy.

### Lead agent responsibilities

- Input: user task/query, scope (`project/global`), mode/toggles, optional transcript/session.
- Steps:
  1. Route operation (`create/read/update/delete`).
  2. Invoke explorer subagent for candidate gathering (read-only).
  3. Invoke DSPy pipeline for extraction/merge decision (create/update paths).
  4. Apply deterministic write/delete policy in core runtime.
  5. Return answer + evidence (which memories used, why).
- Lead agent is the only component allowed to persist/delete memory records.
- Memory-write runs must enforce `PreToolUse` guardrails so `Write|Edit` stay inside `memory_root` and current run workspace folder.
