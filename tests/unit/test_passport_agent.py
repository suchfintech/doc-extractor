"""Unit tests for the Passport agent factory.

Mocks ``VisionModelFactory.create``, ``VisionModelFactory.validate_api_key``,
and ``load_prompt`` so the test runs offline with no API calls.
"""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest
from agno.agent import Agent
from agno.models.base import Model

from doc_extractor.agents import passport as passport_module
from doc_extractor.agents.passport import create_passport_agent
from doc_extractor.schemas.ids import Passport


@pytest.fixture(autouse=True)
def clear_doc_extractor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip DOC_EXTRACTOR_* env vars so the host shell can't leak into tests."""
    for key in list(os.environ):
        if key.startswith("DOC_EXTRACTOR_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def mocked_deps(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Replace external collaborators with MagicMocks.

    Returns the mocks keyed by collaborator name so tests can assert against
    their call args.
    """
    create_mock = MagicMock(name="VisionModelFactory.create")
    # spec=Model so Agno's isinstance(model, Model) check passes; each call
    # returns a distinct mock so per-Agent .model identity holds.
    create_mock.side_effect = lambda **_: MagicMock(spec=Model)
    validate_mock = MagicMock(name="VisionModelFactory.validate_api_key")
    validate_mock.return_value = "test-api-key"
    load_prompt_mock = MagicMock(name="load_prompt")
    load_prompt_mock.return_value = ("PASSPORT PROMPT BODY", "0.1.0")

    monkeypatch.setattr(
        passport_module.VisionModelFactory, "create", create_mock
    )
    monkeypatch.setattr(
        passport_module.VisionModelFactory, "validate_api_key", validate_mock
    )
    monkeypatch.setattr(passport_module, "load_prompt", load_prompt_mock)

    return {
        "create": create_mock,
        "validate_api_key": validate_mock,
        "load_prompt": load_prompt_mock,
    }


def test_happy_path_returns_agent_with_yaml_configured_model(
    mocked_deps: dict[str, MagicMock],
) -> None:
    agent = create_passport_agent()

    assert isinstance(agent, Agent)
    assert agent.output_schema is Passport
    assert agent.instructions == ["PASSPORT PROMPT BODY"]

    # YAML has passport → anthropic / claude-sonnet-4-6-20260101
    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "anthropic"
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    assert create_kwargs["api_key"] == "test-api-key"

    mocked_deps["validate_api_key"].assert_called_once_with("anthropic")
    mocked_deps["load_prompt"].assert_called_once_with("passport")


def test_provider_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    create_passport_agent(provider="openai")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "openai"
    # CLI override only sets provider; model still resolves via lower layers (YAML).
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    mocked_deps["validate_api_key"].assert_called_once_with("openai")


def test_model_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    """P15 — ``--model`` plumbs through the factory signature into
    ``resolve_agent_config`` as a CLI override. Without this plumbing,
    ``doc-extractor extract --model claude-haiku-4-5-20251001`` silently ran the YAML default."""
    create_passport_agent(model="claude-haiku-4-5-20251001")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["model_id"] == "claude-haiku-4-5-20251001"
    # CLI override only sets model; provider still resolves via lower layers.
    assert create_kwargs["provider"] == "anthropic"


def test_each_call_constructs_a_fresh_agent(
    mocked_deps: dict[str, MagicMock],
) -> None:
    """No module-level state — repeated calls must build new Agents."""
    agent_a = create_passport_agent()
    agent_b = create_passport_agent()

    assert agent_a is not agent_b
    assert mocked_deps["create"].call_count == 2
    # Model instances are also distinct (different MagicMock per side_effect call).
    assert agent_a.model is not agent_b.model


def test_no_module_level_agent_attribute() -> None:
    """Sentinel: the factory module must not expose a pre-built singleton."""
    public_attrs = {a for a in dir(passport_module) if not a.startswith("_")}
    # No attribute should be an Agent instance — only the constructor function.
    for name in public_attrs:
        value = getattr(passport_module, name)
        assert not isinstance(value, Agent), (
            f"Module exposes pre-built Agent at {name!r} — violates 'no global Agent' rule"
        )
