from enum import StrEnum
from typing import Protocol
from pydantic import BaseModel, ConfigDict, Field


class PaymentStatus(StrEnum):
    PENDING = 'pending'
    REQUIRES_ACTION = 'requires_action'
    AUTHORIZED = 'authorized'
    SUCCEEDED = 'succeeded'
    CANCELLED = 'cancelled'
    REFUNDED = 'refunded'
    UNKNOWN = 'unknown'


class PaymentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    intent_id: str
    organization_id: str
    owner_id: str
    agent_id: str
    mandate_id: str
    mandate_version: int
    merchant: str
    merchant_id: str | None = None
    order_id: str | None = None
    amount: int = Field(strict=True, gt=0)
    currency: str
    description: str
    fingerprint: str
    provider: str


class ProviderPayment(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    payment_id: str
    status: PaymentStatus
    amount: int = Field(strict=True, gt=0)
    currency: str
    request_hash: str
    receipt: str | None = None
    confirmation_url: str | None = None
    test: bool = Field(strict=True)


class ProviderError(Exception):
    """Only a bounded code is persisted, never provider body/credentials."""
    def __init__(self, code='PROVIDER_UNAVAILABLE'):
        self.code = code
        super().__init__(code)


class PaymentProvider(Protocol):
    name: str
    def create_payment_intent(self, request: PaymentRequest, idempotency_key: str) -> ProviderPayment: ...
    def authorize_test_payment(self, payment_id: str, idempotency_key: str) -> ProviderPayment: ...
    def get_payment_status(self, payment_id: str) -> ProviderPayment: ...
    def cancel(self, payment_id: str, idempotency_key: str) -> ProviderPayment: ...
    def refund(self, payment_id: str, idempotency_key: str) -> ProviderPayment: ...
    def reconcile(self, payment_id: str | None, idempotency_key: str) -> ProviderPayment | None: ...
    def handle_callback(self, headers: dict[str, str], body: bytes) -> str: ...
