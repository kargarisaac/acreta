# Acreta Python Package

## Summary

This folder contains Acreta runtime code.
The package is organized by feature boundary:

- `app/`: CLI, daemon loop, dashboard server
- `config/`: config loading, scope resolution, logging
- `sessions/`: platform indexing, session catalog, queue
- `memory/`: memory taxonomy/record schema (`memory_record.py`), repository paths/write API (`memory_repo.py`), maintenance, extraction pipeline, trace summarization pipeline
- `runtime/`: lead agent runtime and provider wiring
- `adapters/`: platform-specific session readers

## How to use

Read these files in order:

1. `app/cli.py` for the public command surface.
2. `app/daemon.py` for sync/maintain execution flow.
3. `sessions/catalog.py` + `memory/extract_pipeline.py` for ingest and extraction.
4. `memory/memory_repo.py` + `memory/memory_record.py` for persisted memory behavior.
