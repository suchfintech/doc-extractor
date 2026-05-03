"""Agent factories. Each factory returns a fresh ``agno.Agent`` per call.

No module-level Agent instances live here — see architecture §Anti-Patterns.
"""
from doc_extractor.agents.passport import create_passport_agent
from doc_extractor.agents.payment_receipt import create_payment_receipt_agent

__all__ = ["create_passport_agent", "create_payment_receipt_agent"]
