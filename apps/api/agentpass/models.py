from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    JSON,
    UniqueConstraint,
    CheckConstraint,
    Index,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, uid, now
from datetime import datetime


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Identity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret_ciphertext: Mapped[str | None] = mapped_column(Text)
    mfa_pending_ciphertext: Mapped[str | None] = mapped_column(Text)
    mfa_last_counter: Mapped[int | None] = mapped_column(BigInteger)


class Organization(Identity, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")
    __table_args__ = (CheckConstraint("status IN ('active','suspended')"),)


class Member(Identity, Base):
    __tablename__ = "organization_members"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        CheckConstraint("role IN ('owner','developer','viewer')"),
    )


class Project(Identity, Base):
    __tablename__ = "projects"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))


class Agent(Identity, Base):
    __tablename__ = "agents"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    __table_args__ = (
        CheckConstraint("status IN ('active','paused')"),
        UniqueConstraint("id", "organization_id", "owner_id", name="uq_agent_identity_tenant"),
    )


class Mandate(Identity, Base):
    __tablename__ = "mandates"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    categories: Mapped[list] = mapped_column(JSON)
    merchant_allowlist: Mapped[list] = mapped_column(JSON, default=list)
    merchant_denylist: Mapped[list] = mapped_column(JSON, default=list)
    per_transaction: Mapped[int] = mapped_column(BigInteger)
    daily_limit: Mapped[int] = mapped_column(BigInteger)
    weekly_limit: Mapped[int] = mapped_column(BigInteger)
    monthly_limit: Mapped[int] = mapped_column(BigInteger)
    approval_threshold: Mapped[int] = mapped_column(BigInteger)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint("id", "organization_id", "owner_id", "agent_id", name="uq_mandate_identity_tenant"),
        ForeignKeyConstraint(["agent_id", "organization_id", "owner_id"], ["agents.id", "agents.organization_id", "agents.owner_id"], name="fk_mandate_agent_tenant"),
        CheckConstraint(
            "per_transaction > 0 AND daily_limit > 0 AND weekly_limit > 0 AND monthly_limit > 0 AND approval_threshold > 0"
        ),
        CheckConstraint("valid_until > valid_from"),
        CheckConstraint("status IN ('active','revoked')"),
    )


class MandateVersion(Identity, Base):
    __tablename__ = "mandate_versions"
    mandate_id: Mapped[str] = mapped_column(ForeignKey("mandates.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    rules: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("mandate_id", "version"),)


class PaymentIntent(Identity, Base):
    __tablename__ = "payment_intents"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    mandate_id: Mapped[str] = mapped_column(ForeignKey("mandates.id"), index=True)
    merchant: Mapped[str] = mapped_column(String(120))
    merchant_id: Mapped[str | None] = mapped_column(String(120))
    order_id: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(120))
    fingerprint: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    structured_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    decision: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(30))
    reasons: Mapped[list] = mapped_column(JSON)
    evaluated_version: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint("id", "organization_id", "owner_id", name="uq_intent_identity_tenant"),
        UniqueConstraint("id", "mandate_id", "amount", name="uq_intent_budget_binding"),
        ForeignKeyConstraint(["mandate_id", "organization_id", "owner_id", "agent_id"], ["mandates.id", "mandates.organization_id", "mandates.owner_id", "mandates.agent_id"], name="fk_intent_mandate_tenant"),
        UniqueConstraint("agent_id", "idempotency_key"),
        CheckConstraint("amount > 0"),
        CheckConstraint("decision IN ('APPROVE','ASK','DENY')"),
        CheckConstraint(
            "status IN ('authorized','pending','denied','completed','cancelled','expired','executing','payment_pending','payment_unknown')"
        ),
        Index("ix_intents_org_created", "organization_id", "created_at"),
    )


class Evaluation(Identity, Base):
    __tablename__ = "policy_evaluations"
    intent_id: Mapped[str] = mapped_column(ForeignKey("payment_intents.id"), index=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    decision: Mapped[str] = mapped_column(String(10))
    reasons: Mapped[list] = mapped_column(JSON)
    rule_version: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(30))


class Reservation(Identity, Base):
    __tablename__ = "budget_reservations"
    intent_id: Mapped[str] = mapped_column(
        ForeignKey("payment_intents.id"), unique=True
    )
    mandate_id: Mapped[str] = mapped_column(ForeignKey("mandates.id"), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default="held")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(["intent_id", "mandate_id", "amount"], ["payment_intents.id", "payment_intents.mandate_id", "payment_intents.amount"], name="fk_reservation_exact_budget"),
        CheckConstraint("amount > 0"),
        CheckConstraint("status IN ('held','inflight','consumed','released','expired')"),
        Index("ix_reservation_budget", "mandate_id", "status", "created_at"),
    )


class Approval(Identity, Base):
    __tablename__ = "approval_requests"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    intent_id: Mapped[str] = mapped_column(
        ForeignKey("payment_intents.id"), unique=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(["intent_id", "organization_id", "owner_id"], ["payment_intents.id", "payment_intents.organization_id", "payment_intents.owner_id"], name="fk_approval_intent_tenant"),
        CheckConstraint(
            "status IN ('pending','approved','rejected','expired','invalidated')"
        ),
    )


class Transaction(Identity, Base):
    __tablename__ = "simulated_transactions"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    intent_id: Mapped[str] = mapped_column(
        ForeignKey("payment_intents.id"), unique=True
    )
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    receipt: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="simulated")
    __table_args__ = (ForeignKeyConstraint(["intent_id", "organization_id", "owner_id"], ["payment_intents.id", "payment_intents.organization_id", "payment_intents.owner_id"], name="fk_transaction_intent_tenant"),)


class APIKey(Identity, Base):
    __tablename__ = "api_keys"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    name: Mapped[str] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(20))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list] = mapped_column(
        JSON, default=lambda: ["intents:write", "intents:read"]
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginSession(Identity, Base):
    __tablename__ = "sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookEndpoint(Identity, Base):
    __tablename__ = "webhook_endpoints"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(500))
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class WebhookDelivery(Identity, Base):
    __tablename__ = "webhook_deliveries"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    endpoint_id: Mapped[str] = mapped_column(
        ForeignKey("webhook_endpoints.id"), index=True
    )
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now
    )
    last_error: Mapped[str | None] = mapped_column(String(200))
    response_status: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (Index("ix_webhook_queue", "status", "next_attempt_at"),)


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    actor_id: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[str] = mapped_column(String(80))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class RequestLog(Identity, Base):
    __tablename__ = "request_logs"
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    request_id: Mapped[str] = mapped_column(String(36))
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(200))
    status_code: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)


class RateWindow(Base):
    __tablename__ = "rate_windows"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    window: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)


class WebhookReceipt(Base):
    __tablename__ = "webhook_receipts"
    # Delivery ID is an external deduplication token, deliberately not a delivery FK:
    # receiver must not wait on the sender's in-flight delivery row lock.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    endpoint_id: Mapped[str] = mapped_column(
        ForeignKey("webhook_endpoints.id"), index=True
    )
    event: Mapped[str] = mapped_column(String(80))
    body_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ExecutionGrant(Identity, Base):
    __tablename__ = "execution_grants"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    intent_id: Mapped[str] = mapped_column(ForeignKey("payment_intents.id"), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    claims: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (ForeignKeyConstraint(["intent_id", "organization_id", "owner_id"], ["payment_intents.id", "payment_intents.organization_id", "payment_intents.owner_id"], name="fk_grant_intent_tenant"),)


class PaymentExecution(Identity, Base):
    __tablename__ = "payment_executions"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    intent_id: Mapped[str] = mapped_column(ForeignKey("payment_intents.id"), unique=True)
    grant_id: Mapped[str] = mapped_column(ForeignKey("execution_grants.id"), unique=True)
    provider: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    request_snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    provider_payment_id: Mapped[str | None] = mapped_column(String(120))
    provider_status: Mapped[str | None] = mapped_column(String(40))
    confirmation_url: Mapped[str | None] = mapped_column(String(1000))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    last_error: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        ForeignKeyConstraint(["intent_id", "organization_id", "owner_id"], ["payment_intents.id", "payment_intents.organization_id", "payment_intents.owner_id"], name="fk_execution_intent_tenant"),
        CheckConstraint("status IN ('queued','dispatching','pending','unknown','succeeded','cancelled','failed','refunded')"),
        Index("ix_execution_queue", "status", "next_attempt_at"),
    )


class SimulatorPayment(Identity, Base):
    """Independent provider journal: deliberately no FK to an uncommitted execution."""
    __tablename__ = "simulator_payments"
    organization_id: Mapped[str] = mapped_column(String(36), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    request_snapshot: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    receipt: Mapped[str | None] = mapped_column(String(80))
    __table_args__ = (CheckConstraint("status IN ('pending','succeeded','cancelled','refunded')"),)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
