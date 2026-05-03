"""Agent registry — single dispatch table from ``DOC_TYPES`` to factory functions.

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
from doc_extractor.agents.driver_licence import create_driver_licence_agent
from doc_extractor.agents.national_id import create_national_id_agent
from doc_extractor.agents.passport import create_passport_agent
from doc_extractor.agents.payment_receipt import create_payment_receipt_agent
from doc_extractor.agents.pep_declaration import create_pep_declaration_agent
from doc_extractor.agents.verification_report import create_verification_report_agent
from doc_extractor.agents.visa import create_visa_agent

AgentFactory = Callable[..., Agent]


def _other_placeholder(provider: str | None = None) -> Agent:
    """Sentinel factory for doc-types whose real specialist hasn't shipped yet.

    Routes the nine Epic 5 specialists (and ``Other``) here until Story 5.5
    lands the real ``create_other_agent``. Raises rather than silently
    returning a degraded Agent so callers see a clear error in CI / logs
    rather than a low-quality extraction with the wrong schema.
    """
    del provider
    raise NotImplementedError(
        "Specialist not yet implemented — Story 5.5 will replace this placeholder. "
        "Until then, doc-types routed here cannot be extracted via the vision pipeline."
    )


FACTORIES: dict[str, AgentFactory] = {
    # Epic 1 / 4 — fully implemented specialists
    "Passport": create_passport_agent,
    "DriverLicence": create_driver_licence_agent,
    "NationalID": create_national_id_agent,
    "Visa": create_visa_agent,
    # Epic 3 — fully implemented
    "PaymentReceipt": create_payment_receipt_agent,
    # Epic 5 — compliance documents (Story 5.1)
    "PEP_Declaration": create_pep_declaration_agent,
    "VerificationReport": create_verification_report_agent,
    "ApplicationForm": create_application_form_agent,
    # Epic 5 — bank documents (Story 5.2). BankStatement uses
    # `pdf_to_images(mode="all_pages")` per `_pdf_mode_for` in vision_path.
    "BankStatement": create_bank_statement_agent,
    "BankAccountConfirmation": create_bank_account_confirmation_agent,
    # Epic 5 — placeholders (replace with real factories as each ships):
    "CompanyExtract": _other_placeholder,
    "EntityOwnership": _other_placeholder,
    "ProofOfAddress": _other_placeholder,
    "TaxResidency": _other_placeholder,
    # Catch-all — Story 5.5 wires this to the real Other agent
    "Other": _other_placeholder,
}
