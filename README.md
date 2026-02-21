# Acreta

Continual memory layer for coding agents.

## Summary

Acreta Memory V2 is file-first and primitive-first.

- Primitive folders: `decisions`, `learnings`, `summaries`
- Project memory first: `<repo>/.acreta/`
- Global fallback memory: `~/.acreta/`
- Search default: `files` (no index required)
- Extraction model: `dspy.RLM` with Ollama `qwen3:8b`
- Graph source of truth: explicit `related` ids/slugs + explicit id/slug references

This keeps memory readable by humans and easy for agents to traverse.

Lead flow:

1. Extract candidates from transcript archive.
2. Lead agent runs `TodoWrite` checklist and delegates read-only explorer tasks (`Explore` first).
3. Lead runs deterministic decision policy for `add|update|no-op`.
4. Lead writes memory under hook-enforced write boundaries.
5. `sync` stays lightweight; offline refinement (merge, dedupe, forget) runs in `maintain`.

## How to use

### Prerequisites

`dspy.RLM` uses DSPy's Deno-based Python interpreter. Deno must be installed or extraction will fail.

```bash
brew install deno
deno --version
```

### Install

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
```

### Core commands

```bash
acreta connect auto
acreta sync
acreta maintain
acreta daemon
acreta dashboard
acreta memory list
acreta memory search "why did we choose this"
acreta memory add --primitive decision --title "..." --body "..."
acreta memory reset --scope both --yes
acreta chat "Why did we choose this pattern?"
acreta status
```

### Test commands

Use the canonical runner:

```bash
scripts/run_tests.sh unit
scripts/run_tests.sh integration
scripts/run_tests.sh e2e
scripts/run_tests.sh all
```

### Search modes

Configured in `.acreta/config.toml` or `~/.acreta/config.toml`:

- `files`: scan markdown files directly (default)

Toggles:
- `search.enable_fts`
- `search.enable_vectors`
- `search.enable_graph`

In the simplified runtime, retrieval stays file-first.

## Memory layout

Project scope:

```text
<repo>/.acreta/
  config.toml
  memory/
    decisions/
    learnings/
    summaries/
      YYYYMMDD/
        HHMMSS/
          {slug}.md
    archived/
      decisions/
      learnings/
  meta/
    traces/
      sessions/
  workspace/
    sync-<YYYYMMDD-HHMMSS>-<shortid>/
      extract.json
      summary.json
      memory_actions.json
      agent.log
      subagents.log
      session.log
    maintain-<YYYYMMDD-HHMMSS>-<shortid>/
      maintain_actions.json
      agent.log
      subagents.log
  index/   # reserved
```

Global fallback scope follows the same layout under `~/.acreta/`.

## Primitive frontmatter (lean)

- `decision`: `id,title,created,updated,source,confidence,tags,related`
- `learning`: `id,title,created,updated,source,confidence,tags,related,kind`
- `summary`: `id,title,description,date,time,coding_agent,raw_trace_path,run_id,repo_name,related,created,updated`

All metadata lives in frontmatter — no sidecars.

## Reset policy

Memory reset is explicit and destructive.

- `acreta memory reset --scope project|global|both --yes`
- Deletes `memory/`, `workspace/`, and `index/` under selected root(s), then recreates canonical folders.
- `--scope project`: resets `<repo>/.acreta/` only.
- `--scope global`: resets `~/.acreta/` only (includes sessions DB).
- `--scope both` (default): resets both.
- Sessions DB lives in global `index/`, so `--scope project` alone does not reset sessions.

Fresh start:
```bash
acreta memory reset --yes        # wipe everything
acreta sync --max-sessions 5     # re-sync newest conversations
```

## Docs map

- Runtime architecture: `docs/architecture.md`
- CLI source of truth: `.claude/skills/acreta/cli-reference.md`
