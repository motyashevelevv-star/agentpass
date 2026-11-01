"""RFC 6238 TOTP step-up with per-user replay protection and no insecure reset API."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote
from sqlalchemy import select
from .models import User
from .security import fail, verify_password, rate_limit
from .webhooks import encrypt, decrypt
from .config import settings


def totp(secret, counter):
    key = base64.b32decode(secret + '=' * (-len(secret) % 8))
    value = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = value[-1] & 15
    number = struct.unpack('>I', value[offset:offset+4])[0] & 0x7fffffff
    return str(number % 1_000_000).zfill(6)


def verify_code(user, code, pending=False, instant=None):
    rate_limit('mfa:'+user.id, 10)
    ciphertext = user.mfa_pending_ciphertext if pending else user.mfa_secret_ciphertext
    if not ciphertext:
        fail(403, 'MFA_ENROLLMENT_REQUIRED', 'Подключите приложение-аутентификатор в разделе «Безопасность»')
    if not code or len(code) != 6 or not code.isascii() or not code.isdecimal():
        fail(403, 'MFA_REQUIRED', 'Введите одноразовый код аутентификатора для этой операции')
    secret = decrypt(ciphertext)
    counter = int(instant if instant is not None else time.time()) // 30
    for candidate in (counter, counter-1, counter+1):
        if candidate >= 0 and (user.mfa_last_counter is None or candidate > user.mfa_last_counter):
            if hmac.compare_digest(totp(secret, candidate), code):
                user.mfa_last_counter = candidate
                return
    fail(403, 'MFA_INVALID_OR_REPLAYED', 'Код неверен, истёк или уже использован; дождитесь нового кода')


def step_up(db, p, code):
    p.user()
    user = db.scalar(select(User).where(User.id == p.user_id).with_for_update(key_share=True))
    if settings().require_mfa or user.mfa_secret_ciphertext:
        verify_code(user, code)
    return user


def enroll(db, p, password):
    p.user()
    user = db.scalar(select(User).where(User.id == p.user_id).with_for_update(key_share=True))
    if not verify_password(password, user.password_hash):
        fail(401, 'INVALID_CREDENTIALS', 'Текущий пароль неверен')
    if user.mfa_secret_ciphertext:
        fail(409, 'MFA_ALREADY_ENROLLED', 'Аутентификатор уже подключён')
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
    user.mfa_pending_ciphertext, user.mfa_last_counter = encrypt(secret), None
    return {'secret':secret, 'provisioning_uri':'otpauth://totp/'+quote('AgentPass:'+user.email, safe='')+'?secret='+secret+'&issuer=AgentPass&algorithm=SHA1&digits=6&period=30'}
