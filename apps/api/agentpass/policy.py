"""Deterministic authority checks. All budget writers lock the mandate row first."""

from datetime import timedelta
import hashlib, json
from sqlalchemy import select, func, text, or_, and_
from .db import now, uid
from .models import (
    Agent,
    Mandate,
    PaymentIntent,
    Reservation,
    Evaluation,
    Approval,
    Transaction,
    AuditEvent,
    WebhookEndpoint,
    WebhookDelivery,
)
from .security import fail, Principal
from .schemas import IntentIn
from .grants import fingerprint as request_fingerprint, verify_intent
from .config import settings

REASONS = {
    "AGENT_INACTIVE": "Агент приостановлен",
    "MANDATE_REVOKED": "Полномочия отозваны",
    "MANDATE_NOT_STARTED": "Срок полномочий ещё не начался",
    "MANDATE_EXPIRED": "Срок полномочий истёк",
    "CURRENCY_MISMATCH": "Валюта не соответствует мандату",
    "CATEGORY_DENIED": "Категория не разрешена",
    "MERCHANT_DENIED": "Продавец запрещён",
    "MERCHANT_NOT_ALLOWED": "Продавец отсутствует в списке разрешённых",
    "PER_TRANSACTION_LIMIT": "Превышен лимит одной операции",
    "DAILY_LIMIT": "Превышен дневной бюджет",
    "WEEKLY_LIMIT": "Превышен недельный бюджет",
    "MONTHLY_LIMIT": "Превышен месячный бюджет",
    "APPROVAL_REQUIRED": "Сумма достигла порога подтверждения",
    "POLICY_MATCH": "Операция соответствует всем правилам",
    "USER_REJECTED": "Пользователь отклонил запрос",
    "APPROVAL_EXPIRED": "Время подтверждения истекло",
    "RULES_CHANGED": "Правила изменились до исполнения",
    "RESERVATION_EXPIRED": "Резерв истёк",
    "CANCELLED": "Операция отменена",
}


def reasons(codes):
    return [{"code": code, "message": REASONS[code]} for code in codes]


def audit(db, p, action, resource_id, details=None):
    db.add(
        AuditEvent(
            organization_id=p.organization_id,
            actor_id=p.actor,
            action=action,
            resource_id=resource_id,
            details=details or {},
        )
    )


def emit(db, org, event, intent):
    payload = {
        "id": uid(),
        "event": event,
        "created_at": now().isoformat(),
        "data": {
            "intent_id": intent.id,
            "decision": intent.decision,
            "status": intent.status,
            "amount": intent.amount,
            "currency": intent.currency,
            "agent_id": intent.agent_id,
            "mandate_id": intent.mandate_id,
        },
    }
    for endpoint in db.scalars(
        select(WebhookEndpoint).where(
            WebhookEndpoint.organization_id == org, WebhookEndpoint.active.is_(True)
        )
    ):
        db.add(
            WebhookDelivery(
                organization_id=org, endpoint_id=endpoint.id, payload=payload
            )
        )


def owned_mandate(db, p, mandate_id, lock=True):
    m = db.get(Mandate, mandate_id)
    if not m or m.organization_id != p.organization_id or m.owner_id != p.user_id:
        fail(404, "MANDATE_NOT_FOUND", "Мандат не найден")
    if p.agent_id and m.agent_id != p.agent_id:
        fail(404, "MANDATE_NOT_FOUND", "Мандат не найден")
    # Consistent lock order: agent → mandate → intent → approval/reservation.
    a = (
        db.scalar(select(Agent).where(Agent.id == m.agent_id).with_for_update())
        if lock
        else db.get(Agent, m.agent_id)
    )
    if lock:
        m = db.scalar(
            select(Mandate)
            .where(Mandate.id == mandate_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    return m, a


def expire_for_mandate(db, m, instant=None):
    instant = instant or now()
    held = list(
        db.scalars(
            select(Reservation).where(
                Reservation.mandate_id == m.id,
                Reservation.status == "held",
                Reservation.expires_at <= instant,
            )
        )
    )
    for r in held:
        r.status = "expired"
        intent = db.get(PaymentIntent, r.intent_id)
        if intent.status == "authorized":
            intent.status = "expired"
            intent.reasons = reasons(["RESERVATION_EXPIRED"])
            emit(db, m.organization_id, "intent.expired", intent)
            audit(
                db,
                Principal("system", m.organization_id, "system"),
                "reservation.expired",
                intent.id,
            )
    pending = list(
        db.scalars(
            select(Approval)
            .join(PaymentIntent, Approval.intent_id == PaymentIntent.id)
            .where(
                PaymentIntent.mandate_id == m.id,
                Approval.status == "pending",
                Approval.expires_at <= instant,
            )
        )
    )
    for a in pending:
        a.status = "expired"
        a.resolved_at = instant
        intent = db.get(PaymentIntent, a.intent_id)
        intent.status = "expired"
        intent.decision = "DENY"
        intent.reasons = reasons(["APPROVAL_EXPIRED"])
        db.add(
            Evaluation(
                intent_id=intent.id,
                organization_id=m.organization_id,
                decision="DENY",
                reasons=intent.reasons,
                rule_version=m.version,
                stage="expiry",
            )
        )
        emit(db, m.organization_id, "approval.expired", intent)
        audit(
            db,
            Principal("system", m.organization_id, "system"),
            "approval.expired",
            a.id,
        )
    db.flush()


def budget_usage(db, m, instant=None, exclude_intent=None):
    instant = instant or now()
    day = instant.replace(hour=0, minute=0, second=0, microsecond=0)
    week = day - timedelta(days=day.weekday())
    month = day.replace(day=1)
    result = {}
    for name, start in [("daily", day), ("weekly", week), ("monthly", month)]:
        stmt = select(func.coalesce(func.sum(Reservation.amount), 0)).where(
            Reservation.mandate_id == m.id,
            or_(
                Reservation.status == "inflight",
                and_(Reservation.created_at >= start, or_(
                    Reservation.status == "consumed",
                    and_(Reservation.status == "held", Reservation.expires_at > instant),
                )),
            ),
        )
        if exclude_intent:
            stmt = stmt.where(Reservation.intent_id != exclude_intent)
        result[name] = db.scalar(stmt)
    return result


def check_rules(m, agent, intent, usage, confirmed=False, instant=None):
    instant = instant or now()
    codes = []
    if agent.status != "active":
        codes.append("AGENT_INACTIVE")
    if m.status != "active":
        codes.append("MANDATE_REVOKED")
    if instant < m.valid_from:
        codes.append("MANDATE_NOT_STARTED")
    if instant >= m.valid_until:
        codes.append("MANDATE_EXPIRED")
    if intent.currency != m.currency:
        codes.append("CURRENCY_MISMATCH")
    if intent.category.strip().casefold() not in m.categories:
        codes.append("CATEGORY_DENIED")
    merchant = intent.merchant.strip().casefold()
    if merchant in m.merchant_denylist:
        codes.append("MERCHANT_DENIED")
    if m.merchant_allowlist and merchant not in m.merchant_allowlist:
        codes.append("MERCHANT_NOT_ALLOWED")
    if intent.amount > m.per_transaction:
        codes.append("PER_TRANSACTION_LIMIT")
    for period, code in [
        ("daily", "DAILY_LIMIT"),
        ("weekly", "WEEKLY_LIMIT"),
        ("monthly", "MONTHLY_LIMIT"),
    ]:
        if usage[period] + intent.amount > getattr(m, period + "_limit"):
            codes.append(code)
    if codes:
        return "DENY", reasons(codes)
    if intent.amount >= m.approval_threshold and not confirmed:
        return "ASK", reasons(["APPROVAL_REQUIRED"])
    return "APPROVE", reasons(["POLICY_MATCH"])


def record_evaluation(db, intent, m, decision, why, stage):
    intent.decision = decision
    intent.reasons = why
    intent.evaluated_version = m.version
    intent.status = {"APPROVE": "authorized", "ASK": "pending", "DENY": "denied"}[
        decision
    ]
    db.add(
        Evaluation(
            intent_id=intent.id,
            organization_id=m.organization_id,
            decision=decision,
            reasons=why,
            rule_version=m.version,
            stage=stage,
        )
    )


def reserve(db, intent, m):
    db.add(
        Reservation(
            intent_id=intent.id,
            mandate_id=m.id,
            amount=intent.amount,
            expires_at=now() + timedelta(minutes=15),
        )
    )


def create_intent(db, p: Principal, data: IntentIn):
    if p.role == "viewer":
        fail(403, "FORBIDDEN", "Наблюдатель не может инициировать операции")
    if settings().environment in ('pilot','production') and (not data.merchant_id or not data.order_id):
        fail(422, 'MERCHANT_ORDER_REQUIRED', 'Pilot требует явные merchant_id и order_id')
    # An agent-bound API key and a user-owned demo console both authenticate the caller.
    if p.agent_id and p.agent_id != data.agent_id:
        fail(403, "AGENT_MISMATCH", "Ключ привязан к другому агенту")
    fingerprint = request_fingerprint(data)
    lock_key = f"{p.organization_id}:{data.agent_id}:{data.idempotency_key}"
    lock_num = int.from_bytes(
        hashlib.sha256(lock_key.encode()).digest()[:8], "big", signed=True
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_num})
    existing = db.scalar(
        select(PaymentIntent).where(
            PaymentIntent.agent_id == data.agent_id,
            PaymentIntent.idempotency_key == data.idempotency_key,
        )
    )
    if existing:
        if (
            existing.organization_id != p.organization_id
            or existing.owner_id != p.user_id
        ):
            fail(404, "INTENT_NOT_FOUND", "Операция не найдена")
        if existing.fingerprint != fingerprint:
            fail(409, "IDEMPOTENCY_CONFLICT", "Ключ уже использован с другим запросом")
        return existing
    if abs((now() - data.timestamp).total_seconds()) > 300:
        fail(422, "STALE_TIMESTAMP", "Timestamp должен быть в пределах пяти минут")
    m, agent = owned_mandate(db, p, data.mandate_id)
    if m.agent_id != data.agent_id:
        fail(404, "MANDATE_NOT_FOUND", "Мандат не найден для агента")
    expire_for_mandate(db, m)
    decision, why = check_rules(m, agent, data, budget_usage(db, m))
    intent = PaymentIntent(
        id=uid(),
        organization_id=m.organization_id,
        owner_id=m.owner_id,
        fingerprint=fingerprint,
        decision=decision,
        status="pending",
        reasons=why,
        evaluated_version=m.version,
        **data.model_dump(),
    )
    db.add(intent)
    db.flush()
    record_evaluation(db, intent, m, decision, why, "initial")
    if decision == "APPROVE":
        reserve(db, intent, m)
    if decision == "ASK":
        db.add(
            Approval(
                organization_id=m.organization_id,
                owner_id=m.owner_id,
                intent_id=intent.id,
                expires_at=now() + timedelta(minutes=15),
            )
        )
    audit(
        db,
        p,
        "intent.evaluated",
        intent.id,
        {
            "decision": decision,
            "rule_version": m.version,
            "codes": [r["code"] for r in why],
        },
    )
    emit(db, p.organization_id, "intent.evaluated", intent)
    db.flush()
    return intent


def owned_intent(db, p, intent_id):
    i = db.get(PaymentIntent, intent_id)
    if (
        not i
        or i.organization_id != p.organization_id
        or i.owner_id != p.user_id
        or (p.agent_id and i.agent_id != p.agent_id)
    ):
        fail(404, "INTENT_NOT_FOUND", "Операция не найдена")
    return i


def resolve_approval(db, p, approval_id, action):
    p.user()
    if p.role == "viewer":
        fail(403, "FORBIDDEN", "Нет прав подтверждения")
    a = db.get(Approval, approval_id)
    if not a or a.organization_id != p.organization_id or a.owner_id != p.user_id:
        fail(404, "APPROVAL_NOT_FOUND", "Запрос не найден")
    intent = owned_intent(db, p, a.intent_id)
    verify_intent(intent)
    m, agent = owned_mandate(db, p, intent.mandate_id)
    intent = db.scalar(
        select(PaymentIntent)
        .where(PaymentIntent.id == intent.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    a = db.scalar(
        select(Approval)
        .where(Approval.id == a.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if a.status != "pending":
        fail(409, "APPROVAL_ALREADY_RESOLVED", "Подтверждение уже использовано")
    if a.expires_at <= now():
        a.status = "expired"
        a.resolved_at = now()
        record_evaluation(
            db, intent, m, "DENY", reasons(["APPROVAL_EXPIRED"]), "approval"
        )
        intent.status = "expired"
    elif action == "reject":
        a.status = "rejected"
        a.resolved_at = now()
        record_evaluation(db, intent, m, "DENY", reasons(["USER_REJECTED"]), "approval")
    else:
        expire_for_mandate(db, m)
        decision, why = check_rules(
            m, agent, intent, budget_usage(db, m), confirmed=True
        )
        record_evaluation(db, intent, m, decision, why, "approval")
        a.status = "approved" if decision == "APPROVE" else "invalidated"
        a.resolved_at = now()
        if decision == "APPROVE":
            reserve(db, intent, m)
    audit(
        db,
        p,
        "approval." + a.status,
        a.id,
        {"intent_id": intent.id, "decision": intent.decision},
    )
    emit(db, p.organization_id, "approval.resolved", intent)
    db.flush()
    return intent


def execute_intent(db, p, intent_id):
    if settings().environment not in ("sandbox", "development"):
        fail(403, "EXECUTION_GRANT_REQUIRED", "Используйте отдельного исполнителя и Execution Grant")
    if p.role == "viewer":
        fail(403, "FORBIDDEN", "Нет прав исполнения")
    intent = owned_intent(db, p, intent_id)
    verify_intent(intent)
    m, agent = owned_mandate(db, p, intent.mandate_id)
    intent = db.scalar(
        select(PaymentIntent)
        .where(PaymentIntent.id == intent.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if intent.status == "completed":
        return intent
    if intent.status != "authorized":
        fail(409, "NOT_AUTHORIZED", "Операция не имеет действующего разрешения")
    r = db.scalar(
        select(Reservation).where(Reservation.intent_id == intent.id).with_for_update()
    )
    expire_for_mandate(db, m)
    if r.status != "held":
        # Persist expiry as a business result, not an exception rollback.
        return intent
    decision, why = check_rules(
        m, agent, intent, budget_usage(db, m, exclude_intent=intent.id), confirmed=True
    )
    if intent.evaluated_version != m.version:
        decision, why = "DENY", reasons(["RULES_CHANGED"])
    if decision != "APPROVE":
        r.status = "released"
        record_evaluation(db, intent, m, "DENY", why, "execution")
        emit(db, p.organization_id, "intent.invalidated", intent)
        audit(db, p, "intent.invalidated", intent.id)
        return intent
    # Legacy API remains a local-only simulator, now using the same provider contract.
    from .grants import issue_grant
    from .payments.local import LocalPaymentProvider, request_hash
    from .payments.base import PaymentRequest, PaymentStatus
    from .models import PaymentExecution
    grant, _ = issue_grant(db, p, intent.id)
    request = PaymentRequest.model_validate(grant.claims["payment"])
    provider = LocalPaymentProvider(session=db)
    payment = provider.create_payment_intent(request, "ap:" + intent.id)
    payment = provider.authorize_test_payment(payment.payment_id, "ap:" + intent.id)
    if payment.status != PaymentStatus.SUCCEEDED or payment.request_hash != request_hash(request) or not payment.test:
        fail(409, "PROVIDER_NOT_CONFIRMED", "Провайдер не подтвердил симулированную покупку")
    grant.consumed_at = now()
    db.add(PaymentExecution(organization_id=p.organization_id, owner_id=p.user_id,
        agent_id=intent.agent_id, intent_id=intent.id, grant_id=grant.id,
        provider="local_simulator", idempotency_key="ap:" + intent.id,
        request_snapshot=grant.claims["payment"], status="succeeded",
        provider_payment_id=payment.payment_id, provider_status=payment.status.value))
    # Re-date reservation at execution after rechecking current UTC budget windows.
    r.created_at = now()
    r.status = "consumed"
    intent.status = "completed"
    db.add(
        Transaction(
            organization_id=p.organization_id,
            owner_id=p.user_id,
            intent_id=intent.id,
            amount=intent.amount,
            currency=intent.currency,
            receipt=payment.receipt,
        )
    )
    audit(db, p, "transaction.simulated", intent.id)
    emit(db, p.organization_id, "transaction.simulated", intent)
    db.flush()
    return intent


def cancel_intent(db, p, intent_id):
    if p.role == "viewer":
        fail(403, "FORBIDDEN", "Нет прав отмены")
    intent = owned_intent(db, p, intent_id)
    m, _ = owned_mandate(db, p, intent.mandate_id)
    intent = db.scalar(
        select(PaymentIntent)
        .where(PaymentIntent.id == intent.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if intent.status == "cancelled":
        return intent
    if intent.status not in ("authorized", "pending"):
        fail(409, "NOT_CANCELLABLE", "Операция уже завершена")
    r = db.scalar(select(Reservation).where(Reservation.intent_id == intent.id))
    if r and r.status == "held":
        r.status = "released"
    a = db.scalar(select(Approval).where(Approval.intent_id == intent.id))
    if a and a.status == "pending":
        a.status = "invalidated"
        a.resolved_at = now()
    intent.status = "cancelled"
    intent.reasons = reasons(["CANCELLED"])
    audit(db, p, "intent.cancelled", intent.id)
    emit(db, p.organization_id, "intent.cancelled", intent)
    db.flush()
    return intent
