"""Visa agent factory.

Mirrors :func:`doc_extractor.agents.national_id.create_national_id_agent`:
precedence-resolved provider/model + versioned prompt + Pydantic
``output_schema=Visa``. No module-level Agent state — each call returns
a fresh ``agno.Agent``.
"""
from __future__ import annotations

from agno.agent import Agent

from doc_extractor.agents.factory import VisionModelFactory
from doc_extractor.config.precedence import build_cli_overrides, resolve_agent_config
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.ids import Visa

AGENT_NAME = "visa"


def create_visa_agent(
    provider: str | None = None, model: str | None = None
) -> Agent:
    """Construct a Visa extraction agent.

    Both ``provider`` and ``model`` route through the precedence chain as
    CLI overrides.
    """
    cfg = resolve_agent_config(
        AGENT_NAME,
        cli_overrides=build_cli_overrides(provider=provider, model=model),
    )
    prompt_text, _prompt_version = load_prompt(AGENT_NAME)
    api_key = VisionModelFactory.validate_api_key(cfg.provider)
    model = VisionModelFactory.create(
        provider=cfg.provider,
        model_id=cfg.model,
        api_key=api_key,
    )
    return Agent(
        model=model,
        instructions=[prompt_text],
        output_schema=Visa,
    )
