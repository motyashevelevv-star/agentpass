"""Durable local test provider. Shared DB models an independent provider ledger.

Worker calls commit this journal separately from AgentPass finalization. The legacy
synchronous simulator uses the same session because it has no external side effect.
"""
from contextlib import nullcontext
import hashlib
from sqlalchemy import select, text
from ..db import SessionLocal, uid
from ..models import SimulatorPayment
from ..grants import canonical
from .base import PaymentRequest, PaymentStatus, ProviderPayment, ProviderError


def request_hash(request):
    return hashlib.sha256(canonical(request.model_dump(mode='json'))).hexdigest()


class LocalPaymentProvider:
    name = 'local_simulator'
    def __init__(self, session=None):
        self.session = session

    def transaction(self):
        return nullcontext(self.session) if self.session is not None else SessionLocal.begin()

    @staticmethod
    def result(row):
        return ProviderPayment(payment_id=row.id, status=PaymentStatus(row.status),
            amount=row.request_snapshot['amount'], currency=row.request_snapshot['currency'],
            request_hash=row.request_hash, receipt=row.receipt, test=True)

    def create_payment_intent(self, request: PaymentRequest, idempotency_key: str):
        with self.transaction() as db:
            lock = int.from_bytes(hashlib.sha256(('local-provider:'+idempotency_key).encode()).digest()[:8], 'big', signed=True)
            db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock})
            row = db.scalar(select(SimulatorPayment).where(SimulatorPayment.idempotency_key == idempotency_key).with_for_update())
            if row:
                if row.request_hash != request_hash(request):
                    raise ProviderError('PROVIDER_IDEMPOTENCY_CONFLICT')
                return self.result(row)
            row = SimulatorPayment(id=uid(), organization_id=request.organization_id,
                idempotency_key=idempotency_key, request_hash=request_hash(request),
                request_snapshot=request.model_dump(mode='json'), status='pending')
            db.add(row)
            db.flush()
            return self.result(row)

    def _change(self, payment_id, action):
        with self.transaction() as db:
            row = db.scalar(select(SimulatorPayment).where(SimulatorPayment.id == payment_id).with_for_update())
            if not row:
                raise ProviderError('PROVIDER_NOT_FOUND')
            if action == 'authorize':
                if row.status == 'pending':
                    row.status, row.receipt = 'succeeded', 'SIM-'+uid()
                elif row.status not in ('succeeded', 'refunded'):
                    raise ProviderError('PROVIDER_PAYMENT_CANCELLED')
            elif action == 'cancel':
                if row.status == 'pending':
                    row.status = 'cancelled'
                elif row.status != 'cancelled':
                    raise ProviderError('PROVIDER_NOT_CANCELLABLE')
            elif action == 'refund':
                if row.status == 'succeeded':
                    row.status = 'refunded'
                elif row.status != 'refunded':
                    raise ProviderError('PROVIDER_NOT_REFUNDABLE')
            db.flush()
            return self.result(row)

    def authorize_test_payment(self, payment_id, idempotency_key):
        return self._change(payment_id, 'authorize')

    def get_payment_status(self, payment_id):
        with self.transaction() as db:
            row = db.get(SimulatorPayment, payment_id)
            if not row:
                raise ProviderError('PROVIDER_NOT_FOUND')
            return self.result(row)

    def cancel(self, payment_id, idempotency_key):
        return self._change(payment_id, 'cancel')

    def refund(self, payment_id, idempotency_key):
        return self._change(payment_id, 'refund')

    def reconcile(self, payment_id, idempotency_key):
        with self.transaction() as db:
            row = db.scalar(select(SimulatorPayment).where(SimulatorPayment.idempotency_key == idempotency_key))
            if not row:
                return None
            if payment_id and row.id != payment_id:
                raise ProviderError('PROVIDER_ID_MISMATCH')
            return self.result(row)

    def handle_callback(self, headers, body):
        # Simulator is queried directly: accepting unsigned fake callbacks would add an unsafe API.
        raise ProviderError('CALLBACK_NOT_SUPPORTED')
