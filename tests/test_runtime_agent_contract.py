"""test runtime agent contract."""

from __future__ import annotations

from acreta.runtime.agent import AcretaAgent, _build_system_prompt


def test_system_prompt_enforces_parallel_explorer_contract() -> None:
    prompt = _build_system_prompt(["acreta"])
    assert "parallel read-only Task explorers" in prompt
    assert "add, update, or no-op" in prompt
    assert "project-first, then global fallback" in prompt
    assert "[[" not in prompt


def test_skill_tool_is_added_when_skills_enabled() -> None:
    agent = AcretaAgent(skills=["acreta"])
    assert "Skill" in agent.single_tools
    assert "Skill" in agent.task_tools
    assert not hasattr(agent, "plan_tools")
