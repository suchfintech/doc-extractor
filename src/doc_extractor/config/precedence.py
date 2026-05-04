"""Configuration precedence chain for per-agent provider/model resolution.

Resolution order (first non-None per field wins):
  1. CLI overrides
  2. Env vars (``DOC_EXTRACTOR_PROVIDER_<AGENT>``, ``DOC_EXTRACTOR_MODEL_<AGENT>``)
  3. ``config/agents.yaml``
  4. Hardcoded fallback

See ``planning-artifacts/architecture.md`` Decision 4 (FR31).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = "anthropic"

# P17 — Decision 4 per-class default. Safety-critical ID extractors fall
# back to Sonnet (high-precision typed output); everything else falls back
# to Haiku (cheaper, appropriate for less-strict schemas). A YAML deletion
# or typo on one of the four ID-class entries used to silently downgrade
# them to Haiku via the global ``DEFAULT_MODEL`` constant; per-class
# resolution closes that gap.
_SONNET_4_6 = "claude-sonnet-4-6-20260101"
_HAIKU_4_5 = "claude-haiku-4-5-20251001"

_SONNET_FALLBACK_AGENTS: frozenset[str] = frozenset({
    "passport",
    "driver_licence",
    "national_id",
    "visa",
})


def _default_model_for(agent_name: str) -> str:
    """Per-class default per Decision 4: Sonnet for the four safety-critical
    ID extractors, Haiku for everything else."""
    return _SONNET_4_6 if agent_name in _SONNET_FALLBACK_AGENTS else _HAIKU_4_5


# Kept as a module-level constant for the small number of consumers that
# imported it for telemetry / debugging — they get the *non-ID* default.
# Callers that need the per-class value should call ``_default_model_for``
# directly. (Tests that pinned this to assert the old global behaviour
# have been migrated to the per-class lookup.)
DEFAULT_MODEL = _HAIKU_4_5

ENV_PREFIX = "DOC_EXTRACTOR"
AGENTS_YAML_PATH = Path(__file__).parent / "agents.yaml"


def build_cli_overrides(
    *, provider: str | None, model: str | None
) -> dict[str, str] | None:
    """Build the CLI-override dict for ``resolve_agent_config``.

    Returns ``None`` when neither flag is set so the precedence chain
    falls through to env / YAML / fallback uniformly. Both factory
    signatures (15 specialists + classifier + verifier) call this so the
    plumbing for ``--model`` lives in exactly one place.
    """
    overrides: dict[str, str] = {}
    if provider:
        overrides["provider"] = provider
    if model:
        overrides["model"] = model
    return overrides or None


class AgentConfig(BaseModel):
    """Resolved configuration for a single agent.

    ``temperature`` is invariant at 0 (Story 1.3): vision extraction is deterministic.
    Carried on the model so downstream factories have a single typed contract.
    """

    provider: str
    model: str
    temperature: float = Field(default=0.0)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(
            f"agents.yaml must be a mapping at the top level (got {type(data).__name__})"
        )
    return data


def _env_key(agent_name: str, field: str) -> str:
    return f"{ENV_PREFIX}_{field.upper()}_{agent_name.upper()}"


def resolve_agent_config(
    agent_name: str,
    cli_overrides: dict[str, Any] | None = None,
) -> AgentConfig:
    """Resolve ``provider`` and ``model`` for ``agent_name`` through the precedence chain.

    ``cli_overrides`` is a mapping like ``{"provider": "openai", "model": "gpt-4o"}``;
    keys that are absent or ``None`` defer to lower-priority layers.
    """
    overrides = cli_overrides or {}
    yaml_data = _load_yaml(AGENTS_YAML_PATH)
    yaml_entry = yaml_data.get(agent_name) or {}
    if not isinstance(yaml_entry, dict):
        raise ValueError(
            f"agents.yaml entry for {agent_name!r} must be a mapping "
            f"(got {type(yaml_entry).__name__})"
        )

    used_fallback = False
    resolved: dict[str, str] = {}
    fallbacks = (
        ("provider", DEFAULT_PROVIDER),
        ("model", _default_model_for(agent_name)),
    )
    for field, fallback in fallbacks:
        cli_value = overrides.get(field)
        env_value = os.environ.get(_env_key(agent_name, field))
        yaml_value = yaml_entry.get(field)
        if cli_value is not None:
            resolved[field] = str(cli_value)
        elif env_value is not None:
            resolved[field] = env_value
        elif yaml_value is not None:
            resolved[field] = str(yaml_value)
        else:
            resolved[field] = fallback
            used_fallback = True

    if used_fallback:
        logger.warning(
            "agent %r falling back to hardcoded default (provider=%s, model=%s); "
            "configure via CLI, env, or agents.yaml to silence",
            agent_name,
            resolved["provider"],
            resolved["model"],
        )

    return AgentConfig(provider=resolved["provider"], model=resolved["model"])
