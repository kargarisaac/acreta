"""Central config loading from env + TOML with project/global scope resolution."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from acreta.config.project_scope import git_root_for, resolve_data_dirs

DEFAULT_DATA_DIR = Path.home() / ".acreta"
DEFAULT_MEMORY_DIR = DEFAULT_DATA_DIR / "memory"
DEFAULT_INDEX_DIR = DEFAULT_DATA_DIR / "index"
DEFAULT_MEMORY_DB_PATH = DEFAULT_INDEX_DIR / "fts.sqlite3"
DEFAULT_GRAPH_DB_PATH = DEFAULT_INDEX_DIR / "graph.sqlite3"
DEFAULT_SESSIONS_DB_PATH = DEFAULT_INDEX_DIR / "sessions.sqlite3"
DEFAULT_VECTORS_DIR = DEFAULT_INDEX_DIR / "vectors.lance"
DEFAULT_PROJECT_DIR_NAME = ".acreta"
DEFAULT_CLAUDE_DIR = Path.home() / ".claude" / "projects"
DEFAULT_CODEX_DIR = Path.home() / ".codex" / "sessions"
DEFAULT_OPENCODE_DIR = Path.home() / ".local" / "share" / "opencode"
DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 8765

REPO_ROOT = Path(__file__).parent.parent.parent
DEFAULT_REPO_CONFIG_PATH = REPO_ROOT / "config.toml"
DEFAULT_XDG_CONFIG_PATH = Path.home() / ".config" / "acreta" / "config.toml"
DEFAULT_USER_CONFIG_PATH = Path.home() / ".acreta" / "config.toml"

_LAST_CONFIG_SOURCES: list[dict[str, str]] = []


def load_toml_file(path: Path | None) -> dict:
    """Load a TOML file into a dict, returning ``{}`` on read/parse errors."""
    if not path or not path.exists():
        return {}
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge nested dict values with ``override`` precedence."""
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def get_user_config_path() -> Path:
    """Return the canonical user override config path."""
    return DEFAULT_USER_CONFIG_PATH


def ensure_user_config_exists() -> Path:
    """Create the user config scaffold on first run outside pytest."""
    path = get_user_config_path()
    if path.exists():
        return path

    if os.getenv("PYTEST_CURRENT_TEST"):
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "# Acreta user overrides\n"
        "# Generated on first run.\n\n"
        "[agent]\n"
        "# provider = \"anthropic\"\n"
        "# model = \"claude-haiku-4-5-20251001\"\n\n"
        "[embeddings]\n"
        "# provider = \"local\"\n"
        "# model = \"Alibaba-NLP/gte-modernbert-base\"\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def _ensure_project_config_exists(data_root: Path) -> Path:
    """Create per-data-root project config scaffold when missing."""
    path = data_root / "config.toml"
    if path.exists():
        return path
    if os.getenv("PYTEST_CURRENT_TEST"):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "# Acreta project overrides\n"
        "# This file is optional. Uncomment only what this repo needs.\n\n"
        "[memory]\n"
        "# scope = \"project_fallback_global\"\n"
        "# project_dir_name = \".acreta\"\n"
        "\n"
        "[search]\n"
        "# mode = \"files\"    # files | fts | hybrid\n"
        "# enable_fts = false\n"
        "# enable_vectors = false\n"
        "# enable_graph = true\n"
        "# graph_depth = 1\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def _config_layer_specs() -> list[tuple[str, Path]]:
    """Return config layers in load order."""
    return [
        ("repo_default", DEFAULT_REPO_CONFIG_PATH),
        ("xdg_user", DEFAULT_XDG_CONFIG_PATH),
        ("user_override", DEFAULT_USER_CONFIG_PATH),
    ]


def _load_toml_layers() -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Load and merge all config layers, returning merged payload + source list."""
    merged: dict[str, Any] = {}
    sources: list[dict[str, str]] = []

    for source, path in _config_layer_specs():
        if not path.exists():
            continue
        payload = load_toml_file(path)
        if not payload:
            continue
        merged = _deep_merge(merged, payload)
        sources.append({"source": source, "path": str(path)})

    project_root = git_root_for(Path.cwd())
    if project_root:
        project_override = project_root / DEFAULT_PROJECT_DIR_NAME / "config.toml"
        if project_override.exists():
            payload = load_toml_file(project_override)
            if payload:
                merged = _deep_merge(merged, payload)
                sources.append({"source": "project_override", "path": str(project_override)})

    env_path = os.getenv("ACRETA_CONFIG")
    if env_path:
        explicit = Path(env_path).expanduser()
        if explicit.exists():
            payload = load_toml_file(explicit)
            if payload:
                merged = _deep_merge(merged, payload)
                sources.append({"source": "explicit", "path": str(explicit)})

    return merged, sources


def get_config_sources() -> list[dict[str, str]]:
    """Return the last computed config source stack."""
    return [dict(item) for item in _LAST_CONFIG_SOURCES]


def _get_nested(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Read nested dict keys safely with a default value."""
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is default:
            return default
    return current


def _parse_int(value: Any, default: int) -> int:
    """Parse integer-like value with fallback default."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _parse_port(value: Any, default: int) -> int:
    """Parse and clamp network port to valid range."""
    port = _parse_int(value, default)
    if port <= 0 or port > 65535:
        return default
    return port


def _parse_bool(value: Any, default: bool = False) -> bool:
    """Parse permissive boolean strings and bool values."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _expand_path(value: Any, default: Path) -> Path:
    """Expand path-like value with fallback default."""
    if value in (None, ""):
        return default
    try:
        return Path(str(value)).expanduser()
    except (TypeError, OSError, ValueError):
        return default


def _env_or_toml(env_key: str, toml_data: dict[str, Any], *toml_keys: str, default: Any = None) -> Any:
    """Resolve setting from env first, then TOML, then provided default."""
    env_val = os.getenv(env_key)
    if env_val not in (None, ""):
        return env_val
    toml_val = _get_nested(toml_data, *toml_keys, default=None)
    if toml_val not in (None, ""):
        return toml_val
    return default


@dataclass(frozen=True)
class Config:
    data_dir: Path
    memory_dir: Path
    index_dir: Path
    memory_db_path: Path
    sessions_db_path: Path
    vectors_dir: Path

    platforms_path: Path
    claude_dir: Path
    codex_dir: Path
    opencode_dir: Path

    server_host: str
    server_port: int
    poll_interval_minutes: int

    provider: str
    agent_model: str | None
    agent_timeout: int

    anthropic_api_key: str | None
    zai_api_key: str | None
    openai_api_key: str | None
    openrouter_api_key: str | None

    embeddings_provider: str
    embedding_model: str
    embeddings_base_url: str | None
    embedding_chunk_tokens: int
    embedding_chunk_overlap_tokens: int
    embedding_max_input_tokens: int

    graph_export: bool = False
    global_data_dir: Path | None = None
    graph_db_path: Path | None = None
    memory_scope: str = "project_fallback_global"
    memory_project_dir_name: str = DEFAULT_PROJECT_DIR_NAME
    search_mode: str = "files"
    search_enable_fts: bool = False
    search_enable_vectors: bool = False
    search_enable_graph: bool = True
    search_graph_depth: int = 1

    def public_dict(self) -> dict[str, Any]:
        """Return a safe serializable config snapshot for user-facing output."""
        return {
            "data_dir": str(self.data_dir),
            "global_data_dir": str(self.global_data_dir or self.data_dir),
            "memory_dir": str(self.memory_dir),
            "index_dir": str(self.index_dir),
            "memory_db_path": str(self.memory_db_path),
            "graph_db_path": str(self.graph_db_path or (self.index_dir / "graph.sqlite3")),
            "sessions_db_path": str(self.sessions_db_path),
            "vectors_dir": str(self.vectors_dir),
            "platforms_path": str(self.platforms_path),
            "claude_dir": str(self.claude_dir),
            "codex_dir": str(self.codex_dir),
            "opencode_dir": str(self.opencode_dir),
            "server_host": self.server_host,
            "server_port": self.server_port,
            "poll_interval_minutes": self.poll_interval_minutes,
            "provider": self.provider,
            "agent_model": self.agent_model,
            "agent_timeout": self.agent_timeout,
            "embeddings_provider": self.embeddings_provider,
            "embedding_model": self.embedding_model,
            "embeddings_base_url": self.embeddings_base_url,
            "embedding_chunk_tokens": self.embedding_chunk_tokens,
            "embedding_chunk_overlap_tokens": self.embedding_chunk_overlap_tokens,
            "embedding_max_input_tokens": self.embedding_max_input_tokens,
            "memory_scope": self.memory_scope,
            "memory_project_dir_name": self.memory_project_dir_name,
            "search_mode": self.search_mode,
            "search_enable_fts": self.search_enable_fts,
            "search_enable_vectors": self.search_enable_vectors,
            "search_enable_graph": self.search_enable_graph,
            "search_graph_depth": self.search_graph_depth,
            "graph_export": self.graph_export,
        }


@lru_cache(maxsize=1)
def load_config() -> Config:
    """Load effective config, ensure layout, and cache the result."""
    load_dotenv()
    ensure_user_config_exists()
    toml_data, sources = _load_toml_layers()

    global _LAST_CONFIG_SOURCES
    _LAST_CONFIG_SOURCES = sources

    global_data_dir = _expand_path(
        _env_or_toml("ACRETA_DATA_DIR", toml_data, "data", "dir", default=DEFAULT_DATA_DIR),
        DEFAULT_DATA_DIR,
    )
    memory_scope = str(
        _env_or_toml(
            "ACRETA_MEMORY_SCOPE",
            toml_data,
            "memory",
            "scope",
            default="project_fallback_global",
        )
    ).strip().lower()
    memory_project_dir_name = str(
        _env_or_toml(
            "ACRETA_MEMORY_PROJECT_DIR",
            toml_data,
            "memory",
            "project_dir_name",
            default=DEFAULT_PROJECT_DIR_NAME,
        )
    ).strip() or DEFAULT_PROJECT_DIR_NAME
    env_memory_dir_set = os.getenv("ACRETA_MEMORY_DIR") not in (None, "")
    env_index_dir_set = os.getenv("ACRETA_INDEX_DIR") not in (None, "")
    env_data_dir_set = os.getenv("ACRETA_DATA_DIR") not in (None, "")
    use_project_scope = not (env_memory_dir_set or env_index_dir_set or env_data_dir_set)
    scope = resolve_data_dirs(
        scope=memory_scope if use_project_scope else "global_only",
        project_dir_name=memory_project_dir_name,
        global_data_dir=global_data_dir,
        repo_path=Path.cwd(),
    )
    primary_data_dir = scope.ordered_data_dirs[0] if scope.ordered_data_dirs else global_data_dir

    memory_dir = _expand_path(
        _env_or_toml("ACRETA_MEMORY_DIR", toml_data, "memory", "dir", default=primary_data_dir / "memory"),
        primary_data_dir / "memory",
    )
    index_dir = _expand_path(
        _env_or_toml("ACRETA_INDEX_DIR", toml_data, "index", "dir", default=primary_data_dir / "index"),
        primary_data_dir / "index",
    )

    memory_db_path = _expand_path(
        _env_or_toml("ACRETA_INDEX_MEMORY_DB", toml_data, "index", "memory_db", default=index_dir / "fts.sqlite3"),
        index_dir / "fts.sqlite3",
    )
    graph_db_path = _expand_path(
        _env_or_toml("ACRETA_GRAPH_DB", toml_data, "index", "graph_db", default=index_dir / "graph.sqlite3"),
        index_dir / "graph.sqlite3",
    )
    sessions_db_path = _expand_path(
        _env_or_toml(
            "ACRETA_SESSIONS_DB",
            toml_data,
            "index",
            "sessions_db",
            default=global_data_dir / "index" / "sessions.sqlite3",
        ),
        global_data_dir / "index" / "sessions.sqlite3",
    )
    vectors_dir = _expand_path(
        _env_or_toml("ACRETA_VECTORS_DIR", toml_data, "index", "vectors_dir", default=index_dir / "vectors.lance"),
        index_dir / "vectors.lance",
    )

    platforms_path = _expand_path(
        _env_or_toml(
            "ACRETA_PLATFORMS_PATH",
            toml_data,
            "paths",
            "platforms",
            default=global_data_dir / "platforms.json",
        ),
        global_data_dir / "platforms.json",
    )
    claude_dir = _expand_path(
        _env_or_toml("ACRETA_CLAUDE_DIR", toml_data, "paths", "claude_dir", default=DEFAULT_CLAUDE_DIR),
        DEFAULT_CLAUDE_DIR,
    )
    codex_dir = _expand_path(
        _env_or_toml("ACRETA_CODEX_DIR", toml_data, "paths", "codex_dir", default=DEFAULT_CODEX_DIR),
        DEFAULT_CODEX_DIR,
    )
    opencode_dir = _expand_path(
        _env_or_toml("ACRETA_OPENCODE_DIR", toml_data, "paths", "opencode_dir", default=DEFAULT_OPENCODE_DIR),
        DEFAULT_OPENCODE_DIR,
    )

    server_host = str(_env_or_toml("ACRETA_HOST", toml_data, "server", "host", default=DEFAULT_SERVER_HOST))
    server_port = _parse_port(
        _env_or_toml("ACRETA_PORT", toml_data, "server", "port", default=os.getenv("PORT", DEFAULT_SERVER_PORT)),
        DEFAULT_SERVER_PORT,
    )
    poll_interval_minutes = max(
        1,
        _parse_int(_env_or_toml("ACRETA_POLL_INTERVAL_MINUTES", toml_data, "server", "poll_interval_minutes", default=5), 5),
    )

    provider = str(_env_or_toml("ACRETA_PROVIDER", toml_data, "agent", "provider", default="zai"))
    agent_model_raw = _env_or_toml("ACRETA_MODEL", toml_data, "agent", "model", default=None)
    agent_model = str(agent_model_raw) if agent_model_raw not in (None, "") else None
    agent_timeout = max(30, _parse_int(_env_or_toml("ACRETA_AGENT_TIMEOUT", toml_data, "agent", "timeout", default=120), 120))

    anthropic_api_key = _env_or_toml("ANTHROPIC_API_KEY", toml_data, "api_keys", "anthropic", default=None)
    zai_api_key = _env_or_toml("ZAI_API_KEY", toml_data, "api_keys", "zai", default=None)
    openai_api_key = _env_or_toml("OPENAI_API_KEY", toml_data, "api_keys", "openai", default=None)
    openrouter_api_key = _env_or_toml("OPENROUTER_API_KEY", toml_data, "api_keys", "openrouter", default=None)

    embeddings_provider = str(_env_or_toml("ACRETA_EMBEDDINGS_PROVIDER", toml_data, "embeddings", "provider", default="local"))
    embedding_model = str(
        _env_or_toml(
            "ACRETA_EMBEDDING_MODEL",
            toml_data,
            "embeddings",
            "model",
            default="Alibaba-NLP/gte-modernbert-base",
        )
    )
    embeddings_base_url_raw = _env_or_toml("ACRETA_EMBEDDINGS_BASE_URL", toml_data, "embeddings", "base_url", default=None)
    embeddings_base_url = str(embeddings_base_url_raw) if embeddings_base_url_raw not in (None, "") else None

    embedding_chunk_tokens = max(
        64,
        _parse_int(_env_or_toml("ACRETA_EMBEDDING_CHUNK_TOKENS", toml_data, "embeddings", "chunk_tokens", default=800), 800),
    )
    embedding_chunk_overlap_tokens = max(
        0,
        _parse_int(
            _env_or_toml("ACRETA_EMBEDDING_CHUNK_OVERLAP", toml_data, "embeddings", "chunk_overlap_tokens", default=200),
            200,
        ),
    )
    embedding_max_input_tokens = max(
        128,
        _parse_int(
            _env_or_toml("ACRETA_EMBEDDING_MAX_INPUT_TOKENS", toml_data, "embeddings", "max_input_tokens", default=8192),
            8192,
        ),
    )

    search_mode = str(_env_or_toml("ACRETA_SEARCH_MODE", toml_data, "search", "mode", default="files")).strip().lower()
    if search_mode not in {"files", "fts", "hybrid"}:
        search_mode = "files"
    default_enable_fts = search_mode in {"fts", "hybrid"}
    default_enable_vectors = search_mode == "hybrid"
    default_enable_graph = True
    search_enable_fts = _parse_bool(
        _env_or_toml("ACRETA_SEARCH_ENABLE_FTS", toml_data, "search", "enable_fts", default=default_enable_fts),
        default_enable_fts,
    )
    search_enable_vectors = _parse_bool(
        _env_or_toml("ACRETA_SEARCH_ENABLE_VECTORS", toml_data, "search", "enable_vectors", default=default_enable_vectors),
        default_enable_vectors,
    )
    search_enable_graph = _parse_bool(
        _env_or_toml("ACRETA_SEARCH_ENABLE_GRAPH", toml_data, "search", "enable_graph", default=default_enable_graph),
        default_enable_graph,
    )
    search_graph_depth = max(
        0,
        _parse_int(_env_or_toml("ACRETA_SEARCH_GRAPH_DEPTH", toml_data, "search", "graph_depth", default=1), 1),
    )

    graph_export = _parse_bool(_env_or_toml("ACRETA_GRAPH_EXPORT", toml_data, "search", "graph_export", default=False))

    from acreta.memory.layout import build_layout, ensure_layout

    for data_root in scope.ordered_data_dirs:
        ensure_layout(build_layout(data_root))
        _ensure_project_config_exists(data_root)

    return Config(
        data_dir=primary_data_dir,
        global_data_dir=global_data_dir,
        memory_dir=memory_dir,
        index_dir=index_dir,
        memory_db_path=memory_db_path,
        graph_db_path=graph_db_path,
        sessions_db_path=sessions_db_path,
        vectors_dir=vectors_dir,
        platforms_path=platforms_path,
        claude_dir=claude_dir,
        codex_dir=codex_dir,
        opencode_dir=opencode_dir,
        server_host=server_host,
        server_port=server_port,
        poll_interval_minutes=poll_interval_minutes,
        provider=provider,
        agent_model=agent_model,
        agent_timeout=agent_timeout,
        anthropic_api_key=str(anthropic_api_key) if anthropic_api_key not in (None, "") else None,
        zai_api_key=str(zai_api_key) if zai_api_key not in (None, "") else None,
        openai_api_key=str(openai_api_key) if openai_api_key not in (None, "") else None,
        openrouter_api_key=str(openrouter_api_key) if openrouter_api_key not in (None, "") else None,
        embeddings_provider=embeddings_provider,
        embedding_model=embedding_model,
        embeddings_base_url=embeddings_base_url,
        embedding_chunk_tokens=embedding_chunk_tokens,
        embedding_chunk_overlap_tokens=embedding_chunk_overlap_tokens,
        embedding_max_input_tokens=embedding_max_input_tokens,
        memory_scope=memory_scope,
        memory_project_dir_name=memory_project_dir_name,
        search_mode=search_mode,
        search_enable_fts=search_enable_fts,
        search_enable_vectors=search_enable_vectors,
        search_enable_graph=search_enable_graph,
        search_graph_depth=search_graph_depth,
        graph_export=graph_export,
    )


def get_config() -> Config:
    """Return cached effective config."""
    return load_config()


def reload_config() -> Config:
    """Clear config cache and reload effective config."""
    load_config.cache_clear()
    return load_config()


if __name__ == "__main__":
    """Run a real-path smoke test that loads and prints effective config."""
    cfg = load_config()
    assert cfg.data_dir
    assert cfg.memory_dir
    assert cfg.index_dir
    assert isinstance(cfg.public_dict(), dict)
