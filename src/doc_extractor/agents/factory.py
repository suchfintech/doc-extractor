"""VisionModelFactory — provider-agnostic Agno model construction.

Wraps Agno's `Claude`, `OpenAIChat`, and `OpenAILike` constructors so every
agent in the system goes through one funnel. Pins fully dated model
identifiers (no bare aliases) per FR34 and forces ``temperature=0`` per FR35.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agno.models.anthropic import Claude
from agno.models.base import Model
from agno.models.openai import OpenAIChat
from agno.models.openai.like import OpenAILike

from doc_extractor.exceptions import AuthenticationError, ConfigurationError


@dataclass(frozen=True)
class ProviderSpec:
    """Static metadata for a provider slot in the factory.

    ``cls`` is typed as ``Callable[..., Model]`` because each concrete Agno
    model class accepts a different ctor signature; the factory funnels them
    through a uniform ``id`` / ``api_key`` / ``temperature`` call.
    """

    cls: Callable[..., Model]
    env_var: str | None
    models: tuple[str, ...]


class VisionModelFactory:
    """Construct Agno vision-capable model instances with pinned identifiers."""

    # TODO(Story 7.4): DashScope (Qwen-VL) is deliberately absent from PROVIDERS
    # for v1 pending the vendor-terms gate documented in
    # `docs/vendor-data-handling.md`. See FR33 and architecture Decision 5
    # ("Vendor ToS Documentation Discipline"). Adding a provider here without a
    # corresponding row in that document must fail CI
    # (tests/unit/test_provider_terms_documented.py).
    PROVIDERS: dict[str, ProviderSpec] = {
        "anthropic": ProviderSpec(
            cls=Claude,
            env_var="ANTHROPIC_API_KEY",
            models=(
                "claude-haiku-4-5-20251001",
                "claude-sonnet-4-6-20260101",
            ),
        ),
        "openai": ProviderSpec(
            cls=OpenAIChat,
            env_var="OPENAI_API_KEY",
            models=(
                "gpt-5.4-mini-2025-12-15",
                "gpt-5.4-2025-12-15",
            ),
        ),
        "openai_like": ProviderSpec(
            cls=OpenAILike,
            env_var=None,
            models=(),
        ),
    }

    @classmethod
    def create(
        cls,
        provider: str,
        model_id: str,
        api_key: str,
        **extra: Any,
    ) -> Model:
        """Return a configured Agno model.

        ``temperature=0`` is forced for deterministic extraction (FR35).
        ``extra`` forwards provider-specific kwargs (e.g. ``base_url`` for
        ``openai_like``) untouched.
        """
        spec = cls.PROVIDERS.get(provider)
        if spec is None:
            raise ConfigurationError(
                f"Unknown provider {provider!r}. "
                f"Known providers: {sorted(cls.PROVIDERS)}"
            )
        if not api_key:
            raise AuthenticationError(
                f"Provider {provider!r} requires a non-empty api_key."
            )
        return spec.cls(id=model_id, api_key=api_key, temperature=0, **extra)

    @classmethod
    def validate_api_key(cls, provider: str) -> str:
        """Read the provider's API-key env var or raise.

        Raises:
            ConfigurationError: ``provider`` is not registered.
            AuthenticationError: the provider's env var is unset, empty, or
                not applicable (e.g. ``openai_like`` has no fixed env var —
                callers must supply the key explicitly).
        """
        spec = cls.PROVIDERS.get(provider)
        if spec is None:
            raise ConfigurationError(
                f"Unknown provider {provider!r}. "
                f"Known providers: {sorted(cls.PROVIDERS)}"
            )
        if spec.env_var is None:
            raise AuthenticationError(
                f"Provider {provider!r} has no fixed API-key env var; "
                "callers must pass api_key explicitly to create()."
            )
        value = os.environ.get(spec.env_var, "")
        if not value:
            raise AuthenticationError(
                f"Environment variable {spec.env_var} is required for "
                f"provider {provider!r} but is unset or empty."
            )
        return value
