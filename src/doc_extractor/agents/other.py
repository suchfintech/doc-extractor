"""Other agent factory — catch-all specialist for documents that didn't
fit any of the 14 typed specialists.

Defaults to **Haiku** (not Sonnet, unlike every other Story 4-5 specialist)
because Other's contract is graceful-degradation OCR-style dump, not
high-precision typed extraction. Cheap-model is appropriate when the
output is loose by design.
"""
from __future__ import annotations

from agno.agent import Agent

from doc_extractor.agents.factory import VisionModelFactory
from doc_extractor.config.precedence import resolve_agent_config
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.other import Other

AGENT_NAME = "other"


def create_other_agent(provider: str | None = None) -> Agent:
    """Construct an Other catch-all extraction agent.

    Same factory pattern as :func:`doc_extractor.agents.passport.create_passport_agent`
    — but the resolved model defaults to Haiku, not Sonnet, per agents.yaml.
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
        output_schema=Other,
    )
