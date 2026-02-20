"""Minimal Claude Agent SDK runtime for Acreta chat and memory-write flows."""

from __future__ import annotations

import asyncio
import json
import secrets
import shlex
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from acreta.config.settings import get_config
from acreta.runtime.providers import ProviderConfig, apply_provider_env, get_provider_config, resolve_model

RunMode = Literal["hot", "cold", "sync"]

READ_ONLY_TOOLS = ["Read", "Grep", "Glob", "Task"]
MEMORY_WRITE_TOOLS = ["Read", "Grep", "Glob", "Write", "Edit", "Bash", "Task", "TodoWrite"]


def _default_run_folder_name(run_mode: RunMode) -> str:
    """Build deterministic per-run workspace folder name."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{run_mode}-{stamp}-{secrets.token_hex(3)}"


def _build_system_prompt(skills: list[str] | None = None) -> str:
    """Build minimal lead-agent system prompt."""
    skills_section = ""
    if skills:
        skills_section = "\nSkills:\n" + "\n".join(f"- {item}" for item in skills)
    return (
        "You are AcretaAgent, the lead memory orchestrator.\n"
        "Rules:\n"
        "- Lead agent is the only writer and final decider.\n"
        "- Decisions must be explicit: add, update, or no-op.\n"
        "- Use TodoWrite for checklist lifecycle.\n"
        "- Use Task with Explore subagent for read-only memory matching.\n"
        "- Search project-first, then global fallback.\n"
        "- Never emit wikilink syntax.\n"
        "- Keep outputs concise and structured." + skills_section
    )


def _run_coroutine_sync(coro: Any) -> Any:
    """Run a coroutine in sync context, including active-loop fallback."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


def _build_artifact_paths(run_folder: Path) -> dict[str, Path]:
    """Return canonical workspace artifact paths for one run folder."""
    return {
        "extract": run_folder / "extract.json",
        "summary": run_folder / "summary.json",
        "memory_actions": run_folder / "memory_actions.json",
        "agent_log": run_folder / "agent.log",
        "subagents_log": run_folder / "subagents.log",
        "session_log": run_folder / "session.log",
    }


class AcretaAgent:
    """Thin runtime wrapper around Claude Agent SDK with one memory-write flow."""

    def __init__(
        self,
        model: str | None = None,
        provider: str | None = None,
        skills: list[str] | None = None,
        timeout_seconds: int | None = None,
        single_tools: list[str] | None = None,
        allowed_read_dirs: list[str | Path] | None = None,
        default_cwd: str | None = None,
    ) -> None:
        """Create runtime with provider/model resolution and chat tool config."""
        config = get_config()
        model_alias = model if model is not None else config.agent_model
        self.provider_config: ProviderConfig = get_provider_config(provider)
        self.model = resolve_model(model_alias, self.provider_config)
        self.skills = list(skills or [])
        self.system_prompt = _build_system_prompt(self.skills)
        self.single_tools = list(single_tools) if single_tools is not None else list(READ_ONLY_TOOLS)
        if self.skills and "Skill" not in self.single_tools:
            self.single_tools.append("Skill")
        self._allowed_read_dirs = [Path(path).expanduser().resolve() for path in (allowed_read_dirs or [])]
        self._default_cwd = default_cwd
        self._timeout_seconds = timeout_seconds if timeout_seconds and timeout_seconds > 0 else config.agent_timeout
        self._persist_sessions_in_workspace = bool(config.persist_sessions_in_workspace)

    @staticmethod
    def generate_session_id() -> str:
        """Generate a random session identifier."""
        return f"acreta-{secrets.token_hex(6)}"

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        """Return whether ``path`` is equal to or inside ``root``."""
        resolved = path.resolve()
        root_resolved = root.resolve()
        return resolved == root_resolved or root_resolved in resolved.parents

    @staticmethod
    def _dedupe_dirs(paths: list[Path]) -> list[str]:
        """Return unique directory list for SDK add_dirs option."""
        deduped: list[str] = []
        for path in paths:
            candidate = path if path.is_dir() else path.parent
            value = str(candidate.resolve())
            if value not in deduped:
                deduped.append(value)
        return deduped

    def _runtime_env(self, runtime_cwd: Path) -> dict[str, str]:
        """Build SDK process env additions for this runtime invocation."""
        if not self._persist_sessions_in_workspace:
            return {}
        return {"CLAUDE_CONFIG_DIR": str((runtime_cwd / ".acreta" / "workspace" / ".claude").resolve())}

    def _build_pretool_hooks(self, allowed_roots: tuple[Path, ...]) -> dict[str, list[Any]]:
        """Build PreToolUse hook config that denies Write/Edit outside allowed roots."""
        from claude_agent_sdk import HookMatcher

        async def _pretool_guard(input_data: dict[str, Any], _tool_use_id: str | None, _context: Any) -> dict[str, Any]:
            tool_input = input_data.get("tool_input") or {}
            raw_path = tool_input.get("file_path")
            if not raw_path:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "missing_file_path_for_write",
                    }
                }
            resolved = Path(str(raw_path)).expanduser().resolve()
            if any(self._is_within(resolved, root) for root in allowed_roots):
                updated_input = dict(tool_input)
                updated_input["file_path"] = str(resolved)
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                        "updatedInput": updated_input,
                    }
                }
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"write_outside_allowed_roots:{resolved}",
                }
            }

        return {"PreToolUse": [HookMatcher(matcher="Write|Edit", hooks=[_pretool_guard])]}

    async def _run_sdk_once(
        self,
        *,
        prompt: str,
        session_id: str | None,
        cwd: str | None,
        allowed_tools: list[str],
        permission_mode: str,
        add_dirs: tuple[Path, ...] = (),
        env: dict[str, str] | None = None,
        hooks: dict[str, list[Any]] | None = None,
        agents: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Execute one prompt via Claude Agent SDK and return response + session id."""
        from claude_agent_sdk import ClaudeAgentOptions, query
        from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock

        apply_provider_env(self.provider_config)
        runtime_cwd = Path(cwd or self._default_cwd or str(Path.cwd())).expanduser().resolve()
        option_kwargs: dict[str, Any] = {
            "system_prompt": self.system_prompt,
            "allowed_tools": allowed_tools,
            "model": self.model,
            "cwd": str(runtime_cwd),
            "permission_mode": permission_mode,
            "add_dirs": self._dedupe_dirs([runtime_cwd, *self._allowed_read_dirs, *add_dirs]),
        }
        if env:
            option_kwargs["env"] = {str(key): str(value) for key, value in env.items()}
        if hooks:
            option_kwargs["hooks"] = hooks
        if agents:
            option_kwargs["agents"] = agents
        if "Skill" in allowed_tools:
            option_kwargs["setting_sources"] = ["user", "project"]

        parts: list[str] = []
        resolved_session_id = session_id or self.generate_session_id()
        async for message in query(prompt=prompt, options=ClaudeAgentOptions(**option_kwargs)):
            if isinstance(message, AssistantMessage):
                parts.extend(block.text for block in message.content if isinstance(block, TextBlock))
            elif isinstance(message, ResultMessage):
                if message.session_id:
                    resolved_session_id = message.session_id
                if message.result and not parts:
                    parts.append(message.result)
        return ("".join(parts).strip() or "(no response)"), resolved_session_id

    def _run_sdk_sync(
        self,
        *,
        prompt: str,
        session_id: str | None,
        cwd: str | None,
        allowed_tools: list[str],
        permission_mode: str,
        add_dirs: tuple[Path, ...] = (),
        env: dict[str, str] | None = None,
        hooks: dict[str, list[Any]] | None = None,
        agents: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Synchronous wrapper around one SDK run with timeout."""
        return _run_coroutine_sync(
            asyncio.wait_for(
                self._run_sdk_once(
                    prompt=prompt,
                    session_id=session_id,
                    cwd=cwd,
                    allowed_tools=allowed_tools,
                    permission_mode=permission_mode,
                    add_dirs=add_dirs,
                    env=env,
                    hooks=hooks,
                    agents=agents,
                ),
                timeout=self._timeout_seconds,
            )
        )

    def _build_memory_write_prompt(
        self,
        *,
        trace_file: Path,
        memory_root: Path,
        run_folder: Path,
        artifact_paths: dict[str, Path],
        metadata: dict[str, str],
    ) -> str:
        """Build lead-agent prompt for the memory write flow."""
        metadata_json = json.dumps(metadata, ensure_ascii=True)
        artifact_json = json.dumps({key: str(path) for key, path in artifact_paths.items()}, ensure_ascii=True)
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
            f"--metadata-json {shlex.quote(metadata_json)} "
            "--metrics-json '{}'"
        )
        return (
            "Run the Acreta agent-led memory write flow.\n\n"
            "Inputs:\n"
            f"- trace_path: {trace_file}\n"
            f"- memory_root_path: {memory_root}\n"
            f"- run_folder_path: {run_folder}\n"
            f"- artifact_paths_json: {artifact_json}\n\n"
            "Checklist (must use TodoWrite and move statuses from pending -> in_progress -> completed):\n"
            "- validate_inputs\n- run_extract_pipeline\n- run_summary_pipeline\n- run_explorer_checks\n"
            "- decide_add_update_no_op\n- write_memory_files\n- write_run_decision_report\n\n"
            "Execution rules:\n"
            "- Do not inline or normalize trace content. Use only trace_path file access.\n"
            "- Use Bash to run DSPy pipelines:\n"
            f"  1) {extract_cmd}\n"
            f"  2) {summary_cmd}\n"
            "- Read extract.json and summary.json from artifact paths.\n"
            "- For candidate matching, use Task with built-in Explore subagent first. If unavailable, use Task with `explore-reader`.\n"
            "- Explorer subagents are read-only and must return: candidate_id, action_hint, matched_file, evidence.\n"
            "- Lead agent is the only writer and final decider.\n"
            "- Deterministic decision policy for non-summary candidates:\n"
            "  - no_op when matched memory has exact same primitive + title + body.\n"
            "  - update when primitive matches and token-overlap score >= 0.72.\n"
            "  - add otherwise.\n"
            "- Summary is always add and always written to memory_root/summaries/.\n"
            "- Write/update markdown memory files with YAML frontmatter in memory_root/decisions, memory_root/learnings, memory_root/summaries.\n"
            f"- Write explorer outputs to {artifact_paths['subagents_log']} as JSONL.\n"
            f"- Write run report JSON to {artifact_paths['memory_actions']} with keys: run_id, todos, actions, counts, written_memory_paths, summary_path, trace_path.\n"
            "- Include overlap score evidence in actions when action is update/no_op.\n"
            "- counts keys must be: add, update, no_op.\n"
            "- Every written/updated file path must be absolute.\n\n"
            "Return one short plain-text completion line."
        )

    def run_sync(
        self,
        prompt: str,
        session_id: str | None = None,
        cwd: str | None = None,
    ) -> tuple[str, str]:
        """Run one chat/read prompt in synchronous mode."""
        runtime_cwd = Path(cwd or self._default_cwd or str(Path.cwd())).expanduser().resolve()
        return self._run_sdk_sync(
            prompt=prompt,
            session_id=session_id,
            cwd=str(runtime_cwd),
            allowed_tools=self.single_tools,
            permission_mode="acceptEdits",
            env=self._runtime_env(runtime_cwd),
        )

    def run(
        self,
        trace_path: str | Path,
        memory_root: str | Path | None = None,
        workspace_root: str | Path | None = None,
        run_mode: RunMode = "sync",
    ) -> dict[str, Any]:
        """Run lead memory-write flow using trace-path input and SDK orchestration."""
        if run_mode not in {"hot", "cold", "sync"}:
            raise ValueError(f"invalid_run_mode:{run_mode}")
        trace_file = Path(trace_path).expanduser().resolve()
        if not trace_file.exists() or not trace_file.is_file():
            raise FileNotFoundError(f"trace_path_missing:{trace_file}")

        repo_root = Path(self._default_cwd or Path.cwd()).expanduser().resolve()
        resolved_memory_root = Path(memory_root).expanduser().resolve() if memory_root else (repo_root / ".acreta" / "memory")
        resolved_workspace_root = (
            Path(workspace_root).expanduser().resolve() if workspace_root else (repo_root / ".acreta" / "workspace")
        )
        run_folder = resolved_workspace_root / _default_run_folder_name(run_mode)
        run_folder.mkdir(parents=True, exist_ok=True)
        artifact_paths = _build_artifact_paths(run_folder)
        metadata = {"run_id": run_folder.name, "trace_path": str(trace_file), "repo_name": repo_root.name, "run_mode": run_mode}
        artifact_paths["session_log"].write_text(json.dumps(metadata, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

        prompt = self._build_memory_write_prompt(
            trace_file=trace_file,
            memory_root=resolved_memory_root,
            run_folder=run_folder,
            artifact_paths=artifact_paths,
            metadata=metadata,
        )
        hooks = self._build_pretool_hooks((resolved_memory_root, run_folder))
        tools = list(MEMORY_WRITE_TOOLS)
        if self.skills and "Skill" not in tools:
            tools.append("Skill")
        from claude_agent_sdk import AgentDefinition

        agents = {
            "explore-reader": AgentDefinition(
                description="Read-only memory explorer for candidate matching evidence.",
                prompt="Return JSONL-style evidence with fields: candidate_id, action_hint, matched_file, evidence.",
                tools=["Read", "Grep", "Glob"],
                model="inherit",
            )
        }
        response, _ = self._run_sdk_sync(
            prompt=prompt,
            session_id=self.generate_session_id(),
            cwd=str(repo_root),
            allowed_tools=tools,
            permission_mode="acceptEdits",
            add_dirs=(resolved_memory_root, resolved_workspace_root, run_folder, trace_file.parent),
            env=self._runtime_env(repo_root),
            hooks=hooks,
            agents=agents,
        )
        artifact_paths["agent_log"].write_text((response if response.endswith("\n") else f"{response}\n"), encoding="utf-8")

        for key in ("extract", "summary", "memory_actions", "subagents_log"):
            if not artifact_paths[key].exists():
                raise RuntimeError(f"missing_artifact:{artifact_paths[key]}")
        try:
            report = json.loads(artifact_paths["memory_actions"].read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid_json_artifact:{artifact_paths['memory_actions']}") from exc
        if not isinstance(report, dict):
            raise RuntimeError(f"invalid_report_shape:{artifact_paths['memory_actions']}")

        counts_raw = report.get("counts") if isinstance(report.get("counts"), dict) else {}
        counts = {
            "add": int(counts_raw.get("add") or 0),
            "update": int(counts_raw.get("update") or 0),
            "no_op": int(counts_raw.get("no_op") or counts_raw.get("no-op") or 0),
        }
        written_memory_paths = [str(item) for item in (report.get("written_memory_paths") or []) if isinstance(item, str) and item]
        summary_path = str(report.get("summary_path") or "").strip()
        if not summary_path:
            raise RuntimeError("missing_summary_path_in_report")

        return {
            "trace_path": str(trace_file),
            "memory_root": str(resolved_memory_root),
            "workspace_root": str(resolved_workspace_root),
            "run_mode": run_mode,
            "run_folder": str(run_folder),
            "artifacts": {key: str(path) for key, path in artifact_paths.items()},
            "counts": counts,
            "written_memory_paths": written_memory_paths,
            "summary_path": summary_path,
        }


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    agent = AcretaAgent(skills=["acreta"])
    assert agent.generate_session_id().startswith("acreta-")
    assert "Task with Explore subagent" in agent.system_prompt
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        trace_file = root / "trace.jsonl"
        trace_file.write_text('{"role":"user","content":"hello"}\n', encoding="utf-8")
        run_folder = root / "workspace" / "sync-selftest"
        prompt = agent._build_memory_write_prompt(
            trace_file=trace_file,
            memory_root=root / "memory",
            run_folder=run_folder,
            artifact_paths=_build_artifact_paths(run_folder),
            metadata={"run_id": "sync-selftest", "trace_path": str(trace_file), "repo_name": "acreta", "run_mode": "sync"},
        )
        assert "artifact_paths_json" in prompt
