# Acreta

Continual memory layer for coding agents.

## Summary

Acreta Memory V2 is file-first and primitive-first.

- Primitive folders: `decisions`, `learnings`, `conventions`, `context`
- Project memory first: `<repo>/.acreta/`
- Global fallback memory: `~/.acreta/`
- Search default: `files` (no index required)
- Extraction model: `dspy.RLM` with Ollama `qwen3:8b`
- Graph source of truth: explicit `related` ids/slugs + explicit id/slug references

This keeps memory readable by humans and easy for agents to traverse.

Lead flow:

1. Extract candidates from transcript archive.
2. Lead agent delegates parallel read-only explorer tasks for retrieval evidence.
3. Lead decides `add|update|no-op`.
4. Lead writes memory and sidecars.
5. `sync` stays lightweight; cold rebuilds stay in `maintain`.

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
    conventions/
    context/
  meta/
    evidence/
    state/
    traces/
      sessions/
  index/   # reserved
```

Global fallback scope:

```text
~/.acreta/
  config.toml
  memory/
    decisions/
    learnings/
    conventions/
    context/
  meta/
    evidence/
    state/
    traces/
      sessions/
  index/   # reserved
```

## Primitive frontmatter (lean)

- `decision`: `id,title,status,decided_by,tags,related,created,updated`
- `learning`: `id,title,kind,tags,related,created,updated`
- `convention`: `id,title,scope,tags,related,created,updated`
- `context`: `id,title,area,tags,related,created,updated`

Operational metadata is not in frontmatter.
It is stored in sidecars under `meta/state` and `meta/evidence`.

## Reset policy

Memory reset is explicit and destructive.

- manual reset: `acreta memory reset --scope project|global|both --yes`
- reset deletes `memory/`, `meta/`, and `index/` under selected root(s)
- reset recreates canonical empty V2 folders immediately

## Docs map

- Runtime architecture: `docs/architecture.md`
- Manual validation: `docs/manual-test-pre-phase-3.md`
- CLI source of truth: `.claude/skills/acreta/cli-reference.md`
