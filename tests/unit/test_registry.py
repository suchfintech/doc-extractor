"""Coverage for the agents/registry FACTORIES dispatch table.

The two load-bearing assertions:

1. ``set(FACTORIES.keys()) == set(get_args(DOC_TYPES))`` — the keys-equal-
   DOC_TYPES sentinel that fails loudly if a 16th doc-type lands without a
   matching registry entry. This is what enforces the NFR19 5-file
   extension cost in CI.
2. The five fully-implemented factories construct real Agno Agents (with
   the right ``output_schema``); the ten Epic 5 placeholders all share the
   same callable and raise ``NotImplementedError``.
"""
from __future__ import annotations

import os
from typing import Any, get_args
from unittest.mock import MagicMock

import pytest
from agno.agent import Agent
from agno.models.base import Model

from doc_extractor.agents import registry
from doc_extractor.agents.registry import FACTORIES, _other_placeholder
from doc_extractor.schemas.application_form import ApplicationForm
from doc_extractor.schemas.bank_account_confirmation import BankAccountConfirmation
from doc_extractor.schemas.bank_statement import BankStatement
from doc_extractor.schemas.classification import DOC_TYPES
from doc_extractor.schemas.company_extract import CompanyExtract
from doc_extractor.schemas.entity_ownership import EntityOwnership
from doc_extractor.schemas.ids import DriverLicence, NationalID, Passport, Visa
from doc_extractor.schemas.payment_receipt import PaymentReceipt
from doc_extractor.schemas.pep_declaration import PEP_Declaration
from doc_extractor.schemas.verification_report import VerificationReport

REAL_FACTORIES: dict[str, type] = {
    "Passport": Passport,
    "DriverLicence": DriverLicence,
    "NationalID": NationalID,
    "Visa": Visa,
    "PaymentReceipt": PaymentReceipt,
    # Story 5.1 — Epic 5 compliance documents promoted from _other_placeholder
    "PEP_Declaration": PEP_Declaration,
    "VerificationReport": VerificationReport,
    "ApplicationForm": ApplicationForm,
    # Story 5.2 — Epic 5 bank documents promoted from _other_placeholder
    "BankStatement": BankStatement,
    "BankAccountConfirmation": BankAccountConfirmation,
    # Story 5.3 — Epic 5 entity documents promoted from _other_placeholder
    "CompanyExtract": CompanyExtract,
    "EntityOwnership": EntityOwnership,
}

PLACEHOLDER_DOC_TYPES = (
    "ProofOfAddress",
    "TaxResidency",
    "Other",
)


@pytest.fixture(autouse=True)
def clear_doc_extractor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip DOC_EXTRACTOR_* env vars so the host shell can't leak into tests."""
    for key in list(os.environ):
        if key.startswith("DOC_EXTRACTOR_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def mocked_factory_deps(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock VisionModelFactory + load_prompt across every real factory module.

    The five real factories live in their own modules; each imports
    VisionModelFactory and load_prompt independently, so we patch each
    module's bound name. This lets us call FACTORIES["Passport"]() etc.
    offline.
    """
    from doc_extractor.agents import (
        application_form,
        bank_account_confirmation,
        bank_statement,
        company_extract,
        driver_licence,
        entity_ownership,
        national_id,
        passport,
        payment_receipt,
        pep_declaration,
        verification_report,
        visa,
    )

    def _make_model(**kwargs: Any) -> MagicMock:
        m = MagicMock(spec=Model)
        m.id = kwargs.get("model_id")
        return m

    for module in (
        passport,
        driver_licence,
        national_id,
        visa,
        payment_receipt,
        pep_declaration,
        verification_report,
        application_form,
        bank_statement,
        bank_account_confirmation,
        company_extract,
        entity_ownership,
    ):
        create_mock = MagicMock(side_effect=_make_model)
        validate_mock = MagicMock(return_value="test-api-key")
        load_prompt_mock = MagicMock(return_value=("PROMPT BODY", "0.1.0"))
        monkeypatch.setattr(module.VisionModelFactory, "create", create_mock)
        monkeypatch.setattr(
            module.VisionModelFactory, "validate_api_key", validate_mock
        )
        monkeypatch.setattr(module, "load_prompt", load_prompt_mock)


def test_factories_keys_exactly_cover_doc_types() -> None:
    """NFR19 sentinel: every DOC_TYPES literal must have a registry entry.

    A future contributor who appends a 16th doc-type but skips the registry
    edit will get a clear failure here pointing at the gap.
    """
    declared = set(get_args(DOC_TYPES))
    registered = set(FACTORIES.keys())
    assert registered == declared, (
        f"FACTORIES drift: missing {declared - registered}, "
        f"extras {registered - declared}"
    )


def test_factories_dict_has_fifteen_entries() -> None:
    """Anchor count — independent of the keys-equal test, catches a refactor
    that accidentally widens both DOC_TYPES and FACTORIES at once."""
    assert len(FACTORIES) == 15


@pytest.mark.parametrize("doc_type", sorted(REAL_FACTORIES.keys()))
def test_real_factories_construct_agents_with_correct_schema(
    doc_type: str,
    mocked_factory_deps: None,
) -> None:
    factory = FACTORIES[doc_type]
    agent = factory()

    assert isinstance(agent, Agent)
    assert agent.output_schema is REAL_FACTORIES[doc_type]


@pytest.mark.parametrize("doc_type", PLACEHOLDER_DOC_TYPES)
def test_placeholder_doc_types_all_route_to_other_placeholder(doc_type: str) -> None:
    """Epic 5 specialists + Other share the single ``_other_placeholder``.

    When Story 5.5 lands, the ``Other`` entry flips to the real factory and
    the nine Epic 5 specialists each replace their entry with their own
    factory. Until then, all ten share one callable.
    """
    assert FACTORIES[doc_type] is _other_placeholder


@pytest.mark.parametrize("doc_type", PLACEHOLDER_DOC_TYPES)
def test_placeholder_factory_raises_not_implemented(doc_type: str) -> None:
    factory = FACTORIES[doc_type]
    with pytest.raises(NotImplementedError, match="Specialist not yet implemented"):
        factory()


def test_factories_is_re_exported_from_package() -> None:
    """Sanity check on the public API surface — pipeline code reaches in via
    ``from doc_extractor.agents import FACTORIES``."""
    from doc_extractor.agents import FACTORIES as exported

    assert exported is FACTORIES


def test_registry_module_has_no_side_effect_state() -> None:
    """The registry must be a pure dispatch table — no Agent instances at
    module load time, no mutable globals beyond ``FACTORIES`` itself."""
    forbidden_types = (Agent,)
    for name in dir(registry):
        if name.startswith("_") and name.endswith("_"):
            continue
        if name == "FACTORIES":
            continue
        value = getattr(registry, name)
        assert not isinstance(value, forbidden_types), (
            f"Module-level Agent at {name!r} — violates 'no global Agent' rule"
        )
