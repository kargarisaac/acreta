"""Sync (memory-write) prompt builder for the AcretaAgent lead orchestrator."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from acreta.memory.memory_record import memory_write_schema_prompt


def build_sync_prompt(
    *,
    trace_file: Path,
    memory_root: Path,
    run_folder: Path,
    artifact_paths: dict[str, Path],
    metadata: dict[str, str],
) -> str:
    """Build lead-agent prompt for the memory write flow."""
    metadata_json = json.dumps(metadata, ensure_ascii=True)
    artifact_json = json.dumps(
        {key: str(path) for key, path in artifact_paths.items()}, ensure_ascii=True
    )
    extract_cmd = (
        "python3 -m acreta.memory.extract_pipeline "
        f"--trace-path {shlex.quote(str(trace_file))} "
        f"--output {shlex.quote(str(artifact_paths['extract']))} "
        f"--metadata-json {shlex.quote(metadata_json)} "
        "--metrics-json '{}'"
    )
    summary_cmd = (
        "python3 -m acreta.memory.summarization_pipeline "
        f"--trace-path {shlex.quote(str(trace_file))} "
        f"--output {shlex.quote(str(artifact_paths['summary']))} "
        f"--memory-root {shlex.quote(str(memory_root))} "
        f"--metadata-json {shlex.quote(metadata_json)} "
        "--metrics-json '{}'"
    )
    schema_rules = memory_write_schema_prompt()
    return f"""\
Run the Acreta agent-led memory write flow.

Inputs:
- trace_path: {trace_file}
- memory_root_path: {memory_root}
- run_folder_path: {run_folder}
- artifact_paths_json: {artifact_json}

Checklist (must use TodoWrite and move statuses from pending -> in_progress -> completed):
- validate_inputs
- run_extract_pipeline
- run_summary_pipeline
- run_explorer_checks
- decide_add_update_no_op
- write_memory_files
- write_run_decision_report

{schema_rules}

Execution rules:
- Do not inline or normalize trace content. Use only trace_path file access.
- Use Bash to run DSPy pipelines:
  1) {extract_cmd}
  2) {summary_cmd}
- Read extract.json from artifact paths.
- The summary pipeline writes the summary directly to memory_root/summaries/ via --memory-root. Do NOT write summary files yourself.
- For candidate matching, use Task with built-in Explore subagent first. If unavailable, use Task with `explore-reader`.
- Explorer subagents are read-only and must return: candidate_id, action_hint, matched_file, evidence.
- Lead agent is the only writer and final decider.
- Deterministic decision policy for non-summary candidates:
  - no_op when matched memory has exact same primitive + title + body.
  - update when primitive matches and token-overlap score >= 0.72.
  - add otherwise.
- Write/update markdown memory files with YAML frontmatter in memory_root/decisions, memory_root/learnings.
- If extract returns 0 candidates, write an empty JSONL file to subagents_log (explorer is skipped).
- Write explorer outputs to {artifact_paths["subagents_log"]} as JSONL.
- Write run report JSON to {artifact_paths["memory_actions"]} with keys: run_id, todos, actions, counts, written_memory_paths, trace_path.
- Include overlap score evidence in actions when action is update/no_op.
- counts keys must be: add, update, no_op.
- Every written/updated file path must be absolute.

Return one short plain-text completion line."""


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        trace_file = root / "trace.jsonl"
        trace_file.write_text('{"role":"user","content":"hello"}\n', encoding="utf-8")
        run_folder = root / "workspace" / "sync-selftest"
        artifact_paths = {
            "extract": run_folder / "extract.json",
            "summary": run_folder / "summary.json",
            "memory_actions": run_folder / "memory_actions.json",
            "agent_log": run_folder / "agent.log",
            "subagents_log": run_folder / "subagents.log",
            "session_log": run_folder / "session.log",
        }
        prompt = build_sync_prompt(
            trace_file=trace_file,
            memory_root=root / "memory",
            run_folder=run_folder,
            artifact_paths=artifact_paths,
            metadata={
                "run_id": "sync-selftest",
                "trace_path": str(trace_file),
                "repo_name": "acreta",
            },
        )
        assert "artifact_paths_json" in prompt
        assert "--memory-root" in prompt
        assert "Do NOT write summary files yourself" in prompt
