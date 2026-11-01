"""Reproducible sandbox fixtures. Real policy calls; one archived simulated purchase."""

from datetime import timedelta
from sqlalchemy import select, text
from .db import SessionLocal, now, uid
from .models import (
    User,
    Organization,
    Member,
    Project,
    Agent,
    Mandate,
    MandateVersion,
    PaymentIntent,
    Evaluation,
    Reservation,
    Transaction,
)
from .security import password_hash, Principal
from .config import settings
from .schemas import IntentIn
from .policy import create_intent, execute_intent


def demo_setup(db, p, start=None):
    agent = Agent(
        id=uid(),
        organization_id=p.organization_id,
        owner_id=p.user_id,
        name="Personal Shopping Assistant",
        description="Покупки из тестового каталога. Каждое намерение проходит Policy Engine.",
    )
    db.add(agent)
    db.flush()
    m = Mandate(
        id=uid(),
        owner_id=p.user_id,
        organization_id=p.organization_id,
        agent_id=agent.id,
        name="Покупки электроники",
        currency="RUB",
        categories=["electronics"],
        merchant_allowlist=[],
        merchant_denylist=[],
        per_transaction=1500000,
        daily_limit=2500000,
        weekly_limit=10000000,
        monthly_limit=25000000,
        approval_threshold=1000000,
        valid_from=start or now() - timedelta(minutes=1),
        valid_until=now() + timedelta(days=30),
    )
    db.add(m)
    db.flush()
    from .main import record

    db.add(MandateVersion(mandate_id=m.id, version=m.version, rules=record(m)))
    return agent, m


def seed():
    if settings().environment != "sandbox":
        raise RuntimeError("Demo seed is sandbox-only")
    if len(settings().demo_password) < 12:
        raise RuntimeError("DEMO_PASSWORD must be configured")
    with SessionLocal.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(73401001)"))
        if db.scalar(select(User).where(User.email == "demo@agentpass.local")):
            return
        user = User(
            id=uid(),
            email="demo@agentpass.local",
            name="Александр Петров",
            password_hash=password_hash(settings().demo_password),
        )
        org = Organization(id=uid(), name="Моя организация")
        admin_user = User(
            id=uid(),
            email="admin@agentpass.local",
            name="Администратор sandbox",
            password_hash=password_hash(settings().demo_password),
            platform_admin=True,
        )
        admin_org = Organization(id=uid(), name="AgentPass Operations")
        db.add_all([user, org, admin_user, admin_org])
        db.flush()
        db.add_all(
            [
                Member(organization_id=org.id, user_id=user.id, role="owner"),
                Member(
                    organization_id=admin_org.id, user_id=admin_user.id, role="owner"
                ),
                Project(organization_id=org.id, name="Shopping Sandbox"),
            ]
        )
        db.flush()
        p = Principal(user.id, org.id, "owner")
        agent, m = demo_setup(db, p, start=now() - timedelta(days=7))
        for amount, label in [
            (800000, "Soundcore Life Q30"),
            (1200000, "Sony WH-CH720N"),
            (1800000, "Marshall Major V"),
        ]:
            i = create_intent(
                db,
                p,
                IntentIn(
                    agent_id=agent.id,
                    mandate_id=m.id,
                    merchant="Soundstore",
                    category="electronics",
                    amount=amount,
                    currency="RUB",
                    description=label,
                    idempotency_key="seed-" + str(amount),
                    timestamp=now(),
                    structured_metadata={"fixture": True},
                ),
            )
            if i.decision == "APPROVE":
                execute_intent(db, p, i.id)
                # Historical fixture: yesterday's execution, so the interactive demo has today's full budget.
                archived = now() - timedelta(days=1)
                i.created_at = archived
                for model in (Reservation, Transaction, Evaluation):
                    for row in db.scalars(select(model).where(model.intent_id == i.id)):
                        row.created_at = archived
