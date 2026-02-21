"""test runtime agent contract."""

from __future__ import annotations

import asyncio
from pathlib import Path
import json

import pytest

from acreta.runtime.agent import AcretaAgent, _build_system_prompt


def test_system_prompt_enforces_parallel_explorer_contract() -> None:
    prompt = _build_system_prompt(["acreta"])
    assert "Task with Explore subagent" in prompt
    assert "add, update, or no-op" in prompt
    assert "project-first, then global fallback" in prompt
    assert "[[" not in prompt


def test_skill_tool_is_added_when_skills_enabled() -> None:
    agent = AcretaAgent(skills=["acreta"])
    assert "Skill" in agent.single_tools
    assert not hasattr(agent, "task_tools")


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


async def _fake_run_sdk_once(
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
    """Fake SDK run that writes expected artifacts for run() contract tests."""
    _ = (session_id, cwd, allowed_tools, permission_mode, add_dirs, env, hooks, agents)
    artifacts = _extract_artifacts_from_prompt(prompt)
    memory_root = _extract_memory_root_from_prompt(prompt)

    extract_path = Path(artifacts["extract"])
    extract_path.parent.mkdir(parents=True, exist_ok=True)
    extract_path.write_text("[]\n", encoding="utf-8")

    summary_path = Path(artifacts["summary"])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {"title": "Run summary", "summary": "Summary body"},
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    summary_memory_path = memory_root / "summaries" / "summary--s202602200001.md"
    summary_memory_path.parent.mkdir(parents=True, exist_ok=True)
    summary_memory_path.write_text(
        "---\nid: s202602200001\ntitle: Summary\n---\nSummary body\n", encoding="utf-8"
    )

    Path(artifacts["subagents_log"]).write_text(
        json.dumps(
            {
                "candidate_id": 0,
                "action_hint": "add",
                "matched_file": "",
                "evidence": "no strong match",
            },
            ensure_ascii=True,
        )
        + "\n",
        encoding="utf-8",
    )

    report = {
        "run_id": "run-1",
        "todos": [],
        "actions": [
            {
                "candidate_id": 0,
                "action": "add",
                "matched_file": "",
                "evidence": "no strong match",
            }
        ],
        "counts": {"add": 1, "update": 0, "no_op": 0},
        "written_memory_paths": [str(summary_memory_path)],
        "summary_path": str(summary_memory_path),
        "trace_path": "/tmp/trace.jsonl",
    }
    Path(artifacts["memory_actions"]).write_text(
        json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    return "ok", "session-1"


def test_memory_write_run_contract_creates_workspace_folder(tmp_path) -> None:
    trace_path = tmp_path / "session.jsonl"
    trace_path.write_text('{"role":"user","content":"hello"}\n', encoding="utf-8")

    agent = AcretaAgent(default_cwd=str(tmp_path))
    agent._run_sdk_once = _fake_run_sdk_once.__get__(agent, AcretaAgent)
    result = agent.run(trace_path)

    assert result["trace_path"] == str(trace_path.resolve())
    assert Path(result["run_folder"]).exists()
    assert Path(result["artifacts"]["extract"]).name == "extract.json"
    assert Path(result["summary_path"]).exists()


def test_memory_write_run_contract_fails_fast_on_missing_trace(tmp_path) -> None:
    agent = AcretaAgent(default_cwd=str(tmp_path))
    with pytest.raises(FileNotFoundError):
        agent.run(tmp_path / "missing.jsonl")


def test_memory_write_prompt_uses_trace_path_not_trace_content(tmp_path) -> None:
    trace_path = tmp_path / "session.jsonl"
    trace_payload = '{"role":"user","content":"NEVER_INLINE_THIS_TRACE_CONTENT"}\n'
    trace_path.write_text(trace_payload, encoding="utf-8")
    run_folder = tmp_path / "workspace" / "sync-20260220-120000-aaaaaa"
    artifact_paths = {
        "extract": run_folder / "extract.json",
        "summary": run_folder / "summary.json",
        "memory_actions": run_folder / "memory_actions.json",
        "agent_log": run_folder / "agent.log",
        "subagents_log": run_folder / "subagents.log",
        "session_log": run_folder / "session.log",
    }

    agent = AcretaAgent(default_cwd=str(tmp_path))
    prompt = agent._build_memory_write_prompt(
        trace_file=trace_path,
        memory_root=tmp_path / "memory",
        run_folder=run_folder,
        artifact_paths=artifact_paths,
        metadata={
            "run_id": "run-1",
            "trace_path": str(trace_path),
            "repo_name": "acreta",
        },
    )

    assert str(trace_path.resolve()) in prompt
    assert "NEVER_INLINE_THIS_TRACE_CONTENT" not in prompt


def test_pretool_write_hook_enforces_allowed_roots(tmp_path) -> None:
    memory_root = tmp_path / "memory"
    run_folder = tmp_path / "workspace" / "sync-1"
    allowed_target = memory_root / "learnings" / "entry.md"
    denied_target = tmp_path / "outside.md"
    agent = AcretaAgent(default_cwd=str(tmp_path))
    hooks = agent._build_pretool_hooks((memory_root, run_folder))
    callback = hooks["PreToolUse"][0].hooks[0]

    allowed_payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(allowed_target), "content": "ok"},
    }
    allowed_result = asyncio.run(callback(allowed_payload, None, None))
    assert allowed_result["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert allowed_result["hookSpecificOutput"]["updatedInput"]["file_path"] == str(
        allowed_target.resolve()
    )

    denied_payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(denied_target), "content": "no"},
    }
    denied_result = asyncio.run(callback(denied_payload, None, None))
    assert denied_result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert (
        "write_outside_allowed_roots"
        in denied_result["hookSpecificOutput"]["permissionDecisionReason"]
    )
