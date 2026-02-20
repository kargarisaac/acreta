"""Shared test utilities for constructing canonical runtime configuration."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from acreta.config.settings import Config


def make_config(base: Path) -> Config:
    """Build a deterministic Config object rooted at ``base`` for tests."""
    return Config(
        data_dir=base,
        memory_dir=base / "memory",
        index_dir=base / "index",
        memory_db_path=base / "index" / "fts.sqlite3",
        sessions_db_path=base / "index" / "sessions.sqlite3",
        vectors_dir=base / "index" / "vectors.lance",
        platforms_path=base / "platforms.json",
        claude_dir=base / "claude",
        codex_dir=base / "codex",
        opencode_dir=base / "opencode",
        server_host="127.0.0.1",
        server_port=8765,
        poll_interval_minutes=5,
        provider="zai",
        agent_model=None,
        agent_timeout=120,
        anthropic_api_key=None,
        zai_api_key=None,
        openai_api_key=None,
        openrouter_api_key=None,
        embeddings_provider="local",
        embedding_model="Alibaba-NLP/gte-modernbert-base",
        embeddings_base_url=None,
        embedding_chunk_tokens=800,
        embedding_chunk_overlap_tokens=200,
        embedding_max_input_tokens=8192,
        graph_export=False,
    )


def run_cli(args: list[str]) -> tuple[int, str]:
    """Run CLI command and return ``(exit_code, stdout_text)``."""
    from acreta.app import cli

    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(args)
    return code, out.getvalue()


def run_cli_json(args: list[str]) -> tuple[int, dict]:
    """Run CLI command and parse stdout JSON payload."""
    code, output = run_cli(args)
    return code, json.loads(output)
