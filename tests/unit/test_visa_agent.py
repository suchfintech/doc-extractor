"""Unit tests for the Visa agent factory.

Mocks ``VisionModelFactory.create``, ``VisionModelFactory.validate_api_key``,
and ``load_prompt`` so the test runs offline. Uses ``MagicMock(spec=Model)``
so Agno's isinstance(model, Model) check passes (convention from the
vision-pipeline tests).
"""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest
from agno.agent import Agent
from agno.models.base import Model

from doc_extractor.agents import visa as visa_module
from doc_extractor.agents.visa import create_visa_agent
from doc_extractor.schemas.ids import Visa


@pytest.fixture(autouse=True)
def clear_doc_extractor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip DOC_EXTRACTOR_* env vars so the host shell can't leak into tests."""
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
    validate_mock = MagicMock(name="VisionModelFactory.validate_api_key")
    validate_mock.return_value = "test-api-key"
    load_prompt_mock = MagicMock(name="load_prompt")
    load_prompt_mock.return_value = ("VISA PROMPT BODY", "0.1.0")

    monkeypatch.setattr(visa_module.VisionModelFactory, "create", create_mock)
    monkeypatch.setattr(
        visa_module.VisionModelFactory, "validate_api_key", validate_mock
    )
    monkeypatch.setattr(visa_module, "load_prompt", load_prompt_mock)

    return {
        "create": create_mock,
        "validate_api_key": validate_mock,
        "load_prompt": load_prompt_mock,
    }


def test_happy_path_returns_agent_with_visa_schema(
    mocked_deps: dict[str, MagicMock],
) -> None:
    agent = create_visa_agent()

    assert isinstance(agent, Agent)
    assert agent.output_schema is Visa
    assert agent.instructions == ["VISA PROMPT BODY"]
    mocked_deps["load_prompt"].assert_called_once_with("visa")


def test_sonnet_model_is_wired(mocked_deps: dict[str, MagicMock]) -> None:
    """Visa formats need format-internal class-code handling and ISO normalisation."""
    agent = create_visa_agent()

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "anthropic"
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    assert "haiku" not in create_kwargs["model_id"]
    assert agent.model is not None
    assert agent.model.id == "claude-sonnet-4-6-20260101"


def test_provider_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    create_visa_agent(provider="openai")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "openai"
    # CLI override only sets provider; model still resolves via YAML.
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    mocked_deps["validate_api_key"].assert_called_once_with("openai")


def test_model_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    """P15 — ``--model`` plumbs through the factory signature into
    ``resolve_agent_config`` as a CLI override. Without this plumbing,
    ``doc-extractor extract --model claude-haiku-4-5-20251001`` silently ran the YAML default."""
    create_visa_agent(model="claude-haiku-4-5-20251001")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["model_id"] == "claude-haiku-4-5-20251001"
    # CLI override only sets model; provider still resolves via lower layers.
    assert create_kwargs["provider"] == "anthropic"
