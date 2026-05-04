"""Unit tests for the CompanyExtract agent factory."""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest
from agno.agent import Agent
from agno.models.base import Model

from doc_extractor.agents import company_extract as company_extract_module
from doc_extractor.agents.company_extract import create_company_extract_agent
from doc_extractor.schemas.company_extract import CompanyExtract


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
    load_prompt_mock = MagicMock(return_value=("COMPANY EXTRACT PROMPT BODY", "0.1.0"))

    monkeypatch.setattr(
        company_extract_module.VisionModelFactory, "create", create_mock
    )
    monkeypatch.setattr(
        company_extract_module.VisionModelFactory, "validate_api_key", validate_mock
    )
    monkeypatch.setattr(company_extract_module, "load_prompt", load_prompt_mock)

    return {
        "create": create_mock,
        "validate_api_key": validate_mock,
        "load_prompt": load_prompt_mock,
    }


def test_happy_path_returns_agent_with_company_extract_schema(
    mocked_deps: dict[str, MagicMock],
) -> None:
    agent = create_company_extract_agent()

    assert isinstance(agent, Agent)
    assert agent.output_schema is CompanyExtract
    assert agent.instructions == ["COMPANY EXTRACT PROMPT BODY"]
    mocked_deps["load_prompt"].assert_called_once_with("company_extract")


def test_sonnet_model_is_wired(mocked_deps: dict[str, MagicMock]) -> None:
    """Director / shareholder list-ordering preservation needs Sonnet."""
    agent = create_company_extract_agent()

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "anthropic"
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    assert "haiku" not in create_kwargs["model_id"]
    assert agent.model is not None
    assert agent.model.id == "claude-sonnet-4-6-20260101"


def test_provider_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    create_company_extract_agent(provider="openai")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "openai"
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    mocked_deps["validate_api_key"].assert_called_once_with("openai")


def test_model_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    """P15 — ``--model`` plumbs through the factory signature into
    ``resolve_agent_config`` as a CLI override. Without this plumbing,
    ``doc-extractor extract --model claude-haiku-4-5-20251001`` silently ran the YAML default."""
    create_company_extract_agent(model="claude-haiku-4-5-20251001")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["model_id"] == "claude-haiku-4-5-20251001"
    # CLI override only sets model; provider still resolves via lower layers.
    assert create_kwargs["provider"] == "anthropic"


def test_no_module_level_agent_attribute() -> None:
    public_attrs = {a for a in dir(company_extract_module) if not a.startswith("_")}
    for name in public_attrs:
        value = getattr(company_extract_module, name)
        assert not isinstance(value, Agent), (
            f"Module exposes pre-built Agent at {name!r} — violates 'no global Agent' rule"
        )
