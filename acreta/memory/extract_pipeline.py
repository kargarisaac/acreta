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

from acreta.memory.models import LearningType, PrimitiveType
from acreta.memory.utils import configure_dspy_lm, env_positive_int
from acreta.sessions import catalog as session_db


class MemoryCandidate(BaseModel):
    """One extracted memory candidate from a transcript."""

    primitive: PrimitiveType = Field(description="Primitive folder type: decision, learning, convention, or context.")
    learning_type: LearningType | None = Field(
        default=None,
        description="Subtype taxonomy. Use friction for blockers/struggles. Usually set when primitive=learning.",
    )
    title: str = Field(description="Short memory title.")
    body: str = Field(description="Memory content in plain language.")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Confidence score from 0 to 1.")


class MemoryExtractSignature(dspy.Signature):
    """Extract reusable memory candidates from transcript text.

    Focus on high-value items:
    - repeated struggles and blockers
    - lessons and fixes that worked
    - decisions and conventions to reuse later
    - project context worth remembering

    Use Acreta primitive values exactly: decision, learning, convention, context.
    For struggle/blocker memories, use primitive=learning and learning_type=friction.
    """

    transcript: str = dspy.InputField(desc="Raw transcript text")
    metadata: dict[str, Any] = dspy.InputField(desc="Session metadata")
    metrics: dict[str, Any] = dspy.InputField(desc="Deterministic metrics")
    primitives: list[MemoryCandidate] = dspy.OutputField(desc="Extracted memory candidate list")


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
        item.model_dump(mode="json", exclude_none=True) if isinstance(item, MemoryCandidate) else item
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


def extract_session_memories(
    run_id: str,
    *,
    no_llm: bool = False,
) -> dict[str, Any]:
    """Resolve one run id, extract candidates from its session trace, and return summary."""
    session = session_db.fetch_session_doc(run_id)
    if session is None:
        session_db.index_new_sessions()
        session = session_db.fetch_session_doc(run_id)
    if session is None:
        return {"run_id": run_id, "status": "missing"}

    source_path_raw = str(session.get("session_path") or "").strip()
    if not source_path_raw:
        return {"run_id": run_id, "status": "session_path_missing"}

    session_file_path = Path(source_path_raw).expanduser()
    if not session_file_path.exists() or not session_file_path.is_file():
        return {"run_id": run_id, "status": "session_path_missing"}

    candidates: list[dict[str, Any]] = []
    if not no_llm:
        candidates = extract_memories_from_session_file(
            session_file_path,
            metadata={**session, "run_id": run_id},
            metrics={},
        )

    tags = []
    if session.get("agent_type"):
        tags.append(f"agent:{session.get('agent_type')}")
    if session.get("repo_name"):
        tags.append(f"repo:{session.get('repo_name')}")
    tags = sorted(set(tags))

    session_db.update_session_extract_fields(
        run_id=run_id,
        summary_text=str(session.get("summary_text") or "").strip() or None,
        tags=json.dumps(tags, ensure_ascii=True) if tags else None,
        outcome="unclear_from_transcript",
    )

    return {
        "run_id": run_id,
        "status": "completed",
        "tags": tags,
        "candidates": candidates,
        "metadata": {**session, "run_id": run_id},
        "session_path": str(session_file_path),
        "learnings_new": 0,
        "learnings_updated": 0,
        "learnings_no_op": 0,
    }


def build_extract_report(
    *,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    agent_types: list[str] | None = None,
    no_llm: bool = False,
) -> dict[str, Any]:
    """Build aggregate extraction stats for dashboard and maintenance views."""
    _ = no_llm
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
        "narratives": {"at_a_glance": {"working": "", "hindering": "", "quick_wins": "", "horizon": ""}},
    }


if __name__ == "__main__":
    """Run a real self-test for extraction quality on a realistic session."""
    from tempfile import TemporaryDirectory

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

    primitive_values = {item.value for item in PrimitiveType}
    learning_type_values = {item.value for item in LearningType}
    quality_hits = 0
    for item in candidates:
        assert isinstance(item, dict), "self-test failed: candidate must be dict"
        primitive = str(item.get("primitive") or "").strip()
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        learning_type = item.get("learning_type")

        assert primitive in primitive_values, f"self-test failed: invalid primitive={primitive!r}"
        assert len(title) >= 8, "self-test failed: title too short"
        assert len(body) >= 24, "self-test failed: body too short"
        if learning_type is not None:
            assert str(learning_type) in learning_type_values, (
                f"self-test failed: invalid learning_type={learning_type!r}"
            )

        text_blob = f"{title} {body}".lower()
        if any(keyword in text_blob for keyword in ("heartbeat", "dead_letter", "file path", "retry", "friction")):
            quality_hits += 1

    assert quality_hits >= 1, "self-test failed: extracted memories miss expected session signals"
