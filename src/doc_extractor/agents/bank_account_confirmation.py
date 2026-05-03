"""BankAccountConfirmation agent factory — single-page bank-letter extraction."""
from __future__ import annotations

from agno.agent import Agent

from doc_extractor.agents.factory import VisionModelFactory
from doc_extractor.config.precedence import resolve_agent_config
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.bank_account_confirmation import BankAccountConfirmation

AGENT_NAME = "bank_account_confirmation"


def create_bank_account_confirmation_agent(provider: str | None = None) -> Agent:
    """Construct a BankAccountConfirmation extraction agent.

    Same factory pattern as :func:`doc_extractor.agents.passport.create_passport_agent`.
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
        output_schema=BankAccountConfirmation,
    )
