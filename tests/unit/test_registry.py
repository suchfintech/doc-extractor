"""Coverage for the agents/registry FACTORIES dispatch table.

The two load-bearing assertions:

1. ``set(FACTORIES.keys()) == set(get_args(DOC_TYPES))`` — the keys-equal-
   DOC_TYPES sentinel that fails loudly if a 16th doc-type lands without a
   matching registry entry. This is what enforces the NFR19 5-file
   extension cost in CI.
2. **All 15 factories construct real Agno Agents (Story 5.5 closed Epic 5)**
   with the right ``output_schema``. There are no placeholders left.
"""
from __future__ import annotations

import os
from typing import Any, get_args
from unittest.mock import MagicMock

import pytest
from agno.agent import Agent
from agno.models.base import Model

from doc_extractor.agents import registry
from doc_extractor.agents.registry import FACTORIES
from doc_extractor.schemas.application_form import ApplicationForm
from doc_extractor.schemas.bank_account_confirmation import BankAccountConfirmation
from doc_extractor.schemas.bank_statement import BankStatement
from doc_extractor.schemas.classification import DOC_TYPES
from doc_extractor.schemas.company_extract import CompanyExtract
from doc_extractor.schemas.entity_ownership import EntityOwnership
from doc_extractor.schemas.ids import DriverLicence, NationalID, Passport, Visa
from doc_extractor.schemas.other import Other
from doc_extractor.schemas.payment_receipt import PaymentReceipt
from doc_extractor.schemas.pep_declaration import PEP_Declaration
from doc_extractor.schemas.proof_of_address import ProofOfAddress
from doc_extractor.schemas.tax_residency import TaxResidency
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
    # Story 5.4 — Epic 5 person-related documents promoted from _other_placeholder
    "ProofOfAddress": ProofOfAddress,
    "TaxResidency": TaxResidency,
    # Story 5.5 — Epic 5 catch-all promoted from _other_placeholder; closes Epic 5.
    "Other": Other,
}

# Story 5.5 emptied this tuple — every DOC_TYPES literal now has a real
# factory. The parametrized "placeholder" tests below become no-ops
# (parametrize over an empty list runs zero iterations), which is the
# desired end state. Future schema additions that ship without an agent
# would re-populate this tuple.
PLACEHOLDER_DOC_TYPES: tuple[str, ...] = ()


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
        other,
        passport,
        payment_receipt,
        pep_declaration,
        proof_of_address,
        tax_residency,
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
        proof_of_address,
        tax_residency,
        other,
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


def test_placeholder_doc_types_is_empty() -> None:
    """Story 5.5 closed Epic 5 — every DOC_TYPES literal has a real factory.

    Story 4.5 introduced ``_other_placeholder`` as a sentinel that raised
    NotImplementedError; Stories 5.1 → 5.2 → 5.3 → 5.4 → 5.5 progressively
    promoted each placeholder to a real factory. The placeholder symbol is
    gone from registry.py entirely now.
    """
    assert PLACEHOLDER_DOC_TYPES == ()
    assert not hasattr(registry, "_other_placeholder"), (
        "registry._other_placeholder should be removed now that no doc-type "
        "depends on it (Story 5.5 closed Epic 5)."
    )


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
