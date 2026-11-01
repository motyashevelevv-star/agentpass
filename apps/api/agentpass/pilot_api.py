"""Additive pilot API. The v1 sandbox execution contract remains unchanged."""
import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy import select, func, text
from .db import get_db, now, uid
from .models import (User, APIKey, WebhookEndpoint, WebhookDelivery, PaymentExecution,
                     WorkerHeartbeat, LoginSession)
from .schemas import GrantIn, ExecutionIn, MFACodeIn, CurrentPasswordIn
from .security import authenticate, digest, verify_password, fail
from .policy import audit, owned_intent, owned_mandate
from .grants import issue_grant
from .execution import submit_execution, owned_execution
from .mfa import enroll, step_up, verify_code
from .webhooks import encrypt

router = APIRouter()


def record(row):
    from .main import record as encode
    return encode(row)


@router.post('/v1/intents/{intent_id}/execution-grant', tags=['Executions'])
def grant(intent_id: str, data: GrantIn, p=Depends(authenticate), db=Depends(get_db, scope='function')):
    row, token = issue_grant(db, p, intent_id, data.provider)
    return {'id':row.id,'intent_id':row.intent_id,'provider':data.provider,
            'expires_at':row.expires_at,'grant_token':token,'single_use':True}


@router.post('/v1/executions', status_code=201, tags=['Executions'])
def execute(data: ExecutionIn, p=Depends(authenticate), db=Depends(get_db, scope='function')):
    return record(submit_execution(db, p, data.grant_token))


@router.get('/v1/executions/{execution_id}', tags=['Executions'])
def get_execution(execution_id: str, p=Depends(authenticate), db=Depends(get_db, scope='function')):
    return record(owned_execution(db, p, execution_id))


@router.post('/v1/executions/{execution_id}/reconcile', tags=['Executions'])
def reconcile(execution_id: str, p=Depends(authenticate), db=Depends(get_db, scope='function')):
    row = owned_execution(db, p, execution_id)
    owned_mandate(db, p, owned_intent(db, p, row.intent_id).mandate_id)
    row = db.scalar(select(PaymentExecution).where(PaymentExecution.id == row.id).with_for_update().execution_options(populate_existing=True))
    if p.role == 'viewer':
        fail(403, 'FORBIDDEN', 'Нет прав сверки')
    if row.lease_until and row.lease_until > now():
        fail(409, 'EXECUTION_INFLIGHT', 'Исполнитель ещё обрабатывает операцию')
    if row.status in ('pending','unknown','dispatching'):
        row.next_attempt_at, row.attempts = now(), 0
        audit(db, p, 'execution.reconciliation_requested', row.id)
    return record(row)


@router.get('/v1/security/mfa', tags=['Security'])
def mfa_state(p=Depends(authenticate), db=Depends(get_db, scope='function')):
    p.user()
    return {'enabled':bool(db.get(User,p.user_id).mfa_secret_ciphertext), 'type':'totp', 'recovery':'operator-reviewed; no insecure reset endpoint'}


@router.post('/v1/security/mfa/enroll', tags=['Security'])
def mfa_enroll(data: CurrentPasswordIn, p=Depends(authenticate), db=Depends(get_db, scope='function')):
    result = enroll(db, p, data.password)
    audit(db, p, 'mfa.enrollment_started', p.user_id)
    return result


@router.post('/v1/security/mfa/confirm', tags=['Security'])
def mfa_confirm(data: MFACodeIn, p=Depends(authenticate), db=Depends(get_db, scope='function')):
    p.user()
    user = db.scalar(select(User).where(User.id == p.user_id).with_for_update(key_share=True))
    if user.mfa_secret_ciphertext:
        fail(409, 'MFA_ALREADY_ENROLLED', 'Аутентификатор уже подключён')
    verify_code(user, data.code, pending=True)
    user.mfa_secret_ciphertext, user.mfa_pending_ciphertext = user.mfa_pending_ciphertext, None
    for session in db.scalars(select(LoginSession).where(LoginSession.user_id == p.user_id, LoginSession.id != p.session_id)):
        session.revoked_at = now()
    audit(db, p, 'mfa.enrolled', p.user_id)
    return {'enabled':True}


@router.post('/v1/developer/api-keys/{key_id}/rotate', tags=['Developer'])
def rotate_key(key_id: str, request: Request, p=Depends(authenticate), db=Depends(get_db, scope='function')):
    p.developer()
    step_up(db,p,request.headers.get('x-mfa-code'))
    row=db.scalar(select(APIKey).where(APIKey.id==key_id,APIKey.organization_id==p.organization_id,APIKey.created_by==p.user_id).with_for_update())
    if not row or row.revoked_at or row.expires_at<=now():
        fail(404,'NOT_FOUND','Активный ключ не найден')
    raw='ap_sk_sandbox_'+secrets.token_urlsafe(32)
    replacement=APIKey(id=uid(),organization_id=row.organization_id,created_by=row.created_by,
        agent_id=row.agent_id,name=row.name,prefix=raw[:20],key_hash=digest(raw),scopes=list(row.scopes),expires_at=row.expires_at)
    row.revoked_at=now()
    db.add(replacement)
    audit(db,p,'api_key.rotated',row.id,{'replacement_id':replacement.id})
    db.flush()
    return dict(record(replacement),secret=raw)


@router.post('/v1/webhooks/{endpoint_id}/rotate-secret', tags=['Webhooks'])
def rotate_hook(endpoint_id: str, request: Request, p=Depends(authenticate), db=Depends(get_db, scope='function')):
    p.developer()
    step_up(db,p,request.headers.get('x-mfa-code'))
    row=db.scalar(select(WebhookEndpoint).where(WebhookEndpoint.id==endpoint_id,WebhookEndpoint.organization_id==p.organization_id).with_for_update())
    if not row or not row.active:
        fail(404,'NOT_FOUND','Endpoint не найден')
    raw='whsec_'+secrets.token_urlsafe(32)
    row.secret_ciphertext=encrypt(raw)
    audit(db,p,'webhook.secret_rotated',row.id)
    return dict(record(row),secret=raw)


@router.get('/live', tags=['System'])
def liveness():
    return {'status':'ok'}


@router.get('/ready', tags=['System'])
def readiness(db=Depends(get_db, scope='function')):
    from sqlalchemy.exc import SQLAlchemyError
    try:
        db.execute(text('SELECT 1'))
        db.execute(select(PaymentExecution.id).limit(0))
        revision=db.scalar(text('SELECT version_num FROM alembic_version'))
        if revision!='dbfc8b45cfa9':
            fail(503,'SCHEMA_NOT_READY','Миграции базы данных не завершены')
    except SQLAlchemyError:
        fail(503,'DATABASE_NOT_READY','База данных не готова')
    return {'status':'ready','database':'available','schema':revision}


@router.get('/v1/admin/operations', tags=['Admin'])
def operations(p=Depends(authenticate), db=Depends(get_db, scope='function')):
    p.user()
    if not p.platform_admin:
        fail(403,'ADMIN_REQUIRED','Нужна роль администратора')
    return {'workers': [{'id':r.id,'observed_at':r.observed_at,'stale':r.observed_at<now()-timedelta(seconds=90)} for r in db.scalars(select(WorkerHeartbeat))],
        'execution_unknown':db.scalar(select(func.count()).select_from(PaymentExecution).where(PaymentExecution.status=='unknown')),
        'execution_quarantined':db.scalar(select(func.count()).select_from(PaymentExecution).where(PaymentExecution.status.in_(['unknown','pending']),PaymentExecution.attempts>=10)),
        'webhook_dead_letter':db.scalar(select(func.count()).select_from(WebhookDelivery).where(WebhookDelivery.status=='failed'))}


@router.post('/v1/providers/yookassa/callback', status_code=202, tags=['Payment Providers'])
def yookassa_callback(data: dict, request: Request, db=Depends(get_db, scope='function')):
    import json
    from .config import settings
    from .execution import provider_for
    from .payments.local import request_hash
    from .payments.base import PaymentRequest, ProviderError
    from .security import rate_limit, Principal
    if not settings().yookassa_sandbox_enabled:
        fail(404,'NOT_FOUND','Провайдер не включён')
    rate_limit('provider-callback:'+digest(request.client.host if request.client else 'unknown'),30)
    adapter=provider_for('yookassa_sandbox')
    try:
        payment_id=adapter.handle_callback(dict(request.headers),json.dumps(data).encode())
        obj=data.get('object')
        metadata=obj.get('metadata') if isinstance(obj,dict) else None
        hint=metadata.get('agentpass_intent_id') if isinstance(metadata,dict) else None
        if not isinstance(hint,str):
            hint=None
        # Incoming IDs/status are hints, not authority to mark a payment as paid.
        from sqlalchemy import or_
        candidate=db.scalar(select(PaymentExecution).where(PaymentExecution.provider=='yookassa_sandbox',
            or_(PaymentExecution.provider_payment_id==payment_id,PaymentExecution.intent_id==hint)))
        if not candidate or candidate.status in ('succeeded','cancelled','refunded','failed'):
            return {'accepted':True}
        evidence=adapter.get_payment_status(payment_id)
        expected=PaymentRequest.model_validate(candidate.request_snapshot)
        if evidence.request_hash!=request_hash(expected) or evidence.amount!=expected.amount or evidence.currency!=expected.currency:
            fail(401,'CALLBACK_BINDING_MISMATCH','Подтверждение провайдера не связано с намерением')
        row=db.scalar(select(PaymentExecution).where(PaymentExecution.id==candidate.id).with_for_update().execution_options(populate_existing=True))
        if row.provider_payment_id and row.provider_payment_id!=evidence.payment_id:
            fail(409,'PROVIDER_ID_MISMATCH','Другой идентификатор платежа')
        if row.status not in ('succeeded','cancelled','refunded','failed'):
            row.provider_payment_id=evidence.payment_id
            row.next_attempt_at=now()
            row.attempts=0
            p=Principal(row.owner_id,row.organization_id,'system')
            audit(db,p,'provider.callback_refetched',row.id)
        return {'accepted':True,'verification':'authenticated-provider-refetch'}
    except ProviderError:
        fail(503,'PROVIDER_VERIFICATION_FAILED','Проверка провайдера не завершена; повторите доставку')
    finally:
        adapter.client.close()
