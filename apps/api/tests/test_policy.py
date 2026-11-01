from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from sqlalchemy import select, func
from agentpass.db import SessionLocal, now, uid
from agentpass.models import (
    Mandate,
    Reservation,
    PaymentIntent,
    Approval,
    Transaction,
    Evaluation,
)
from agentpass.policy import (
    create_intent,
    resolve_approval,
    execute_intent,
    cancel_intent,
    budget_usage,
)
from agentpass.security import DomainError, Principal


def create(setup, **changes):
    p, _, data, _ = setup
    data = data.model_copy(update=changes)
    with SessionLocal.begin() as db:
        return create_intent(db, p, data)


@pytest.mark.parametrize(
    "amount,decision", [(800000, "APPROVE"), (1200000, "ASK"), (1800000, "DENY")]
)
def test_demo_decisions(setup, amount, decision):
    i = create(setup, amount=amount)
    assert i.decision == decision
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Reservation)) == (
            1 if decision == "APPROVE" else 0
        )
        assert db.scalar(select(func.count()).select_from(Approval)) == (
            1 if decision == "ASK" else 0
        )


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"valid_until": now() - timedelta(seconds=1)}, "MANDATE_EXPIRED"),
        ({"valid_from": now() + timedelta(days=1)}, "MANDATE_NOT_STARTED"),
        ({"status": "revoked"}, "MANDATE_REVOKED"),
        ({"merchant_denylist": ["soundstore"]}, "MERCHANT_DENIED"),
        ({"merchant_allowlist": ["another merchant"]}, "MERCHANT_NOT_ALLOWED"),
        ({"categories": ["travel"]}, "CATEGORY_DENIED"),
        ({"daily_limit": 700000}, "DAILY_LIMIT"),
        ({"weekly_limit": 700000}, "WEEKLY_LIMIT"),
        ({"monthly_limit": 700000}, "MONTHLY_LIMIT"),
    ],
)
def test_denial_rules(setup, change, expected):
    with SessionLocal.begin() as db:
        m = db.get(Mandate, setup[1].id)
        for key, value in change.items():
            setattr(m, key, value)
    i = create(setup)
    assert i.decision == "DENY"
    assert expected in [x["code"] for x in i.reasons]


def test_currency_mismatch(setup):
    i = create(setup, currency="USD")
    assert i.decision == "DENY" and i.reasons[0]["code"] == "CURRENCY_MISMATCH"


def test_idempotency_identical_and_conflict(setup):
    first = create(setup)
    second = create(setup)
    assert first.id == second.id
    with pytest.raises(DomainError) as e:
        create(setup, amount=700000)
    assert e.value.code == "IDEMPOTENCY_CONFLICT"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PaymentIntent)) == 1
        assert db.scalar(select(func.count()).select_from(Reservation)) == 1


def test_parallel_budget_atomicity(setup):
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(lambda _: create(setup, idempotency_key=uid()), range(8))
        )
    assert sum(i.decision == "APPROVE" for i in results) == 3
    assert sum(i.decision == "DENY" for i in results) == 5
    with SessionLocal() as db:
        assert budget_usage(db, setup[1])["daily"] == 2400000


def test_parallel_identical_idempotency(setup):
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: create(setup), range(8)))
    assert len(set(i.id for i in results)) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Reservation)) == 1


def test_cross_org_mandate(setup):
    with SessionLocal.begin() as db, pytest.raises(DomainError) as e:
        create_intent(db, setup[3], setup[2])
    assert e.value.status == 404


def test_cross_user_same_org_mandate(setup):
    other = Principal(setup[3].user_id, setup[0].organization_id, "developer")
    with SessionLocal.begin() as db, pytest.raises(DomainError) as e:
        create_intent(db, other, setup[2])
    assert e.value.status == 404


def test_replay_timestamp(setup):
    with pytest.raises(DomainError) as e:
        create(setup, timestamp=now() - timedelta(minutes=6))
    assert e.value.code == "STALE_TIMESTAMP"


def test_approval_once_and_execution_once(setup):
    p, m, _, _ = setup
    i = create(setup, amount=1200000)
    with SessionLocal() as db:
        aid = db.scalar(select(Approval.id))
    with SessionLocal.begin() as db:
        accepted = resolve_approval(db, p, aid, "approve")
    assert accepted.status == "authorized"
    with SessionLocal.begin() as db, pytest.raises(DomainError) as e:
        resolve_approval(db, p, aid, "approve")
    assert e.value.code == "APPROVAL_ALREADY_RESOLVED"
    with SessionLocal.begin() as db:
        assert execute_intent(db, p, i.id).status == "completed"
    with SessionLocal.begin() as db:
        assert execute_intent(db, p, i.id).status == "completed"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction)) == 1
        assert budget_usage(db, m)["daily"] == 1200000


def test_parallel_approval_single_use(setup):
    i = create(setup, amount=1200000)
    with SessionLocal() as db:
        aid = db.scalar(select(Approval.id))

    def accept(_):
        try:
            with SessionLocal.begin() as db:
                return resolve_approval(db, setup[0], aid, "approve").decision
        except DomainError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(accept, range(6)))
    assert results.count("APPROVE") == 1
    assert results.count("APPROVAL_ALREADY_RESOLVED") == 5


def test_approval_expiry(setup):
    i = create(setup, amount=1200000)
    with SessionLocal.begin() as db:
        a = db.scalar(select(Approval))
        a.expires_at = now() - timedelta(seconds=1)
        aid = a.id
    with SessionLocal.begin() as db:
        result = resolve_approval(db, setup[0], aid, "approve")
        assert result.decision == "DENY" and result.status == "expired"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Reservation)) == 0


def test_rules_change_while_waiting(setup):
    i = create(setup, amount=1200000)
    with SessionLocal.begin() as db:
        m = db.get(Mandate, setup[1].id)
        m.per_transaction = 1000000
        m.version += 1
        aid = db.scalar(select(Approval.id))
    with SessionLocal.begin() as db:
        result = resolve_approval(db, setup[0], aid, "approve")
        assert result.decision == "DENY" and result.evaluated_version == 2
        assert result.reasons[0]["code"] == "PER_TRANSACTION_LIMIT"


def test_budget_spent_while_waiting(setup):
    i = create(setup, amount=1200000)
    create(setup, idempotency_key=uid())
    create(setup, idempotency_key=uid())
    with SessionLocal() as db:
        aid = db.scalar(select(Approval.id))
    with SessionLocal.begin() as db:
        result = resolve_approval(db, setup[0], aid, "approve")
        assert result.decision == "DENY" and result.reasons[0]["code"] == "DAILY_LIMIT"


def test_reject_does_not_reserve(setup):
    create(setup, amount=1200000)
    with SessionLocal() as db:
        aid = db.scalar(select(Approval.id))
    with SessionLocal.begin() as db:
        assert resolve_approval(db, setup[0], aid, "reject").decision == "DENY"
    with SessionLocal() as db:
        assert budget_usage(db, setup[1])["daily"] == 0


def test_cancellation_releases_budget(setup):
    first = create(setup)
    create(setup, idempotency_key=uid())
    create(setup, idempotency_key=uid())
    assert create(setup, idempotency_key=uid()).decision == "DENY"
    with SessionLocal.begin() as db:
        assert cancel_intent(db, setup[0], first.id).status == "cancelled"
    assert create(setup, idempotency_key=uid()).decision == "APPROVE"


def test_reservation_expiry_release(setup):
    i = create(setup)
    with SessionLocal.begin() as db:
        r = db.scalar(select(Reservation))
        r.expires_at = now() - timedelta(seconds=1)
    with SessionLocal.begin() as db:
        assert execute_intent(db, setup[0], i.id).status == "expired"
    with SessionLocal() as db:
        assert budget_usage(db, setup[1])["daily"] == 0


def test_execution_checks_changed_rules(setup):
    i = create(setup)
    with SessionLocal.begin() as db:
        m = db.get(Mandate, setup[1].id)
        m.version += 1
    with SessionLocal.begin() as db:
        assert execute_intent(db, setup[0], i.id).decision == "DENY"
    with SessionLocal() as db:
        assert db.scalar(select(Reservation.status)) == "released"


def test_execution_parallel_no_double_spend(setup):
    i = create(setup)

    def execute(_):
        with SessionLocal.begin() as db:
            return execute_intent(db, setup[0], i.id).status

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert set(executor.map(execute, range(8))) == {"completed"}
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Transaction)) == 1


def test_execution_across_utc_day_rechecks_current_budget(setup):
    with SessionLocal.begin() as db:
        m = db.get(Mandate, setup[1].id)
        m.per_transaction = 2000000
        m.approval_threshold = 3000000
    yesterday = create(setup)
    with SessionLocal.begin() as db:
        r = db.scalar(select(Reservation).where(Reservation.intent_id == yesterday.id))
        r.created_at = now() - timedelta(days=1)
    today = create(setup, amount=1800000, idempotency_key=uid())
    assert today.decision == "APPROVE"
    with SessionLocal.begin() as db:
        result = execute_intent(db, setup[0], yesterday.id)
        assert result.decision == "DENY"
        assert result.reasons[0]["code"] == "DAILY_LIMIT"
    with SessionLocal() as db:
        assert budget_usage(db, setup[1])["daily"] == 1800000
