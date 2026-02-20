"""Lead agent runtime wrapper around Claude Agent SDK execution."""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path
from typing import Literal

from acreta.config.settings import get_config
from acreta.runtime.providers import (
    ProviderConfig,
    apply_provider_env,
    get_provider_config,
    resolve_model,
)


ExecutionMode = Literal["single"]
ToolProfile = Literal["read_only", "workspace_write", "full_ops"]

_TOOL_PROFILE_TOOLS: dict[ToolProfile, list[str]] = {
    "read_only": ["Read", "Grep", "Glob", "Task"],
    "workspace_write": ["Read", "Grep", "Glob", "Write", "Edit", "Task"],
    "full_ops": ["Read", "Write", "Edit", "Bash", "Grep", "Glob", "Task"],
}


def _default_tools_for_profile(profile: ToolProfile) -> list[str]:
    """Return a copy of default allowed tools for a tool profile."""
    return list(_TOOL_PROFILE_TOOLS[profile])


def _build_system_prompt(skills: list[str] | None = None) -> str:
    """Build the orchestration system prompt, optionally appending skill hints."""
    skills_section = ""
    if skills:
        lines = "\n".join(f"- {item}" for item in skills)
        skills_section = f"\nSkills:\n{lines}"
    return (
        "You are AcretaAgent, the lead orchestrator for memory extraction and retrieval.\n"
        "Lead authority rules:\n"
        "- Lead agent is the only writer and final decider.\n"
        "- Lead decisions must be explicit: add, update, or no-op.\n"
        "- Delegate retrieval to parallel read-only Task explorers.\n"
        "- Choose Task fan-out dynamically by candidate count and uncertainty.\n"
        "- Explorer subagents must return evidence-first outputs with file paths/line refs.\n"
        "- Search project-first, then global fallback.\n"
        "- Never emit wikilink syntax. Use explicit ids/slugs in `related` fields.\n"
        "Use bounded reads. Do not request full transcript dumps.\n"
        "Return concise, structured outputs." + skills_section
    )


class AcretaAgent:
    """Thin orchestration wrapper for SDK-based agent execution."""

    def __init__(
        self,
        model: str | None = None,
        provider: str | None = None,
        skills: list[str] | None = None,
        timeout_seconds: int | None = None,
        output_format: str | None = None,
        json_schema: dict | str | None = None,
        execution_mode: ExecutionMode = "single",
        single_tools: list[str] | None = None,
        tool_profile: ToolProfile = "read_only",
        workflow: str = "generic",
        purpose: str = "generic",
        allowed_read_dirs: list[str | Path] | None = None,
        allowed_subagents: list[str] | None = None,
        subagents: dict[str, dict] | None = None,
        default_cwd: str | None = None,
    ) -> None:
        """Create an agent runtime with provider/model/tool/profile configuration."""
        config = get_config()
        model_alias = model if model is not None else config.agent_model
        self.provider_config: ProviderConfig = get_provider_config(provider)
        self.model = resolve_model(model_alias, self.provider_config)
        self.skills = skills or []
        self.system_prompt = _build_system_prompt(skills)
        self.execution_mode: ExecutionMode = execution_mode
        self.tool_profile: ToolProfile = tool_profile
        self.workflow = workflow
        self.purpose = purpose
        self._allowed_read_dirs = [Path(path).expanduser() for path in (allowed_read_dirs or [])]
        self.subagents = dict(subagents or {})
        if allowed_subagents is None:
            self.allowed_subagents = ["Explore", "general-purpose"]
        else:
            self.allowed_subagents = list(allowed_subagents)
        self.single_tools = list(single_tools) if single_tools is not None else _default_tools_for_profile(tool_profile)
        self.task_tools = list(self.single_tools)
        if self.skills:
            for tool_list in (self.single_tools, self.task_tools):
                if "Skill" not in tool_list:
                    tool_list.append("Skill")
        self._default_cwd = default_cwd
        self._timeout_seconds = timeout_seconds if timeout_seconds and timeout_seconds > 0 else config.agent_timeout
        self._output_format = output_format
        self._json_schema = json_schema

    @staticmethod
    def generate_session_id() -> str:
        """Generate a random session identifier for SDK calls."""
        return f"acreta-{secrets.token_hex(6)}"

    def _apply_output_constraints(self, prompt: str) -> str:
        """Append JSON-only output constraints when structured mode is requested."""
        if self._output_format != "json":
            return prompt
        sections = [
            prompt,
            "",
            "Output constraints:",
            "- Return valid JSON only.",
            "- Do not wrap JSON in markdown fences.",
        ]
        if self._json_schema:
            schema = self._json_schema
            if not isinstance(schema, str):
                schema = json.dumps(schema, ensure_ascii=True)
            sections.extend(["- Match this JSON schema exactly:", schema])
        return "\n".join(sections)

    @staticmethod
    def _sdk_add_dirs(paths: tuple[Path, ...]) -> list[str]:
        """Convert readable path set to unique directory strings for SDK options."""
        normalized: list[str] = []
        for path in paths:
            candidate = path if path.is_dir() else path.parent
            entry = str(candidate)
            if entry not in normalized:
                normalized.append(entry)
        return normalized

    async def _run_sdk(
        self,
        prompt: str,
        session_id: str,
        cwd: str | None,
        *,
        permission_mode: str,
        allowed_tools: list[str],
    ) -> tuple[str, str]:
        """Execute one prompt via Claude Agent SDK and return text + session id."""
        session_id = session_id or self.generate_session_id()
        apply_provider_env(self.provider_config)
        runtime_cwd = Path(cwd or self._default_cwd or str(Path.home())).expanduser().resolve()

        try:
            from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
            from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock
        except ImportError:
            return (
                "Claude Agent SDK is not installed. Install with: pip install claude-agent-sdk",
                session_id,
            )

        allowed_dirs = tuple([runtime_cwd, *self._allowed_read_dirs])

        options_kwargs: dict[str, object] = {
            "system_prompt": self.system_prompt,
            "allowed_tools": allowed_tools,
            "model": self.model,
            "cwd": str(runtime_cwd),
            "permission_mode": permission_mode,
            "add_dirs": self._sdk_add_dirs(allowed_dirs),
            "extra_args": {"no-session-persistence": None},
        }
        if self.subagents:
            agents_payload: dict[str, object] = {}
            try:
                from claude_agent_sdk import AgentDefinition

                for name, spec in self.subagents.items():
                    if isinstance(spec, AgentDefinition):
                        agents_payload[name] = spec
                        continue
                    if not isinstance(spec, dict):
                        continue
                    agents_payload[name] = AgentDefinition(
                        description=str(spec.get("description") or name),
                        prompt=str(spec.get("prompt") or ""),
                        tools=[str(item) for item in (spec.get("tools") or []) if str(item).strip()],
                        model=(str(spec.get("model")) if spec.get("model") else None),
                    )
            except Exception:
                for name, spec in self.subagents.items():
                    if isinstance(spec, dict):
                        agents_payload[name] = spec

            if agents_payload:
                options_kwargs["agents"] = agents_payload
        options = ClaudeAgentOptions(**options_kwargs)

        client = ClaudeSDKClient(options)
        try:
            await client.connect()
            await client.query(prompt, session_id=session_id or "default")
            response_parts: list[str] = []
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_parts.append(block.text)
                elif isinstance(message, ResultMessage):
                    if message.result and not response_parts:
                        response_parts.append(message.result)
            return "".join(response_parts) or "(no response)", session_id
        except Exception as exc:
            return f"Agent error: {exc}", session_id
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def run(
        self,
        prompt: str,
        session_id: str | None = None,
        cwd: str | None = None,
    ) -> tuple[str, str]:
        """Run one prompt asynchronously with configured timeout and tool profile."""
        session_id = session_id or self.generate_session_id()
        prepared_prompt = self._apply_output_constraints(prompt)
        return await asyncio.wait_for(
            self._run_sdk(
                prepared_prompt,
                session_id,
                cwd,
                permission_mode="bypassPermissions",
                allowed_tools=self.single_tools,
            ),
            timeout=self._timeout_seconds,
        )

    def run_sync(
        self,
        prompt: str,
        session_id: str | None = None,
        cwd: str | None = None,
    ) -> tuple[str, str]:
        """Run one prompt synchronously, including active event-loop fallback."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run(prompt, session_id=session_id, cwd=cwd))

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, self.run(prompt, session_id=session_id, cwd=cwd)).result()


if __name__ == "__main__":
    agent = AcretaAgent(skills=["acreta"])
    session_id = agent.generate_session_id()
    assert session_id.startswith("acreta-")
    assert "Lead authority rules" in agent.system_prompt
