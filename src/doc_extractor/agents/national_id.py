"""NationalID agent factory.

Mirrors :func:`doc_extractor.agents.driver_licence.create_driver_licence_agent`:
precedence-resolved provider/model + versioned prompt + Pydantic
``output_schema=NationalID``. No module-level Agent state — each call
returns a fresh ``agno.Agent``.
"""
from __future__ import annotations

from agno.agent import Agent

from doc_extractor.agents.factory import VisionModelFactory
from doc_extractor.config.precedence import resolve_agent_config
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.ids import NationalID

AGENT_NAME = "national_id"


def create_national_id_agent(provider: str | None = None) -> Agent:
    """Construct a NationalID extraction agent.

    The optional ``provider`` argument routes through the precedence chain
    as a CLI override.
    """
    cli_overrides = {"provider": provider} if provider else None
    cfg = resolve_agent_config(AGENT_NAME, cli_overrides=cli_overrides)
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
        output_schema=NationalID,
    )
