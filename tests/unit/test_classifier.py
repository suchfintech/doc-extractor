"""Unit tests for ClassifierAgent and the Classification schema."""

from __future__ import annotations

from typing import Any, get_args
from unittest.mock import MagicMock

import pytest
from agno.agent import Agent
from agno.models.base import Model
from pydantic import ValidationError

from doc_extractor.agents import classifier as classifier_module
from doc_extractor.agents.classifier import create_classifier_agent
from doc_extractor.agents.factory import VisionModelFactory
from doc_extractor.schemas.classification import DOC_TYPES, Classification


def test_doc_types_has_exactly_fifteen_entries() -> None:
    types = get_args(DOC_TYPES)
    assert len(types) == 15
    assert "Passport" in types
    assert "Other" in types
    assert "PaymentReceipt" in types


def test_doc_types_entries_are_unique() -> None:
    types = get_args(DOC_TYPES)
    assert len(set(types)) == len(types)


def test_classification_accepts_known_doc_type() -> None:
    instance = Classification(doc_type="Passport", jurisdiction="CN", doc_subtype="P")
    assert instance.doc_type == "Passport"
    assert instance.jurisdiction == "CN"
    assert instance.doc_subtype == "P"


def test_classification_defaults_jurisdiction_and_subtype() -> None:
    instance = Classification(doc_type="Other")
    assert instance.doc_type == "Other"
    assert instance.jurisdiction == "OTHER"
    assert instance.doc_subtype == ""


def test_classification_rejects_unknown_doc_type() -> None:
    with pytest.raises(ValidationError):
        Classification(doc_type="DefinitelyNotARealType")  # type: ignore[arg-type]


def _patch_factory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    api_key: str = "sk-test-key",
) -> tuple[MagicMock, list[dict[str, Any]]]:
    """Patch ``VisionModelFactory`` so the classifier never hits real providers."""
    fake_model = MagicMock(spec=Model, name="FakeModel")
    calls: list[dict[str, Any]] = []

    def fake_create(provider: str, model_id: str, api_key: str, **extra: Any) -> Model:
        calls.append({"provider": provider, "model_id": model_id, "api_key": api_key, **extra})
        return fake_model

    def fake_validate(provider: str) -> str:
        return api_key

    monkeypatch.setattr(VisionModelFactory, "create", staticmethod(fake_create))
    monkeypatch.setattr(VisionModelFactory, "validate_api_key", staticmethod(fake_validate))
    return fake_model, calls


def test_create_classifier_agent_returns_configured_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_model, calls = _patch_factory(monkeypatch)

    agent = create_classifier_agent()

    assert isinstance(agent, Agent)
    assert agent.output_schema is Classification
    assert agent.model is fake_model
    assert agent.instructions is not None
    assert len(calls) == 1
    assert calls[0]["provider"] == "anthropic"
    assert calls[0]["model_id"] == "claude-haiku-4-5-20251001"
    assert calls[0]["api_key"] == "sk-test-key"


def test_create_classifier_agent_uses_haiku_per_yaml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The classifier must run on the cheapest configured provider (Haiku)."""
    _, calls = _patch_factory(monkeypatch)

    create_classifier_agent()

    assert calls[0]["provider"] == "anthropic"
    assert "haiku" in calls[0]["model_id"].lower()
    assert any(ch.isdigit() for ch in calls[0]["model_id"].split("-")[-1])


def test_classifier_module_exports_create_function() -> None:
    """Sentinel: the public surface stays callable."""
    assert callable(classifier_module.create_classifier_agent)
