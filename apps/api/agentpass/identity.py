"""Offline OIDC assertion validation boundary. No completed SSO login is claimed.

Discovery, authorization-code/PKCE/state/nonce lifecycle, identity provisioning and
IdP recovery still require an agreed enterprise provider and end-to-end tests.
"""
import base64
import json
import time
from dataclasses import dataclass
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
from .security import fail


@dataclass(frozen=True)
class EnterpriseIdentity:
    issuer: str
    subject: str
    mfa: bool


class OIDCAssertionValidator:
    def __init__(self, issuer, client_id, trusted_jwks):
        if not issuer.startswith('https://') or not client_id:
            raise ValueError('Explicit HTTPS issuer and client ID required')
        self.issuer,self.client_id,self.jwks=issuer,client_id,trusted_jwks

    def validate(self, token, nonce, require_mfa=True, instant=None):
        try:
            if len(token)>16384 or not nonce:
                raise ValueError
            head,payload,signature=token.split('.')
            decode=lambda s:base64.urlsafe_b64decode(s+'='*(-len(s)%4))
            header,claims=json.loads(decode(head)),json.loads(decode(payload))
            if header.get('alg')!='RS256' or 'jku' in header or 'x5u' in header:
                raise ValueError
            keys=[k for k in self.jwks['keys'] if k.get('kid')==header.get('kid') and k.get('kty')=='RSA' and k.get('use','sig')=='sig' and k.get('alg','RS256')=='RS256']
            if len(keys)!=1:
                raise ValueError
            jwk=keys[0]
            key=rsa.RSAPublicNumbers(int.from_bytes(decode(jwk['e']),'big'),int.from_bytes(decode(jwk['n']),'big')).public_key()
            if key.key_size<2048:
                raise ValueError
            key.verify(decode(signature),(head+'.'+payload).encode(),padding.PKCS1v15(),hashes.SHA256())
            current=instant if instant is not None else time.time()
            audience=claims.get('aud')
            audiences=[audience] if isinstance(audience,str) else audience
            if not isinstance(audiences,list) or self.client_id not in audiences:
                raise ValueError
            if len(audiences)>1 and claims.get('azp')!=self.client_id:
                raise ValueError
            if claims.get('iss')!=self.issuer or claims.get('nonce')!=nonce:
                raise ValueError
            if not isinstance(claims.get('sub'),str) or not 0<len(claims['sub'])<=255:
                raise ValueError
            for field in ('exp','iat'):
                if not isinstance(claims.get(field),int) or isinstance(claims[field],bool):
                    raise ValueError
            if claims['exp']<=current or claims['iat']>current+30 or claims.get('nbf',0)>current+30:
                raise ValueError
            amr=claims.get('amr',[])
            mfa=isinstance(amr,list) and ('mfa' in amr or ('pwd' in amr and 'otp' in amr))
            if require_mfa and not mfa:
                raise ValueError
            return EnterpriseIdentity(self.issuer,claims['sub'],mfa)
        except Exception:
            fail(401,'OIDC_ASSERTION_REJECTED','OIDC assertion не прошёл проверку')
