"""ApplicationForm agent factory — customer-onboarding / credit application forms."""
from __future__ import annotations

from agno.agent import Agent

from doc_extractor.agents.factory import VisionModelFactory
from doc_extractor.config.precedence import build_cli_overrides, resolve_agent_config
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.application_form import ApplicationForm

AGENT_NAME = "application_form"


def create_application_form_agent(
    provider: str | None = None, model: str | None = None
) -> Agent:
    """Construct an ApplicationForm extraction agent.

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
        output_schema=ApplicationForm,
    )
