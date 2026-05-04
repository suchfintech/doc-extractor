"""Sentinel: every specialist factory module must expose only constructors,
never a pre-built ``Agent`` singleton.

Pre-built singletons would leak provider/model state across runs and defeat
the YAML→CLI override precedence layered in ``config.precedence``. A single
parametrized check replaces the 15 duplicated copies that previously lived
inside each ``test_<doc_type>_agent.py``.
"""

from __future__ import annotations

import importlib

import pytest
from agno.agent import Agent

SPECIALIST_MODULES: tuple[str, ...] = (
    "doc_extractor.agents.application_form",
    "doc_extractor.agents.bank_account_confirmation",
    "doc_extractor.agents.bank_statement",
    "doc_extractor.agents.company_extract",
    "doc_extractor.agents.driver_licence",
    "doc_extractor.agents.entity_ownership",
    "doc_extractor.agents.national_id",
    "doc_extractor.agents.other",
    "doc_extractor.agents.passport",
    "doc_extractor.agents.payment_receipt",
    "doc_extractor.agents.pep_declaration",
    "doc_extractor.agents.proof_of_address",
    "doc_extractor.agents.tax_residency",
    "doc_extractor.agents.verification_report",
    "doc_extractor.agents.visa",
)


@pytest.mark.parametrize("module_name", SPECIALIST_MODULES)
def test_no_module_level_agent_attribute(module_name: str) -> None:
    module = importlib.import_module(module_name)
    public_attrs = {a for a in dir(module) if not a.startswith("_")}
    for name in public_attrs:
        value = getattr(module, name)
        assert not isinstance(value, Agent), (
            f"{module_name} exposes pre-built Agent at {name!r} — violates 'no global Agent' rule"
        )
