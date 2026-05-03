"""PEP_Declaration agent factory — politically-exposed-person disclosures."""
from __future__ import annotations

from agno.agent import Agent

from doc_extractor.agents.factory import VisionModelFactory
from doc_extractor.config.precedence import resolve_agent_config
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.pep_declaration import PEP_Declaration

AGENT_NAME = "pep_declaration"


def create_pep_declaration_agent(provider: str | None = None) -> Agent:
    """Construct a PEP_Declaration extraction agent.

    Same factory pattern as :func:`doc_extractor.agents.passport.create_passport_agent`:
    precedence-resolved provider/model + versioned prompt + Pydantic
    ``output_schema=PEP_Declaration``. No module-level Agent state.
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
        output_schema=PEP_Declaration,
    )
