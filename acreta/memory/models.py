"""Core memory domain models, markdown serialization, and sidecar metadata types."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from enum import Enum

import yaml
from pydantic import BaseModel, Field


class PrimitiveType(str, Enum):
    """Top-level memory primitive folder types."""

    decision = "decision"
    learning = "learning"
    convention = "convention"
    context = "context"


class LearningType(str, Enum):
    """Learning subtype taxonomy."""

    insight = "insight"
    procedure = "procedure"
    friction = "friction"
    pitfall = "pitfall"
    preference = "preference"


class LifecycleState(str, Enum):
    """Lifecycle state machine for memory confidence and curation."""

    candidate = "candidate"
    validated = "validated"
    established = "established"
    stale = "stale"
    archived = "archived"


class EvidenceItem(BaseModel):
    """Evidence snippet linked to a learning from a source session."""

    session_id: str
    snippet: str = ""
    timestamp: str | None = None
    source_path: str | None = None
    source_type: str = "message"
    source_ref: str | None = None
    outcome: str = "unknown"


class Learning(BaseModel):
    """Canonical memory record persisted as markdown + sidecar metadata."""

    id: str
    title: str
    body: str = ""
    primitive: PrimitiveType = PrimitiveType.learning
    kind: str = "insight"
    status: str = "active"
    decided_by: str = "agent"
    scope: str = "project"
    area: str = "general"
    related: list[str] = Field(default_factory=list)
    learning_type: LearningType = LearningType.insight
    lifecycle_state: LifecycleState = LifecycleState.candidate
    confidence: float = 0.7
    occurrences: int = 1
    source_sessions: list[str] = Field(default_factory=list)
    agent_types: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    content_hash: str | None = None
    useful_count: int = 0
    not_useful_count: int = 0
    evidence: list[EvidenceItem] = Field(default_factory=list)
    signal_sources: list[str] = Field(default_factory=list)
    durability_score: float = 0.5
    volatility: str = "medium"
    last_validated_at: datetime | None = None
    version_of: str | None = None
    supersedes: list[str] = Field(default_factory=list)
    created: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def _normalize_text(value: str) -> str:
        """Normalize line endings and trim trailing whitespace."""
        text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
        return "\n".join(line.rstrip() for line in text.split("\n")).strip()

    @staticmethod
    def _normalize_list(values: list[str]) -> list[str]:
        """Lowercase, trim, deduplicate, and sort list values."""
        cleaned = [str(item).strip().lower() for item in values if str(item).strip()]
        return sorted(set(cleaned))

    @property
    def primitive_type(self) -> PrimitiveType:
        """Backward-compatible alias for ``primitive``."""
        return self.primitive

    @property
    def state(self) -> str:
        """Backward-compatible alias for ``lifecycle_state.value``."""
        return self.lifecycle_state.value

    @staticmethod
    def slugify(value: str) -> str:
        """Generate a filesystem-safe ASCII slug from text."""
        raw = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", raw.strip().lower()).strip("-")
        return cleaned or "memory"

    def filename(self) -> str:
        """Return canonical markdown filename for this learning."""
        return f"{self.slugify(self.title)}--{self.id}.md"

    def primitive_dirname(self) -> str:
        """Return primitive folder name for markdown storage."""
        return f"{self.primitive.value}s"

    def resolve_related_ids(self) -> list[str]:
        """Return cleaned explicit related reference IDs/slugs."""
        return [str(value).strip() for value in self.related if str(value).strip()]

    def compute_content_hash(self) -> str:
        """Compute stable content hash used for dedupe and consolidation."""
        payload = {
            "primitive": self.primitive.value,
            "title": self._normalize_text(self.title).lower(),
            "body": self._normalize_text(self.body),
            "kind": self.kind,
            "status": self.status,
            "decided_by": self.decided_by,
            "scope": self.scope,
            "area": self.area,
            "tags": self._normalize_list(self.tags),
            "related": self._normalize_list(self.related),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def ensure_content_hash(self) -> str:
        """Populate missing ``content_hash`` and return it."""
        if not self.content_hash:
            self.content_hash = self.compute_content_hash()
        return self.content_hash

    def to_frontmatter_dict(self) -> dict:
        """Build minimal frontmatter payload based on primitive type."""
        base = {
            "id": self.id,
            "title": self.title,
            "tags": self.tags,
            "related": self.related,
            "created": self.created.isoformat(),
            "updated": self.updated.isoformat(),
        }
        if self.primitive == PrimitiveType.decision:
            base["status"] = self.status
            base["decided_by"] = self.decided_by
        elif self.primitive == PrimitiveType.learning:
            base["kind"] = self.kind
        elif self.primitive == PrimitiveType.convention:
            base["scope"] = self.scope
        elif self.primitive == PrimitiveType.context:
            base["area"] = self.area
        return base

    def to_markdown(self) -> str:
        """Serialize learning to frontmatter + body markdown format."""
        fm = yaml.dump(
            self.to_frontmatter_dict(),
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
        return f"---\n{fm}---\n{self.body}"

    @classmethod
    def from_markdown(cls, text: str) -> "Learning":
        """Parse learning from markdown frontmatter + body format."""
        match = re.match(r"^---\n(.+?\n)---\n(.*)", text, re.DOTALL)
        if not match:
            raise ValueError("Invalid learning markdown: missing frontmatter")
        fm_text, body = match.group(1), match.group(2)
        fm = yaml.safe_load(fm_text)
        if not isinstance(fm, dict):
            raise ValueError("Invalid frontmatter: not a mapping")

        def _parse_datetime(value: object) -> datetime | None:
            """Parse datetime-like frontmatter values into UTC-aware datetimes."""
            if isinstance(value, datetime):
                if value.tzinfo is None:
                    return value.replace(tzinfo=timezone.utc)
                return value
            if isinstance(value, str):
                try:
                    parsed = datetime.fromisoformat(value)
                except ValueError:
                    return None
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed
            return None

        def _coerce_list(value: object) -> list[str]:
            """Coerce frontmatter values into a string list."""
            if not value:
                return []
            if isinstance(value, list):
                return [str(item) for item in value if item is not None]
            return [str(value)]

        def _coerce_sources(value: object) -> list[str]:
            """Coerce mixed source/session structures into session id strings."""
            if not value:
                return []
            if isinstance(value, list):
                items: list[str] = []
                for item in value:
                    if item is None:
                        continue
                    if isinstance(item, dict):
                        session_id = item.get("session") or item.get("id") or item.get("run_id")
                        if session_id:
                            items.append(str(session_id))
                    else:
                        items.append(str(item))
                return items
            return [str(value)]

        primitive_raw = str(fm.get("primitive") or "").strip().lower()
        if primitive_raw in {item.value for item in PrimitiveType}:
            primitive = PrimitiveType(primitive_raw)
        else:
            if "decided_by" in fm or "status" in fm:
                primitive = PrimitiveType.decision
            elif "scope" in fm:
                primitive = PrimitiveType.convention
            elif "area" in fm:
                primitive = PrimitiveType.context
            else:
                primitive = PrimitiveType.learning

        raw_type = fm.get("learning_type") or "insight"
        created = _parse_datetime(fm.get("created") or fm.get("created_at")) or datetime.now(timezone.utc)
        updated = _parse_datetime(fm.get("updated") or fm.get("updated_at")) or datetime.now(timezone.utc)
        last_validated_at = _parse_datetime(fm.get("last_validated_at"))

        learning = cls(
            id=str(fm["id"]),
            title=str(fm["title"]),
            body=body,
            primitive=primitive,
            kind=str(fm.get("kind") or "insight"),
            status=str(fm.get("status") or "active"),
            decided_by=str(fm.get("decided_by") or "agent"),
            scope=str(fm.get("scope") or "project"),
            area=str(fm.get("area") or "general"),
            related=_coerce_list(fm.get("related")),
            learning_type=LearningType(str(raw_type)),
            lifecycle_state=LifecycleState(str(fm.get("lifecycle_state", "candidate"))),
            confidence=float(fm.get("confidence", 0.7)),
            occurrences=int(fm.get("occurrences", 1)),
            source_sessions=_coerce_sources(fm.get("source_sessions") or fm.get("sources")),
            agent_types=_coerce_list(fm.get("agent_types")),
            projects=_coerce_list(fm.get("projects")),
            tags=_coerce_list(fm.get("tags")),
            useful_count=int(fm.get("useful_count", 0)),
            not_useful_count=int(fm.get("not_useful_count", 0)),
            evidence=[EvidenceItem(**item) for item in (fm.get("evidence") or []) if isinstance(item, dict)],
            signal_sources=_coerce_list(fm.get("signal_sources")),
            durability_score=float(fm.get("durability_score", 0.5)),
            volatility=str(fm.get("volatility", "medium") or "medium"),
            last_validated_at=last_validated_at,
            content_hash=fm.get("content_hash") or None,
            version_of=fm.get("version_of") or None,
            supersedes=_coerce_list(fm.get("supersedes")),
            created=created,
            updated=updated,
        )
        learning.ensure_content_hash()
        return learning


class StateMeta(BaseModel):
    """Operational state sidecar model for a learning."""

    id: str
    confidence: float = 0.7
    occurrences: int = 1
    source_sessions: list[str] = Field(default_factory=list)
    agent_types: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    useful_count: int = 0
    not_useful_count: int = 0
    signal_sources: list[str] = Field(default_factory=list)
    durability_score: float = 0.7
    volatility: str = "medium"
    lifecycle_state: str = "candidate"
    content_hash: str | None = None
    last_validated_at: str | None = None
    version_of: str | None = None
    supersedes: list[str] = Field(default_factory=list)
    updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_learning(cls, learning: Learning) -> "StateMeta":
        """Build state sidecar data from a learning record."""
        return cls(
            id=learning.id,
            confidence=learning.confidence,
            occurrences=learning.occurrences,
            source_sessions=list(learning.source_sessions),
            agent_types=list(learning.agent_types),
            projects=list(learning.projects),
            useful_count=learning.useful_count,
            not_useful_count=learning.not_useful_count,
            signal_sources=list(learning.signal_sources),
            durability_score=learning.durability_score,
            volatility=learning.volatility,
            lifecycle_state=learning.lifecycle_state.value,
            content_hash=learning.content_hash,
            last_validated_at=(
                learning.last_validated_at.isoformat() if isinstance(learning.last_validated_at, datetime) else None
            ),
            version_of=learning.version_of,
            supersedes=list(learning.supersedes),
            updated=learning.updated.isoformat(),
        )

    def apply_to_learning(self, learning: Learning) -> Learning:
        """Apply sidecar state fields onto a learning record."""
        learning.confidence = float(self.confidence)
        learning.occurrences = int(self.occurrences)
        learning.source_sessions = list(self.source_sessions)
        learning.agent_types = list(self.agent_types)
        learning.projects = list(self.projects)
        learning.useful_count = int(self.useful_count)
        learning.not_useful_count = int(self.not_useful_count)
        learning.signal_sources = list(self.signal_sources)
        learning.durability_score = float(self.durability_score)
        learning.volatility = str(self.volatility or "medium")
        try:
            learning.lifecycle_state = LifecycleState(str(self.lifecycle_state or "candidate"))
        except ValueError:
            learning.lifecycle_state = LifecycleState.candidate
        learning.content_hash = self.content_hash
        if self.last_validated_at:
            try:
                parsed = datetime.fromisoformat(self.last_validated_at)
                learning.last_validated_at = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                learning.last_validated_at = None
        else:
            learning.last_validated_at = None
        learning.version_of = self.version_of
        learning.supersedes = list(self.supersedes)
        try:
            parsed_updated = datetime.fromisoformat(self.updated)
            learning.updated = parsed_updated if parsed_updated.tzinfo else parsed_updated.replace(tzinfo=timezone.utc)
        except ValueError:
            learning.updated = datetime.now(timezone.utc)
        learning.ensure_content_hash()
        return learning


class EvidenceMeta(BaseModel):
    """Evidence sidecar model for a learning."""

    id: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_learning(cls, learning: Learning) -> "EvidenceMeta":
        """Build evidence sidecar data from a learning record."""
        return cls(id=learning.id, evidence=list(learning.evidence), updated=learning.updated.isoformat())

    def apply_to_learning(self, learning: Learning) -> Learning:
        """Apply sidecar evidence data onto a learning record."""
        learning.evidence = list(self.evidence)
        return learning


if __name__ == "__main__":
    sample = Learning(id="learning-1", title="Queue lifecycle", body="Keep queue states explicit.")
    encoded = sample.to_markdown()
    decoded = Learning.from_markdown(encoded)
    assert decoded.id == sample.id
    assert decoded.title == sample.title
    assert decoded.compute_content_hash()
