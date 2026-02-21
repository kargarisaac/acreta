# Acreta CLI Reference (Source Of Truth)

Canonical parser source:
- `acreta/app/cli.py`

Canonical command:
- `acreta`

## Global flag

```bash
--json
```

## Exit codes

- `0`: success
- `1`: runtime failure
- `2`: usage error
- `3`: partial success
- `4`: lock busy

## Command map

- `connect`
- `sync`
- `maintain`
- `daemon`
- `dashboard`
- `memory` (`search`, `list`, `add`, `export`, `reset`)
- `chat`
- `status`

## Commands

### `acreta connect`

```bash
acreta connect list
acreta connect auto
acreta connect <platform> [--path <dir>]
acreta connect remove <platform>
```

Platforms:
- `claude`, `codex`, `cursor`, `opencode`

### `acreta sync`

```bash
acreta sync
acreta sync --run-id <id>
acreta sync --agent claude,codex
acreta sync --window 30d|all
acreta sync --since 2026-02-01T00:00:00Z --until 2026-02-08T00:00:00Z
acreta sync --no-extract
acreta sync --force
acreta sync --max-sessions 100
acreta sync --dry-run
acreta sync --ignore-lock
```

Notes:
- `sync` is the hot path (queue + DSPy `dspy.RLM` extraction + lead decision/write).
- Cold maintenance work is not executed in `sync`.
- Extraction requires Deno for DSPy's interpreter (`brew install deno`).

### `acreta maintain`

```bash
acreta maintain
acreta maintain --force
acreta maintain --dry-run
```

Notes:
- `maintain` is the cold path for offline memory refinement (merge duplicates, archive low-value, consolidate related).
- Runs a single agent invocation that scans existing memories and decides what to merge/archive/consolidate.
- Soft-deletes archived memories to `memory/archived/{decisions,learnings}/`.

### `acreta daemon`

```bash
acreta daemon
acreta daemon --once
acreta daemon --poll-seconds 120
```

### `acreta dashboard`

```bash
acreta dashboard
acreta dashboard --host 127.0.0.1 --port 8765
```

### `acreta memory`

```bash
acreta memory search "<query>" [--project <project>] [--limit 20]
acreta memory list [--project <project>] [--limit 50]
acreta memory add --primitive decision|learning --title "<title>" --body "<body>"
acreta memory add --kind insight|procedure|friction|pitfall|preference ...
acreta memory export [--project <project>] [--format json|markdown] [--output <path>]
acreta memory reset --scope project|global|both --yes
```

Notes:
- `memory reset` is destructive.
- It deletes `memory/`, `meta/`, and `index/` under selected roots, then recreates canonical folders.

### `acreta chat`

```bash
acreta chat "<question>" [--project <project>] [--limit 12]
```

Notes:
- Chat uses memory retrieval evidence.
- If provider auth fails, CLI returns an error.

### `acreta status`

```bash
acreta status
```
