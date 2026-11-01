from dataclasses import dataclass
from datetime import timedelta
import hashlib, hmac, secrets, time
from fastapi import Depends, Request
from fastapi.security import HTTPBearer, APIKeyCookie
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from .db import get_db, SessionLocal, now
from .models import User, Member, Organization, APIKey, LoginSession, RateWindow
from .config import settings


class DomainError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def fail(status, code, message):
    raise DomainError(status, code, message)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    salt = secrets.token_bytes(16)
    hashed = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f"scrypt${salt.hex()}${hashed.hex()}"


def verify_password(password, value):
    try:
        _, salt, hashed = value.split("$")
        actual = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1
        )
        return hmac.compare_digest(actual.hex(), hashed)
    except (ValueError, TypeError):
        return False


DUMMY_PASSWORD_HASH = password_hash('agentpass-nonexistent-account')


@dataclass
class Principal:
    user_id: str
    organization_id: str
    role: str
    platform_admin: bool = False
    agent_id: str | None = None
    session_id: str | None = None
    key_id: str | None = None

    @property
    def actor(self):
        return f"key:{self.key_id}" if self.key_id else self.user_id

    def user(self):
        if self.agent_id:
            fail(403, "USER_REQUIRED", "Нужна пользовательская сессия")

    def developer(self):
        self.user()
        if self.role not in ("owner", "developer"):
            fail(403, "FORBIDDEN", "Недостаточно полномочий")

    def owner(self):
        self.user()
        if self.role != "owner":
            fail(403, "OWNER_REQUIRED", "Нужна роль владельца организации")


def rate_limit(key, limit):
    window = int(time.time()) // 60
    with SessionLocal.begin() as db:
        stmt = insert(RateWindow).values(key=key, window=window, count=1)
        count = db.scalar(
            stmt.on_conflict_do_update(
                index_elements=["key", "window"], set_={"count": RateWindow.count + 1}
            ).returning(RateWindow.count)
        )
    if count > limit:
        fail(429, "RATE_LIMITED", "Слишком много запросов. Повторите через минуту.")


bearer_auth = HTTPBearer(auto_error=False, scheme_name="AgentAPIKey")
session_auth = APIKeyCookie(
    name="ap_session", auto_error=False, scheme_name="UserSession"
)


def authenticate(
    request: Request,
    db=Depends(get_db, scope="function"),
    credentials=Depends(bearer_auth),
    session_cookie=Depends(session_auth),
):
    authorization = request.headers.get("authorization", "")
    if credentials:
        key = db.scalar(
            select(APIKey).where(APIKey.key_hash == digest(credentials.credentials))
        )
        if not key or key.revoked_at or key.expires_at <= now():
            fail(401, "INVALID_API_KEY", "API-ключ недействителен")
        # Uniform order: organization → membership → credential → financial locks.
        organization = db.scalar(
            select(Organization)
            .where(Organization.id == key.organization_id)
            .with_for_update(read=True)
        )
        member = db.scalar(
            select(Member)
            .where(
                Member.organization_id == key.organization_id,
                Member.user_id == key.created_by,
            )
            .with_for_update(read=True)
        )
        if not member or member.role not in ("owner", "developer"):
            fail(401, "INVALID_API_KEY", "Полномочия создателя ключа отозваны")
        key = db.scalar(
            select(APIKey)
            .where(APIKey.id == key.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if key.revoked_at or key.expires_at <= now():
            fail(401, "INVALID_API_KEY", "API-ключ недействителен")
        if request.url.path.startswith('/v1/executions'):
            required = 'payments:read' if request.method == 'GET' else 'payments:execute'
        else:
            required = "intents:read" if request.method == "GET" else "intents:write"
        if required not in key.scopes:
            fail(403, "SCOPE_REQUIRED", "Недостаточная область доступа ключа")
        key.last_used_at = now()
        principal = Principal(
            key.created_by,
            key.organization_id,
            "executor" if 'payments:execute' in key.scopes else "agent",
            agent_id=key.agent_id,
            key_id=key.id,
        )
    else:
        if authorization:
            fail(401, "INVALID_AUTH_SCHEME", "Используйте Bearer API-ключ")
        token = session_cookie or ""
        session = (
            db.scalar(
                select(LoginSession).where(LoginSession.token_hash == digest(token))
            )
            if token
            else None
        )
        if not session or session.revoked_at or session.expires_at <= now():
            fail(401, "UNAUTHENTICATED", "Войдите в AgentPass")
        user = db.get(User, session.user_id)
        stmt = select(Member).where(Member.user_id == user.id)
        org_id = request.headers.get("x-organization-id")
        if org_id:
            stmt = stmt.where(Member.organization_id == org_id)
        candidate = db.scalar(stmt.order_by(Member.created_at))
        if not candidate:
            fail(403, "ORG_ACCESS_DENIED", "Нет доступа к организации")
        org_query = select(Organization).where(
            Organization.id == candidate.organization_id
        )
        # Platform operations lock only their target organization, avoiding unrelated locks.
        if not (user.platform_admin and request.url.path.startswith("/v1/admin")):
            org_query = org_query.with_for_update(read=True)
        organization = db.scalar(org_query)
        member = db.scalar(
            select(Member)
            .where(Member.id == candidate.id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if not member:
            fail(403, "ORG_ACCESS_DENIED", "Нет доступа к организации")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            csrf = request.headers.get("x-csrf-token", "")
            if not csrf or not hmac.compare_digest(session.csrf_hash, digest(csrf)):
                fail(403, "CSRF_FAILED", "Проверка сессии не пройдена")
        principal = Principal(
            user.id,
            member.organization_id,
            member.role,
            user.platform_admin,
            session_id=session.id,
        )
    if organization.status != "active" and not (
        principal.platform_admin and request.url.path.startswith("/v1/admin")
    ):
        fail(403, "ORGANIZATION_SUSPENDED", "Организация приостановлена")
    rate_limit(principal.key_id or principal.user_id, settings().rate_limit)
    request.state.org_id = principal.organization_id
    return principal


def new_session(db, user, response):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    row = LoginSession(
        user_id=user.id,
        token_hash=digest(token),
        csrf_hash=digest(csrf),
        expires_at=now() + timedelta(hours=settings().session_hours),
    )
    db.add(row)
    response.set_cookie(
        "ap_session",
        token,
        httponly=True,
        secure=settings().cookie_secure,
        samesite="lax",
        max_age=settings().session_hours * 3600,
        path="/",
    )
    response.set_cookie(
        "ap_csrf",
        csrf,
        httponly=False,
        secure=settings().cookie_secure,
        samesite="lax",
        max_age=settings().session_hours * 3600,
        path="/",
    )
