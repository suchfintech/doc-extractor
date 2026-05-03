"""Validation-failure retry with provider escalation (FR6, NFR13).

A specialist agent that returns malformed structured output (Pydantic
``ValidationError``) is retried **once** with an escalated provider tier:

- ``anthropic-haiku``  → ``anthropic-sonnet``
- ``openai-gpt-4o-mini`` → ``openai-gpt-4o``

When the primary tier is already top-tier (e.g. ``anthropic-sonnet``), there
is no escalation target — the original ``PydanticValidationError`` is
re-raised so the caller can route to the disagreement queue with
``status="validation_failure"``.

Both attempts emit a ``record_extraction`` telemetry line so the cost
JSONL has paired ``retry_count=0`` / ``retry_count=1`` records under the
same ``source_key``. ``success=False`` is recorded for failed attempts.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from agno.agent import Agent
from pydantic import BaseModel

from doc_extractor import __version__
from doc_extractor.exceptions import PydanticValidationError
from doc_extractor.telemetry import record_extraction

# Per-provider model-tier escalation. v1 only the Anthropic Haiku→Sonnet
# path is exercised in tests; the OpenAI entry is wired forward-compat for
# the day a v1.x specialist runs on the smaller OpenAI model.
_ESCALATION: dict[str, dict[str, str]] = {
    "anthropic": {"haiku": "sonnet"},
    "openai": {"gpt-4o-mini": "gpt-4o"},
}


def _split_tier(tier: str) -> tuple[str, str]:
    """``"anthropic-haiku"`` → ``("anthropic", "haiku")``.

    Returns ``("", tier)`` on a malformed input rather than raising — the
    telemetry path stays robust to a typo'd primary_provider, even though
    such a value would also block escalation (and surface in tests).
    """
    provider, _, model = tier.partition("-")
    if not model:
        return "", tier
    return provider, model


def _escalate(tier: str) -> str | None:
    """Return the escalated tier token, or ``None`` if no escalation defined."""
    provider, model = _split_tier(tier)
    if not provider:
        return None
    next_model = _ESCALATION.get(provider, {}).get(model)
    if next_model is None:
        return None
    return f"{provider}-{next_model}"


async def with_validation_retry(
    agent_factory: Callable[[str], Agent],
    *arun_args: Any,
    agent_name: str,
    source_key: str,
    primary_provider: str,
    arun_kwargs: dict[str, Any] | None = None,
    prompt_version: str = "",
    doc_type: str = "",
) -> tuple[BaseModel, int]:
    """Run the agent once; on ``PydanticValidationError``, retry once with an
    escalated tier. Returns ``(content, retry_count)``.

    Note: the AC sketches an ``image: Image`` parameter; in practice the
    pipeline's specialist call shape is ``agent.arun(prompt_text, images=[image])``,
    so this implementation accepts ``*arun_args`` plus ``arun_kwargs`` and
    forwards them verbatim. The tests exercise both shapes.
    """
    kwargs = arun_kwargs or {}

    async def _attempt(tier: str, retry_count: int) -> BaseModel:
        agent = agent_factory(tier)
        provider_part, model_part = _split_tier(tier)
        start = time.monotonic()
        try:
            result = await agent.arun(*arun_args, **kwargs)
        except PydanticValidationError:
            latency_ms = (time.monotonic() - start) * 1000.0
            record_extraction(
                source_key=source_key,
                doc_type=doc_type,
                agent=agent_name,
                provider=provider_part,
                model=model_part,
                cost_usd=0.0,
                latency_ms=latency_ms,
                retry_count=retry_count,
                success=False,
                prompt_version=prompt_version,
                extractor_version=__version__,
            )
            raise

        latency_ms = (time.monotonic() - start) * 1000.0
        record_extraction(
            source_key=source_key,
            doc_type=doc_type,
            agent=agent_name,
            provider=provider_part,
            model=model_part,
            cost_usd=0.0,
            latency_ms=latency_ms,
            retry_count=retry_count,
            success=True,
            prompt_version=prompt_version,
            extractor_version=__version__,
        )
        if not isinstance(result.content, BaseModel):
            # Agno usually surfaces malformed output as a ValidationError, but
            # if it ever returns a non-Pydantic content we treat it the same
            # way for the retry contract.
            raise TypeError(
                f"agent {agent_name!r} returned content of type "
                f"{type(result.content).__name__}, expected pydantic BaseModel"
            )
        return result.content

    try:
        content = await _attempt(primary_provider, retry_count=0)
        return content, 0
    except PydanticValidationError:
        escalated = _escalate(primary_provider)
        if escalated is None:
            # Already top-tier (or unknown tier) — no retry. Caller routes
            # to the disagreement queue with status="validation_failure".
            raise
        # One retry with the escalated tier — any failure here propagates.
        content = await _attempt(escalated, retry_count=1)
        return content, 1
