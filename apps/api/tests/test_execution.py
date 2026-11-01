from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from agentpass.db import SessionLocal, now, uid
from agentpass.models import (PaymentIntent, ExecutionGrant, PaymentExecution, Reservation, Transaction, SimulatorPayment, Mandate)
from agentpass.policy import create_intent, budget_usage
from agentpass.grants import issue_grant, encode_token
from agentpass.execution import submit_execution, dispatch_once
from agentpass.payments.base import ProviderError, PaymentStatus
from agentpass.payments.local import LocalPaymentProvider
from agentpass.security import DomainError


def prepared(setup):
    p, _, data, _=setup
    with SessionLocal.begin() as db:
        intent=create_intent(db,p,data)
        grant,token=issue_grant(db,p,intent.id)
    return intent.id,grant.id,token


def test_grant_binding_expiry_and_idempotence(setup):
    iid,gid,token=prepared(setup)
    with SessionLocal.begin() as db:
        row,repeat=issue_grant(db,setup[0],iid)
        assert row.id==gid and repeat==token
        assert row.claims['payment']['amount']==800000
        assert row.claims['payment']['organization_id']==setup[0].organization_id
        assert row.expires_at<=now()+timedelta(seconds=121)
    assert token.startswith('apg1.')


@pytest.mark.parametrize('column,value',[
 ('amount',900000),('merchant','Other'),('currency','USD'),('order_id','changed'),
 ('merchant_id','changed'),('agent_id','wrong'),('owner_id','wrong'),('organization_id','wrong'),
 ('structured_metadata',{'changed':True}),
])
def test_database_rejects_intent_tampering(setup,column,value):
    iid,_,_=prepared(setup)
    with pytest.raises(DBAPIError),SessionLocal.begin() as db:
        i=db.get(PaymentIntent,iid)
        setattr(i,column,value)


def test_signature_tamper_and_foreign_tenant(setup):
    iid,_,token=prepared(setup)
    with SessionLocal.begin() as db,pytest.raises(DomainError) as error:
        submit_execution(db,setup[0],token[:-1]+('A' if token[-1]!='A' else 'B'))
    assert error.value.code=='INVALID_EXECUTION_GRANT'
    with SessionLocal.begin() as db,pytest.raises(DomainError) as error:
        submit_execution(db,setup[3],token)
    assert error.value.status==404


def test_unsigned_deep_payload_is_rejected_before_json_parsing():
    import base64
    from agentpass.grants import decode_token
    payload=base64.urlsafe_b64encode(('['*1100+']'*1100).encode()).rstrip(b'=').decode()
    with pytest.raises(DomainError) as error:decode_token('apg1.'+payload+'.unsigned')
    assert error.value.code=='INVALID_EXECUTION_GRANT'


def test_expired_grant_cannot_execute(setup,monkeypatch):
    from agentpass import execution
    _,_,token=prepared(setup)
    monkeypatch.setattr(execution,'now',lambda:now()+timedelta(minutes=3))
    with SessionLocal.begin() as db,pytest.raises(DomainError) as error:
        submit_execution(db,setup[0],token)
    assert error.value.code=='GRANT_EXPIRED_OR_USED'


def test_one_grant_one_execution_parallel_retries(setup):
    iid,_,token=prepared(setup)
    def submit(_):
        with SessionLocal.begin() as db:return submit_execution(db,setup[0],token).id
    with ThreadPoolExecutor(max_workers=6) as pool:ids=list(pool.map(submit,range(6)))
    assert len(set(ids))==1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction))==0
        assert db.get(PaymentIntent,iid).status=='executing'
    with ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(lambda _:dispatch_once(ids[0]),range(6)))
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction))==1
        assert db.scalar(select(func.count()).select_from(SimulatorPayment))==1
        assert db.get(PaymentExecution,ids[0]).status=='succeeded'
        assert budget_usage(db,setup[1])['daily']==800000


def test_timeout_after_provider_success_is_reconciled_once(setup):
    iid,_,token=prepared(setup)
    with SessionLocal.begin() as db:eid=submit_execution(db,setup[0],token).id
    class TimeoutAfterSuccess(LocalPaymentProvider):
        def authorize_test_payment(self,*args):
            super().authorize_test_payment(*args)
            raise TimeoutError('sensitive provider details must not be logged')
    assert dispatch_once(eid,TimeoutAfterSuccess())
    with SessionLocal.begin() as db:
        e=db.get(PaymentExecution,eid)
        assert e.status=='unknown' and e.last_error=='PROVIDER_UNAVAILABLE'
        assert db.scalar(select(func.count()).select_from(Transaction))==0
        r=db.scalar(select(Reservation))
        assert r.status=='inflight'
        # In-flight uncertainty blocks all budget windows even on following days.
        assert budget_usage(db,setup[1],instant=now()+timedelta(days=35))['daily']==800000
        e.next_attempt_at=now()
    assert dispatch_once(eid)
    with SessionLocal() as db:
        assert db.get(PaymentExecution,eid).status=='succeeded'
        assert db.scalar(select(func.count()).select_from(Transaction))==1
        assert db.scalar(select(func.count()).select_from(SimulatorPayment))==1


def test_wrong_provider_evidence_never_marks_success(setup):
    iid,_,token=prepared(setup)
    with SessionLocal.begin() as db:eid=submit_execution(db,setup[0],token).id
    class WrongEvidence(LocalPaymentProvider):
        def authorize_test_payment(self,*args):
            result=super().authorize_test_payment(*args)
            return result.model_copy(update={'amount':1})
    assert dispatch_once(eid,WrongEvidence())
    with SessionLocal() as db:
        assert db.get(PaymentExecution,eid).status=='unknown'
        assert db.scalar(select(func.count()).select_from(Transaction))==0
        assert db.scalar(select(Reservation.status))=='inflight'


def test_unknown_provider_status_retains_verified_id_and_can_reconcile(setup):
    iid,_,token=prepared(setup)
    with SessionLocal.begin() as db:eid=submit_execution(db,setup[0],token).id
    class UnknownStatus(LocalPaymentProvider):
        def create_payment_intent(self,*args):
            result=super().create_payment_intent(*args)
            return result.model_copy(update={'status':PaymentStatus.UNKNOWN})
    assert dispatch_once(eid,UnknownStatus())
    with SessionLocal.begin() as db:
        e=db.get(PaymentExecution,eid)
        assert e.status=='unknown' and e.provider_payment_id
        assert db.scalar(select(func.count()).select_from(Transaction))==0
        e.next_attempt_at=now()
    assert dispatch_once(eid)
    with SessionLocal() as db:
        assert db.get(PaymentExecution,eid).status=='succeeded'
        assert db.scalar(select(func.count()).select_from(SimulatorPayment))==1


def test_rule_revocation_before_dispatch_releases_queued_reservation(setup):
    iid,_,token=prepared(setup)
    with SessionLocal.begin() as db:
        eid=submit_execution(db,setup[0],token).id
        db.get(Mandate,setup[1].id).status='revoked'
    assert not dispatch_once(eid)
    with SessionLocal() as db:
        assert db.get(PaymentExecution,eid).status=='cancelled'
        assert db.scalar(select(Reservation.status))=='released'
        assert db.scalar(select(func.count()).select_from(SimulatorPayment))==0


def test_provider_refund_and_cancel_are_idempotent(setup):
    from agentpass.payments.base import PaymentRequest
    _,gid,_=prepared(setup)
    with SessionLocal() as db:req=PaymentRequest.model_validate(db.get(ExecutionGrant,gid).claims['payment'])
    provider=LocalPaymentProvider()
    pay=provider.create_payment_intent(req,'test-payment')
    assert provider.create_payment_intent(req,'test-payment').payment_id==pay.payment_id
    done=provider.authorize_test_payment(pay.payment_id,'authorize')
    assert done.status==PaymentStatus.SUCCEEDED
    assert provider.refund(pay.payment_id,'refund').status==PaymentStatus.REFUNDED
    assert provider.refund(pay.payment_id,'refund').status==PaymentStatus.REFUNDED
    other=provider.create_payment_intent(req,'test-payment-2')
    assert provider.cancel(other.payment_id,'cancel').status==PaymentStatus.CANCELLED
    assert provider.cancel(other.payment_id,'cancel').status==PaymentStatus.CANCELLED


def test_grant_consumption_rollback_does_not_queue_or_pay(setup,monkeypatch):
    iid,_,token=prepared(setup)
    with SessionLocal() as db:
        submit_execution(db,setup[0],token)
        db.rollback()
    with SessionLocal() as db:
        assert db.scalar(select(ExecutionGrant.consumed_at)) is None
        assert db.scalar(select(func.count()).select_from(PaymentExecution))==0
        assert db.scalar(select(func.count()).select_from(SimulatorPayment))==0


def test_api_agent_cannot_act_as_trusted_executor(client,setup):
    iid,_,token=prepared(setup)
    key=client.post('/v1/developer/api-keys',json={'name':'agent','agent_id':setup[2].agent_id}).json()['secret']
    assert client.post('/v1/executions',headers={'Authorization':'Bearer '+key},json={'grant_token':token}).status_code==403
    executor=client.post('/v1/developer/api-keys',json={'name':'executor','agent_id':setup[2].agent_id,'purpose':'executor'}).json()['secret']
    headers={'Authorization':'Bearer '+executor}
    response=client.post('/v1/executions',headers=headers,json={'grant_token':token})
    assert response.status_code==201
    assert client.get('/v1/executions/'+response.json()['id'],headers=headers).status_code==200
    assert client.post('/v1/intents',headers=headers,json=setup[2].model_dump(mode='json')).status_code==403


def test_worker_crash_after_provider_success_recovers_and_fences_old_lease(setup):
    from agentpass.execution import _claim,_apply
    from agentpass.payments.base import PaymentRequest
    iid,_,token=prepared(setup)
    with SessionLocal.begin() as db:eid=submit_execution(db,setup[0],token).id
    stale_claim=_claim(eid)
    provider=LocalPaymentProvider()
    payment=provider.create_payment_intent(PaymentRequest.model_validate(stale_claim['snapshot']),stale_claim['key'])
    result=provider.authorize_test_payment(payment.payment_id,stale_claim['key'])
    # Process dies after the provider commit, before applying evidence to AgentPass.
    with SessionLocal.begin() as db:db.get(PaymentExecution,eid).lease_until=now()-timedelta(seconds=1)
    assert dispatch_once(eid)
    _apply(stale_claim,error='LATE_OLD_WORKER_ERROR')
    with SessionLocal() as db:
        assert db.get(PaymentExecution,eid).status=='succeeded'
        assert db.get(PaymentIntent,iid).status=='completed'
        assert db.scalar(select(func.count()).select_from(Transaction))==1
        assert db.scalar(select(func.count()).select_from(SimulatorPayment))==1


def test_expired_queued_grant_never_reaches_provider(setup,monkeypatch):
    import agentpass.execution as execution
    _,_,token=prepared(setup)
    with SessionLocal.begin() as db:eid=submit_execution(db,setup[0],token).id
    monkeypatch.setattr(execution,'now',lambda:now()+timedelta(minutes=3))
    assert not dispatch_once(eid)
    with SessionLocal() as db:
        assert db.get(PaymentExecution,eid).status=='cancelled'
        assert db.scalar(select(Reservation.status))=='released'
        assert db.scalar(select(func.count()).select_from(SimulatorPayment))==0
