from datetime import timedelta
from sqlalchemy import select
from agentpass.db import SessionLocal, now, uid
from agentpass.models import APIKey, Reservation, Approval, User, Member
from agentpass.security import digest


def test_unauthenticated(client):
    client.cookies.clear()
    assert client.get("/v1/mandates").status_code == 401


def test_csrf(client, setup):
    client.headers.pop("X-CSRF-Token")
    assert (
        client.post("/v1/intents", json=setup[2].model_dump(mode="json")).status_code
        == 403
    )


def test_origin(client, setup):
    response = client.post(
        "/v1/intents",
        json=setup[2].model_dump(mode="json"),
        headers={"Origin": "https://malicious.example"},
    )
    assert response.status_code == 403


def test_admin_not_user(client):
    assert client.get("/v1/admin/metrics").status_code == 403


def test_wrong_organization_header(client, setup):
    assert (
        client.get(
            "/v1/mandates", headers={"X-Organization-ID": setup[3].organization_id}
        ).status_code
        == 403
    )


def test_api_key_hash_agent_scope_and_revocation(client, setup):
    response = client.post(
        "/v1/developer/api-keys", json={"name": "test", "agent_id": setup[2].agent_id}
    )
    assert response.status_code == 201
    body = response.json()
    secret = body["secret"]
    with SessionLocal() as db:
        row = db.get(APIKey, body["id"])
        assert row.key_hash == digest(secret) and secret not in row.key_hash
    headers = {"Authorization": "Bearer " + secret}
    i = client.post(
        "/v1/intents", headers=headers, json=setup[2].model_dump(mode="json")
    )
    assert i.status_code == 201 and i.json()["decision"] == "APPROVE"
    wrong = setup[2].model_dump(mode="json")
    wrong["agent_id"] = uid()
    wrong["idempotency_key"] = uid()
    assert client.post("/v1/intents", headers=headers, json=wrong).status_code == 403
    assert client.get("/v1/approvals", headers=headers).status_code == 403
    assert client.get("/v1/auth/me", headers=headers).status_code == 403
    assert client.delete("/v1/developer/api-keys/" + body["id"]).status_code == 200
    assert client.get("/v1/intents", headers=headers).status_code == 401


def test_revoke_pending_and_reserved(client, setup):
    body = setup[2].model_dump(mode="json")
    assert client.post("/v1/intents", json=body).json()["decision"] == "APPROVE"
    body.update(amount=1200000, idempotency_key=uid())
    intent = client.post("/v1/intents", json=body).json()
    assert intent["decision"] == "ASK"
    assert client.post("/v1/mandates/" + setup[1].id + "/revoke").status_code == 200
    response = client.post(
        "/v1/approvals/" + intent["approval"]["id"] + "/resolve",
        json={"action": "approve"},
    )
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.scalar(select(Reservation.status)) == "released"
        assert db.scalar(select(Approval.status)) == "invalidated"


def test_input_validation(client, setup):
    body = setup[2].model_dump(mode="json")
    body["amount"] = 8.2
    response = client.post("/v1/intents", json=body)
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "VALIDATION_ERROR"
    )
    body["amount"] = 800000
    body["structured_metadata"] = {"nested": {"cvv": "123"}}
    assert client.post("/v1/intents", json=body).status_code == 422


def test_request_ids_and_secret_redaction(client, setup):
    response = client.post("/v1/intents", json=setup[2].model_dump(mode="json"))
    assert response.headers["x-request-id"]
    logs = client.get("/v1/developer/requests").json()
    assert (
        logs["total"] >= 2
        and "password" not in str(logs)
        and "structured_metadata" not in str(logs)
    )


def test_viewer_denied_mutations(client, setup):
    with SessionLocal.begin() as db:
        db.scalar(
            select(Member).where(Member.user_id == setup[0].user_id)
        ).role = "viewer"
    assert (
        client.post("/v1/intents", json=setup[2].model_dump(mode="json")).status_code
        == 403
    )
    assert client.get("/v1/developer/api-keys").status_code == 403


def test_pagination_search_and_analytics(client, setup):
    body = setup[2].model_dump(mode="json")
    client.post("/v1/intents", json=body)
    assert client.get("/v1/intents?search=Headphones").json()["total"] == 1
    assert client.get("/v1/intents?search=missing").json()["total"] == 0
    assert client.get("/v1/intents?limit=101").status_code == 422
    analytics = client.get("/v1/analytics?days=30").json()
    assert (
        len(analytics["trend"]) == 30
        and analytics["total"] == 1
        and analytics["reserved"] == 800000
    )


def test_rate_limit_is_enforced_and_structured(client, monkeypatch):
    from agentpass.config import settings

    monkeypatch.setattr(settings(), "rate_limit", 1)
    assert client.get("/v1/auth/me").status_code == 200
    limited = client.get("/v1/auth/me")
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


def test_body_size_rejects_chunked_payload(client):
    chunks = (b"a" * 10000 for _ in range(7))
    response = client.post(
        "/v1/intents", content=chunks, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_unexpected_errors_do_not_expose_secrets(client, setup, monkeypatch, caplog):
    from agentpass import main

    def failing(*args, **kwargs):
        raise RuntimeError("secret-that-must-not-appear")

    monkeypatch.setattr(main, "create_intent", failing)
    response = client.post("/v1/intents", json=setup[2].model_dump(mode="json"))
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret-that-must-not-appear" not in response.text
    assert "secret-that-must-not-appear" not in caplog.text


def test_audit_database_rejects_mutation(client):
    import pytest
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    with SessionLocal.begin() as db, pytest.raises(DBAPIError):
        db.execute(text("UPDATE audit_events SET action='tampered'"))


def test_key_cannot_list_other_agents(client, setup):
    client.post("/v1/agents", json={"name": "Other agent"})
    key = client.post(
        "/v1/developer/api-keys", json={"name": "Scoped", "agent_id": setup[2].agent_id}
    ).json()["secret"]
    result = client.get("/v1/agents", headers={"Authorization": "Bearer " + key}).json()
    assert result["total"] == 1
    assert result["items"][0]["id"] == setup[2].agent_id


def test_unknown_endpoint_uses_error_envelope(client):
    response = client.get("/v1/not-a-real-endpoint")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_failed_commit_is_not_acknowledged_as_authorization(client, setup, monkeypatch):
    from sqlalchemy.orm import Session
    from sqlalchemy import func
    from agentpass.models import PaymentIntent

    def unavailable_commit(self):
        raise RuntimeError("simulated-database-commit-failure")

    monkeypatch.setattr(Session, "commit", unavailable_commit)
    response = client.post("/v1/intents", json=setup[2].model_dump(mode="json"))
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PaymentIntent)) == 0
        assert db.scalar(select(func.count()).select_from(Reservation)) == 0


def test_removed_member_loses_existing_agent_key(client, setup):
    from fastapi.testclient import TestClient
    from agentpass.main import app

    member = client.post(
        "/v1/organizations/members",
        json={"email": "other@example.com", "role": "developer"},
    ).json()
    with TestClient(app) as other:
        other.post(
            "/v1/auth/login",
            json={"email": "other@example.com", "password": "other-password-123"},
        ).raise_for_status()
        other.headers.update(
            {
                "X-CSRF-Token": other.cookies["ap_csrf"],
                "X-Organization-ID": setup[0].organization_id,
            }
        )
        agent = other.post("/v1/agents", json={"name": "Member Agent"}).json()
        key = other.post(
            "/v1/developer/api-keys",
            json={"name": "Member Key", "agent_id": agent["id"]},
        ).json()
        assert (
            other.get(
                "/v1/agents", headers={"Authorization": "Bearer " + key["secret"]}
            ).status_code
            == 200
        )
        removed = client.delete("/v1/organizations/members/" + member["id"])
        assert removed.status_code == 200 and removed.json()["keys_revoked"] == 1
        assert (
            other.get(
                "/v1/agents", headers={"Authorization": "Bearer " + key["secret"]}
            ).status_code
            == 401
        )
        assert other.get("/v1/mandates").status_code == 403


def test_viewer_cannot_use_previously_issued_key(client, setup):
    key = client.post(
        "/v1/developer/api-keys",
        json={"name": "Old Key", "agent_id": setup[2].agent_id},
    ).json()["secret"]
    with SessionLocal.begin() as db:
        db.scalar(
            select(Member).where(Member.user_id == setup[0].user_id)
        ).role = "viewer"
    assert (
        client.get("/v1/agents", headers={"Authorization": "Bearer " + key}).status_code
        == 401
    )


def test_sandbox_quick_login_is_disabled_outside_default_sandbox(client, monkeypatch):
    from agentpass.config import settings

    config = settings()
    monkeypatch.setattr(config, 'environment', 'sandbox')
    monkeypatch.setattr(config, 'seed_demo', True)
    monkeypatch.setattr(config, 'demo_password', 'AgentPass-demo-2026!')
    assert client.get('/v1/sandbox/access').json() == {'quick_login': True}
    monkeypatch.setattr(config, 'demo_password', 'custom-local-password')
    assert client.get('/v1/sandbox/access').json() == {'quick_login': False}
    monkeypatch.setattr(config, 'demo_password', 'AgentPass-demo-2026!')
    monkeypatch.setattr(config, 'environment', 'production')
    assert client.get('/v1/sandbox/access').json() == {'quick_login': False}


def test_sandbox_loopback_aliases_keep_origin_validation(client, setup):
    response = client.post(
        '/v1/intents',
        json=setup[2].model_dump(mode='json'),
        headers={'Origin': 'http://127.0.0.1:3000'},
    )
    assert response.status_code == 201
    assert client.post(
        '/v1/intents',
        json=setup[2].model_dump(mode='json'),
        headers={'Origin': 'http://127.0.0.1:3001'},
    ).status_code == 403


def test_production_origins_do_not_include_sandbox_aliases(client, monkeypatch):
    from agentpass.config import settings

    config = settings()
    monkeypatch.setattr(config, 'environment', 'production')
    monkeypatch.setattr(config, 'web_origin', 'https://bank.example')
    assert config.allowed_web_origins == {'https://bank.example'}
    assert client.post('/v1/auth/login',
        json={'email': 'test@example.com', 'password': 'test-password-123'},
        headers={'Origin': 'http://terminal.local:3000'},
    ).status_code == 403
