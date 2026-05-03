"""Agent registry — single dispatch table from ``DOC_TYPES`` to factory functions.

**All 15 specialists are real factories as of Story 5.5.** The Epic 5
sequence (Stories 5.1 → 5.2 → 5.3 → 5.4 → 5.5) progressively replaced
the ``_other_placeholder`` sentinel that was Story 4.5's seed for the
nine Epic 5 doc-types plus ``Other``; the placeholder is gone now and
every entry below points at a working ``create_*_agent`` function.

The vision pipeline reads :data:`FACTORIES` to look up the specialist for a
given ``Classification.doc_type``. Centralising the mapping here means
adding a new specialist requires touching exactly **five** production files
(per NFR19) — and the keys-equal-DOC_TYPES test in ``test_registry`` fails
loudly if any of them is forgotten.

Adding a new specialist (NFR19 — five-file extension cost)
-----------------------------------------------------------

1. ``src/doc_extractor/schemas/<name>.py`` *(or extend ``schemas/ids.py``
   for ID-class variants)* — Pydantic schema class derived from
   ``Frontmatter`` (or one of its subclasses).
2. ``src/doc_extractor/agents/<name>.py`` — factory function
   ``create_<name>_agent(provider: str | None = None) -> agno.Agent``,
   following the established pattern (resolve config → load prompt →
   ``VisionModelFactory.create`` → return ``Agent`` with ``output_schema``
   set, no module-level Agent state).
3. ``src/doc_extractor/prompts/<name>.md`` — versioned prompt (frontmatter
   ``agent``, ``version``, ``last_modified``).
4. ``src/doc_extractor/config/agents.yaml`` — provider/model entry keyed by
   the agent's snake-case name.
5. ``src/doc_extractor/agents/registry.py`` *(this file)* — add an entry to
   :data:`FACTORIES` mapping the ``DOC_TYPES`` literal to your factory.

Plus (test surface, not counted in the 5-file rule):

* ``tests/golden/<name>/README.md`` — golden corpus directory scaffold.
* ``tests/unit/test_<name>_agent.py`` — happy-path / provider-override /
  no-module-state coverage using ``MagicMock(spec=Model)``.

If you've added a 16th ``DOC_TYPES`` entry but skipped any of the five
files above, the keys-equal-DOC_TYPES sentinel in
``tests/unit/test_registry.py`` fails before the change can land.
"""
from __future__ import annotations

from collections.abc import Callable

from agno.agent import Agent

from doc_extractor.agents.application_form import create_application_form_agent
from doc_extractor.agents.bank_account_confirmation import (
    create_bank_account_confirmation_agent,
)
from doc_extractor.agents.bank_statement import create_bank_statement_agent
from doc_extractor.agents.company_extract import create_company_extract_agent
from doc_extractor.agents.driver_licence import create_driver_licence_agent
from doc_extractor.agents.entity_ownership import create_entity_ownership_agent
from doc_extractor.agents.national_id import create_national_id_agent
from doc_extractor.agents.other import create_other_agent
from doc_extractor.agents.passport import create_passport_agent
from doc_extractor.agents.payment_receipt import create_payment_receipt_agent
from doc_extractor.agents.pep_declaration import create_pep_declaration_agent
from doc_extractor.agents.proof_of_address import create_proof_of_address_agent
from doc_extractor.agents.tax_residency import create_tax_residency_agent
from doc_extractor.agents.verification_report import create_verification_report_agent
from doc_extractor.agents.visa import create_visa_agent

AgentFactory = Callable[..., Agent]

FACTORIES: dict[str, AgentFactory] = {
    # Epic 1 / 4 — ID-class specialists
    "Passport": create_passport_agent,
    "DriverLicence": create_driver_licence_agent,
    "NationalID": create_national_id_agent,
    "Visa": create_visa_agent,
    # Epic 3 — transactional specialist
    "PaymentReceipt": create_payment_receipt_agent,
    # Epic 5 — compliance documents (Story 5.1)
    "PEP_Declaration": create_pep_declaration_agent,
    "VerificationReport": create_verification_report_agent,
    "ApplicationForm": create_application_form_agent,
    # Epic 5 — bank documents (Story 5.2). BankStatement uses
    # `pdf_to_images(mode="all_pages")` per `_pdf_mode_for` in vision_path.
    "BankStatement": create_bank_statement_agent,
    "BankAccountConfirmation": create_bank_account_confirmation_agent,
    # Epic 5 — entity documents (Story 5.3). EntityOwnership is the first
    # specialist to emit a nested-object schema (UltimateBeneficialOwner).
    "CompanyExtract": create_company_extract_agent,
    "EntityOwnership": create_entity_ownership_agent,
    # Epic 5 — person-related documents (Story 5.4).
    "ProofOfAddress": create_proof_of_address_agent,
    "TaxResidency": create_tax_residency_agent,
    # Epic 5 catch-all (Story 5.5) — graceful-degradation surface for
    # documents the classifier didn't fit to one of the 14 typed
    # specialists. The only Haiku-default agent in the system.
    "Other": create_other_agent,
}
