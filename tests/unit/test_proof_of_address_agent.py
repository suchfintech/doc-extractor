"""Unit tests for the ProofOfAddress agent factory."""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest
from agno.agent import Agent
from agno.models.base import Model

from doc_extractor.agents import proof_of_address as proof_of_address_module
from doc_extractor.agents.proof_of_address import create_proof_of_address_agent
from doc_extractor.schemas.proof_of_address import ProofOfAddress


@pytest.fixture(autouse=True)
def clear_doc_extractor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("DOC_EXTRACTOR_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def mocked_deps(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    create_mock = MagicMock(name="VisionModelFactory.create")

    def _make_model(**kwargs: Any) -> MagicMock:
        m = MagicMock(spec=Model)
        m.id = kwargs.get("model_id")
        return m

    create_mock.side_effect = _make_model
    validate_mock = MagicMock(return_value="test-api-key")
    load_prompt_mock = MagicMock(return_value=("PROOF OF ADDRESS PROMPT BODY", "0.1.0"))

    monkeypatch.setattr(
        proof_of_address_module.VisionModelFactory, "create", create_mock
    )
    monkeypatch.setattr(
        proof_of_address_module.VisionModelFactory,
        "validate_api_key",
        validate_mock,
    )
    monkeypatch.setattr(proof_of_address_module, "load_prompt", load_prompt_mock)

    return {
        "create": create_mock,
        "validate_api_key": validate_mock,
        "load_prompt": load_prompt_mock,
    }


def test_happy_path_returns_agent_with_proof_of_address_schema(
    mocked_deps: dict[str, MagicMock],
) -> None:
    agent = create_proof_of_address_agent()

    assert isinstance(agent, Agent)
    assert agent.output_schema is ProofOfAddress
    assert agent.instructions == ["PROOF OF ADDRESS PROMPT BODY"]
    mocked_deps["load_prompt"].assert_called_once_with("proof_of_address")


def test_sonnet_model_is_wired(mocked_deps: dict[str, MagicMock]) -> None:
    """Issuer-priority discipline (government > utility > bank > other) and
    multi-format date conversion benefit from Sonnet."""
    agent = create_proof_of_address_agent()

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "anthropic"
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    assert "haiku" not in create_kwargs["model_id"]
    assert agent.model is not None
    assert agent.model.id == "claude-sonnet-4-6-20260101"


def test_provider_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    create_proof_of_address_agent(provider="openai")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "openai"
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    mocked_deps["validate_api_key"].assert_called_once_with("openai")


def test_model_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    """P15 — ``--model`` plumbs through the factory signature into
    ``resolve_agent_config`` as a CLI override. Without this plumbing,
    ``doc-extractor extract --model claude-haiku-4-5-20251001`` silently ran the YAML default."""
    create_proof_of_address_agent(model="claude-haiku-4-5-20251001")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["model_id"] == "claude-haiku-4-5-20251001"
    # CLI override only sets model; provider still resolves via lower layers.
    assert create_kwargs["provider"] == "anthropic"


def test_no_module_level_agent_attribute() -> None:
    public_attrs = {a for a in dir(proof_of_address_module) if not a.startswith("_")}
    for name in public_attrs:
        value = getattr(proof_of_address_module, name)
        assert not isinstance(value, Agent), (
            f"Module exposes pre-built Agent at {name!r} — violates 'no global Agent' rule"
        )
