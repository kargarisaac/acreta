"""Trace summarization pipeline that outputs markdown-frontmatter-ready metadata + summary.

When --memory-root is provided, the pipeline writes the summary markdown file
directly to memory_root/summaries/{date}-{slug}.md using python-frontmatter.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dspy
import frontmatter
from pydantic import BaseModel, Field

from acreta.memory.memory_record import MemoryType, canonical_memory_filename, slugify
from acreta.memory.utils import configure_dspy_lm, env_positive_int
from acreta.sessions import catalog as session_db


class TraceSummaryCandidate(BaseModel):
    """Structured trace summary payload used to build markdown frontmatter later."""

    title: str = Field(description="Short trace title for markdown frontmatter.")
    description: str = Field(
        description="One-line description of what the session achieved."
    )
    summary: str = Field(description="Natural-language summary with at most 300 words.")
    date: str = Field(description="Session date in YYYY-MM-DD.")
    time: str = Field(description="Session time in HH:MM:SS.")
    coding_agent: str = Field(
        description="Coding agent label like codex, claude code, cursor, or windsurf."
    )
    raw_trace_path: str = Field(
        description="Absolute path to the original raw trace file."
    )
    run_id: str | None = Field(
        default=None, description="Session run id when available."
    )
    repo_name: str | None = Field(
        default=None, description="Repository short name when available."
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Group/cluster labels for this summary. No limit.",
    )


class TraceSummarySignature(dspy.Signature):
    """Summarize a raw session trace into markdown-ready metadata plus summary text.

    Rules:
    - Keep summary factual and grounded in trace evidence.
    - Keep summary length <= 300 words.
    - Keep title and description concise and specific.
    - Assign descriptive tags (group/cluster labels) for categorization. No limit on tag count.
    """

    transcript: str = dspy.InputField(desc="Raw transcript text")
    metadata: dict[str, Any] = dspy.InputField(desc="Session metadata")
    metrics: dict[str, Any] = dspy.InputField(desc="Deterministic metrics")
    summary_payload: TraceSummaryCandidate = dspy.OutputField(
        desc="Structured summary payload with title/description/date/time/agent/path/tags fields"
    )


def _summarize_trace_with_rlm(
    transcript: str,
    *,
    metadata: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    session_file_path: Path,
) -> dict[str, Any]:
    """Run DSPy RLM summarization and return schema-validated summary metadata payload."""
    if not transcript.strip():
        raise RuntimeError("session_trace_empty")
    max_iterations = env_positive_int("ACRETA_DSPY_RLM_MAX_ITERATIONS", 24)
    max_llm_calls = env_positive_int("ACRETA_DSPY_RLM_MAX_LLM_CALLS", 24)
    configure_dspy_lm()
    rlm = dspy.RLM(
        TraceSummarySignature,
        max_iterations=max_iterations,
        max_llm_calls=max_llm_calls,
        verbose=True,
    )
    result = rlm(
        transcript=transcript,
        metadata=metadata or {},
        metrics=metrics or {},
    )
    payload = getattr(result, "summary_payload", None)
    if isinstance(payload, TraceSummaryCandidate):
        candidate = payload
    elif isinstance(payload, dict):
        candidate = TraceSummaryCandidate.model_validate(payload)
    else:
        raise RuntimeError("dspy summary_payload must be TraceSummaryCandidate or dict")
    return candidate.model_dump(mode="json", exclude_none=True)


def write_summary_markdown(
    payload: dict[str, Any],
    memory_root: Path,
    *,
    run_id: str = "",
) -> Path:
    """Write summary markdown with frontmatter to memory_root/summaries/{date}-{slug}.md."""
    title = str(payload.get("title") or "untitled")
    summary_body = str(payload.get("summary") or "")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    fm_dict: dict[str, Any] = {
        "id": slugify(title),
        "title": title,
        "created": now_iso,
        "source": run_id,
        "description": payload.get("description", ""),
        "date": payload.get("date", now_iso[:10]),
        "time": payload.get("time", now_iso[11:19]),
        "coding_agent": payload.get("coding_agent", "unknown"),
        "raw_trace_path": payload.get("raw_trace_path", ""),
        "run_id": payload.get("run_id") or run_id,
        "repo_name": payload.get("repo_name", ""),
        "tags": payload.get("tags", []),
    }

    filename = canonical_memory_filename(
        primitive=MemoryType.summary,
        title=title,
        run_id=run_id,
    )
    summaries_dir = memory_root / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summaries_dir / filename

    post = frontmatter.Post(summary_body, **fm_dict)
    summary_path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    return summary_path


def summarize_trace_from_session_file(
    session_file_path: Path,
    *,
    metadata: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize one session trace file into markdown-ready metadata + <=300 word summary."""
    if not session_file_path.exists() or not session_file_path.is_file():
        raise FileNotFoundError(f"session_file_missing:{session_file_path}")
    transcript = session_file_path.read_text(encoding="utf-8")
    session_metadata = {**(metadata or {}), "raw_trace_path": str(session_file_path)}
    return _summarize_trace_with_rlm(
        transcript,
        metadata=session_metadata,
        metrics=metrics,
        session_file_path=session_file_path,
    )


if __name__ == "__main__":
    """Run CLI summary mode by trace path or run a real-path self-test."""
    import argparse
    import os
    import sys
    from tempfile import TemporaryDirectory

    from acreta.config.settings import reload_config

    parser = argparse.ArgumentParser(
        prog="python -m acreta.memory.summarization_pipeline"
    )
    parser.add_argument("--trace-path")
    parser.add_argument("--output")
    parser.add_argument(
        "--memory-root",
        help="When provided, write summary markdown to memory_root/summaries/",
    )
    parser.add_argument("--metadata-json", default="{}")
    parser.add_argument("--metrics-json", default="{}")
    args = parser.parse_args()

    if args.trace_path:
        session_file = Path(args.trace_path).expanduser()
        metadata = json.loads(args.metadata_json)
        metrics = json.loads(args.metrics_json)
        payload = summarize_trace_from_session_file(
            session_file,
            metadata=metadata if isinstance(metadata, dict) else {},
            metrics=metrics if isinstance(metrics, dict) else {},
        )

        # Write summary markdown if --memory-root provided
        if args.memory_root:
            mr = Path(args.memory_root).expanduser().resolve()
            run_id = (metadata if isinstance(metadata, dict) else {}).get("run_id", "")
            summary_path = write_summary_markdown(payload, mr, run_id=run_id)
            payload["summary_path"] = str(summary_path)

        encoded = json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
        if args.output:
            output_path = Path(args.output).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(encoded, encoding="utf-8")
        else:
            sys.stdout.write(encoded)
    else:
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            os.environ["ACRETA_DATA_DIR"] = str(tmp_path)
            os.environ["ACRETA_MEMORY_DIR"] = str(tmp_path / "memory")
            os.environ["ACRETA_INDEX_DIR"] = str(tmp_path / "index")
            os.environ["ACRETA_SESSIONS_DB"] = str(
                tmp_path / "index" / "sessions.sqlite3"
            )
            os.environ["ACRETA_MEMORY_SCOPE"] = "global_only"
            reload_config()
            session_db.init_sessions_db()

            run_id = "summary-self-test-1"
            session_path = tmp_path / "sessions" / f"{run_id}.jsonl"
            session_path.parent.mkdir(parents=True, exist_ok=True)
            session_path.write_text(
                '{"role":"user","content":"Fix queue heartbeat drift and duplicate claims."}\n'
                '{"role":"assistant","content":"Implemented heartbeat every 15 seconds and bounded retries."}\n',
                encoding="utf-8",
            )
            session_db.index_session_for_fts(
                run_id=run_id,
                agent_type="codex",
                repo_name="acreta",
                content="queue heartbeat fix",
                session_path=str(session_path),
            )
            payload = summarize_trace_from_session_file(
                session_path, metadata={"run_id": run_id}, metrics={}
            )

        assert isinstance(payload, dict)
        assert payload["title"]
        assert payload["description"]
        assert payload["coding_agent"] == "codex"
        assert payload["raw_trace_path"].endswith(f"{run_id}.jsonl")
        assert len(payload["summary"].split()) <= 300
