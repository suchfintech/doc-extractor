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
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

ENV_PREFIX = "DOC_EXTRACTOR"
AGENTS_YAML_PATH = Path(__file__).parent / "agents.yaml"


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
    for field, fallback in (("provider", DEFAULT_PROVIDER), ("model", DEFAULT_MODEL)):
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
