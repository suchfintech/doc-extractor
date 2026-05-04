"""Unit tests for the Other catch-all agent factory.

Other is the **only Haiku-default agent** — every other Story 4-5 specialist
runs on Sonnet because the typed extraction needs precision; Other is the
graceful-degradation surface where loose output is acceptable, so cheap-model
is appropriate. The Haiku-wired test below pins this default explicitly so a
future agents.yaml edit that flipped Other to Sonnet (e.g. a careless
copy-paste from a sibling specialist) would surface immediately.
"""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock

import pytest
from agno.agent import Agent
from agno.models.base import Model

from doc_extractor.agents import other as other_module
from doc_extractor.agents.other import create_other_agent
from doc_extractor.schemas.other import Other


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
    load_prompt_mock = MagicMock(return_value=("OTHER PROMPT BODY", "0.1.0"))

    monkeypatch.setattr(other_module.VisionModelFactory, "create", create_mock)
    monkeypatch.setattr(
        other_module.VisionModelFactory, "validate_api_key", validate_mock
    )
    monkeypatch.setattr(other_module, "load_prompt", load_prompt_mock)

    return {
        "create": create_mock,
        "validate_api_key": validate_mock,
        "load_prompt": load_prompt_mock,
    }


def test_happy_path_returns_agent_with_other_schema(
    mocked_deps: dict[str, MagicMock],
) -> None:
    agent = create_other_agent()

    assert isinstance(agent, Agent)
    assert agent.output_schema is Other
    assert agent.instructions == ["OTHER PROMPT BODY"]
    mocked_deps["load_prompt"].assert_called_once_with("other")


def test_haiku_model_is_wired_not_sonnet(mocked_deps: dict[str, MagicMock]) -> None:
    """Other is the ONLY Haiku-default agent — pin this explicitly so a future
    edit that flips it to Sonnet (e.g. careless copy-paste from a sibling
    specialist's yaml entry) surfaces immediately. Cheap-model is the *intent*
    here, not the path of least resistance."""
    agent = create_other_agent()

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "anthropic"
    assert create_kwargs["model_id"] == "claude-haiku-4-5-20251001"
    assert "sonnet" not in create_kwargs["model_id"]
    assert agent.model is not None
    assert agent.model.id == "claude-haiku-4-5-20251001"


def test_provider_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    create_other_agent(provider="openai")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["provider"] == "openai"
    # CLI override only sets provider; model still resolves via YAML (Haiku).
    assert create_kwargs["model_id"] == "claude-haiku-4-5-20251001"
    mocked_deps["validate_api_key"].assert_called_once_with("openai")


def test_model_override_beats_yaml(mocked_deps: dict[str, MagicMock]) -> None:
    """P15 — ``--model`` plumbs through the factory signature into
    ``resolve_agent_config`` as a CLI override. Without this plumbing,
    ``doc-extractor extract --model claude-sonnet-4-6-20260101`` silently ran the YAML default."""
    create_other_agent(model="claude-sonnet-4-6-20260101")

    create_kwargs: dict[str, Any] = mocked_deps["create"].call_args.kwargs
    assert create_kwargs["model_id"] == "claude-sonnet-4-6-20260101"
    # CLI override only sets model; provider still resolves via lower layers.
    assert create_kwargs["provider"] == "anthropic"


def test_no_module_level_agent_attribute() -> None:
    public_attrs = {a for a in dir(other_module) if not a.startswith("_")}
    for name in public_attrs:
        value = getattr(other_module, name)
        assert not isinstance(value, Agent), (
            f"Module exposes pre-built Agent at {name!r} — violates 'no global Agent' rule"
        )
