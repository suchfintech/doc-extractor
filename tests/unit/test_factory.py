"""Unit tests for VisionModelFactory and the AuthenticationError contract."""

from __future__ import annotations

import pytest
from agno.models.anthropic import Claude
from agno.models.openai import OpenAIChat
from agno.models.openai.like import OpenAILike

from doc_extractor.agents.factory import VisionModelFactory
from doc_extractor.exceptions import AuthenticationError, ConfigurationError


def test_providers_dict_lists_three_supported_providers() -> None:
    assert set(VisionModelFactory.PROVIDERS) == {"anthropic", "openai", "openai_like"}
    assert VisionModelFactory.PROVIDERS["anthropic"].cls is Claude
    assert VisionModelFactory.PROVIDERS["openai"].cls is OpenAIChat
    assert VisionModelFactory.PROVIDERS["openai_like"].cls is OpenAILike


def test_dashscope_is_deferred_for_v1() -> None:
    assert "dashscope" not in VisionModelFactory.PROVIDERS
    assert "qwen" not in VisionModelFactory.PROVIDERS


def test_provider_models_are_fully_dated_identifiers() -> None:
    """No bare aliases — every Anthropic/OpenAI model id must carry a date suffix."""
    for provider in ("anthropic", "openai"):
        spec = VisionModelFactory.PROVIDERS[provider]
        assert spec.models, f"{provider} must list at least one pinned model"
        for model_id in spec.models:
            assert any(ch.isdigit() for ch in model_id.split("-")[-1]), (
                f"{provider} model {model_id!r} is missing a dated suffix"
            )
            assert "latest" not in model_id


def test_create_anthropic_returns_claude_with_temperature_zero() -> None:
    model = VisionModelFactory.create(
        "anthropic", "claude-haiku-4-5-20251001", "test-key"
    )
    assert isinstance(model, Claude)
    assert model.id == "claude-haiku-4-5-20251001"
    assert model.api_key == "test-key"
    assert model.temperature == 0


def test_create_openai_returns_openaichat_with_temperature_zero() -> None:
    model = VisionModelFactory.create(
        "openai", "gpt-5.4-mini-2025-12-15", "test-key"
    )
    assert isinstance(model, OpenAIChat)
    assert model.id == "gpt-5.4-mini-2025-12-15"
    assert model.api_key == "test-key"
    assert model.temperature == 0


def test_create_unknown_provider_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="Unknown provider"):
        VisionModelFactory.create("dashscope", "qwen-vl-max", "test-key")


def test_create_empty_api_key_raises_authentication_error() -> None:
    with pytest.raises(AuthenticationError, match="non-empty api_key"):
        VisionModelFactory.create("anthropic", "claude-haiku-4-5-20251001", "")


def test_validate_api_key_raises_when_env_var_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(AuthenticationError, match="ANTHROPIC_API_KEY"):
        VisionModelFactory.validate_api_key("anthropic")


def test_validate_api_key_raises_when_env_var_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with pytest.raises(AuthenticationError, match="OPENAI_API_KEY"):
        VisionModelFactory.validate_api_key("openai")


def test_validate_api_key_returns_value_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    assert VisionModelFactory.validate_api_key("anthropic") == "sk-ant-fake"


def test_validate_api_key_unknown_provider_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="Unknown provider"):
        VisionModelFactory.validate_api_key("dashscope")


def test_validate_api_key_openai_like_has_no_fixed_env_var() -> None:
    """openai_like is generic; callers must supply the key explicitly."""
    with pytest.raises(AuthenticationError, match="no fixed API-key env var"):
        VisionModelFactory.validate_api_key("openai_like")
