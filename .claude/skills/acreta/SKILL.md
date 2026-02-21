---
name: acreta
description: User-facing Acreta usage guide for the simplified lead-agent memory flow.
tools: [Bash, Read]
---

# Acreta — Public User Skill

## Summary

Use this skill for user-facing Acreta usage.
Keep guidance simple and aligned with the lead-agent flow.

CLI source of truth:
- `.claude/skills/acreta/cli-reference.md`

## Core commands

- `acreta connect list|auto|<platform>|remove`
- `acreta sync`
- `acreta maintain`
- `acreta daemon`
- `acreta dashboard`
- `acreta memory search|list|add|export|reset`
- `acreta chat`
- `acreta status`

## Runtime contract

- Lead agent is the only writer and final decision maker.
- DSPy extraction uses `dspy.RLM` on Ollama model `qwen3:8b`.
- Explorer subagents are read-only and gather evidence in parallel via `Task`.
- Sync decision actions are `add`, `update`, `no-op`.
- Maintain actions are `merge`, `archive`, `consolidate`, `unchanged`.
- Keep `related` values as explicit ids/slugs.
- Do not depend on wikilink syntax.

## Memory V2 notes

- Canonical store is markdown files in primitive folders.
- Project-first memory root: `.acreta/` in repo.
- Global fallback root: `~/.acreta/`.
- Search default is files mode.
- FTS/vector/graph are optional toggles and only run when enabled.
