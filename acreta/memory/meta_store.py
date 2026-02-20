"""Sidecar metadata persistence for learning state and evidence files."""

from __future__ import annotations

import json
from pathlib import Path

from acreta.memory.models import EvidenceMeta, Learning, StateMeta


class MetaStore:
    """Read/write helper for per-learning state/evidence JSON sidecars."""

    def __init__(self, meta_dir: Path) -> None:
        """Create state and evidence directories under ``meta_dir``."""
        self.meta_dir = meta_dir
        self.state_dir = meta_dir / "state"
        self.evidence_dir = meta_dir / "evidence"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self, memory_id: str) -> Path:
        """Return state sidecar path for a memory ID."""
        return self.state_dir / f"{memory_id}.json"

    def _evidence_path(self, memory_id: str) -> Path:
        """Return evidence sidecar path for a memory ID."""
        return self.evidence_dir / f"{memory_id}.json"

    def write_from_learning(self, learning: Learning) -> None:
        """Write both state and evidence sidecars from a learning record."""
        state = StateMeta.from_learning(learning)
        evidence = EvidenceMeta.from_learning(learning)
        self._state_path(learning.id).write_text(
            json.dumps(state.model_dump(mode="json"), ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
        self._evidence_path(learning.id).write_text(
            json.dumps(evidence.model_dump(mode="json"), ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def load_into_learning(self, learning: Learning) -> Learning:
        """Hydrate a learning record from available sidecar files."""
        state_path = self._state_path(learning.id)
        if state_path.exists():
            try:
                payload = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict):
                try:
                    state = StateMeta(**payload)
                    learning = state.apply_to_learning(learning)
                except Exception:
                    pass

        evidence_path = self._evidence_path(learning.id)
        if evidence_path.exists():
            try:
                payload = json.loads(evidence_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict):
                try:
                    evidence = EvidenceMeta(**payload)
                    learning = evidence.apply_to_learning(learning)
                except Exception:
                    pass
        return learning

    def delete(self, memory_id: str) -> None:
        """Delete all sidecar files for a memory ID."""
        self._state_path(memory_id).unlink(missing_ok=True)
        self._evidence_path(memory_id).unlink(missing_ok=True)


if __name__ == "__main__":
    """Run a real-path smoke test for sidecar write/load/delete flow."""
    from tempfile import TemporaryDirectory

    from acreta.memory.models import PrimitiveType

    with TemporaryDirectory() as tmp_dir:
        store = MetaStore(Path(tmp_dir) / "meta")
        learning = Learning(
            id="l202602190001",
            title="Meta store smoke test",
            body="verify sidecar persistence",
            primitive=PrimitiveType.learning,
        )
        store.write_from_learning(learning)
        assert (store.state_dir / f"{learning.id}.json").exists()
        assert (store.evidence_dir / f"{learning.id}.json").exists()
        loaded = store.load_into_learning(learning)
        assert loaded.id == learning.id
        store.delete(learning.id)
        assert not (store.state_dir / f"{learning.id}.json").exists()
        assert not (store.evidence_dir / f"{learning.id}.json").exists()
