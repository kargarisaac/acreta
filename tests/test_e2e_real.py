"""Real-path end-to-end coverage for chat and extract pipeline flows."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from acreta.config.settings import reload_config
from acreta.memory import extract_pipeline as pipeline
from acreta.sessions import catalog
from tests.helpers import run_cli


def _sdk_available() -> bool:
    try:
        from claude_agent_sdk import ClaudeSDKClient  # noqa: F401
        return True
    except ImportError:
        return False


_HAS_SDK = _sdk_available()
_HAS_ZAI = bool(os.environ.get("ZAI_API_KEY"))
_HAS_OPENAI = bool(os.environ.get("OPENAI_API_KEY"))


@pytest.mark.e2e
@pytest.mark.agent
@unittest.skipUnless(
    _HAS_SDK and _HAS_ZAI and _HAS_OPENAI and os.environ.get("ACRETA_E2E", ""),
    "Set ACRETA_E2E=1 with ZAI_API_KEY and OPENAI_API_KEY to run E2E tests",
)
class TestE2EReal(unittest.TestCase):
    def test_chat_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env = {
                "ACRETA_DATA_DIR": str(tmp_path),
                "ACRETA_MEMORY_DIR": str(tmp_path / "memory"),
                "ACRETA_INDEX_DIR": str(tmp_path / "index"),
                "ACRETA_PROVIDER": "zai",
                "ACRETA_MODEL": "glm-4.7-flash",
                "ACRETA_EMBEDDINGS_PROVIDER": "openai",
                "ACRETA_EMBEDDING_MODEL": "text-embedding-3-small",
                "ACRETA_AGENT_TIMEOUT": "120",
            }
            with patch.dict(os.environ, env, clear=False):
                reload_config()
                exit_code, output = run_cli(["chat", "Respond with exactly: OK"])

        self.assertEqual(exit_code, 0)
        self.assertIn("OK", output)
        self.assertGreater(len(output.strip()), 0)


def test_extract_pipeline_end_to_end_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = {
        "ACRETA_DATA_DIR": str(tmp_path),
        "ACRETA_MEMORY_DIR": str(tmp_path / "memory"),
        "ACRETA_INDEX_DIR": str(tmp_path / "index"),
        "ACRETA_SESSIONS_DB": str(tmp_path / "index" / "sessions.sqlite3"),
        "ACRETA_MEMORY_SCOPE": "global_only",
    }
    with patch.dict(os.environ, env, clear=False):
        reload_config()
        catalog.init_sessions_db()
        session_path = tmp_path / "sessions" / "run-e2e-1.jsonl"
        session_path.parent.mkdir(parents=True, exist_ok=True)
        session_path.write_text(
            '{"role":"user","content":"keep queue lifecycle stable"}\n'
            '{"role":"assistant","content":"implemented heartbeat handling"}\n',
            encoding="utf-8",
        )
        catalog.index_session_for_fts(
            run_id="run-e2e-1",
            agent_type="codex",
            content="user asked for queue stability",
            session_path=str(session_path),
        )

        monkeypatch.setattr(
            pipeline,
            "extract_memories_from_session_file",
            lambda *_args, **_kwargs: [
                {
                    "primitive": "learning",
                    "title": "Queue lifecycle contract",
                    "body": "Keep enqueue, claim, heartbeat, complete, and fail states consistent.",
                    "confidence": 0.9,
                    "kind": "pattern",
                    "related": ["queue-lifecycle"],
                    "projects": ["acreta"],
                    "agent_types": ["codex"],
                    "signal_sources": ["user_agent", "tool_runtime"],
                    "evidence": [],
                }
            ],
        )
        result = pipeline.extract_session_memories("run-e2e-1", no_llm=False)

    assert result["status"] == "completed"
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["title"] == "Queue lifecycle contract"


if __name__ == "__main__":
    unittest.main()
