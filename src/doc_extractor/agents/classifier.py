"""ClassifierAgent factory.

Constructs an Agno ``Agent`` with ``output_schema=Classification``. Resolves
provider/model via the precedence chain (Story 1.4), constructs the model
through ``VisionModelFactory`` (Story 1.3), and loads the versioned prompt
via ``load_prompt`` (Story 1.5). No module-level ``Agent`` instances —
construction is per-call so test isolation and per-run config overrides hold
(architecture Anti-Patterns).
"""

from __future__ import annotations

from agno.agent import Agent

from doc_extractor.agents.factory import VisionModelFactory
from doc_extractor.config.precedence import resolve_agent_config
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.classification import Classification

AGENT_NAME = "classifier"


def create_classifier_agent() -> Agent:
    """Construct a fresh classifier ``Agent`` ready to receive a vision input."""
    config = resolve_agent_config(AGENT_NAME)
    api_key = VisionModelFactory.validate_api_key(config.provider)
    model = VisionModelFactory.create(
        provider=config.provider,
        model_id=config.model,
        api_key=api_key,
    )
    prompt_text, _prompt_version = load_prompt(AGENT_NAME)
    return Agent(
        name="ClassifierAgent",
        model=model,
        instructions=[prompt_text],
        output_schema=Classification,
    )
