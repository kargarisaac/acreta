"""E2E-style contract tests for hot/cold/sync memory-write modes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acreta.runtime.agent import AcretaAgent


def _extract_artifacts_from_prompt(prompt: str) -> dict[str, str]:
    """Extract artifact path mapping from the lead prompt."""
    for line in prompt.splitlines():
        if line.startswith("- artifact_paths_json: "):
            return json.loads(line.split(": ", 1)[1])
    raise AssertionError("artifact_paths_json not found in prompt")


def _extract_memory_root_from_prompt(prompt: str) -> Path:
    """Extract memory root path from the lead prompt."""
    for line in prompt.splitlines():
        if line.startswith("- memory_root_path: "):
            return Path(line.split(": ", 1)[1].strip())
    raise AssertionError("memory_root_path not found in prompt")


def _fake_sdk_run_factory() -> callable:
    """Build fake SDK runner that emits add, update, then no_op across runs."""
    sequence = [{"add": 1, "update": 0, "no_op": 0}, {"add": 0, "update": 1, "no_op": 0}, {"add": 0, "update": 0, "no_op": 1}]
    state = {"index": 0}

    async def _fake_run(
        _self: AcretaAgent,
        *,
        prompt: str,
        session_id: str | None,
        cwd: str | None,
        allowed_tools: list[str],
        permission_mode: str,
        add_dirs=(),
        env=None,
        hooks=None,
        agents=None,
    ):
        _ = (session_id, cwd, allowed_tools, permission_mode, add_dirs, env, hooks, agents)
        artifacts = _extract_artifacts_from_prompt(prompt)
        memory_root = _extract_memory_root_from_prompt(prompt)
        counts = sequence[min(state["index"], len(sequence) - 1)]
        state["index"] += 1

        Path(artifacts["extract"]).write_text("[]\n", encoding="utf-8")
        Path(artifacts["summary"]).write_text(
            json.dumps({"title": "Run summary", "summary": "Summary body"}, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        Path(artifacts["subagents_log"]).write_text(
            json.dumps({"candidate_id": 0, "action_hint": "add", "matched_file": "", "evidence": "no strong match"}, ensure_ascii=True)
            + "\n",
            encoding="utf-8",
        )

        summary_memory_path = memory_root / "summaries" / f"summary--s20260220{state['index']:04d}.md"
        summary_memory_path.parent.mkdir(parents=True, exist_ok=True)
        summary_memory_path.write_text("---\nid: s202602200001\ntitle: Summary\n---\nSummary body\n", encoding="utf-8")

        report = {
            "run_id": f"run-{state['index']}",
            "todos": [],
            "actions": [],
            "counts": counts,
            "written_memory_paths": [str(summary_memory_path)],
            "summary_path": str(summary_memory_path),
            "trace_path": "/tmp/trace.jsonl",
        }
        Path(artifacts["memory_actions"]).write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        return "ok", "session-1"

    return _fake_run


@pytest.mark.e2e
def test_hot_cold_sync_flow_contract(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """E2E contract: hot/cold/sync each produce run folder + artifacts + mode-specific result."""
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text('{"role":"user","content":"hello"}\n', encoding="utf-8")
    monkeypatch.setattr(AcretaAgent, "_run_sdk_once", _fake_sdk_run_factory())

    agent = AcretaAgent(default_cwd=str(tmp_path))
    hot = agent.run(trace_path, run_mode="hot")
    cold = agent.run(trace_path, run_mode="cold")
    sync = agent.run(trace_path, run_mode="sync")

    assert Path(hot["run_folder"]).name.startswith("hot-")
    assert Path(cold["run_folder"]).name.startswith("cold-")
    assert Path(sync["run_folder"]).name.startswith("sync-")
    assert hot["counts"]["add"] == 1
    assert cold["counts"]["update"] == 1
    assert sync["counts"]["no_op"] == 1
    for result in (hot, cold, sync):
        assert Path(result["artifacts"]["extract"]).exists()
        assert Path(result["artifacts"]["summary"]).exists()
        assert Path(result["artifacts"]["memory_actions"]).exists()
        assert Path(result["summary_path"]).exists()
        assert "/summaries/" in result["summary_path"]
