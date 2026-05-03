"""Agent factories. Each factory returns a fresh ``agno.Agent`` per call.

No module-level Agent instances live here — see architecture §Anti-Patterns.
"""
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
from doc_extractor.agents.registry import FACTORIES
from doc_extractor.agents.tax_residency import create_tax_residency_agent
from doc_extractor.agents.verification_report import create_verification_report_agent
from doc_extractor.agents.verifier import create_verifier_agent
from doc_extractor.agents.visa import create_visa_agent

__all__ = [
    "FACTORIES",
    "create_application_form_agent",
    "create_bank_account_confirmation_agent",
    "create_bank_statement_agent",
    "create_company_extract_agent",
    "create_driver_licence_agent",
    "create_entity_ownership_agent",
    "create_national_id_agent",
    "create_other_agent",
    "create_passport_agent",
    "create_payment_receipt_agent",
    "create_pep_declaration_agent",
    "create_proof_of_address_agent",
    "create_tax_residency_agent",
    "create_verification_report_agent",
    "create_verifier_agent",
    "create_visa_agent",
]
