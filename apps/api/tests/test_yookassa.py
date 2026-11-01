import json
import httpx
import pytest
from agentpass.payments.base import PaymentRequest,PaymentStatus,ProviderError
from agentpass.payments.yookassa import YooKassaSandbox
from agentpass.payments.local import request_hash


def request():
    return PaymentRequest(intent_id='intent',organization_id='org',owner_id='user',agent_id='agent',
        mandate_id='mandate',mandate_version=1,merchant='Demo',merchant_id='yookassa:123',
        order_id='order-1',amount=800000,currency='RUB',description='Test checkout',fingerprint='a'*64,provider='yookassa_sandbox')


def response(**updates):
    return {'id':'payment-id','test':True,'recipient':{'account_id':'123'},'status':'pending','paid':False,
        'amount':{'value':'8000.00','currency':'RUB'},'metadata':{'agentpass_request_hash':request_hash(request())},
        'confirmation':{'confirmation_url':'https://yoomoney.ru/checkout/test'},**updates}


def adapter(handler):
    return YooKassaSandbox('123','test_never-real','https://app.example/return',
        client=httpx.Client(base_url='https://api.yookassa.ru/v3/',transport=httpx.MockTransport(handler)))


def test_checkout_is_test_and_requires_human_redirect():
    calls=[]
    def handler(r):
        calls.append(r)
        assert r.headers['Idempotence-Key']=='stable-key'
        body=json.loads(r.content)
        assert body['capture'] and body['confirmation']['type']=='redirect'
        assert body['amount']=={'value':'8000.00','currency':'RUB'}
        assert 'payment_method_data' not in body and 'payment_method_id' not in body
        return httpx.Response(200,json=response())
    p=adapter(handler)
    result=p.create_payment_intent(request(),'stable-key')
    assert result.status==PaymentStatus.PENDING and result.receipt is None
    with pytest.raises(ProviderError,match='USER_CHECKOUT_REQUIRED'):
        p.authorize_test_payment(result.payment_id,'key')
    assert len(calls)==1


@pytest.mark.parametrize('changes',[
 {'test':False},{'test':'true'},{'recipient':{'account_id':'another'}},
 {'metadata':{}},{'confirmation':{'confirmation_url':'http://attacker.example'}},
 {'amount':{'value':'NaN','currency':'RUB'}},
])
def test_rejects_wrong_provider_evidence(changes):
    p=adapter(lambda r:httpx.Response(200,json=response(**changes)))
    with pytest.raises(ProviderError):p.create_payment_intent(request(),'key')


def test_success_only_for_paid_test_payment_and_unknown_status_is_safe():
    p=adapter(lambda r:httpx.Response(200,json=response(status='succeeded',paid=True)))
    assert p.get_payment_status('payment-id').status==PaymentStatus.SUCCEEDED
    p=adapter(lambda r:httpx.Response(200,json=response(status='succeeded',paid=False)))
    assert p.get_payment_status('payment-id').status==PaymentStatus.UNKNOWN
    p=adapter(lambda r:httpx.Response(200,json=response(status='new_unknown_status')))
    assert p.get_payment_status('payment-id').status==PaymentStatus.UNKNOWN


def test_never_recreates_unknown_external_payment_without_id():
    p=adapter(lambda r:pytest.fail('No request allowed without known provider ID'))
    with pytest.raises(ProviderError,match='PROVIDER_ID_UNKNOWN_REQUIRES_CALLBACK'):
        p.reconcile(None,'key')


def test_live_key_and_path_injection_are_rejected():
    with pytest.raises(ProviderError,match='LIVE_CREDENTIALS_FORBIDDEN'):
        YooKassaSandbox('123','live-not-allowed','https://app.example')
    p=adapter(lambda r:pytest.fail('No unsafe URL request'))
    with pytest.raises(ProviderError):p.get_payment_status('../another-host')


def test_callback_does_not_accept_status_as_confirmation():
    p=adapter(lambda r:httpx.Response(200,json=response(status='pending')))
    payment_id=p.handle_callback({},json.dumps({'type':'notification','event':'payment.succeeded','object':{'id':'payment-id'}}).encode())
    assert p.get_payment_status(payment_id).status==PaymentStatus.PENDING


def test_timeout_is_not_success():
    def timeout(r):raise httpx.ReadTimeout('private response')
    with pytest.raises(ProviderError,match='PROVIDER_UNAVAILABLE'):
        adapter(timeout).create_payment_intent(request(),'key')


def test_callback_refetches_evidence_and_worker_reconciles_without_second_create(client,setup,monkeypatch):
    from agentpass.config import settings
    from agentpass.db import SessionLocal
    from agentpass.models import PaymentExecution,Transaction
    from agentpass.execution import dispatch_once
    import agentpass.execution as execution
    from sqlalchemy import select
    monkeypatch.setattr(settings(),'yookassa_sandbox_enabled',True)
    monkeypatch.setattr(settings(),'yookassa_shop_id','123')
    body=setup[2].model_dump(mode='json');body.update(merchant_id='yookassa:123',order_id='order-1')
    intent=client.post('/v1/intents',json=body).json()
    grant=client.post('/v1/intents/'+intent['id']+'/execution-grant',json={'provider':'yookassa_sandbox'}).json()
    operation=client.post('/v1/executions',json={'grant_token':grant['grant_token']}).json()
    with SessionLocal() as db:
        expected=PaymentRequest.model_validate(db.get(PaymentExecution,operation['id']).request_snapshot)
    calls=[]
    def handler(r):
        calls.append(r.method)
        assert r.method=='GET', 'Callback-provided payment ID must be reconciled, never create another checkout'
        return httpx.Response(200,json=response(metadata={'agentpass_request_hash':request_hash(expected)},status='pending'))
    # Every API callback/worker owns and closes its client.
    monkeypatch.setattr(execution,'provider_for',lambda name:adapter(handler))
    forged={'type':'notification','event':'payment.succeeded','object':{'id':'payment-id',
        'status':'succeeded','metadata':{'agentpass_intent_id':intent['id']}}}
    for _ in range(2):
        result=client.post('/v1/providers/yookassa/callback',json=forged)
        assert result.status_code==202
    assert dispatch_once(operation['id'])
    with SessionLocal() as db:
        row=db.get(PaymentExecution,operation['id'])
        assert row.status=='pending'
        assert db.scalar(select(Transaction).where(Transaction.intent_id==intent['id'])) is None
    assert calls==['GET','GET','GET']
    # Only authenticated evidence changing to paid=true may complete this intent.
    monkeypatch.setattr(execution,'provider_for',lambda name:adapter(lambda r:httpx.Response(200,json=response(
        metadata={'agentpass_request_hash':request_hash(expected)},status='succeeded',paid=True))))
    assert client.post('/v1/providers/yookassa/callback',json=forged).status_code==202
    assert dispatch_once(operation['id'])
    assert client.post('/v1/providers/yookassa/callback',json=forged).status_code==202
    with SessionLocal() as db:
        assert db.get(PaymentExecution,operation['id']).status=='succeeded'
        payments=list(db.scalars(select(Transaction).where(Transaction.intent_id==intent['id'])))
        assert len(payments)==1 and payments[0].status=='external_test'


def test_callback_rejects_authenticated_but_different_purchase(client,setup,monkeypatch):
    from agentpass.config import settings
    import agentpass.execution as execution
    monkeypatch.setattr(settings(),'yookassa_sandbox_enabled',True)
    monkeypatch.setattr(settings(),'yookassa_shop_id','123')
    body=setup[2].model_dump(mode='json');body.update(merchant_id='yookassa:123',order_id='order-1')
    intent=client.post('/v1/intents',json=body).json()
    grant=client.post('/v1/intents/'+intent['id']+'/execution-grant',json={'provider':'yookassa_sandbox'}).json()
    client.post('/v1/executions',json={'grant_token':grant['grant_token']})
    monkeypatch.setattr(execution,'provider_for',lambda name:adapter(lambda r:httpx.Response(200,json=response(status='succeeded',paid=True))))
    result=client.post('/v1/providers/yookassa/callback',json={'type':'notification','event':'payment.succeeded',
        'object':{'id':'payment-id','metadata':{'agentpass_intent_id':intent['id']}}})
    assert result.status_code==401 and result.json()['error']['code']=='CALLBACK_BINDING_MISMATCH'
