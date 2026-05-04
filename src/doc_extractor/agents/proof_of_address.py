"""ProofOfAddress agent factory — utility / council / bank / 户口本 documents."""
from __future__ import annotations

from agno.agent import Agent

from doc_extractor.agents.factory import VisionModelFactory
from doc_extractor.config.precedence import build_cli_overrides, resolve_agent_config
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.proof_of_address import ProofOfAddress

AGENT_NAME = "proof_of_address"


def create_proof_of_address_agent(
    provider: str | None = None, model: str | None = None
) -> Agent:
    """Construct a ProofOfAddress extraction agent.

    Same factory pattern as :func:`doc_extractor.agents.passport.create_passport_agent`.
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
        output_schema=ProofOfAddress,
    )
