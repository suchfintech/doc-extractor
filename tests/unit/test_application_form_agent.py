"""Unit tests for the ApplicationForm agent factory."""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest
from agno.agent import Agent
from agno.models.base import Model

from doc_extractor.agents import application_form as application_form_module
from doc_extractor.agents.application_form import create_application_form_agent
from doc_extractor.schemas.application_form import ApplicationForm


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
    load_prompt_mock = MagicMock(return_value=("APPLICATION FORM PROMPT BODY", "0.1.0"))

    monkeypatch.setattr(
        application_form_module.VisionModelFactory, "create", create_mock
    )
    monkeypatch.setattr(
        application_form_module.VisionModelFactory,
        "validate_api_key",
        validate_mock,
    )
    monkeypatch.setattr(application_form_module, "load_prompt", load_prompt_mock)

    return {
        "create": create_mock,
        "validate_api_key": validate_mock,
        "load_prompt": load_prompt_mock,
    }


def test_happy_path_returns_agent_with_application_form_schema(
    mocked_deps: dict[str, MagicMock],
) -> None:
    agent = create_application_form_agent()

    assert isinstance(agent, Agent)
    assert agent.output_schema is ApplicationForm
    assert agent.instructions == ["APPLICATION FORM PROMPT BODY"]
    mocked_deps["load_prompt"].assert_called_once_with("application_form")


def test_sonnet_model_is_wired(mocked_deps: dict[str, MagicMock]) -> None:
    """Handwritten OCR + day-first DOB conversion benefit from Sonnet."""
    agent = create_application_form_agent()

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "anthropic"
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    assert "haiku" not in create_kwargs["model_id"]
    assert agent.model is not None
    assert agent.model.id == "claude-sonnet-4-6-20260101"


def test_provider_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    create_application_form_agent(provider="openai")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "openai"
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    mocked_deps["validate_api_key"].assert_called_once_with("openai")


def test_no_module_level_agent_attribute() -> None:
    public_attrs = {a for a in dir(application_form_module) if not a.startswith("_")}
    for name in public_attrs:
        value = getattr(application_form_module, name)
        assert not isinstance(value, Agent), (
            f"Module exposes pre-built Agent at {name!r} — violates 'no global Agent' rule"
        )
