"""Verifier agent factory.

Same pattern as the per-doc-type specialists: resolve provider/model via the
config precedence chain, load the versioned prompt, and assemble an
``agno.Agent`` with ``output_schema=VerifierAudit``. No module-level Agent —
each call returns a fresh instance.

The verifier is intentionally NOT a per-doc-type specialist: a single agent
audits whichever specialist just ran. The prompt is audit-framed (not
extraction-framed) so the verifier catches a different class of error than
re-running an extraction prompt would (architecture Decision 1).
"""
from __future__ import annotations

from agno.agent import Agent

from doc_extractor.agents.factory import VisionModelFactory
from doc_extractor.config.precedence import build_cli_overrides, resolve_agent_config
from doc_extractor.prompts.loader import load_prompt
from doc_extractor.schemas.verifier import VerifierAudit

AGENT_NAME = "verifier"


def create_verifier_agent(
    provider: str | None = None, model: str | None = None
) -> Agent:
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
        output_schema=VerifierAudit,
    )
