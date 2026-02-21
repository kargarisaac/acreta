"""Integration tests for agent-led memory write flow contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from acreta.config.settings import reload_config
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
    """Fake SDK execution that writes full artifact set for integration tests."""
    _ = (session_id, cwd, allowed_tools, permission_mode, add_dirs, env, hooks, agents)
    artifacts = _extract_artifacts_from_prompt(prompt)
    memory_root = _extract_memory_root_from_prompt(prompt)

    Path(artifacts["extract"]).write_text("[]\n", encoding="utf-8")

    summary_memory_path = memory_root / "summaries" / "summary--s202602200001.md"
    summary_memory_path.parent.mkdir(parents=True, exist_ok=True)
    summary_memory_path.write_text(
        "---\nid: s202602200001\ntitle: Summary\n---\nSummary body\n", encoding="utf-8"
    )
    Path(artifacts["summary"]).write_text(
        json.dumps(
            {"summary_path": str(summary_memory_path)}, ensure_ascii=True, indent=2
        )
        + "\n",
        encoding="utf-8",
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
        "actions": [],
        "counts": {"add": 1, "update": 0, "no_op": 0},
        "written_memory_paths": [str(summary_memory_path)],
        "summary_path": str(summary_memory_path),
        "trace_path": "/tmp/trace.jsonl",
    }
    Path(artifacts["memory_actions"]).write_text(
        json.dumps(report, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    return "ok", "session-1"


@pytest.mark.integration
def test_memory_write_sync_artifacts_and_summary_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Integration contract: run writes all workspace artifacts and summary path."""
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text('{"role":"user","content":"hello"}\n', encoding="utf-8")
    monkeypatch.setattr(AcretaAgent, "_run_sdk_once", _fake_run_sdk_once)

    agent = AcretaAgent(default_cwd=str(tmp_path))
    result = agent.run(trace_path)

    assert Path(result["artifacts"]["extract"]).exists()
    assert Path(result["artifacts"]["summary"]).exists()
    assert Path(result["artifacts"]["memory_actions"]).exists()
    assert Path(result["artifacts"]["subagents_log"]).exists()
    assert "/summaries/" in result["summary_path"]
    assert Path(result["summary_path"]).exists()


@pytest.mark.integration
def test_session_persistence_toggle_scopes_claude_config_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Integration contract: CLAUDE_CONFIG_DIR is injected only when toggle is enabled."""
    monkeypatch.setenv("ACRETA_PERSIST_SESSIONS_IN_WORKSPACE", "1")
    reload_config()
    enabled_agent = AcretaAgent(default_cwd=str(tmp_path))
    enabled_env = enabled_agent._runtime_env(tmp_path)
    assert enabled_env["CLAUDE_CONFIG_DIR"] == str(
        (tmp_path / ".acreta" / "workspace" / ".claude").resolve()
    )

    monkeypatch.setenv("ACRETA_PERSIST_SESSIONS_IN_WORKSPACE", "0")
    reload_config()
    disabled_agent = AcretaAgent(default_cwd=str(tmp_path))
    assert disabled_agent._runtime_env(tmp_path) == {}
