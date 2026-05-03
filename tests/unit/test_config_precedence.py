"""Exercise the config precedence chain — one passing case per layer."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from doc_extractor.config import precedence
from doc_extractor.config.precedence import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    AgentConfig,
    resolve_agent_config,
)


@pytest.fixture
def isolated_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the resolver at an empty agents.yaml unless a test overwrites it."""
    yaml_file = tmp_path / "agents.yaml"
    yaml_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(precedence, "AGENTS_YAML_PATH", yaml_file)
    return yaml_file


@pytest.fixture(autouse=True)
def clear_doc_extractor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip any DOC_EXTRACTOR_* env vars so the host shell can't leak into tests."""
    for key in list(os.environ):
        if key.startswith("DOC_EXTRACTOR_"):
            monkeypatch.delenv(key, raising=False)


def test_hardcoded_fallback_when_nothing_configured(
    isolated_yaml: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="doc_extractor.config.precedence"):
        cfg = resolve_agent_config("passport")

    assert cfg == AgentConfig(provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL, temperature=0.0)
    assert cfg.temperature == 0.0
    assert any("falling back" in rec.message for rec in caplog.records), (
        "fallback path must emit a warning"
    )


def test_yaml_wins_when_no_env_no_cli(isolated_yaml: Path) -> None:
    isolated_yaml.write_text(
        "passport:\n  provider: anthropic\n  model: claude-sonnet-4-6-20260101\n",
        encoding="utf-8",
    )

    cfg = resolve_agent_config("passport")

    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-sonnet-4-6-20260101"
    assert cfg.temperature == 0.0


def test_env_wins_over_yaml(
    isolated_yaml: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolated_yaml.write_text(
        "passport:\n  provider: anthropic\n  model: claude-sonnet-4-6-20260101\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DOC_EXTRACTOR_PROVIDER_PASSPORT", "openai")
    monkeypatch.setenv("DOC_EXTRACTOR_MODEL_PASSPORT", "gpt-4o-2024-08-06")

    cfg = resolve_agent_config("passport")

    assert cfg.provider == "openai"
    assert cfg.model == "gpt-4o-2024-08-06"


def test_cli_wins_over_env_and_yaml(
    isolated_yaml: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolated_yaml.write_text(
        "passport:\n  provider: anthropic\n  model: claude-sonnet-4-6-20260101\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DOC_EXTRACTOR_PROVIDER_PASSPORT", "openai")
    monkeypatch.setenv("DOC_EXTRACTOR_MODEL_PASSPORT", "gpt-4o-2024-08-06")

    cfg = resolve_agent_config(
        "passport",
        cli_overrides={"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    )

    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-haiku-4-5-20251001"


def test_partial_cli_override_falls_through_to_lower_layers(
    isolated_yaml: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-field resolution: CLI overrides only the fields it sets."""
    isolated_yaml.write_text(
        "passport:\n  provider: anthropic\n  model: claude-sonnet-4-6-20260101\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DOC_EXTRACTOR_MODEL_PASSPORT", "gpt-4o-2024-08-06")

    cfg = resolve_agent_config("passport", cli_overrides={"provider": "openai"})

    assert cfg.provider == "openai"  # CLI sets provider
    assert cfg.model == "gpt-4o-2024-08-06"  # CLI didn't set model, env still wins
