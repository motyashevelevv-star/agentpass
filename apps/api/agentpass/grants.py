"""Short-lived, single-use capabilities bound to a frozen purchase intent."""
import base64
import binascii
import hashlib
import hmac
import json
from datetime import timedelta
from sqlalchemy import select
from .config import settings
from .db import now, uid
from .models import ExecutionGrant, PaymentIntent, Reservation
from .schemas import IntentIn
from .security import digest, fail


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def intent_input(intent):
    return IntentIn(**{key: getattr(intent, key) for key in IntentIn.model_fields})


def fingerprint(data):
    # New nullable IDs do not change the legacy request fingerprint.
    return hashlib.sha256(canonical(data.model_dump(mode='json', exclude_none=True))).hexdigest()


def verify_intent(intent):
    if not hmac.compare_digest(intent.fingerprint, fingerprint(intent_input(intent))):
        fail(409, 'INTENT_TAMPERED', 'Параметры намерения не соответствуют проверенному запросу')


def snapshot(intent, provider):
    verify_intent(intent)
    return {
        'intent_id': intent.id, 'organization_id': intent.organization_id,
        'owner_id': intent.owner_id, 'agent_id': intent.agent_id,
        'mandate_id': intent.mandate_id, 'mandate_version': intent.evaluated_version,
        'merchant': intent.merchant, 'merchant_id': intent.merchant_id,
        'order_id': intent.order_id, 'amount': intent.amount, 'currency': intent.currency,
        'description': intent.description, 'fingerprint': intent.fingerprint,
        'provider': provider,
    }


def signing_key():
    config = settings()
    if config.execution_signing_key:
        return config.execution_signing_key.encode()
    return hmac.new(config.encryption_key.encode(), b'agentpass/execution-grant/v1', hashlib.sha256).digest()


def encode_token(claims):
    payload = base64.urlsafe_b64encode(canonical(claims)).rstrip(b'=')
    signature = hmac.new(signing_key(), b'apg1.' + payload, hashlib.sha256).digest()
    return 'apg1.' + payload.decode() + '.' + base64.urlsafe_b64encode(signature).rstrip(b'=').decode()


def decode_token(token):
    try:
        version, payload, signature = token.split('.')
        if version != 'apg1' or len(payload) > 3500:
            raise ValueError
        expected=base64.urlsafe_b64encode(hmac.new(signing_key(),b'apg1.'+payload.encode(),hashlib.sha256).digest()).rstrip(b'=').decode()
        if not hmac.compare_digest(expected,signature):
            raise ValueError
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        if not isinstance(claims, dict) or not hmac.compare_digest(encode_token(claims), token):
            raise ValueError
        if claims['aud'] != 'agentpass:payment-executor' or claims['kid'] != settings().execution_key_id:
            raise ValueError
        if not isinstance(claims['exp'], int) or not isinstance(claims['payment'], dict):
            raise ValueError
        return claims
    except (ValueError, KeyError, TypeError, UnicodeError, binascii.Error, RecursionError):
        fail(401, 'INVALID_EXECUTION_GRANT', 'Подпись разрешения недействительна')


def issue_grant(db, p, intent_id, provider='local_simulator'):
    from .policy import owned_intent, owned_mandate, expire_for_mandate, check_rules, budget_usage, audit
    intent = owned_intent(db, p, intent_id)
    m, agent = owned_mandate(db, p, intent.mandate_id)
    intent = db.scalar(select(PaymentIntent).where(PaymentIntent.id == intent.id).with_for_update().execution_options(populate_existing=True))
    expire_for_mandate(db, m)
    if p.role in ('viewer', 'executor'):
        fail(403, 'FORBIDDEN', 'Нет полномочий на выпуск разрешения')
    if provider != 'local_simulator' and not (provider == 'yookassa_sandbox' and settings().yookassa_sandbox_enabled):
        fail(422, 'PROVIDER_NOT_ENABLED', 'Внешняя песочница не настроена')
    if provider == 'yookassa_sandbox' and (intent.merchant_id != 'yookassa:'+settings().yookassa_shop_id or not intent.order_id or intent.currency != 'RUB'):
        fail(422, 'PROVIDER_BINDING_REQUIRED', 'Нужны order_id, RUB и merchant_id тестового магазина ЮKassa')
    if intent.status != 'authorized' or intent.evaluated_version != m.version:
        fail(409, 'NOT_AUTHORIZED', 'Нет действующего разрешения текущей версии мандата')
    decision, _ = check_rules(m, agent, intent, budget_usage(db, m, exclude_intent=intent.id), confirmed=True)
    if decision != 'APPROVE':
        fail(409, 'NOT_AUTHORIZED', 'Полномочия или бюджет изменились')
    reservation = db.scalar(select(Reservation).where(Reservation.intent_id == intent.id).with_for_update())
    if not reservation or reservation.status != 'held' or reservation.expires_at <= now():
        fail(409, 'RESERVATION_EXPIRED', 'Резерв истёк')
    bound = snapshot(intent, provider)
    existing = db.scalar(select(ExecutionGrant).where(ExecutionGrant.intent_id == intent.id).with_for_update())
    if existing:
        if existing.claims['payment'] != bound or existing.consumed_at or existing.expires_at <= now():
            fail(409, 'GRANT_NOT_REISSUABLE', 'Нужно новое намерение и новая проверка')
        token = encode_token(existing.claims)
        if not hmac.compare_digest(digest(token), existing.token_hash):
            fail(409, 'GRANT_KEY_ROTATED', 'Ключ разрешений изменён; создайте новое намерение')
        return existing, token
    instant = now()
    expiry = min(instant + timedelta(seconds=settings().execution_grant_seconds), reservation.expires_at)
    grant_id = uid()
    claims = {'jti': grant_id, 'aud': 'agentpass:payment-executor', 'kid': settings().execution_key_id,
              'iat': int(instant.timestamp()), 'exp': int(expiry.timestamp()), 'payment': bound}
    token = encode_token(claims)
    row = ExecutionGrant(id=grant_id, organization_id=p.organization_id, owner_id=p.user_id,
                         agent_id=intent.agent_id, intent_id=intent.id, token_hash=digest(token),
                         claims=claims, expires_at=expiry)
    db.add(row)
    audit(db, p, 'execution_grant.issued', grant_id, {'intent_id': intent.id, 'provider': provider})
    db.flush()
    return row, token
