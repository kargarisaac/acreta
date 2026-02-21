"""Maintain (memory maintenance) prompt builder for the AcretaAgent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acreta.memory.memory_record import memory_write_schema_prompt


def build_maintain_artifact_paths(run_folder: Path) -> dict[str, Path]:
    """Return canonical workspace artifact paths for a maintain run folder."""
    return {
        "maintain_actions": run_folder / "maintain_actions.json",
        "agent_log": run_folder / "agent.log",
        "subagents_log": run_folder / "subagents.log",
    }


def build_maintain_prompt(
    *,
    memory_root: Path,
    run_folder: Path,
    artifact_paths: dict[str, Path],
) -> str:
    """Build lead-agent prompt for the memory maintenance flow."""
    artifact_json = json.dumps(
        {key: str(path) for key, path in artifact_paths.items()}, ensure_ascii=True
    )
    schema_rules = memory_write_schema_prompt()
    return f"""\
You are running Acreta memory maintenance — an offline refinement pass over existing memories.
This mimics how human memory works: consolidate, strengthen important memories, forget noise.

Inputs:
- memory_root: {memory_root}
- run_folder: {run_folder} (use this for intermediate files to manage your context)
- artifact_paths: {artifact_json}

Checklist (use TodoWrite, move pending -> in_progress -> completed):
- scan_memories
- analyze_duplicates
- merge_similar
- archive_low_value
- consolidate_related
- write_report

Instructions:

1. SCAN: Use Task with Explore subagents to read all memory files in {memory_root}/decisions/ and {memory_root}/learnings/. Parse their frontmatter (id, title, confidence, tags, created, updated) and body content. Save a summary to {run_folder} for reference if the list is large.

2. ANALYZE DUPLICATES: Identify memories that cover the same topic or have substantially overlapping content. Group them by similarity.

3. MERGE: For memories with overlapping content about the same topic:
   - Keep the most comprehensive version as the primary.
   - Merge unique details from the secondary into the primary using Edit.
   - Update the primary's "updated" timestamp to now.
   - Archive the secondary by moving it: use Bash to run `mkdir -p {memory_root}/archived/{{folder}}/ && mv {{old_path}} {memory_root}/archived/{{folder}}/` where folder is "decisions" or "learnings".

4. ARCHIVE LOW-VALUE: Archive memories that are:
   - Very low confidence (< 0.3)
   - Trivial or obvious (e.g., "installed package X", "ran command Y" with no insight)
   - Superseded by a more complete memory covering the same ground
   Use the same Bash mv pattern to move them to archived/.

5. CONSOLIDATE: When you find 3+ small related memories about the same broader topic, consider combining them into one comprehensive memory file. Write the new consolidated memory via Write tool. Archive the originals.

6. REPORT: Write a JSON report to {artifact_paths["maintain_actions"]} with keys:
   - run_id: the run folder name
   - actions: list of {{"action", "source_path", "target_path", "reason"}} dicts
   - counts: {{"merged", "archived", "consolidated", "unchanged"}}
   - All file paths must be absolute.

Rules:
- You are the only writer. Explore subagents are read-only.
- Memory files use YAML frontmatter between --- delimiters.
- {schema_rules}
- When writing new/updated memory files, follow the same frontmatter schema.
- Do NOT touch {memory_root}/summaries/ — summaries are managed by the pipeline only.
- Do NOT delete files. Always archive (soft-delete via mv to archived/).
- Be conservative: when unsure whether to merge or archive, leave it unchanged.
- Quality over quantity: fewer good memories are better than many noisy ones.

Return one short plain-text completion line."""


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        run_folder = root / "workspace" / "maintain-selftest"
        artifact_paths = build_maintain_artifact_paths(run_folder)
        prompt = build_maintain_prompt(
            memory_root=root / "memory",
            run_folder=run_folder,
            artifact_paths=artifact_paths,
        )
        assert "memory maintenance" in prompt
        assert "scan_memories" in prompt
        assert "analyze_duplicates" in prompt
        assert "merge_similar" in prompt
        assert "archive_low_value" in prompt
        assert "consolidate_related" in prompt
        assert "write_report" in prompt
        assert "maintain_actions" in prompt
        assert "Do NOT touch" in prompt
        assert "soft-delete" in prompt
