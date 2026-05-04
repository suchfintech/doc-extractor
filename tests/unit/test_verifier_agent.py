"""Unit tests for the verifier agent factory + VerifierAudit schema (Story 3.7)."""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest
from agno.agent import Agent
from agno.models.base import Model
from pydantic import ValidationError

from doc_extractor.agents import verifier as verifier_module
from doc_extractor.agents.verifier import create_verifier_agent
from doc_extractor.schemas.verifier import VerifierAudit, _derive_overall


@pytest.fixture(autouse=True)
def clear_doc_extractor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip DOC_EXTRACTOR_* env vars so the host shell can't leak into tests."""
    for key in list(os.environ):
        if key.startswith("DOC_EXTRACTOR_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def mocked_deps(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    create_mock = MagicMock(name="VisionModelFactory.create")
    create_mock.side_effect = lambda **_: MagicMock(spec=Model)
    validate_mock = MagicMock(name="VisionModelFactory.validate_api_key")
    validate_mock.return_value = "test-api-key"
    load_prompt_mock = MagicMock(name="load_prompt")
    load_prompt_mock.return_value = ("VERIFIER PROMPT BODY", "0.1.0")

    monkeypatch.setattr(verifier_module.VisionModelFactory, "create", create_mock)
    monkeypatch.setattr(
        verifier_module.VisionModelFactory, "validate_api_key", validate_mock
    )
    monkeypatch.setattr(verifier_module, "load_prompt", load_prompt_mock)

    return {
        "create": create_mock,
        "validate_api_key": validate_mock,
        "load_prompt": load_prompt_mock,
    }


# ---------------------------------------------------------------------------
# Factory wiring
# ---------------------------------------------------------------------------


def test_create_verifier_agent_returns_agent_with_verifier_audit_schema(
    mocked_deps: dict[str, MagicMock],
) -> None:
    agent = create_verifier_agent()

    assert isinstance(agent, Agent)
    assert agent.output_schema is VerifierAudit
    assert agent.instructions == ["VERIFIER PROMPT BODY"]


def test_verifier_uses_sonnet_model_per_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    """Cheap-model verification is self-defeating — agents.yaml pins Sonnet."""
    create_verifier_agent()

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "anthropic"
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    assert create_kwargs["api_key"] == "test-api-key"

    mocked_deps["validate_api_key"].assert_called_once_with("anthropic")
    mocked_deps["load_prompt"].assert_called_once_with("verifier")


def test_provider_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    create_verifier_agent(provider="openai")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "openai"
    # Override only sets provider; model still resolves via lower layers.
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"


def test_model_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    """P15 — ``--model`` plumbs through the factory signature into
    ``resolve_agent_config`` as a CLI override. Without this plumbing,
    ``doc-extractor extract --model claude-haiku-4-5-20251001`` silently ran the YAML default."""
    create_verifier_agent(model="claude-haiku-4-5-20251001")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["model_id"] == "claude-haiku-4-5-20251001"
    # CLI override only sets model; provider still resolves via lower layers.
    assert create_kwargs["provider"] == "anthropic"


def test_each_call_constructs_a_fresh_agent(mocked_deps: dict[str, MagicMock]) -> None:
    a = create_verifier_agent()
    b = create_verifier_agent()

    assert a is not b
    assert mocked_deps["create"].call_count == 2


# ---------------------------------------------------------------------------
# VerifierAudit schema — accept / reject literal values
# ---------------------------------------------------------------------------


def test_verifier_audit_accepts_known_field_verdicts() -> None:
    audit = VerifierAudit(
        field_audits={
            "receipt_debit_account_name": "agree",
            "receipt_credit_account_name": "disagree",
            "receipt_debit_account_number": "abstain",
        },
        notes="image shows debit=Y, claim was X",
    )
    assert audit.field_audits["receipt_debit_account_name"] == "agree"
    assert audit.field_audits["receipt_credit_account_name"] == "disagree"
    assert audit.field_audits["receipt_debit_account_number"] == "abstain"
    assert audit.notes.startswith("image shows")


def test_verifier_audit_rejects_unknown_field_verdict() -> None:
    with pytest.raises(ValidationError):
        VerifierAudit(field_audits={"some_field": "maybe"})  # type: ignore[dict-item]


def test_verifier_audit_rejects_extra_top_level_fields() -> None:
    with pytest.raises(ValidationError):
        VerifierAudit(
            field_audits={"f": "agree"},
            unknown_extra_field="boom",  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# Overall-verdict derivation
# ---------------------------------------------------------------------------


def test_derive_overall_pass_on_all_agree() -> None:
    assert _derive_overall({"a": "agree", "b": "agree"}) == "pass"


def test_derive_overall_pass_on_empty_audit() -> None:
    assert _derive_overall({}) == "pass"


def test_derive_overall_fail_on_any_disagree() -> None:
    assert _derive_overall({"a": "agree", "b": "disagree", "c": "agree"}) == "fail"


def test_derive_overall_fail_takes_priority_over_abstain() -> None:
    assert _derive_overall({"a": "abstain", "b": "disagree"}) == "fail"


def test_derive_overall_uncertain_on_abstain_without_disagree() -> None:
    assert _derive_overall({"a": "agree", "b": "abstain"}) == "uncertain"


# ---------------------------------------------------------------------------
# Validator pins overall to derivation (overrides model self-reports)
# ---------------------------------------------------------------------------


def test_overall_is_pinned_to_derived_value_overriding_model_claim() -> None:
    """Verifier model claims 'pass' but reports a disagree → final overall = 'fail'."""
    audit = VerifierAudit(
        field_audits={"receipt_debit_account_name": "disagree"},
        overall="pass",  # model's incorrect self-report
    )
    assert audit.overall == "fail"


def test_overall_pinned_to_uncertain_when_only_abstains() -> None:
    audit = VerifierAudit(
        field_audits={"f1": "agree", "f2": "abstain"},
        overall="pass",
    )
    assert audit.overall == "uncertain"
