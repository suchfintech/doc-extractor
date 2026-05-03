"""Passport agent factory.

Single canonical constructor that wires together the four building blocks:

* :func:`config.precedence.resolve_agent_config` for provider/model selection
* :func:`prompts.loader.load_prompt` for the versioned prompt body
* :class:`agents.factory.VisionModelFactory` for the Agno model instance
* :class:`schemas.ids.Passport` as the typed ``output_schema``

No module-level Agent: each call returns a fresh ``agno.Agent``. This keeps
test isolation cheap (no shared session/history state) and aligns with the
"no global Agent instances" anti-pattern (architecture §Anti-Patterns).
"""
from __future__ import annotations

from agno.agent import Agent

from doc_extractor.agents.factory import VisionModelFactory
from doc_extractor.config.precedence import resolve_agent_config
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.ids import Passport

AGENT_NAME = "passport"


def create_passport_agent(provider: str | None = None) -> Agent:
    """Construct a Passport extraction agent.

    Resolution order for the model is the standard precedence chain:
    explicit ``provider`` arg > env vars > ``config/agents.yaml`` > hardcoded
    fallback. The prompt is loaded via the cached :func:`load_prompt`; the
    schema is :class:`Passport`.
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
        output_schema=Passport,
    )
