"""Exercise the config precedence chain — one passing case per layer."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from doc_extractor.config import precedence
from doc_extractor.config.precedence import (
    DEFAULT_PROVIDER,
    AgentConfig,
    _default_model_for,
    _HAIKU_4_5,
    _SONNET_4_6,
    build_cli_overrides,
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


def test_per_class_fallback_passport_resolves_to_sonnet(
    isolated_yaml: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """P17 — Decision 4: Passport (a safety-critical ID extractor) falls
    back to Sonnet, NOT the global Haiku constant. Pre-fix, a YAML
    deletion silently downgraded Passport to Haiku."""
    with caplog.at_level(logging.WARNING, logger="doc_extractor.config.precedence"):
        cfg = resolve_agent_config("passport")

    assert cfg == AgentConfig(provider=DEFAULT_PROVIDER, model=_SONNET_4_6, temperature=0.0)
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


# ---------------------------------------------------------------------------
# P17 — Decision 4 per-class fallback model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "agent_name",
    ["passport", "driver_licence", "national_id", "visa"],
)
def test_safety_critical_id_extractors_fall_back_to_sonnet(
    isolated_yaml: Path, agent_name: str
) -> None:
    """The four ID-class extractors fall back to Sonnet when YAML is silent.
    A YAML deletion or typo on one of these entries used to silently
    downgrade them to Haiku via the global ``DEFAULT_MODEL`` constant —
    per-class fallback closes that gap."""
    cfg = resolve_agent_config(agent_name)
    assert cfg.model == _SONNET_4_6
    assert _default_model_for(agent_name) == _SONNET_4_6


@pytest.mark.parametrize(
    "agent_name",
    [
        "payment_receipt",
        "pep_declaration",
        "verification_report",
        "application_form",
        "bank_statement",
        "bank_account_confirmation",
        "company_extract",
        "entity_ownership",
        "proof_of_address",
        "tax_residency",
        "other",
        "verifier",
        "classifier",
        # Unknown agent name → Haiku fallback (least-privilege default).
        "definitely-not-an-agent",
    ],
)
def test_non_id_agents_fall_back_to_haiku(
    isolated_yaml: Path, agent_name: str
) -> None:
    cfg = resolve_agent_config(agent_name)
    assert cfg.model == _HAIKU_4_5
    assert _default_model_for(agent_name) == _HAIKU_4_5


def test_yaml_entry_overrides_per_class_fallback(isolated_yaml: Path) -> None:
    """A YAML entry on a Sonnet-fallback agent still wins. Per-class
    fallback only fires when the precedence chain has nothing else to
    say."""
    isolated_yaml.write_text(
        "passport:\n  provider: anthropic\n  model: claude-haiku-4-5-20251001\n",
        encoding="utf-8",
    )
    cfg = resolve_agent_config("passport")
    assert cfg.model == _HAIKU_4_5  # YAML wins, NOT the per-class fallback.


# ---------------------------------------------------------------------------
# build_cli_overrides — small helper but exercised by every factory
# ---------------------------------------------------------------------------


def test_build_cli_overrides_with_both_flags() -> None:
    overrides = build_cli_overrides(provider="anthropic", model="claude-haiku-4-5-20251001")
    assert overrides == {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"}


def test_build_cli_overrides_with_only_model() -> None:
    overrides = build_cli_overrides(provider=None, model="claude-haiku-4-5-20251001")
    assert overrides == {"model": "claude-haiku-4-5-20251001"}


def test_build_cli_overrides_returns_none_when_empty() -> None:
    """Both flags unset → return None so the precedence chain falls
    through to env / YAML / fallback uniformly."""
    assert build_cli_overrides(provider=None, model=None) is None
    assert build_cli_overrides(provider="", model="") is None
