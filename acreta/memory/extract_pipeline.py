"""Minimal extraction pipeline for session transcripts.

The extraction path is intentionally simple:
session file (.jsonl/.json) -> read text -> dspy.RLM -> memory candidates.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import dspy
from pydantic import BaseModel, Field

from acreta.memory.memory_record import MemoryType
from acreta.memory.utils import configure_dspy_lm, env_positive_int
from acreta.sessions import catalog as session_db


class MemoryCandidate(BaseModel):
    """One extracted memory candidate from a transcript."""

    primitive: MemoryType = Field(description="Memory type: decision or learning.")
    kind: str | None = Field(
        default=None,
        description="Subtype: insight, procedure, friction, pitfall, or preference. Usually set when primitive=learning.",
    )
    title: str = Field(description="Short memory title.")
    body: str = Field(description="Memory content in plain language.")
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Confidence score from 0 to 1."
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Group/cluster labels for this memory. No limit.",
    )


class MemoryExtractSignature(dspy.Signature):
    """Extract reusable memory candidates from transcript text.

    Focus on high-value items:
    - repeated struggles and blockers
    - lessons and fixes that worked
    - decisions to reuse later
    - practical context embedded as learning tags

    Use Acreta memory type values exactly: decision, learning.
    For struggle/blocker memories, use primitive=learning and kind=friction.
    Assign descriptive tags (group/cluster labels) to each candidate for categorization. No limit on tag count.
    """

    transcript: str = dspy.InputField(desc="Raw transcript text")
    metadata: dict[str, Any] = dspy.InputField(desc="Session metadata")
    metrics: dict[str, Any] = dspy.InputField(desc="Deterministic metrics")
    primitives: list[MemoryCandidate] = dspy.OutputField(
        desc="Extracted memory candidate list"
    )


def _extract_candidates_with_rlm(
    transcript: str,
    *,
    metadata: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run DSPy RLM on transcript text and return normalized candidates."""
    if not transcript.strip():
        return []
    max_iterations = env_positive_int("ACRETA_DSPY_RLM_MAX_ITERATIONS", 24)
    max_llm_calls = env_positive_int("ACRETA_DSPY_RLM_MAX_LLM_CALLS", 24)
    configure_dspy_lm()
    rlm = dspy.RLM(
        MemoryExtractSignature,
        max_iterations=max_iterations,
        max_llm_calls=max_llm_calls,
        verbose=True,
    )
    result = rlm(
        transcript=transcript,
        metadata=metadata or {},
        metrics=metrics or {},
    )
    primitives = getattr(result, "primitives", [])
    if not isinstance(primitives, list):
        return []
    return [
        item.model_dump(mode="json", exclude_none=True)
        if isinstance(item, MemoryCandidate)
        else item
        for item in primitives
        if isinstance(item, (MemoryCandidate, dict))
    ]


def extract_memories_from_session_file(
    session_file_path: Path,
    *,
    metadata: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Extract memory candidates from one on-disk session trace file."""
    if not session_file_path.exists() or not session_file_path.is_file():
        raise FileNotFoundError(f"session_file_missing:{session_file_path}")
    transcript = session_file_path.read_text(encoding="utf-8")
    return _extract_candidates_with_rlm(transcript, metadata=metadata, metrics=metrics)


def build_extract_report(
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    agent_types: list[str] | None = None,
) -> dict[str, Any]:
    """Build aggregate extraction stats for dashboard and maintenance views."""
    rows, _ = session_db.list_sessions_window(
        limit=500,
        offset=0,
        agent_types=agent_types,
        since=window_start,
        until=window_end,
    )
    totals = defaultdict(int)
    for row in rows:
        totals["sessions"] += 1
        totals["messages"] += int(row.get("message_count") or 0)
        totals["tool_calls"] += int(row.get("tool_call_count") or 0)
        totals["errors"] += int(row.get("error_count") or 0)
        totals["tokens"] += int(row.get("total_tokens") or 0)
    return {
        "window_start": window_start.isoformat() if window_start else None,
        "window_end": window_end.isoformat() if window_end else None,
        "agent_filter": ",".join(agent_types) if agent_types else "all",
        "aggregates": {"totals": dict(totals)},
        "narratives": {
            "at_a_glance": {
                "working": "",
                "hindering": "",
                "quick_wins": "",
                "horizon": "",
            }
        },
    }


if __name__ == "__main__":
    """Run CLI extract mode by trace path or run a real-path self-test."""
    import argparse
    import sys
    from tempfile import TemporaryDirectory

    parser = argparse.ArgumentParser(prog="python -m acreta.memory.extract_pipeline")
    parser.add_argument("--trace-path")
    parser.add_argument("--output")
    parser.add_argument("--metadata-json", default="{}")
    parser.add_argument("--metrics-json", default="{}")
    args = parser.parse_args()

    if args.trace_path:
        metadata = json.loads(args.metadata_json)
        metrics = json.loads(args.metrics_json)
        payload = extract_memories_from_session_file(
            Path(args.trace_path).expanduser(),
            metadata=metadata if isinstance(metadata, dict) else {},
            metrics=metrics if isinstance(metrics, dict) else {},
        )
        encoded = json.dumps(payload, ensure_ascii=True, indent=2) + "\n"
        if args.output:
            output_path = Path(args.output).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(encoded, encoding="utf-8")
        else:
            sys.stdout.write(encoded)
    else:
        with TemporaryDirectory() as tmp_dir:
            session_file_path = Path(tmp_dir) / "session.jsonl"
            session_file_path.write_text(
                "\n".join(
                    [
                        '{"role":"user","content":"I keep failing the same edit because the target string exists in test and src. This friction wasted 30 minutes."}',
                        '{"role":"assistant","content":"Lesson: read the exact file first, then patch with file path and larger context. Avoid global replace."}',
                        '{"role":"user","content":"Queue jobs got stuck again. Heartbeat drift caused retries and duplicate claims."}',
                        '{"role":"assistant","content":"Fix worked: heartbeat every 15s, max_attempts=3, then dead_letter. Add metrics for retries and dead letters."}',
                        '{"role":"user","content":"Decision: do not copy traces into Acreta. Keep only session_path and metadata; extract directly from source file."}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            candidates = extract_memories_from_session_file(
                session_file_path,
                metadata={"run_id": "self-test"},
                metrics={},
            )
        assert candidates, "self-test failed: no candidates extracted"

        quality_hits = 0
        for item in candidates:
            assert isinstance(item, dict), "self-test failed: candidate must be dict"
            primitive = str(item.get("primitive") or "").strip()
            title = str(item.get("title") or "").strip()
            body = str(item.get("body") or "").strip()

            assert primitive in {"decision", "learning"}, (
                f"self-test failed: invalid primitive={primitive!r}"
            )
            assert len(title) >= 8, "self-test failed: title too short"
            assert len(body) >= 24, "self-test failed: body too short"

            text_blob = f"{title} {body}".lower()
            if any(
                keyword in text_blob
                for keyword in (
                    "heartbeat",
                    "dead_letter",
                    "file path",
                    "retry",
                    "friction",
                )
            ):
                quality_hits += 1

        assert quality_hits >= 1, (
            "self-test failed: extracted memories miss expected session signals"
        )
