"""Provider configuration and environment wiring for agent runtimes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from acreta.config.settings import get_config


@dataclass(frozen=True)
class ProviderConfig:
    """Runtime provider settings and model alias mappings."""

    name: str
    api_key_env: str
    api_key: str | None = None
    base_url: str | None = None
    default_model: str = "claude-sonnet-4-5-20250929"
    model_mappings: dict[str, str] = field(default_factory=dict)
    timeout_ms: int = 300000

    @classmethod
    def for_zai(cls, api_key: str | None = None) -> ProviderConfig:
        """Build configuration for ZAI Anthropic-compatible endpoint."""
        return cls(
            name="zai",
            api_key_env="ZAI_API_KEY",
            api_key=api_key,
            base_url="https://api.z.ai/api/anthropic",
            default_model="glm-4.7-flash",
            model_mappings={
                "sonnet": "glm-4.7-flash",
                "opus": "glm-4.7-flash",
                "haiku": "glm-4.5-air",
                "glm-4": "glm-4.7-flash",
                "glm": "glm-4.7-flash",
                "glm-4.7-flash": "glm-4.7-flash",
            },
            timeout_ms=300000,
        )

    @classmethod
    def for_anthropic(cls, api_key: str | None = None) -> ProviderConfig:
        """Build configuration for direct Anthropic endpoint."""
        return cls(
            name="anthropic",
            api_key_env="ANTHROPIC_API_KEY",
            api_key=api_key,
            default_model="claude-sonnet-4-5-20250929",
            model_mappings={
                "sonnet": "claude-sonnet-4-5-20250929",
                "opus": "claude-opus-4-5-20251101",
                "haiku": "claude-haiku-4-5-20251001",
            },
            timeout_ms=120000,
        )

    @classmethod
    def for_openrouter(cls, api_key: str | None = None) -> ProviderConfig:
        """Build configuration for OpenRouter Anthropic-compatible endpoint."""
        return cls(
            name="openrouter",
            api_key_env="OPENROUTER_API_KEY",
            api_key=api_key,
            base_url="https://openrouter.ai/api",
            default_model="anthropic/claude-sonnet-4-5-20250929",
            model_mappings={
                "sonnet": "anthropic/claude-sonnet-4-5-20250929",
                "opus": "anthropic/claude-opus-4-5-20251101",
                "haiku": "anthropic/claude-haiku-4-5-20251001",
                "glm-4.7-flash": "z-ai/glm-4.7-flash",
                "glm": "z-ai/glm-4.7-flash",
            },
            timeout_ms=120000,
        )


def get_provider_config(provider: str | None = None) -> ProviderConfig:
    """Get provider config from TOML config with env var override."""
    config = get_config()
    factories = {
        "zai": lambda: ProviderConfig.for_zai(api_key=config.zai_api_key),
        "anthropic": lambda: ProviderConfig.for_anthropic(api_key=config.anthropic_api_key),
        "openrouter": lambda: ProviderConfig.for_openrouter(api_key=config.openrouter_api_key),
    }

    # Provider priority: argument > env var > TOML config
    if not provider:
        provider = config.provider

    selected = factories.get(provider)
    if selected:
        return selected()

    # Auto-detect based on available API keys
    if config.zai_api_key:
        return factories["zai"]()
    if config.anthropic_api_key:
        return factories["anthropic"]()
    if config.openrouter_api_key:
        return factories["openrouter"]()

    # Default to configured provider even without API key
    selected = factories.get(config.provider)
    if selected:
        return selected()
    return factories["anthropic"]()


def resolve_model(model: str | None, config: ProviderConfig) -> str:
    """Resolve model alias names to provider-specific concrete model names."""
    if not model:
        return config.default_model
    return config.model_mappings.get(model, model)


def build_provider_env(config: ProviderConfig) -> dict[str, str]:
    """Build environment variables for Claude Agent SDK.

    ZAI and other Anthropic-compatible providers use:
    - ANTHROPIC_AUTH_TOKEN (the API key)
    - ANTHROPIC_BASE_URL (the endpoint)
    - ANTHROPIC_DEFAULT_*_MODEL (model mappings)
    - API_TIMEOUT_MS (timeout)
    """
    env: dict[str, str] = {}

    # Get API key from config or env
    api_key = config.api_key or os.getenv(config.api_key_env)

    if config.name == "zai":
        # ZAI uses Anthropic-compatible API with different env vars
        if api_key:
            env["ANTHROPIC_AUTH_TOKEN"] = api_key
        if config.base_url:
            env["ANTHROPIC_BASE_URL"] = config.base_url
        # Clear ANTHROPIC_API_KEY to avoid conflicts
        env["ANTHROPIC_API_KEY"] = ""
        # Set model mappings
        env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = config.model_mappings.get("sonnet", "glm-4.7")
        env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = config.model_mappings.get("opus", "glm-4.7")
        env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = config.model_mappings.get("haiku", "glm-4.5-air")
        # Set timeout
        env["API_TIMEOUT_MS"] = str(config.timeout_ms)
    elif config.name == "openrouter":
        if api_key:
            env["ANTHROPIC_AUTH_TOKEN"] = api_key
        if config.base_url:
            env["ANTHROPIC_BASE_URL"] = config.base_url
        env["ANTHROPIC_API_KEY"] = ""
    else:
        # Standard Anthropic
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        if config.base_url:
            env["ANTHROPIC_BASE_URL"] = config.base_url

    return env


def apply_provider_env(config: ProviderConfig) -> None:
    """Apply provider-specific environment variables to current process."""
    for key, value in build_provider_env(config).items():
        os.environ[key] = value


if __name__ == "__main__":
    anthropic = ProviderConfig.for_anthropic(api_key="anthropic-key")
    anthropic_env = build_provider_env(anthropic)
    assert anthropic_env["ANTHROPIC_API_KEY"] == "anthropic-key"
    assert resolve_model(None, anthropic) == anthropic.default_model

    zai = ProviderConfig.for_zai(api_key="zai-key")
    zai_env = build_provider_env(zai)
    assert zai_env["ANTHROPIC_AUTH_TOKEN"] == "zai-key"
    assert zai_env["ANTHROPIC_BASE_URL"] == "https://api.z.ai/api/anthropic"
    assert resolve_model("sonnet", zai) == "glm-4.7-flash"

    openrouter = ProviderConfig.for_openrouter(api_key="openrouter-key")
    openrouter_env = build_provider_env(openrouter)
    assert openrouter_env["ANTHROPIC_AUTH_TOKEN"] == "openrouter-key"
    assert openrouter_env["ANTHROPIC_BASE_URL"] == "https://openrouter.ai/api"
