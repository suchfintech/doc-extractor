"""Unit tests for the EntityOwnership agent factory."""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest
from agno.agent import Agent
from agno.models.base import Model

from doc_extractor.agents import entity_ownership as entity_ownership_module
from doc_extractor.agents.entity_ownership import create_entity_ownership_agent
from doc_extractor.schemas.entity_ownership import EntityOwnership


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
    load_prompt_mock = MagicMock(return_value=("ENTITY OWNERSHIP PROMPT BODY", "0.1.0"))

    monkeypatch.setattr(
        entity_ownership_module.VisionModelFactory, "create", create_mock
    )
    monkeypatch.setattr(
        entity_ownership_module.VisionModelFactory, "validate_api_key", validate_mock
    )
    monkeypatch.setattr(entity_ownership_module, "load_prompt", load_prompt_mock)

    return {
        "create": create_mock,
        "validate_api_key": validate_mock,
        "load_prompt": load_prompt_mock,
    }


def test_happy_path_returns_agent_with_entity_ownership_schema(
    mocked_deps: dict[str, MagicMock],
) -> None:
    agent = create_entity_ownership_agent()

    assert isinstance(agent, Agent)
    assert agent.output_schema is EntityOwnership
    assert agent.instructions == ["ENTITY OWNERSHIP PROMPT BODY"]
    mocked_deps["load_prompt"].assert_called_once_with("entity_ownership")


def test_sonnet_model_is_wired(mocked_deps: dict[str, MagicMock]) -> None:
    """Nested-object UBO list extraction + verbatim ownership_percentage
    preservation needs Sonnet."""
    agent = create_entity_ownership_agent()

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "anthropic"
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    assert "haiku" not in create_kwargs["model_id"]
    assert agent.model is not None
    assert agent.model.id == "claude-sonnet-4-6-20260101"


def test_provider_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    create_entity_ownership_agent(provider="openai")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "openai"
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    mocked_deps["validate_api_key"].assert_called_once_with("openai")


def test_no_module_level_agent_attribute() -> None:
    public_attrs = {a for a in dir(entity_ownership_module) if not a.startswith("_")}
    for name in public_attrs:
        value = getattr(entity_ownership_module, name)
        assert not isinstance(value, Agent), (
            f"Module exposes pre-built Agent at {name!r} — violates 'no global Agent' rule"
        )
