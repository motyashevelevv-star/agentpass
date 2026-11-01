import json, logging, secrets, time
from datetime import timedelta
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, Response, Query
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect
from .db import get_db, SessionLocal, now, uid
from .models import *
from .schemas import *
from .security import *
from .policy import *
from .webhooks import public_target, encrypt
from .catalog import CATALOG
from .interpreter import DeterministicInterpreter, resolve as resolve_proposal

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("agentpass")
logging.getLogger("uvicorn.access").disabled = True


@asynccontextmanager
async def lifespan(app):
    if settings().environment in ('pilot', 'production'):
        with SessionLocal() as db:
            unsafe_role = db.execute(text('SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user')).scalar()
            owns_tables = db.execute(text("SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND pg_get_userbyid(c.relowner)=current_user)")).scalar()
            seeded = db.scalar(select(User.id).where(User.email.in_(['demo@agentpass.local','admin@agentpass.local'])))
            if unsafe_role or owns_tables or seeded:
                raise RuntimeError('Pilot rejects privileged runtime DB role, schema ownership or demo accounts')
    if settings().seed_demo:
        from .seed import seed

        seed()
    yield


app = FastAPI(
    title="AgentPass API",
    version="0.1.0",
    description="Детерминированное управление полномочиями. Локальная симуляция и опциональный внешний TEST checkout; без реальных списаний. Суммы в минимальных единицах валюты.",
    openapi_url="/v1/openapi.json",
    docs_url="/v1/docs",
    lifespan=lifespan,
)


@app.exception_handler(DomainError)
async def domain_error(request, error):
    return JSONResponse(
        status_code=error.status,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
        headers={"Retry-After": "60"} if error.status == 429 else None,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Проверьте данные запроса",
                "fields": [
                    {"path": list(e["loc"]), "message": e["msg"]}
                    for e in error.errors()
                ],
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error(request, error):
    return JSONResponse(
        status_code=error.status_code,
        headers=error.headers,
        content={
            "error": {
                "code": {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(
                    error.status_code, "HTTP_ERROR"
                ),
                "message": str(error.detail),
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.exception_handler(IntegrityError)
async def integrity_error(request, error):
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "CONFLICT",
                "message": "Запись конфликтует с существующими данными",
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.middleware("http")
async def request_logging(request, call_next):
    start = time.perf_counter()
    rid = uid()
    request.state.request_id = rid
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin not in settings().allowed_web_origins:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "ORIGIN_DENIED",
                        "message": "Недопустимый Origin",
                        "request_id": rid,
                    }
                },
            )
    size = request.headers.get("content-length")
    if size and (not size.isdigit() or int(size) > 65536):
        return JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "PAYLOAD_TOO_LARGE",
                    "message": "Запрос превышает 64 KiB",
                    "request_id": rid,
                }
            },
        )
    try:
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            chunks = bytearray()
            async for chunk in request.stream():
                chunks.extend(chunk)
                if len(chunks) > 65536:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "code": "PAYLOAD_TOO_LARGE",
                                "message": "Запрос превышает 64 KiB",
                                "request_id": rid,
                            }
                        },
                    )
            request._body = bytes(chunks)
        response = await call_next(request)
    except Exception as error:
        logger.error(
            json.dumps(
                {
                    "event": "http.error",
                    "request_id": rid,
                    "error_class": type(error).__name__,
                }
            )
        )
        response = JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Внутренняя ошибка. Сохраните request_id для диагностики.",
                    "request_id": rid,
                }
            },
        )
    duration = int((time.perf_counter() - start) * 1000)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    # Only route template, status and duration; credentials and bodies are never logged.
    route = request.scope.get("route")
    path = getattr(route, "path", "/unmatched")
    logger.info(
        json.dumps(
            {
                "event": "http.request",
                "request_id": rid,
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "duration_ms": duration,
            }
        )
    )
    if path not in (
        "/health",
        "/v1/analytics",
        "/v1/developer/requests",
        "/v1/admin/metrics",
    ):
        try:
            with SessionLocal.begin() as db:
                db.add(
                    RequestLog(
                        organization_id=getattr(request.state, "org_id", None),
                        request_id=rid,
                        method=request.method,
                        path=path,
                        status_code=response.status_code,
                        duration_ms=duration,
                    )
                )
        except Exception:
            logger.error(json.dumps({"event": "request_log.failed", "request_id": rid}))
    return response


def record(row):
    hidden = {
        "password_hash",
        "key_hash",
        "secret_ciphertext",
        "token_hash",
        "csrf_hash",
        "fingerprint",
        "mfa_secret_ciphertext",
        "mfa_pending_ciphertext",
        "mfa_last_counter",
        "lease_token",
    }
    return jsonable_encoder(
        {
            c.key: getattr(row, c.key)
            for c in inspect(row).mapper.column_attrs
            if c.key not in hidden
        }
    )


def page(db, stmt, limit, offset):
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    return {
        "items": [record(x) for x in db.scalars(stmt.limit(limit).offset(offset))],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def owned_rows(model, p):
    stmt = select(model).where(model.organization_id == p.organization_id)
    if hasattr(model, "owner_id"):
        stmt = stmt.where(model.owner_id == p.user_id)
    if p.agent_id and model is Agent:
        stmt = stmt.where(Agent.id == p.agent_id)
    elif p.agent_id and hasattr(model, "agent_id"):
        stmt = stmt.where(model.agent_id == p.agent_id)
    elif p.agent_id and model is Transaction:
        stmt = stmt.join(
            PaymentIntent, Transaction.intent_id == PaymentIntent.id
        ).where(PaymentIntent.agent_id == p.agent_id)
    return stmt.order_by(model.created_at.desc())


def intent_view(db, intent):
    result = record(intent)
    a = db.scalar(select(Approval).where(Approval.intent_id == intent.id))
    r = db.scalar(select(Reservation).where(Reservation.intent_id == intent.id))
    tx = db.scalar(select(Transaction).where(Transaction.intent_id == intent.id))
    result.update(
        approval=record(a) if a else None,
        reservation=record(r) if r else None,
        transaction=record(tx) if tx else None,
    )
    execution = db.scalar(select(PaymentExecution).where(PaymentExecution.intent_id == intent.id))
    result['execution'] = record(execution) if execution else None
    result['decision_kind'] = 'ASK_USER' if intent.decision == 'ASK' else intent.decision
    return result


@app.get("/health", tags=["System"])
def health(db=Depends(get_db, scope="function")):
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "environment": settings().environment,
        "payments": "simulated",
    }


@app.get("/v1/sandbox/access", tags=["Sandbox"])
def sandbox_access():
    config = settings()
    return {
        "quick_login": config.environment == "sandbox"
        and config.seed_demo
        and config.demo_password == "AgentPass-demo-2026!"
    }


@app.post("/v1/auth/login", tags=["Auth"])
def login(
    data: LoginIn,
    request: Request,
    response: Response,
    db=Depends(get_db, scope="function"),
):
    rate_limit('login-ip:' + digest(request.client.host if request.client else 'unknown'), 30)
    rate_limit(
        "login:"
        + digest(
            (request.client.host if request.client else "unknown") + data.email.lower()
        ),
        10,
    )
    user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
    # Equal-cost hash for unknown users.
    valid = (
        verify_password(data.password, user.password_hash)
        if user
        else verify_password(data.password, DUMMY_PASSWORD_HASH)
    )
    if not user or not valid:
        fail(401, "INVALID_CREDENTIALS", "Неверный email или пароль")
    if user.mfa_secret_ciphertext:
        from .mfa import verify_code
        user = db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
        verify_code(user, data.mfa_code)
    old = request.cookies.get("ap_session")
    if old:
        row = db.scalar(
            select(LoginSession).where(LoginSession.token_hash == digest(old))
        )
        if row:
            row.revoked_at = now()
    new_session(db, user, response)
    member = db.scalar(
        select(Member).where(Member.user_id == user.id).order_by(Member.created_at)
    )
    if member:
        request.state.org_id = member.organization_id
        audit(
            db,
            Principal(user.id, member.organization_id, member.role),
            "session.created",
            user.id,
        )
    return {"user": record(user)}


@app.post("/v1/auth/register", status_code=201, tags=["Auth"])
def register(
    data: RegisterIn,
    request: Request,
    response: Response,
    db=Depends(get_db, scope="function"),
):
    if not settings().allow_public_registration:
        fail(403, 'REGISTRATION_DISABLED', 'Регистрация выполняется администратором пилота')
    rate_limit(
        "register:" + digest(request.client.host if request.client else "unknown"), 5
    )
    user = User(
        id=uid(),
        email=data.email,
        name=data.name,
        password_hash=password_hash(data.password),
    )
    org = Organization(id=uid(), name=data.organization_name)
    db.add_all([user, org])
    db.flush()
    db.add(Member(organization_id=org.id, user_id=user.id, role="owner"))
    new_session(db, user, response)
    audit(db, Principal(user.id, org.id, "owner"), "user.registered", user.id)
    return {"user": record(user), "organization": record(org)}


@app.get("/v1/auth/me", tags=["Auth"])
def me(p=Depends(authenticate), db=Depends(get_db, scope="function")):
    p.user()
    orgs = []
    for member in db.scalars(select(Member).where(Member.user_id == p.user_id)):
        org = record(db.get(Organization, member.organization_id))
        org["role"] = member.role
        orgs.append(org)
    return {
        "user": dict(record(db.get(User, p.user_id)), mfa_enabled=bool(db.get(User, p.user_id).mfa_secret_ciphertext)),
        "organization_id": p.organization_id,
        "role": p.role,
        "organizations": orgs,
        "environment": settings().environment,
    }


@app.post("/v1/auth/logout", tags=["Auth"])
def logout(
    response: Response, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.user()
    db.get(LoginSession, p.session_id).revoked_at = now()
    response.delete_cookie("ap_session")
    response.delete_cookie("ap_csrf")
    return {"ok": True}


@app.get("/v1/security/sessions", tags=["Security"])
def sessions(p=Depends(authenticate), db=Depends(get_db, scope="function")):
    p.user()
    return {
        "items": [
            {
                "id": s.id,
                "created_at": s.created_at,
                "expires_at": s.expires_at,
                "current": s.id == p.session_id,
            }
            for s in db.scalars(
                select(LoginSession)
                .where(
                    LoginSession.user_id == p.user_id,
                    LoginSession.revoked_at.is_(None),
                    LoginSession.expires_at > now(),
                )
                .order_by(LoginSession.created_at.desc())
            )
        ]
    }


@app.delete("/v1/security/sessions/{sid}", tags=["Security"])
def revoke_session(
    sid: str, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.user()
    row = db.get(LoginSession, sid)
    if not row or row.user_id != p.user_id:
        fail(404, "NOT_FOUND", "Сессия не найдена")
    row.revoked_at = now()
    audit(db, p, "session.revoked", sid)
    return {"ok": True}


@app.patch("/v1/settings/profile", tags=["Settings"])
def profile(
    data: ProfileIn, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.user()
    user = db.get(User, p.user_id)
    user.name = data.name
    audit(db, p, "profile.updated", user.id)
    return record(user)


@app.post("/v1/security/password", tags=["Security"])
def change_password(
    data: PasswordIn, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.user()
    from .mfa import step_up
    step_up(db, p, data.mfa_code)
    user = db.get(User, p.user_id)
    if not verify_password(data.current_password, user.password_hash):
        fail(400, "PASSWORD_MISMATCH", "Текущий пароль неверен")
    if settings().environment in ('pilot','production') and (len(data.new_password)<16 or data.new_password=='AgentPass-demo-2026!'):
        fail(422, 'PASSWORD_POLICY', 'Pilot требует уникальный пароль длиной не менее 16 символов')
    user.password_hash = password_hash(data.new_password)
    for row in db.scalars(
        select(LoginSession).where(
            LoginSession.user_id == p.user_id, LoginSession.id != p.session_id
        )
    ):
        row.revoked_at = now()
    audit(db, p, "password.changed", user.id)
    return {"ok": True}


@app.get("/v1/agents", tags=["Agents"])
def agents(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    return page(db, owned_rows(Agent, p), limit, offset)


@app.post("/v1/agents", status_code=201, tags=["Agents"])
def create_agent(
    data: AgentIn, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.developer()
    if data.project_id:
        project = db.get(Project, data.project_id)
        if not project or project.organization_id != p.organization_id:
            fail(404, "PROJECT_NOT_FOUND", "Проект не найден")
    agent = Agent(
        id=uid(),
        organization_id=p.organization_id,
        owner_id=p.user_id,
        **data.model_dump(),
    )
    db.add(agent)
    db.flush()
    audit(db, p, "agent.created", agent.id)
    return record(agent)


@app.patch("/v1/agents/{agent_id}/status", tags=["Agents"])
def agent_status(
    agent_id: str,
    status: Literal["active", "paused"],
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    p.developer()
    row = db.scalar(
        select(Agent)
        .where(
            Agent.id == agent_id,
            Agent.owner_id == p.user_id,
            Agent.organization_id == p.organization_id,
        )
        .with_for_update()
    )
    if not row:
        fail(404, "AGENT_NOT_FOUND", "Агент не найден")
    row.status = status
    audit(db, p, "agent." + status, row.id)
    return record(row)


@app.get("/v1/mandates", tags=["Mandates"])
def mandates(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    result = page(db, owned_rows(Mandate, p), limit, offset)
    for item in result["items"]:
        m = db.get(Mandate, item["id"])
        item["usage"] = budget_usage(db, m)
        item["agent_name"] = db.get(Agent, m.agent_id).name
    return result


def save_version(db, m):
    db.flush()
    db.add(MandateVersion(mandate_id=m.id, version=m.version, rules=record(m)))


@app.post("/v1/mandates", status_code=201, tags=["Mandates"])
def create_mandate(
    data: MandateIn, request: Request, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.user()
    from .mfa import step_up
    step_up(db, p, request.headers.get('x-mfa-code'))
    if p.role == "viewer":
        fail(403, "FORBIDDEN", "Нет прав делегирования")
    agent = db.scalar(
        select(Agent)
        .where(
            Agent.id == data.agent_id,
            Agent.owner_id == p.user_id,
            Agent.organization_id == p.organization_id,
        )
        .with_for_update()
    )
    if not agent:
        fail(404, "AGENT_NOT_FOUND", "Агент не найден")
    m = Mandate(
        id=uid(),
        owner_id=p.user_id,
        organization_id=p.organization_id,
        **data.model_dump(),
    )
    db.add(m)
    db.flush()
    save_version(db, m)
    audit(db, p, "mandate.created", m.id)
    return record(m)


@app.put("/v1/mandates/{mid}", tags=["Mandates"])
def update_mandate(
    mid: str,
    data: MandateIn,
    request: Request,
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    p.user()
    from .mfa import step_up
    step_up(db, p, request.headers.get('x-mfa-code'))
    if p.role == "viewer":
        fail(403, "FORBIDDEN", "Нет прав делегирования")
    m, _ = owned_mandate(db, p, mid)
    if m.status != "active":
        fail(409, "MANDATE_REVOKED", "Отозванный мандат нельзя изменить")
    if data.agent_id != m.agent_id:
        fail(422, "AGENT_IMMUTABLE", "Нельзя менять агента мандата")
    for key, value in data.model_dump().items():
        setattr(m, key, value)
    m.version += 1
    m.updated_at = now()
    save_version(db, m)
    audit(db, p, "mandate.updated", m.id, {"version": m.version})
    return record(m)


@app.post("/v1/mandates/{mid}/revoke", tags=["Mandates"])
def revoke_mandate(
    mid: str, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.user()
    if p.role == "viewer":
        fail(403, "FORBIDDEN", "Нет прав отзыва")
    m, _ = owned_mandate(db, p, mid)
    if m.status == "revoked":
        return record(m)
    m.status = "revoked"
    m.version += 1
    m.updated_at = now()
    save_version(db, m)
    for intent in db.scalars(
        select(PaymentIntent).where(
            PaymentIntent.mandate_id == mid,
            PaymentIntent.status.in_(["authorized", "pending"]),
        )
    ):
        r = db.scalar(select(Reservation).where(Reservation.intent_id == intent.id))
        if r and r.status == "held":
            r.status = "released"
        a = db.scalar(select(Approval).where(Approval.intent_id == intent.id))
        if a and a.status == "pending":
            a.status = "invalidated"
            a.resolved_at = now()
        record_evaluation(
            db, intent, m, "DENY", reasons(["MANDATE_REVOKED"]), "revocation"
        )
        emit(db, p.organization_id, "intent.invalidated", intent)
    audit(db, p, "mandate.revoked", mid)
    return record(m)


@app.get("/v1/mandates/{mid}/versions", tags=["Mandates"])
def versions(mid: str, p=Depends(authenticate), db=Depends(get_db, scope="function")):
    owned_mandate(db, p, mid, lock=False)
    return {
        "items": [
            record(v)
            for v in db.scalars(
                select(MandateVersion)
                .where(MandateVersion.mandate_id == mid)
                .order_by(MandateVersion.version.desc())
            )
        ]
    }


@app.post("/v1/intents", status_code=201, tags=["Intents"])
def post_intent(
    data: IntentIn,
    request: Request,
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    header = request.headers.get("idempotency-key")
    if header and header != data.idempotency_key:
        fail(
            422, "IDEMPOTENCY_KEY_MISMATCH", "Header и body должны содержать один ключ"
        )
    return intent_view(db, create_intent(db, p, data))


@app.get("/v1/intents", tags=["Intents"])
def intents(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    decision: Literal["APPROVE", "ASK", "DENY"] | None = None,
    search: str = Query("", max_length=120),
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    stmt = owned_rows(PaymentIntent, p)
    if decision:
        stmt = stmt.where(PaymentIntent.decision == decision)
    if search:
        from sqlalchemy import or_

        safe = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(
            or_(
                PaymentIntent.merchant.ilike("%" + safe + "%", escape="\\"),
                PaymentIntent.description.ilike("%" + safe + "%", escape="\\"),
            )
        )
    result = page(db, stmt, limit, offset)
    result["items"] = [
        intent_view(db, db.get(PaymentIntent, i["id"])) for i in result["items"]
    ]
    return result


@app.get("/v1/intents/{intent_id}", tags=["Intents"])
def get_intent(
    intent_id: str, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    intent = owned_intent(db, p, intent_id)
    m, _ = owned_mandate(db, p, intent.mandate_id)
    expire_for_mandate(db, m)
    return intent_view(db, intent)


@app.post("/v1/intents/{intent_id}/execute", tags=["Intents"])
def execute(
    intent_id: str, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    return intent_view(db, execute_intent(db, p, intent_id))


@app.post("/v1/intents/{intent_id}/cancel", tags=["Intents"])
def cancel(
    intent_id: str, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    return intent_view(db, cancel_intent(db, p, intent_id))


@app.get("/v1/evaluations", tags=["Evaluations"])
def evaluations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    stmt = (
        select(Evaluation)
        .join(PaymentIntent, Evaluation.intent_id == PaymentIntent.id)
        .where(
            PaymentIntent.organization_id == p.organization_id,
            PaymentIntent.owner_id == p.user_id,
        )
    )
    if p.agent_id:
        stmt = stmt.where(PaymentIntent.agent_id == p.agent_id)
    return page(db, stmt.order_by(Evaluation.created_at.desc()), limit, offset)


@app.post("/v1/evaluations/preview", tags=["Evaluations"])
def preview(
    data: IntentIn, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.developer()
    m, a = owned_mandate(db, p, data.mandate_id)
    if a.id != data.agent_id:
        fail(404, "MANDATE_NOT_FOUND", "Мандат не найден")
    expire_for_mandate(db, m)
    decision, why = check_rules(m, a, data, budget_usage(db, m))
    return {
        "decision": decision,
        "reasons": why,
        "rule_version": m.version,
        "preview": True,
        "reservation_created": False,
    }


@app.get("/v1/approvals", tags=["Approvals"])
def approvals(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    p.user()
    result = page(db, owned_rows(Approval, p), limit, offset)
    for a in result["items"]:
        a["intent"] = record(db.get(PaymentIntent, a["intent_id"]))
    return result


@app.post("/v1/approvals/{aid}/resolve", tags=["Approvals"])
def resolve(
    aid: str,
    data: ApprovalIn,
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    from .mfa import step_up
    if data.action == 'approve':
        step_up(db, p, data.mfa_code)
    return intent_view(db, resolve_approval(db, p, aid, data.action))


@app.get("/v1/transactions", tags=["Transactions"])
def transactions(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    return page(db, owned_rows(Transaction, p), limit, offset)


@app.get("/v1/audit-events", tags=["Audit"])
def audits(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    p.user()
    stmt = owned_rows(AuditEvent, p)
    if p.role != "owner":
        stmt = stmt.where(AuditEvent.actor_id == p.user_id)
    return page(db, stmt, limit, offset)


@app.get("/v1/analytics", tags=["Analytics"])
def analytics(
    days: int = Query(7, ge=1, le=90),
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    p.user()
    rows = list(db.scalars(owned_rows(PaymentIntent, p)))
    txs = list(db.scalars(owned_rows(Transaction, p)))
    evaluations = list(
        db.scalars(
            select(Evaluation)
            .join(PaymentIntent, Evaluation.intent_id == PaymentIntent.id)
            .where(
                PaymentIntent.organization_id == p.organization_id,
                PaymentIntent.owner_id == p.user_id,
            )
        )
    )
    decisions = Counter(i.decision for i in rows)
    initial = Counter(e.decision for e in evaluations if e.stage == "initial")
    cats = Counter()
    declines = Counter()
    activity = Counter()
    trend = defaultdict(int)
    for i in rows:
        activity[i.agent_id] += 1
        if i.decision == "DENY":
            for r in i.reasons:
                declines[r["message"]] += 1
    for t in txs:
        i = db.get(PaymentIntent, t.intent_id)
        cats[i.category] += t.amount
        trend[t.created_at.date().isoformat()] += t.amount
    series = [
        {
            "date": (now() - timedelta(days=days - 1 - n)).date().isoformat(),
            "amount": trend[(now() - timedelta(days=days - 1 - n)).date().isoformat()],
        }
        for n in range(days)
    ]
    budgets = []
    for m in db.scalars(
        owned_rows(Mandate, p).where(
            Mandate.status == "active",
            Mandate.valid_from <= now(),
            Mandate.valid_until > now(),
        )
    ):
        budgets.append(
            {
                "id": m.id,
                "name": m.name,
                "currency": m.currency,
                "daily_limit": m.daily_limit,
                "weekly_limit": m.weekly_limit,
                "monthly_limit": m.monthly_limit,
                "usage": budget_usage(db, m),
            }
        )
    return {
        "total": len(rows),
        "decisions": dict(decisions),
        "initial_decisions": dict(initial),
        "evaluations": len(evaluations),
        "active_agents": db.scalar(
            select(func.count())
            .select_from(Agent)
            .where(
                Agent.organization_id == p.organization_id,
                Agent.owner_id == p.user_id,
                Agent.status == "active",
            )
        ),
        "spent": sum(t.amount for t in txs if t.currency == "RUB"),
        "pending": sum(i.status == "pending" for i in rows),
        "reserved": db.scalar(
            select(func.coalesce(func.sum(Reservation.amount), 0))
            .join(Mandate)
            .where(
                Mandate.owner_id == p.user_id,
                Mandate.organization_id == p.organization_id,
                or_(Reservation.status == 'inflight', and_(Reservation.status == "held", Reservation.expires_at > now())),
            )
        ),
        "categories": [{"name": k, "amount": v} for k, v in cats.items()],
        "decline_reasons": [{"name": k, "count": v} for k, v in declines.items()],
        "agent_activity": [
            {"name": db.get(Agent, k).name, "count": v} for k, v in activity.items()
        ],
        "trend": series,
        "budgets": budgets,
    }


@app.get("/v1/developer/projects", tags=["Developer"])
def projects(p=Depends(authenticate), db=Depends(get_db, scope="function")):
    p.developer()
    return {"items": [record(x) for x in db.scalars(owned_rows(Project, p))]}


@app.post("/v1/developer/projects", status_code=201, tags=["Developer"])
def new_project(
    data: NameIn, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.developer()
    row = Project(id=uid(), name=data.name, organization_id=p.organization_id)
    db.add(row)
    db.flush()
    audit(db, p, "project.created", row.id)
    return record(row)


@app.post("/v1/organizations", status_code=201, tags=["Organizations"])
def new_org(
    data: NameIn, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.user()
    row = Organization(id=uid(), name=data.name)
    db.add(row)
    db.flush()
    db.add(Member(organization_id=row.id, user_id=p.user_id, role="owner"))
    audit(db, Principal(p.user_id, row.id, "owner"), "organization.created", row.id)
    return record(row)


@app.get("/v1/organizations/members", tags=["Organizations"])
def members(p=Depends(authenticate), db=Depends(get_db, scope="function")):
    p.owner()
    return {
        "items": [
            dict(
                record(m),
                email=db.get(User, m.user_id).email,
                name=db.get(User, m.user_id).name,
            )
            for m in db.scalars(
                select(Member).where(Member.organization_id == p.organization_id)
            )
        ]
    }


@app.post("/v1/organizations/members", status_code=201, tags=["Organizations"])
def add_member(
    data: MemberIn, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.owner()
    user = db.scalar(select(User).where(User.email == data.email.lower().strip()))
    if not user:
        fail(404, "USER_NOT_FOUND", "Пользователь должен сначала зарегистрироваться")
    row = Member(
        id=uid(), organization_id=p.organization_id, user_id=user.id, role=data.role
    )
    db.add(row)
    db.flush()
    audit(db, p, "member.added", row.id, {"role": data.role})
    return record(row)


@app.delete("/v1/organizations/members/{mid}", tags=["Organizations"])
def remove_member(
    mid: str, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.owner()
    row = db.get(Member, mid)
    if not row or row.organization_id != p.organization_id:
        fail(404, "NOT_FOUND", "Участник не найден")
    if row.role == "owner":
        fail(409, "OWNER_IMMUTABLE", "Владельца нельзя удалить")
    row = db.scalar(
        select(Member)
        .where(Member.id == mid, Member.organization_id == p.organization_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not row:
        fail(404, "NOT_FOUND", "Участник не найден")
    if row.role == "owner":
        fail(409, "OWNER_IMMUTABLE", "Владельца нельзя удалить")
    keys = list(
        db.scalars(
            select(APIKey)
            .where(
                APIKey.organization_id == p.organization_id,
                APIKey.created_by == row.user_id,
                APIKey.revoked_at.is_(None),
            )
            .order_by(APIKey.id)
            .with_for_update()
        )
    )
    for key in keys:
        key.revoked_at = now()
    db.delete(row)
    audit(db, p, "member.removed", mid, {"keys_revoked": len(keys)})
    return {"ok": True, "keys_revoked": len(keys)}


@app.get("/v1/developer/api-keys", tags=["Developer"])
def keys(p=Depends(authenticate), db=Depends(get_db, scope="function")):
    p.developer()
    return {
        "items": [
            record(k)
            for k in db.scalars(
                owned_rows(APIKey, p).where(APIKey.created_by == p.user_id)
            )
        ]
    }


@app.post("/v1/developer/api-keys", status_code=201, tags=["Developer"])
def new_key(data: KeyIn, request: Request, p=Depends(authenticate), db=Depends(get_db, scope="function")):
    p.developer()
    from .mfa import step_up
    step_up(db, p, request.headers.get('x-mfa-code'))
    agent = db.get(Agent, data.agent_id)
    if (
        not agent
        or agent.organization_id != p.organization_id
        or agent.owner_id != p.user_id
    ):
        fail(404, "AGENT_NOT_FOUND", "Агент не найден")
    raw = "ap_sk_sandbox_" + secrets.token_urlsafe(32)
    row = APIKey(
        id=uid(),
        organization_id=p.organization_id,
        created_by=p.user_id,
        agent_id=data.agent_id,
        name=data.name,
        prefix=raw[:20],
        key_hash=digest(raw),
        expires_at=now() + timedelta(days=data.expires_days),
        scopes=['intents:read','payments:read','payments:execute'] if data.purpose == 'executor' else ['intents:write','intents:read'],
    )
    db.add(row)
    db.flush()
    audit(db, p, "api_key.created", row.id)
    return dict(record(row), secret=raw)


@app.delete("/v1/developer/api-keys/{kid}", tags=["Developer"])
def revoke_key(kid: str, p=Depends(authenticate), db=Depends(get_db, scope="function")):
    p.developer()
    row = db.get(APIKey, kid)
    if (
        not row
        or row.organization_id != p.organization_id
        or row.created_by != p.user_id
    ):
        fail(404, "NOT_FOUND", "Ключ не найден")
    row.revoked_at = now()
    audit(db, p, "api_key.revoked", kid)
    return {"ok": True}


@app.get("/v1/developer/requests", tags=["Developer"])
def requests_log(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    p.developer()
    return page(db, owned_rows(RequestLog, p), limit, offset)


@app.get("/v1/webhooks", tags=["Webhooks"])
def hooks(p=Depends(authenticate), db=Depends(get_db, scope="function")):
    p.developer()
    return {"items": [record(x) for x in db.scalars(owned_rows(WebhookEndpoint, p))]}


@app.post("/v1/webhooks", status_code=201, tags=["Webhooks"])
def new_hook(
    data: WebhookIn, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.developer()
    public_target(data.url)
    secret = "whsec_" + secrets.token_urlsafe(32)
    row = WebhookEndpoint(
        id=uid(),
        organization_id=p.organization_id,
        name=data.name,
        url=data.url,
        secret_ciphertext=encrypt(secret),
    )
    db.add(row)
    db.flush()
    audit(db, p, "webhook.created", row.id)
    return dict(record(row), secret=secret)


@app.delete("/v1/webhooks/{hid}", tags=["Webhooks"])
def disable_hook(
    hid: str, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.developer()
    row = db.get(WebhookEndpoint, hid)
    if not row or row.organization_id != p.organization_id:
        fail(404, "NOT_FOUND", "Endpoint не найден")
    row.active = False
    audit(db, p, "webhook.disabled", hid)
    return {"ok": True}


@app.get("/v1/webhooks/deliveries", tags=["Webhooks"])
def deliveries(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    p.developer()
    return page(db, owned_rows(WebhookDelivery, p), limit, offset)


@app.post("/v1/webhooks/{hid}/test", tags=["Webhooks"])
def test_hook(hid: str, p=Depends(authenticate), db=Depends(get_db, scope="function")):
    p.developer()
    endpoint = db.get(WebhookEndpoint, hid)
    if (
        not endpoint
        or endpoint.organization_id != p.organization_id
        or not endpoint.active
    ):
        fail(404, "NOT_FOUND", "Активный endpoint не найден")
    row = WebhookDelivery(
        id=uid(),
        organization_id=p.organization_id,
        endpoint_id=hid,
        payload={
            "id": uid(),
            "event": "sandbox.test",
            "created_at": now().isoformat(),
            "data": {"simulated": True},
        },
    )
    db.add(row)
    db.flush()
    return record(row)


@app.get("/v1/catalog", tags=["Agent Console"])
def catalog(p=Depends(authenticate)):
    p.user()
    return {"items": CATALOG}


@app.post("/v1/console/run", tags=["Agent Console"])
def run_console(
    data: ConsoleIn, p=Depends(authenticate), db=Depends(get_db, scope="function")
):
    p.user()
    m, _ = owned_mandate(db, p, data.mandate_id)
    interpreter=DeterministicInterpreter()
    product, budget = resolve_proposal(interpreter.propose(data.prompt))
    existing = db.scalar(
        select(PaymentIntent).where(
            PaymentIntent.agent_id == m.agent_id,
            PaymentIntent.idempotency_key == data.idempotency_key,
        )
    )
    timestamp = existing.timestamp if existing else now()
    intent = create_intent(
        db,
        p,
        IntentIn(
            agent_id=m.agent_id,
            mandate_id=m.id,
            merchant=product["merchant"],
            category=product["category"],
            amount=product["amount"],
            currency=product["currency"],
            description=product["name"],
            idempotency_key=data.idempotency_key,
            timestamp=timestamp,
            merchant_id=existing.merchant_id if existing else 'catalog:'+product['merchant'].casefold(),
            order_id=existing.order_id if existing else 'console:'+data.idempotency_key,
            structured_metadata={"product_id": product["id"], "prompt": data.prompt},
        ),
    )
    if intent.status == "authorized" and settings().environment in ('sandbox','development'):
        intent = execute_intent(db, p, intent.id)
    return {
        "product": product,
        "interpreted_budget": budget,
        "parser": interpreter.name,
        "intent": intent_view(db, intent),
    }


@app.post("/v1/sandbox/demo", status_code=201, tags=["Sandbox"])
def demo(p=Depends(authenticate), db=Depends(get_db, scope="function")):
    p.developer()
    if settings().environment != "sandbox":
        fail(403, "SANDBOX_ONLY", "Доступно только в sandbox")
    from .seed import demo_setup

    agent, m = demo_setup(db, p)
    audit(db, p, "sandbox.demo.created", m.id)
    return {"agent": record(agent), "mandate": record(m)}


def admin(p):
    p.user()
    if not p.platform_admin:
        fail(403, "ADMIN_REQUIRED", "Нужна роль администратора платформы")


@app.get("/v1/admin/organizations", tags=["Admin"])
def admin_orgs(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    admin(p)
    return page(
        db, select(Organization).order_by(Organization.created_at.desc()), limit, offset
    )


@app.patch("/v1/admin/organizations/{oid}", tags=["Admin"])
def admin_org_status(
    oid: str,
    status: Literal["active", "suspended"],
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    admin(p)
    row = db.scalar(
        select(Organization)
        .where(Organization.id == oid)
        .with_for_update(key_share=True)
    )
    if not row:
        fail(404, "NOT_FOUND", "Организация не найдена")
    if oid == p.organization_id and status == "suspended":
        fail(409, "SELF_SUSPENSION", "Нельзя приостановить собственную организацию")
    row.status = status
    audit(db, p, "organization." + status, oid)
    return record(row)


@app.get("/v1/admin/metrics", tags=["Admin"])
def metrics(p=Depends(authenticate), db=Depends(get_db, scope="function")):
    admin(p)
    since = now() - timedelta(hours=24)
    logs = list(db.scalars(select(RequestLog).where(RequestLog.created_at >= since)))
    return {
        "organizations": db.scalar(select(func.count()).select_from(Organization)),
        "requests_24h": len(logs),
        "errors_24h": sum(r.status_code >= 500 for r in logs),
        "denied_requests_24h": sum(r.status_code in (401, 403, 429) for r in logs),
        "average_latency_ms": round(sum(r.duration_ms for r in logs) / len(logs), 1)
        if logs
        else 0,
        "webhook_backlog": db.scalar(
            select(func.count())
            .select_from(WebhookDelivery)
            .where(WebhookDelivery.status.in_(["pending", "retry"]))
        ),
        "database": "connected",
        "environment": settings().environment,
        "payment_mode": "simulated",
    }


@app.get("/v1/admin/events", tags=["Admin"])
def admin_events(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    admin(p)
    return page(
        db, select(AuditEvent).order_by(AuditEvent.created_at.desc()), limit, offset
    )


@app.get("/v1/admin/requests", tags=["Admin"])
def admin_requests(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    p=Depends(authenticate),
    db=Depends(get_db, scope="function"),
):
    admin(p)
    return page(
        db, select(RequestLog).order_by(RequestLog.created_at.desc()), limit, offset
    )


@app.get("/v1/webhooks/config", tags=["Webhooks"])
def webhook_config(p=Depends(authenticate)):
    p.developer()
    return {
        "sandbox_receiver_url": settings().sandbox_receiver_url
        if settings().environment == "sandbox"
        else None
    }


@app.post("/v1/sandbox/webhook-receiver", tags=["Sandbox"])
async def sandbox_receiver(request: Request, db=Depends(get_db, scope="function")):
    if settings().environment != "sandbox":
        fail(404, "NOT_FOUND", "Endpoint не найден")
    from .webhooks import decrypt, verify_signature
    from .security import digest
    from sqlalchemy.dialects.postgresql import insert
    import hashlib

    delivery_id = request.headers.get("x-agentpass-delivery", "")
    delivery = db.get(WebhookDelivery, delivery_id)
    if not delivery:
        fail(401, "INVALID_DELIVERY", "Доставка не найдена")
    endpoint = db.get(WebhookEndpoint, delivery.endpoint_id)
    if not endpoint.active or endpoint.url != settings().sandbox_receiver_url:
        fail(401, "INVALID_ENDPOINT", "Неподходящий endpoint")
    body = await request.body()
    if len(body) > 65536:
        fail(413, "PAYLOAD_TOO_LARGE", "Слишком большой запрос")
    if not verify_signature(
        decrypt(endpoint.secret_ciphertext),
        request.headers.get("x-agentpass-signature", ""),
        body,
    ):
        fail(401, "INVALID_SIGNATURE", "Подпись недействительна или истекла")
    try:
        payload = json.loads(body)
    except ValueError:
        fail(422, "INVALID_JSON", "Некорректный JSON")
    if payload.get("id") != delivery.payload["id"]:
        fail(409, "EVENT_MISMATCH", "Событие не соответствует доставке")
    body_hash = hashlib.sha256(body).hexdigest()
    existing = db.get(WebhookReceipt, delivery_id)
    if existing and existing.body_hash != body_hash:
        fail(409, "REPLAY_CONFLICT", "ID доставки уже использован")
    stmt = insert(WebhookReceipt).values(
        id=delivery_id,
        organization_id=endpoint.organization_id,
        endpoint_id=endpoint.id,
        event=payload["event"],
        body_hash=body_hash,
    )
    # ORM default created_at is applied to this insert; duplicate deliveries are acknowledged.
    inserted = db.scalar(
        stmt.on_conflict_do_nothing(index_elements=["id"]).returning(WebhookReceipt.id)
    )
    if inserted:
        audit(
            db,
            Principal("sandbox-receiver", endpoint.organization_id, "system"),
            "webhook.signature_verified",
            delivery_id,
            {"event": payload["event"]},
        )
    return {
        "received": True,
        "signature_verified": True,
        "duplicate": not bool(inserted),
    }


@app.get("/v1/webhooks/receipts", tags=["Webhooks"])
def webhook_receipts(p=Depends(authenticate), db=Depends(get_db, scope="function")):
    p.developer()
    return {
        "items": [
            record(x) for x in db.scalars(owned_rows(WebhookReceipt, p).limit(20))
        ]
    }


from .pilot_api import router as pilot_router
app.include_router(pilot_router)
