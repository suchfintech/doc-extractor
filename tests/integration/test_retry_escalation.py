"""Integration tests for the validation-failure retry layer (Story 3.8).

Covers the four scenarios in the AC:

1. Happy path — first attempt succeeds, no retry, telemetry single line.
2. Retry-to-success — first attempt raises PydanticValidationError, second
   attempt with escalated tier succeeds; agent factory called twice with
   different tier tokens; telemetry has two lines (retry_count 0 then 1).
3. Retry-to-failure — both attempts raise; exception propagates; telemetry
   has two failed lines.
4. No-escalation when already top-tier — Sonnet primary with first-call
   failure; second call NOT made; exception propagates immediately.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agno.agent import Agent
from pydantic import BaseModel, ValidationError

from doc_extractor.agents.retry import (
    _ESCALATION,
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


@pytest.fixture
def captured_telemetry(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture record_extraction calls — list of kwargs in order."""
    from doc_extractor.agents import retry as retry_module

    calls: list[dict[str, Any]] = []

    def fake_record(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(retry_module, "record_extraction", fake_record)
    return calls


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
async def test_happy_path_returns_retry_count_zero(
    captured_telemetry: list[dict[str, Any]],
) -> None:
    receipt = _payment_receipt_fixture()
    agent, arun = _success_agent(receipt)
    factory_calls: list[str] = []

    def factory(tier: str) -> Agent:
        factory_calls.append(tier)
        return agent

    content, retry_count = await with_validation_retry(
        factory,
        "Extract.",
        agent_name="payment_receipt",
        source_key="doc-001.jpeg",
        primary_provider="anthropic-haiku",
        arun_kwargs={"images": [object()]},
        doc_type="PaymentReceipt",
    )

    assert content is receipt
    assert retry_count == 0
    assert factory_calls == ["anthropic-haiku"]
    assert arun.await_count == 1

    assert len(captured_telemetry) == 1
    line = captured_telemetry[0]
    assert line["retry_count"] == 0
    assert line["success"] is True
    assert line["provider"] == "anthropic"
    assert line["model"] == "haiku"
    assert line["agent"] == "payment_receipt"
    assert line["source_key"] == "doc-001.jpeg"
    assert line["doc_type"] == "PaymentReceipt"


# ---------------------------------------------------------------------------
# Scenario 2 — Retry to success (escalation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_escalates_haiku_to_sonnet_on_validation_error(
    captured_telemetry: list[dict[str, Any]],
) -> None:
    receipt = _payment_receipt_fixture()
    err = _pydantic_validation_error()

    haiku_agent, haiku_arun = _failing_agent(err)
    sonnet_agent, sonnet_arun = _success_agent(receipt)

    factory_calls: list[str] = []

    def factory(tier: str) -> Agent:
        factory_calls.append(tier)
        return haiku_agent if tier == "anthropic-haiku" else sonnet_agent

    content, retry_count = await with_validation_retry(
        factory,
        "Extract.",
        agent_name="payment_receipt",
        source_key="doc-002.jpeg",
        primary_provider="anthropic-haiku",
        arun_kwargs={"images": [object()]},
        doc_type="PaymentReceipt",
    )

    assert content is receipt
    assert retry_count == 1
    # Factory called twice with DIFFERENT tier tokens.
    assert factory_calls == ["anthropic-haiku", "anthropic-sonnet"]
    assert haiku_arun.await_count == 1
    assert sonnet_arun.await_count == 1

    assert len(captured_telemetry) == 2
    first, second = captured_telemetry
    assert first["retry_count"] == 0
    assert first["success"] is False
    assert first["provider"] == "anthropic" and first["model"] == "haiku"
    assert second["retry_count"] == 1
    assert second["success"] is True
    assert second["provider"] == "anthropic" and second["model"] == "sonnet"


# ---------------------------------------------------------------------------
# Scenario 3 — Retry to failure (both attempts raise)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_to_failure_re_raises_validation_error(
    captured_telemetry: list[dict[str, Any]],
) -> None:
    err = _pydantic_validation_error()
    haiku_agent, haiku_arun = _failing_agent(err)
    sonnet_agent, sonnet_arun = _failing_agent(err)

    def factory(tier: str) -> Agent:
        return haiku_agent if tier == "anthropic-haiku" else sonnet_agent

    with pytest.raises(PydanticValidationError):
        await with_validation_retry(
            factory,
            "Extract.",
            agent_name="payment_receipt",
            source_key="doc-003.jpeg",
            primary_provider="anthropic-haiku",
            arun_kwargs={"images": [object()]},
            doc_type="PaymentReceipt",
        )

    # Both attempts ran.
    assert haiku_arun.await_count == 1
    assert sonnet_arun.await_count == 1
    assert len(captured_telemetry) == 2
    assert captured_telemetry[0]["retry_count"] == 0
    assert captured_telemetry[0]["success"] is False
    assert captured_telemetry[1]["retry_count"] == 1
    assert captured_telemetry[1]["success"] is False


# ---------------------------------------------------------------------------
# Scenario 4 — No escalation when already at top tier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sonnet_primary_does_not_retry_on_validation_error(
    captured_telemetry: list[dict[str, Any]],
) -> None:
    """When primary is already top-tier (Sonnet), validation failure must
    propagate immediately — no second attempt is made because there's no
    escalation target. Caller routes to disagreement queue."""
    err = _pydantic_validation_error()
    sonnet_agent, sonnet_arun = _failing_agent(err)
    factory_calls: list[str] = []

    def factory(tier: str) -> Agent:
        factory_calls.append(tier)
        return sonnet_agent

    with pytest.raises(PydanticValidationError):
        await with_validation_retry(
            factory,
            "Extract.",
            agent_name="payment_receipt",
            source_key="doc-004.jpeg",
            primary_provider="anthropic-sonnet",
            arun_kwargs={"images": [object()]},
            doc_type="PaymentReceipt",
        )

    # ONE attempt only — no escalation target.
    assert sonnet_arun.await_count == 1
    assert factory_calls == ["anthropic-sonnet"]
    # Single telemetry line for the failed primary attempt.
    assert len(captured_telemetry) == 1
    assert captured_telemetry[0]["retry_count"] == 0
    assert captured_telemetry[0]["success"] is False
    assert captured_telemetry[0]["model"] == "sonnet"


# ---------------------------------------------------------------------------
# Edge case — non-PydanticValidationError errors propagate without retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runtime_error_is_not_retried(
    captured_telemetry: list[dict[str, Any]],
) -> None:
    """The retry layer is scoped to PydanticValidationError. Other exceptions
    (network, rate-limit, programming bugs) propagate without consuming the
    retry budget — those have their own handling paths in Story 6.1."""
    haiku_agent, haiku_arun = _failing_agent(RuntimeError("oops"))

    def factory(_tier: str) -> Agent:
        return haiku_agent

    with pytest.raises(RuntimeError, match="oops"):
        await with_validation_retry(
            factory,
            "Extract.",
            agent_name="payment_receipt",
            source_key="doc-005.jpeg",
            primary_provider="anthropic-haiku",
            arun_kwargs={"images": [object()]},
            doc_type="PaymentReceipt",
        )

    assert haiku_arun.await_count == 1
    # No telemetry line — RuntimeError isn't part of the retry contract,
    # so the cost telemetry path doesn't fire (callers higher up may still
    # log this).
    assert captured_telemetry == []
