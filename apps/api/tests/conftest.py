import os
from pathlib import Path

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://agentpass:local-sandbox-only@localhost:5432/agentpass_test",
)
os.environ["SEED_DEMO"] = "false"
if not os.environ["DATABASE_URL"].rsplit("/", 1)[-1].endswith("_test"):
    raise RuntimeError("Tests require a dedicated database ending in _test")
import pytest
from sqlalchemy import text
from datetime import timedelta
from fastapi.testclient import TestClient
from agentpass.db import SessionLocal, engine, Base, uid, now
from agentpass.models import User, Organization, Member, Agent, Mandate
from agentpass.security import Principal, password_hash
from agentpass.schemas import IntentIn
from agentpass.main import app


@pytest.fixture(scope="session", autouse=True)
def schema():
    # CI and local runner migrate the dedicated test database before pytest.
    with engine.connect() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version"))
    yield


@pytest.fixture(autouse=True)
def clean():
    with engine.begin() as connection:
        tables = ", ".join('"' + t.name + '"' for t in Base.metadata.sorted_tables)
        connection.execute(text("TRUNCATE " + tables + " RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def setup():
    with SessionLocal.begin() as db:
        user = User(
            id=uid(),
            email="test@example.com",
            name="Test",
            password_hash=password_hash("test-password-123"),
        )
        other = User(
            id=uid(),
            email="other@example.com",
            name="Other",
            password_hash=password_hash("other-password-123"),
        )
        org = Organization(id=uid(), name="Test Org")
        org2 = Organization(id=uid(), name="Other Org")
        db.add_all([user, other, org, org2])
        db.flush()
        db.add_all(
            [
                Member(user_id=user.id, organization_id=org.id, role="owner"),
                Member(user_id=other.id, organization_id=org2.id, role="owner"),
            ]
        )
        agent = Agent(
            id=uid(), name="Shopping", organization_id=org.id, owner_id=user.id
        )
        db.add(agent)
        db.flush()
        mandate = Mandate(
            id=uid(),
            name="Electronics",
            organization_id=org.id,
            owner_id=user.id,
            agent_id=agent.id,
            currency="RUB",
            categories=["electronics"],
            merchant_allowlist=[],
            merchant_denylist=[],
            per_transaction=1500000,
            daily_limit=2500000,
            weekly_limit=10000000,
            monthly_limit=25000000,
            approval_threshold=1000000,
            valid_from=now() - timedelta(days=1),
            valid_until=now() + timedelta(days=30),
        )
        db.add(mandate)
        db.flush()
        p = Principal(user.id, org.id, "owner")
        data = IntentIn(
            agent_id=agent.id,
            mandate_id=mandate.id,
            merchant="Soundstore",
            category="electronics",
            amount=800000,
            currency="RUB",
            description="Headphones",
            idempotency_key=uid(),
            timestamp=now(),
        )
    return p, mandate, data, Principal(other.id, org2.id, "owner")


@pytest.fixture
def client(setup):
    with TestClient(app) as client:
        response = client.post(
            "/v1/auth/login",
            json={"email": "test@example.com", "password": "test-password-123"},
        )
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = client.cookies["ap_csrf"]
        yield client
