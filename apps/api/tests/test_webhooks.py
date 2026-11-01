import json, time, socket
import pytest
from sqlalchemy import select
from agentpass.db import SessionLocal, uid, now
from agentpass.models import WebhookEndpoint, WebhookDelivery
from agentpass.policy import create_intent
from agentpass.security import DomainError
from agentpass import webhooks


def test_hmac_and_replay():
    body = b'{"event":"intent.evaluated"}'
    secret = "test-secret"
    timestamp = int(time.time())
    header = f"t={timestamp},v1={webhooks.sign(secret, timestamp, body)}"
    assert webhooks.verify_signature(secret, header, body)
    assert not webhooks.verify_signature(secret, header, body + b"tamper")
    assert not webhooks.verify_signature(
        secret,
        f"t={timestamp - 301},v1={webhooks.sign(secret, timestamp - 301, body)}",
        body,
    )
    assert not webhooks.verify_signature(secret, "broken", body)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/hooks",
        "https://localhost/hook",
        "https://127.0.0.1/",
        "https://user:pass@example.com/",
        "https://example.com:8443/",
    ],
)
def test_ssrf_rejected(url, monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 443))
        ],
    )
    with pytest.raises(DomainError):
        webhooks.public_target(url)


def test_outbox_retry_and_success(setup, monkeypatch):
    secret = "webhook-secret"
    with SessionLocal.begin() as db:
        endpoint = WebhookEndpoint(
            id=uid(),
            organization_id=setup[0].organization_id,
            name="test",
            url="https://example.com/hook",
            secret_ciphertext=webhooks.encrypt(secret),
        )
        db.add(endpoint)
        db.flush()
        create_intent(db, setup[0], setup[2])
    with SessionLocal() as db:
        endpoint = db.scalar(select(WebhookEndpoint))
        assert secret not in endpoint.secret_ciphertext
        assert webhooks.decrypt(endpoint.secret_ciphertext) == secret
    monkeypatch.setattr(webhooks, "deliver", lambda *a: 503)
    assert webhooks.work_once()
    with SessionLocal.begin() as db:
        row = db.scalar(select(WebhookDelivery))
        assert row.status == "retry" and row.attempts == 1
        row.next_attempt_at = now()
    monkeypatch.setattr(webhooks, "deliver", lambda *a: 204)
    assert webhooks.work_once()
    with SessionLocal() as db:
        row = db.scalar(select(WebhookDelivery))
        assert row.status == "delivered" and row.attempts == 2


def test_outbox_rollback(setup):
    with SessionLocal.begin() as db:
        db.add(
            WebhookEndpoint(
                organization_id=setup[0].organization_id,
                name="test",
                url="https://example.com/hook",
                secret_ciphertext=webhooks.encrypt("test"),
            )
        )
    with SessionLocal() as db:
        create_intent(db, setup[0], setup[2])
        db.rollback()
    with SessionLocal() as db:
        assert db.scalar(select(WebhookDelivery)) is None


def test_actual_receiver_verifies_signature_and_deduplicates(client, setup):
    from agentpass.models import WebhookReceipt

    secret = "receiver-signature-secret"
    payload = {"id": uid(), "event": "sandbox.test", "data": {}}
    with SessionLocal.begin() as db:
        e = WebhookEndpoint(
            id=uid(),
            organization_id=setup[0].organization_id,
            name="receiver",
            url=webhooks.settings().sandbox_receiver_url,
            secret_ciphertext=webhooks.encrypt(secret),
        )
        db.add(e)
        db.flush()
        row = WebhookDelivery(
            id=uid(),
            endpoint_id=e.id,
            organization_id=e.organization_id,
            payload=payload,
        )
        db.add(row)
        did = row.id
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = int(time.time())
    headers = {
        "X-AgentPass-Delivery": did,
        "X-AgentPass-Signature": f"t={timestamp},v1={webhooks.sign(secret, timestamp, body)}",
        "Content-Type": "application/json",
    }
    assert (
        client.post(
            "/v1/sandbox/webhook-receiver",
            content=body,
            headers={**headers, "X-AgentPass-Signature": "bad"},
        ).status_code
        == 401
    )
    first = client.post("/v1/sandbox/webhook-receiver", content=body, headers=headers)
    assert (
        first.status_code == 200
        and first.json()["signature_verified"]
        and not first.json()["duplicate"]
    )
    assert client.post(
        "/v1/sandbox/webhook-receiver", content=body, headers=headers
    ).json()["duplicate"]
    with SessionLocal() as db:
        assert len(list(db.scalars(select(WebhookReceipt)))) == 1
