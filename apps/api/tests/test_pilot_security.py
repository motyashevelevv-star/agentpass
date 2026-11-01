from datetime import timedelta
import time
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from agentpass.config import Settings, settings
from agentpass.db import SessionLocal, now, uid
from agentpass.models import User, Agent, Mandate, Member, LoginSession
from agentpass.mfa import totp
from agentpass.webhooks import encrypt, decrypt


def pilot_settings(**changes):
    return Settings(_env_file=None,environment='pilot',seed_demo=False,demo_password='',
        cookie_secure=True,web_origin='https://pilot.example',allow_public_registration=False,
        require_mfa=True,execution_signing_key='test-pilot-signing-material-32-characters',
        encryption_key=settings().encryption_key,
        database_url='postgresql+psycopg://runtime:a-long-test-database-password-only@db/pilot?sslmode=verify-full',
        webhook_host_allowlist='receiver.example',**changes)


def test_pilot_config_fails_closed():
    assert pilot_settings().validate_operational().environment=='pilot'
    for field,value in [('seed_demo',True),('demo_password','AgentPass-demo-2026!'),
        ('cookie_secure',False),('web_origin','http://pilot.example'),
        ('allow_public_registration',True),('require_mfa',False),
        ('execution_signing_key','weak'),('webhook_host_allowlist',''),
        ('database_url','postgresql+psycopg://postgres:local-sandbox-only@db/pilot')]:
        config=pilot_settings().model_copy(update={field:value})
        with pytest.raises(RuntimeError):config.validate_operational()


def test_rfc6238_vector():
    # RFC 6238 SHA1 vector at t=59: 94287082; six-digit truncation is 287082.
    secret='GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
    assert totp(secret,1)=='287082'


def test_mfa_enrollment_does_not_leak_and_step_up_is_one_time(client,setup,monkeypatch):
    import agentpass.mfa as mfa
    start=client.post('/v1/security/mfa/enroll',json={'password':'test-password-123'})
    assert start.status_code==200
    secret=start.json()['secret']
    assert 'otpauth://' in start.json()['provisioning_uri']
    counter=int(time.time())//30
    monkeypatch.setattr(mfa.time,'time',lambda:counter*30+1)
    code=totp(secret,counter)
    assert client.post('/v1/security/mfa/confirm',json={'code':code}).status_code==200
    profile=client.get('/v1/auth/me').json()
    assert profile['user']['mfa_enabled']
    assert secret not in str(profile) and 'ciphertext' not in str(profile)
    assert client.post('/v1/developer/api-keys',json={'name':'new','agent_id':setup[2].agent_id}).status_code==403
    # The enrollment code has already been consumed.
    assert client.post('/v1/developer/api-keys',headers={'X-MFA-Code':code},json={'name':'new','agent_id':setup[2].agent_id}).status_code==403
    monkeypatch.setattr(mfa.time,'time',lambda:(counter+1)*30+1)
    next_code=totp(secret,counter+1)
    result=client.post('/v1/developer/api-keys',headers={'X-MFA-Code':next_code},json={'name':'new','agent_id':setup[2].agent_id})
    assert result.status_code==201
    assert client.post('/v1/developer/api-keys',headers={'X-MFA-Code':next_code},json={'name':'another','agent_id':setup[2].agent_id}).status_code==403


def test_mfa_required_on_approval_and_login(client,setup,monkeypatch):
    import agentpass.mfa as mfa
    secret='JBSWY3DPEHPK3PXP'
    with SessionLocal.begin() as db:
        db.get(User,setup[0].user_id).mfa_secret_ciphertext=encrypt(secret)
    body=setup[2].model_dump(mode='json');body.update(amount=1200000)
    i=client.post('/v1/intents',json=body).json()
    aid=i['approval']['id']
    assert client.post('/v1/approvals/'+aid+'/resolve',json={'action':'approve'}).status_code==403
    counter=int(time.time())//30
    monkeypatch.setattr(mfa.time,'time',lambda:counter*30+1)
    response=client.post('/v1/approvals/'+aid+'/resolve',json={'action':'approve','mfa_code':totp(secret,counter)})
    assert response.status_code==200 and response.json()['decision']=='APPROVE'
    assert client.post('/v1/auth/login',json={'email':'test@example.com','password':'test-password-123'}).status_code==403


def test_api_and_webhook_rotation_revoke_old_material(client,setup):
    key=client.post('/v1/developer/api-keys',json={'name':'old','agent_id':setup[2].agent_id}).json()
    rotated=client.post('/v1/developer/api-keys/'+key['id']+'/rotate').json()
    assert rotated['secret']!=key['secret']
    assert client.get('/v1/agents',headers={'Authorization':'Bearer '+key['secret']}).status_code==401
    assert client.get('/v1/agents',headers={'Authorization':'Bearer '+rotated['secret']}).status_code==200
    from agentpass.models import WebhookEndpoint
    with SessionLocal.begin() as db:
        row=WebhookEndpoint(id=uid(),organization_id=setup[0].organization_id,name='test',url='https://example.com',secret_ciphertext=encrypt('old'))
        db.add(row);hid=row.id
    hook=client.post('/v1/webhooks/'+hid+'/rotate-secret')
    assert hook.status_code==200
    with SessionLocal() as db:assert decrypt(db.get(WebhookEndpoint,hid).secret_ciphertext)==hook.json()['secret']


def test_composite_fk_rejects_cross_tenant_agent(setup):
    with pytest.raises(DBAPIError),SessionLocal.begin() as db:
        original=db.get(Mandate,setup[1].id)
        original.organization_id=setup[3].organization_id


def test_pilot_registration_disabled(client,monkeypatch):
    monkeypatch.setattr(settings(),'allow_public_registration',False)
    r=client.post('/v1/auth/register',json={'name':'Closed','email':'closed@example.com','password':'secure-password-123','organization_name':'Closed'})
    assert r.status_code==403 and r.json()['error']['code']=='REGISTRATION_DISABLED'


def test_pilot_startup_rejects_current_privileged_database_role(monkeypatch):
    from fastapi.testclient import TestClient
    from agentpass.main import app
    with SessionLocal() as db:
        privileged=db.scalar(text('SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user'))
    if not privileged:
        pytest.skip('This check specifically exercises a privileged sandbox database role')
    monkeypatch.setattr(settings(),'environment','pilot')
    with pytest.raises(RuntimeError,match='Pilot rejects'),TestClient(app):
        pass


def test_new_execution_routes_are_tenant_scoped(client,setup):
    from fastapi.testclient import TestClient
    from agentpass.main import app
    i=client.post('/v1/intents',json=setup[2].model_dump(mode='json')).json()
    grant=client.post('/v1/intents/'+i['id']+'/execution-grant',json={}).json()
    e=client.post('/v1/executions',json={'grant_token':grant['grant_token']})
    assert e.status_code==201
    with TestClient(app) as other:
        other.post('/v1/auth/login',json={'email':'other@example.com','password':'other-password-123'})
        other.headers['X-CSRF-Token']=other.cookies['ap_csrf']
        assert other.get('/v1/executions/'+e.json()['id']).status_code==404
        assert other.post('/v1/intents/'+i['id']+'/execution-grant',json={}).status_code==404
        assert other.post('/v1/executions',json={'grant_token':grant['grant_token']}).status_code==404


def test_oidc_assertion_boundary_validates_signature_nonce_and_audience():
    import base64,json
    from cryptography.hazmat.primitives.asymmetric import rsa,padding
    from cryptography.hazmat.primitives import hashes
    from agentpass.identity import OIDCAssertionValidator
    from agentpass.security import DomainError
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    b64=lambda b:base64.urlsafe_b64encode(b).rstrip(b'=').decode()
    integer=lambda n:b64(n.to_bytes((n.bit_length()+7)//8,'big'))
    public=key.public_key().public_numbers()
    verifier=OIDCAssertionValidator('https://idp.example','client',{'keys':[{'kid':'key1','kty':'RSA','n':integer(public.n),'e':integer(public.e)}]})
    def token(**updates):
        claims={'iss':'https://idp.example','sub':'stable-subject','aud':'client','nonce':'expected','exp':200,'iat':100,'amr':['mfa'],**updates}
        payload=b64(json.dumps({'alg':'RS256','kid':'key1'}).encode())+'.'+b64(json.dumps(claims).encode())
        return payload+'.'+b64(key.sign(payload.encode(),padding.PKCS1v15(),hashes.SHA256()))
    assert verifier.validate(token(),'expected',instant=150).subject=='stable-subject'
    for update in [{'aud':'wrong'},{'iss':'https://attacker.example'},{'nonce':'wrong'},{'exp':149},{'amr':[]},{'amr':['otp']}]:
        with pytest.raises(DomainError):verifier.validate(token(**update),'expected',instant=150)
    with pytest.raises(DomainError):verifier.validate(token()[:-3]+'xxx','expected',instant=150)
