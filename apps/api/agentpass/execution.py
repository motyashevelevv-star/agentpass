"""Transactional execution outbox; provider I/O runs AFTER committing a claim.

A timeout/crash is uncertain, never a successful payment or a released budget.
Retries use the same provider idempotency identity; terminal evidence is validated.
"""
import hmac
from datetime import timedelta
from sqlalchemy import select, or_, and_
from .config import settings
from .db import SessionLocal, now, uid
from .models import (PaymentIntent, PaymentExecution, ExecutionGrant, Reservation,
                     Transaction, Organization, Member)
from .security import fail, digest, Principal
from .grants import decode_token, snapshot, verify_intent
from .policy import (owned_intent, owned_mandate, budget_usage, check_rules,
                     audit, emit, reasons, record_evaluation)
from .payments.base import PaymentRequest, PaymentStatus, ProviderError
from .payments.local import LocalPaymentProvider, request_hash


def provider_for(name, session=None):
    if name == 'local_simulator':
        return LocalPaymentProvider(session=session)
    if name == 'yookassa_sandbox' and settings().yookassa_sandbox_enabled:
        from .payments.yookassa import YooKassaSandbox
        config=settings()
        return YooKassaSandbox(config.yookassa_shop_id,config.yookassa_secret_key,config.payment_return_url)
    raise ProviderError('PROVIDER_NOT_ENABLED')


def owned_execution(db, p, execution_id):
    row = db.get(PaymentExecution, execution_id)
    if (not row or row.organization_id != p.organization_id or row.owner_id != p.user_id
        or (p.agent_id and row.agent_id != p.agent_id)):
        fail(404, 'EXECUTION_NOT_FOUND', 'Исполнение не найдено')
    return row


def submit_execution(db, p, token):
    claims = decode_token(token)
    bound = claims['payment']
    intent = owned_intent(db, p, bound.get('intent_id'))
    m, agent = owned_mandate(db, p, intent.mandate_id)
    intent = db.scalar(select(PaymentIntent).where(PaymentIntent.id == intent.id).with_for_update().execution_options(populate_existing=True))
    grant = db.scalar(select(ExecutionGrant).where(ExecutionGrant.id == claims.get('jti')).with_for_update())
    if not grant or not hmac.compare_digest(grant.token_hash, digest(token)) or grant.intent_id != intent.id:
        fail(401, 'INVALID_EXECUTION_GRANT', 'Разрешение не найдено')
    if grant.organization_id != p.organization_id or grant.owner_id != p.user_id or grant.agent_id != intent.agent_id:
        fail(404, 'EXECUTION_NOT_FOUND', 'Разрешение не найдено')
    if p.role not in ('owner', 'developer', 'agent', 'executor'):
        fail(403, 'FORBIDDEN', 'Нет прав исполнения')
    if settings().environment in ('pilot', 'production') and p.role != 'executor':
        fail(403, 'TRUSTED_EXECUTOR_REQUIRED', 'Нужен отдельный ключ доверенного исполнителя')
    existing = db.scalar(select(PaymentExecution).where(PaymentExecution.intent_id == intent.id))
    if existing:
        if existing.grant_id != grant.id:
            fail(409, 'EXECUTION_CONFLICT', 'Намерение уже имеет другое исполнение')
        return existing
    if grant.consumed_at or grant.expires_at <= now() or claims['exp'] <= int(now().timestamp()):
        fail(409, 'GRANT_EXPIRED_OR_USED', 'Разрешение истекло или использовано')
    if bound != snapshot(intent, bound.get('provider')) or grant.claims != claims:
        fail(409, 'GRANT_BINDING_MISMATCH', 'Параметры исполнения не соответствуют разрешению')
    if intent.status != 'authorized' or intent.evaluated_version != m.version:
        fail(409, 'NOT_AUTHORIZED', 'Полномочия изменились')
    reservation = db.scalar(select(Reservation).where(Reservation.intent_id == intent.id).with_for_update())
    if not reservation or reservation.status != 'held' or reservation.expires_at <= now():
        fail(409, 'RESERVATION_EXPIRED', 'Резерв истёк')
    decision, _ = check_rules(m, agent, intent, budget_usage(db, m, exclude_intent=intent.id), confirmed=True)
    if decision != 'APPROVE':
        fail(409, 'NOT_AUTHORIZED', 'Правила или лимиты изменились')
    grant.consumed_at = now()
    execution = PaymentExecution(id=uid(), organization_id=p.organization_id, owner_id=p.user_id,
        agent_id=intent.agent_id, intent_id=intent.id, grant_id=grant.id,
        provider=bound['provider'], idempotency_key='ap:'+intent.id,
        request_snapshot=bound, status='queued')
    db.add(execution)
    intent.status = 'executing'
    audit(db, p, 'execution.queued', execution.id, {'intent_id': intent.id, 'grant_id': grant.id})
    emit(db, p.organization_id, 'execution.queued', intent)
    db.flush()
    return execution


def _lock_execution(db, execution_id):
    row = db.get(PaymentExecution, execution_id)
    if not row:
        return None
    db.scalar(select(Organization).where(Organization.id == row.organization_id).with_for_update(read=True))
    db.scalar(select(Member).where(Member.organization_id == row.organization_id, Member.user_id == row.owner_id).with_for_update(read=True))
    p = Principal(row.owner_id, row.organization_id, 'executor', agent_id=row.agent_id)
    m, agent = owned_mandate(db, p, db.get(PaymentIntent, row.intent_id).mandate_id)
    i = db.scalar(select(PaymentIntent).where(PaymentIntent.id == row.intent_id).with_for_update().execution_options(populate_existing=True))
    e = db.scalar(select(PaymentExecution).where(PaymentExecution.id == row.id).with_for_update().execution_options(populate_existing=True))
    return p, m, agent, i, e


def _claim(execution_id=None):
    with SessionLocal.begin() as db:
        # The claim uses the same financial lock order as API mutations. No I/O under locks.
        instant = now()
        candidate = select(PaymentExecution.id).where(
            PaymentExecution.status.in_(['queued','dispatching','pending','unknown']),
            PaymentExecution.next_attempt_at <= instant,
            or_(PaymentExecution.lease_until.is_(None), PaymentExecution.lease_until <= instant))
        if not execution_id:
            candidate = candidate.where(PaymentExecution.attempts < 10)
        if execution_id:
            candidate = candidate.where(PaymentExecution.id == execution_id)
        candidate_id = db.scalar(candidate.order_by(PaymentExecution.created_at).limit(1))
        if not candidate_id:
            return None
        p, m, agent, intent, row = _lock_execution(db, candidate_id)
        if row.status not in ('queued','dispatching','pending','unknown') or (row.lease_until and row.lease_until > instant) or row.next_attempt_at > instant:
            return None
        verify_intent(intent)
        reservation = db.scalar(select(Reservation).where(Reservation.intent_id == intent.id).with_for_update())
        first_dispatch = row.status == 'queued'
        if first_dispatch:
            org = db.get(Organization, row.organization_id)
            member = db.scalar(select(Member).where(Member.organization_id == row.organization_id, Member.user_id == row.owner_id))
            grant = db.get(ExecutionGrant, row.grant_id)
            valid_access = org.status == 'active' and member and member.role in ('owner','developer')
            decision, why = check_rules(m, agent, intent, budget_usage(db, m, exclude_intent=intent.id), confirmed=True)
            if (not valid_access or decision != 'APPROVE' or m.version != intent.evaluated_version
                or not reservation or reservation.status != 'held' or reservation.expires_at <= instant
                or grant.expires_at <= instant):
                row.status, row.last_error = 'cancelled', 'AUTHORIZATION_EXPIRED_OR_REVOKED'
                if reservation and reservation.status == 'held':
                    reservation.status = 'released'
                record_evaluation(db, intent, m, 'DENY', why if decision != 'APPROVE' else reasons(['RULES_CHANGED']), 'dispatch')
                audit(db, p, 'execution.cancelled_before_dispatch', row.id)
                emit(db, row.organization_id, 'execution.cancelled', intent)
                return None
            reservation.status, reservation.created_at = 'inflight', instant
        row.status = 'dispatching'
        row.attempts += 1
        row.lease_token, row.lease_until = uid(), instant + timedelta(seconds=30)
        row.updated_at = instant
        audit(db, p, 'execution.dispatch_claimed', row.id, {'attempt': row.attempts})
        return {'id':row.id, 'provider':row.provider, 'snapshot':row.request_snapshot,
                'key':row.idempotency_key, 'payment_id':row.provider_payment_id,
                'lease':row.lease_token, 'first':first_dispatch}


def _apply(claim, result=None, error=None):
    with SessionLocal.begin() as db:
        p, m, agent, intent, row = _lock_execution(db, claim['id'])
        if row.lease_token != claim['lease']:
            return  # Another lease recovered the operation; never overwrite its evidence.
        row.lease_until, row.lease_token, row.updated_at = None, None, now()
        row.next_attempt_at = now() + timedelta(seconds=min(300, 2**min(row.attempts, 8)))
        request = PaymentRequest.model_validate(row.request_snapshot)
        if result is not None and (not result.test or result.request_hash != request_hash(request)
            or result.amount != request.amount or result.currency != request.currency
            or (row.provider_payment_id and row.provider_payment_id != result.payment_id)):
            error, result = 'PROVIDER_EVIDENCE_MISMATCH', None
        if result is not None:
            # A new/unmapped status is uncertain, but a verified provider ID must
            # survive so the next attempt can reconcile instead of losing it.
            row.provider_payment_id, row.provider_status = result.payment_id, result.status.value
        if error or result is None or result.status == PaymentStatus.UNKNOWN:
            row.status, row.last_error = 'unknown', error or 'PROVIDER_UNKNOWN'
            intent.status = 'payment_unknown'
            audit(db, p, 'execution.unknown', row.id, {'code':row.last_error})
            emit(db, row.organization_id, 'execution.unknown', intent)
            return
        row.confirmation_url, row.last_error = result.confirmation_url, None
        reservation = db.scalar(select(Reservation).where(Reservation.intent_id == intent.id).with_for_update())
        if result.status == PaymentStatus.SUCCEEDED:
            if not result.receipt:
                row.status, row.last_error, intent.status = 'unknown', 'PROVIDER_RECEIPT_MISSING', 'payment_unknown'
                return
            row.status, intent.status = 'succeeded', 'completed'
            reservation.status, reservation.created_at = 'consumed', now()
            if not db.scalar(select(Transaction).where(Transaction.intent_id == intent.id)):
                db.add(Transaction(organization_id=intent.organization_id, owner_id=intent.owner_id,
                    intent_id=intent.id, amount=intent.amount, currency=intent.currency,
                    receipt=result.receipt, status='simulated' if row.provider=='local_simulator' else 'external_test'))
            event='transaction.simulated' if row.provider=='local_simulator' else 'payment.test_succeeded'
            audit(db, p, event, intent.id, {'execution_id':row.id, 'provider':row.provider})
            emit(db, row.organization_id, event, intent)
        elif result.status == PaymentStatus.CANCELLED:
            row.status, intent.status, reservation.status = 'cancelled', 'cancelled', 'released'
            audit(db, p, 'execution.cancelled', row.id)
            emit(db, row.organization_id, 'execution.cancelled', intent)
        elif result.status == PaymentStatus.REFUNDED:
            # Refund is not a new spending authorization; consumed budgets are not restored.
            row.status = 'refunded'
            audit(db, p, 'execution.refunded', row.id)
        else:
            row.status, intent.status = 'pending', 'payment_pending'
            audit(db, p, 'execution.pending', row.id, {'provider_status':result.status.value})


def dispatch_once(execution_id=None, provider=None):
    claim = _claim(execution_id)
    if not claim:
        return False
    adapter = None
    try:
        adapter = provider or provider_for(claim['provider'])
        request = PaymentRequest.model_validate(claim['snapshot'])
        # Reconcile first even after a crash before recording a provider ID.
        result = None if claim['first'] and not claim['payment_id'] else adapter.reconcile(claim['payment_id'], claim['key'])
        if result is None:
            result = adapter.create_payment_intent(request, claim['key'])
        if result.status == PaymentStatus.PENDING and claim['provider'] == 'local_simulator':
            result = adapter.authorize_test_payment(result.payment_id, claim['key'])
        _apply(claim, result=result)
    except Exception as error:
        code = error.code if isinstance(error, ProviderError) else 'PROVIDER_UNAVAILABLE'
        _apply(claim, error=code)
    finally:
        if provider is None and adapter is not None and hasattr(adapter,'client'):
            adapter.client.close()
    return True
