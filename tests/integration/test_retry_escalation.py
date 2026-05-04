"""Integration tests for the validation-failure retry layer (Story 3.8).

Covers the four scenarios in the AC:

1. Happy path — first attempt succeeds, no retry, one AttemptRecord.
2. Retry-to-success — first attempt raises PydanticValidationError, second
   attempt with escalated tier succeeds; agent factory called twice with
   different tier tokens; two AttemptRecords (failed, succeeded).
3. Retry-to-failure — both attempts raise; exception propagates; two
   AttemptRecords (both failed) — present in ``attempts_out`` even on the
   exception path so the caller can write a forensic disagreement entry.
4. No-escalation when already top-tier — Sonnet primary with first-call
   failure; second call NOT made; exception propagates immediately.

P10 (code review Round 2) hoisted ``record_extraction`` out of this layer
into ``pipelines.vision_path``. The retry helper now exposes per-attempt
state via the ``attempts_out`` parameter; telemetry assertions moved to
``test_vision_path.py``.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from agno.agent import Agent
from pydantic import BaseModel, ValidationError

from doc_extractor.agents.retry import (
    _ESCALATION,
    AttemptRecord,
    _escalate,
    _split_tier,
    with_validation_retry,
)
from doc_extractor.exceptions import PydanticValidationError
from doc_extractor.schemas.payment_receipt import PaymentReceipt

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StrictModel(BaseModel):
    required_field: str


def _pydantic_validation_error() -> ValidationError:
    """Construct a real PydanticValidationError instance via a failing validate."""
    try:
        _StrictModel.model_validate({})
    except ValidationError as exc:
        return exc
    raise RuntimeError("expected ValidationError but model accepted input")


def _success_agent(content: BaseModel) -> tuple[Agent, AsyncMock]:
    arun = AsyncMock(return_value=MagicMock(content=content))
    agent = MagicMock(spec=Agent)
    agent.arun = arun
    return agent, arun


def _failing_agent(exc: BaseException) -> tuple[Agent, AsyncMock]:
    arun = AsyncMock(side_effect=exc)
    agent = MagicMock(spec=Agent)
    agent.arun = arun
    return agent, arun


def _payment_receipt_fixture() -> PaymentReceipt:
    return PaymentReceipt(
        doc_type="PaymentReceipt",
        receipt_amount="100.00",
        receipt_currency="CNY",
        receipt_debit_account_name="张三",
    )


# ---------------------------------------------------------------------------
# Tier helpers (small, fast unit-style tests)
# ---------------------------------------------------------------------------


def test_split_tier_anthropic_haiku() -> None:
    assert _split_tier("anthropic-haiku") == ("anthropic", "haiku")


def test_split_tier_handles_compound_model_token() -> None:
    """`gpt-4o-mini` has internal hyphens — split on the FIRST one only."""
    assert _split_tier("openai-gpt-4o-mini") == ("openai", "gpt-4o-mini")


def test_escalate_anthropic_haiku_to_sonnet() -> None:
    assert _escalate("anthropic-haiku") == "anthropic-sonnet"


def test_escalate_sonnet_returns_none() -> None:
    """Top-tier has no escalation target."""
    assert _escalate("anthropic-sonnet") is None


def test_escalate_unknown_provider_returns_none() -> None:
    assert _escalate("dashscope-qwen-vl") is None


def test_escalation_map_is_immutable_at_module_scope() -> None:
    """A defensive sentinel: the module-level _ESCALATION should not get
    mutated by any test or library code. Catches accidental writes."""
    assert _ESCALATION == {
        "anthropic": {"haiku": "sonnet"},
        "openai": {"gpt-4o-mini": "gpt-4o"},
    }


# ---------------------------------------------------------------------------
# Scenario 1 — Happy path, no retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_returns_retry_count_zero() -> None:
    receipt = _payment_receipt_fixture()
    agent, arun = _success_agent(receipt)
    factory_calls: list[str] = []

    def factory(tier: str) -> Agent:
        factory_calls.append(tier)
        return agent

    attempts: list[AttemptRecord] = []
    content, retry_count = await with_validation_retry(
        factory,
        "Extract.",
        agent_name="payment_receipt",
        source_key="doc-001.jpeg",
        primary_provider="anthropic-haiku",
        arun_kwargs={"images": [object()]},
        doc_type="PaymentReceipt",
        attempts_out=attempts,
    )

    assert content is receipt
    assert retry_count == 0
    assert factory_calls == ["anthropic-haiku"]
    assert arun.await_count == 1

    # P10 — caller-visible attempt list (telemetry happens upstream now).
    assert len(attempts) == 1
    assert attempts[0].tier == "anthropic-haiku"
    assert attempts[0].success is True
    assert attempts[0].agent is agent
    assert attempts[0].latency_ms >= 0.0


# ---------------------------------------------------------------------------
# Scenario 2 — Retry to success (escalation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_escalates_haiku_to_sonnet_on_validation_error() -> None:
    receipt = _payment_receipt_fixture()
    err = _pydantic_validation_error()

    haiku_agent, haiku_arun = _failing_agent(err)
    sonnet_agent, sonnet_arun = _success_agent(receipt)

    factory_calls: list[str] = []

    def factory(tier: str) -> Agent:
        factory_calls.append(tier)
        return haiku_agent if tier == "anthropic-haiku" else sonnet_agent

    attempts: list[AttemptRecord] = []
    content, retry_count = await with_validation_retry(
        factory,
        "Extract.",
        agent_name="payment_receipt",
        source_key="doc-002.jpeg",
        primary_provider="anthropic-haiku",
        arun_kwargs={"images": [object()]},
        doc_type="PaymentReceipt",
        attempts_out=attempts,
    )

    assert content is receipt
    assert retry_count == 1
    # Factory called twice with DIFFERENT tier tokens.
    assert factory_calls == ["anthropic-haiku", "anthropic-sonnet"]
    assert haiku_arun.await_count == 1
    assert sonnet_arun.await_count == 1

    assert len(attempts) == 2
    first, second = attempts
    assert first.tier == "anthropic-haiku" and first.success is False
    assert first.agent is haiku_agent
    assert second.tier == "anthropic-sonnet" and second.success is True
    assert second.agent is sonnet_agent


# ---------------------------------------------------------------------------
# Scenario 3 — Retry to failure (both attempts raise)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_to_failure_re_raises_validation_error() -> None:
    err = _pydantic_validation_error()
    haiku_agent, haiku_arun = _failing_agent(err)
    sonnet_agent, sonnet_arun = _failing_agent(err)

    def factory(tier: str) -> Agent:
        return haiku_agent if tier == "anthropic-haiku" else sonnet_agent

    attempts: list[AttemptRecord] = []
    with pytest.raises(PydanticValidationError):
        await with_validation_retry(
            factory,
            "Extract.",
            agent_name="payment_receipt",
            source_key="doc-003.jpeg",
            primary_provider="anthropic-haiku",
            arun_kwargs={"images": [object()]},
            doc_type="PaymentReceipt",
            attempts_out=attempts,
        )

    # Both attempts ran.
    assert haiku_arun.await_count == 1
    assert sonnet_arun.await_count == 1
    # P10 — caller can inspect both failed attempts on the exception path
    # too (the helper populates ``attempts_out`` in-place even before raising).
    assert len(attempts) == 2
    assert attempts[0].tier == "anthropic-haiku" and attempts[0].success is False
    assert attempts[1].tier == "anthropic-sonnet" and attempts[1].success is False


# ---------------------------------------------------------------------------
# Scenario 4 — No escalation when already at top tier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sonnet_primary_does_not_retry_on_validation_error() -> None:
    """When primary is already top-tier (Sonnet), validation failure must
    propagate immediately — no second attempt is made because there's no
    escalation target. Caller routes to disagreement queue."""
    err = _pydantic_validation_error()
    sonnet_agent, sonnet_arun = _failing_agent(err)
    factory_calls: list[str] = []

    def factory(tier: str) -> Agent:
        factory_calls.append(tier)
        return sonnet_agent

    attempts: list[AttemptRecord] = []
    with pytest.raises(PydanticValidationError):
        await with_validation_retry(
            factory,
            "Extract.",
            agent_name="payment_receipt",
            source_key="doc-004.jpeg",
            primary_provider="anthropic-sonnet",
            arun_kwargs={"images": [object()]},
            doc_type="PaymentReceipt",
            attempts_out=attempts,
        )

    # ONE attempt only — no escalation target.
    assert sonnet_arun.await_count == 1
    assert factory_calls == ["anthropic-sonnet"]
    # Single failed attempt visible to the caller.
    assert len(attempts) == 1
    assert attempts[0].tier == "anthropic-sonnet"
    assert attempts[0].success is False


# ---------------------------------------------------------------------------
# Edge case — non-PydanticValidationError errors propagate without retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runtime_error_is_not_retried() -> None:
    """The retry layer is scoped to PydanticValidationError. Other exceptions
    (network, rate-limit, programming bugs) propagate without consuming the
    retry budget — those have their own handling paths in Story 6.1."""
    haiku_agent, haiku_arun = _failing_agent(RuntimeError("oops"))

    def factory(_tier: str) -> Agent:
        return haiku_agent

    attempts: list[AttemptRecord] = []
    with pytest.raises(RuntimeError, match="oops"):
        await with_validation_retry(
            factory,
            "Extract.",
            agent_name="payment_receipt",
            source_key="doc-005.jpeg",
            primary_provider="anthropic-haiku",
            arun_kwargs={"images": [object()]},
            doc_type="PaymentReceipt",
            attempts_out=attempts,
        )

    assert haiku_arun.await_count == 1
    # The RuntimeError aborts before the helper appends an AttemptRecord;
    # this is fine since RuntimeError isn't part of the retry contract.
    # Vision_path's higher-level handling logs the failure separately.
    assert attempts == []


# ---------------------------------------------------------------------------
# attempts_out — defaults / call-shape sentinels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_attempts_out_optional_for_callers_that_dont_care() -> None:
    """The ``attempts_out`` parameter defaults to None — callers that don't
    need per-attempt visibility can still call with_validation_retry as
    before."""
    receipt = _payment_receipt_fixture()
    agent, _ = _success_agent(receipt)

    def factory(_tier: str) -> Agent:
        return agent

    content, retry_count = await with_validation_retry(
        factory,
        "Extract.",
        agent_name="payment_receipt",
        source_key="doc-006.jpeg",
        primary_provider="anthropic-haiku",
        arun_kwargs={"images": [object()]},
        doc_type="PaymentReceipt",
    )
    assert content is receipt
    assert retry_count == 0
