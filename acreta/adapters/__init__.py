"""Platform adapters and registry."""

from acreta.adapters.base import SessionRecord, ViewerMessage, ViewerSession
from acreta.adapters.registry import (
    KNOWN_PLATFORMS,
    connect_platform,
    get_adapter,
    get_connected_agents,
    get_connected_platform_paths,
    list_platforms,
    load_platforms,
    remove_platform,
    save_platforms,
)

__all__ = [
    "ViewerMessage",
    "ViewerSession",
    "SessionRecord",
    "KNOWN_PLATFORMS",
    "get_adapter",
    "load_platforms",
    "save_platforms",
    "connect_platform",
    "remove_platform",
    "list_platforms",
    "get_connected_agents",
    "get_connected_platform_paths",
]
