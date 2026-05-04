"""Validation-failure retry with provider escalation (FR6, NFR13).

A specialist agent that returns malformed structured output (Pydantic
``ValidationError``) is retried **once** with an escalated provider tier:

- ``anthropic-haiku``  → ``anthropic-sonnet``
- ``openai-gpt-4o-mini`` → ``openai-gpt-4o``

When the primary tier is already top-tier (e.g. ``anthropic-sonnet``), there
is no escalation target — the original ``PydanticValidationError`` is
re-raised so the caller can route to the disagreement queue with
``status="validation_failure"``.

P10 (code review Round 2) hoisted ``record_extraction`` OUT of this
helper into ``pipelines.vision_path`` — the retry layer no longer knows
about telemetry. ``with_validation_retry`` now returns
``(content, retry_count, attempts)``: an ordered list of
:class:`AttemptRecord` per call (one when the first attempt succeeded,
two when the helper escalated). Vision_path iterates ``attempts`` and
emits one ``record_extraction`` line per attempt.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from agno.agent import Agent
from agno.exceptions import ModelRateLimitError
from pydantic import BaseModel

from doc_extractor.exceptions import PydanticValidationError

logger = logging.getLogger(__name__)

# Story 8.5 — rate-limit retry. Outside the pipeline, wrapping the whole
# per-key extract() at the batch level. The validation retry above is
# inside the pipeline, wrapping the specialist agent call.
RATE_LIMIT_DEFAULT_MAX_RETRIES = 3
RATE_LIMIT_DEFAULT_BASE_DELAY = 1.0


async def with_rate_limit_retry(
    coro_factory: Callable[[], Awaitable[Any]],
    *,
    max_retries: int = RATE_LIMIT_DEFAULT_MAX_RETRIES,
    base_delay: float = RATE_LIMIT_DEFAULT_BASE_DELAY,
) -> Any:
    """Retry on ``ModelRateLimitError`` with exponential backoff + jitter.

    ``coro_factory`` produces a fresh coroutine each call — coroutines
    cannot be re-awaited, so the caller must hand us a thunk that builds
    a new awaitable per attempt. Backoff is
    ``base_delay * (2 ** attempt) + random.uniform(0, base_delay)`` per
    attempt; non-rate-limit errors propagate immediately, max-retries
    re-raises the last ``ModelRateLimitError``.
    """
    if max_retries < 1:
        raise ValueError(f"max_retries must be >= 1, got {max_retries}")

    last_exc: ModelRateLimitError | None = None
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except ModelRateLimitError as exc:
            last_exc = exc
            if attempt == max_retries - 1:
                break
            delay = base_delay * (2**attempt) + random.uniform(0, base_delay)
            logger.warning(
                "rate-limit retry: attempt %d/%d failed (%s); sleeping %.2fs",
                attempt + 1,
                max_retries,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    assert last_exc is not None  # loop must have caught at least one
    raise last_exc

# Per-provider model-tier escalation. v1 only the Anthropic Haiku→Sonnet
# path is exercised in tests; the OpenAI entry is wired forward-compat for
# the day a v1.x specialist runs on the smaller OpenAI model.
_ESCALATION: dict[str, dict[str, str]] = {
    "anthropic": {"haiku": "sonnet"},
    "openai": {"gpt-4o-mini": "gpt-4o"},
}

# P8 (code review Round 3) — keyword inventory for ``tier_for_config``.
# Maps a provider to the substrings that identify a tier inside a full
# model id (e.g. ``claude-haiku-4-5-20251001`` → ``haiku``). Listed
# longest-first so ``gpt-4o-mini`` matches before ``gpt-4o`` would
# spuriously match its prefix. Mirrors the keys of ``_ESCALATION``.
_TIER_KEYWORDS: dict[str, tuple[str, ...]] = {
    "anthropic": ("sonnet", "haiku"),
    "openai": ("gpt-4o-mini", "gpt-4o"),
}


def tier_for_config(provider: str, model_id: str) -> str:
    """Map ``(provider, model_id)`` → the tier string the retry helper
    expects for ``primary_provider``.

    P8 closed a bug where ``vision_path.run`` hardcoded
    ``primary_provider="anthropic-sonnet"`` regardless of the resolved
    AgentConfig — Sonnet is top-tier so escalation was permanently
    dead. This helper derives the right tier from the config so a
    Haiku-default agent (``Other``, ``classifier``) can actually
    escalate to Sonnet on a validation failure.

    Unknown ``provider`` / no keyword match → returns
    ``f"{provider}-{model_id}"`` (the verbatim shape). The retry
    helper's ``_escalate`` returns ``None`` for unrecognised tiers, so
    an unknown shape just behaves as "no escalation" without crashing.
    """
    keywords = _TIER_KEYWORDS.get(provider, ())
    # Iterate longest-first so a more specific keyword wins over a prefix.
    for kw in sorted(keywords, key=len, reverse=True):
        if kw in model_id:
            return f"{provider}-{kw}"
    return f"{provider}-{model_id}"


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


@dataclass(frozen=True)
class AttemptRecord:
    """One specialist call attempt — produced by ``with_validation_retry``
    so callers can emit telemetry per attempt without the retry helper
    needing a telemetry dependency (P10).

    ``agent`` is exposed so the caller can pull cost / raw text /
    provider / model from ``agent.run_response`` via
    ``vision_path._read_run_response`` — the retry layer doesn't import
    Agno-specific helpers, just hands back the agent reference.
    """

    tier: str  # e.g. "anthropic-haiku"
    success: bool
    latency_ms: float  # wall-clock from arun start to end (or to raise)
    agent: Agent  # so the caller can inspect run_response for cost/raw text


async def with_validation_retry(
    agent_factory: Callable[[str], Agent],
    *arun_args: Any,
    agent_name: str,
    source_key: str,
    primary_provider: str,
    arun_kwargs: dict[str, Any] | None = None,
    prompt_version: str = "",
    doc_type: str = "",
    attempts_out: list[AttemptRecord] | None = None,
) -> tuple[BaseModel, int]:
    """Run the agent once; on ``PydanticValidationError``, retry once with an
    escalated tier. Returns ``(content, retry_count)``.

    ``attempts_out`` (P10): callers that need per-attempt telemetry pass a
    fresh list; this helper appends one :class:`AttemptRecord` per call
    (failed or successful). Available even on the exception path so the
    caller can inspect the failed attempt(s) for the disagreement-queue
    forensic payload. Defaulting to ``None`` keeps existing call sites
    working unchanged.

    Note: the AC sketches an ``image: Image`` parameter; in practice the
    pipeline's specialist call shape is ``agent.arun(prompt_text, images=[image])``,
    so this implementation accepts ``*arun_args`` plus ``arun_kwargs`` and
    forwards them verbatim. The tests exercise both shapes.

    ``agent_name``, ``source_key``, ``prompt_version``, ``doc_type`` are
    accepted for backwards-compat with existing call sites but no longer
    consumed here — telemetry framing is vision_path's responsibility now.
    """
    del agent_name, source_key, prompt_version, doc_type  # P10 — caller's now
    kwargs = arun_kwargs or {}
    attempts: list[AttemptRecord] = attempts_out if attempts_out is not None else []

    async def _attempt(tier: str) -> BaseModel:
        agent = agent_factory(tier)
        start = time.monotonic()
        try:
            result = await agent.arun(*arun_args, **kwargs)
        except PydanticValidationError:
            latency_ms = (time.monotonic() - start) * 1000.0
            attempts.append(
                AttemptRecord(tier=tier, success=False, latency_ms=latency_ms, agent=agent)
            )
            raise

        latency_ms = (time.monotonic() - start) * 1000.0
        attempts.append(
            AttemptRecord(tier=tier, success=True, latency_ms=latency_ms, agent=agent)
        )
        if not isinstance(result.content, BaseModel):
            # Agno usually surfaces malformed output as a ValidationError, but
            # if it ever returns a non-Pydantic content we treat it the same
            # way for the retry contract.
            raise TypeError(
                f"agent returned content of type "
                f"{type(result.content).__name__}, expected pydantic BaseModel"
            )
        return result.content

    try:
        content = await _attempt(primary_provider)
        return content, 0
    except PydanticValidationError:
        escalated = _escalate(primary_provider)
        if escalated is None:
            # Already top-tier (or unknown tier) — no retry. Caller routes
            # to the disagreement queue with status="validation_failure".
            raise
        # One retry with the escalated tier — any failure here propagates.
        content = await _attempt(escalated)
        return content, 1
