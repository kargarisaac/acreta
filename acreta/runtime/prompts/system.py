"""System prompt builder for the AcretaAgent lead orchestrator."""

from __future__ import annotations


def build_system_prompt(skills: list[str] | None = None) -> str:
    """Build minimal lead-agent system prompt."""
    skills_section = ""
    if skills:
        skills_section = "\nSkills:\n" + "\n".join(f"- {item}" for item in skills)
    return f"""\
You are AcretaAgent, the lead memory orchestrator.
Rules:
- Lead agent is the only writer and final decider.
- Decisions must be explicit: add, update, or no-op.
- Use TodoWrite for checklist lifecycle.
- Use Task with Explore subagent for read-only memory matching.
- Search project-first, then global fallback.
- Never emit wikilink syntax.
- Keep outputs concise and structured.{skills_section}"""


if __name__ == "__main__":
    prompt = build_system_prompt(["acreta"])
    assert "Task with Explore subagent" in prompt
    assert "add, update, or no-op" in prompt
    assert "project-first, then global fallback" in prompt
    assert "[[" not in prompt
    assert "acreta" in prompt

    prompt_no_skills = build_system_prompt()
    assert "Skills:" not in prompt_no_skills
