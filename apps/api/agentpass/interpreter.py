"""Untrusted language interpretation boundary; no authority over financial decisions.

An external model client must implement propose_json. No external model is enabled
or called by default. Only catalog product IDs and a minor-unit budget are accepted.
"""
from typing import Protocol
from pydantic import BaseModel, ConfigDict, Field
from .catalog import CATALOG, interpret
from .security import fail


class PurchaseProposal(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    product_id: str = Field(min_length=1,max_length=100)
    budget_minor: int = Field(strict=True,gt=0,le=100_000_000_000)


class LanguageModelClient(Protocol):
    def propose_json(self, prompt: str, catalog: list[dict]) -> dict: ...


class DeterministicInterpreter:
    name='deterministic-catalog'
    def propose(self,prompt):
        product,budget=interpret(prompt)
        return PurchaseProposal(product_id=product['id'],budget_minor=budget)


class StructuredLLMInterpreter:
    name='external-llm-proposal'
    def __init__(self,client:LanguageModelClient):
        self.client=client

    def propose(self,prompt):
        # The client has no database, user session, executor key or grant signer.
        proposal=PurchaseProposal.model_validate(self.client.propose_json(prompt,[dict(p) for p in CATALOG]))
        resolve(proposal)
        return proposal


def resolve(proposal:PurchaseProposal):
    product=next((p for p in CATALOG if p['id']==proposal.product_id),None)
    if not product or product['amount']>proposal.budget_minor:
        fail(422,'INVALID_PURCHASE_PROPOSAL','Предложение не соответствует каталогу или бюджету')
    return product,proposal.budget_minor
