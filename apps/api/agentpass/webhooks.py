"""At-least-once outbox, HMAC signatures and pinned public-IP HTTPS delivery."""

import hashlib, hmac, http.client, ipaddress, json, secrets, socket, ssl, time
from datetime import timedelta
from urllib.parse import urlsplit
from cryptography.fernet import Fernet
from sqlalchemy import select
from .config import settings
from .db import SessionLocal, now
from .models import WebhookEndpoint, WebhookDelivery, Mandate, Agent, RateWindow
from .security import fail


def public_target(url):
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        fail(422, "INVALID_WEBHOOK_URL", "Некорректный URL webhook")
    if settings().environment == "sandbox" and url == settings().sandbox_receiver_url:
        return parsed, None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or port not in (None, 443)
    ):
        fail(422, "INVALID_WEBHOOK_URL", "Нужен публичный HTTPS endpoint на порту 443")
    allowed = [
        x.strip().lower()
        for x in settings().webhook_host_allowlist.split(",")
        if x.strip()
    ]
    if allowed and parsed.hostname.lower() not in allowed:
        fail(422, "WEBHOOK_HOST_DENIED", "Домен отсутствует в WEBHOOK_HOST_ALLOWLIST")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        fail(422, "WEBHOOK_DNS_FAILED", "Не удалось разрешить домен")
    ips = list(dict.fromkeys(x[4][0] for x in addresses))
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        fail(422, "PRIVATE_WEBHOOK_DENIED", "Локальные и служебные адреса запрещены")
    return parsed, ips[0]


def encrypt(secret):
    return Fernet(settings().encryption_key.encode()).encrypt(secret.encode()).decode()


def decrypt(cipher):
    return Fernet(settings().encryption_key.encode()).decrypt(cipher.encode()).decode()


def sign(secret, timestamp, body):
    return hmac.new(
        secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256
    ).hexdigest()


def verify_signature(secret, signature_header, body, tolerance=300):
    try:
        values = dict(part.split("=", 1) for part in signature_header.split(","))
        timestamp = int(values["t"])
        return abs(time.time() - timestamp) <= tolerance and hmac.compare_digest(
            values["v1"], sign(secret, timestamp, body)
        )
    except (KeyError, ValueError):
        return False


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip):
        super().__init__(host, 443, timeout=5, context=ssl.create_default_context())
        self.ip = ip

    def connect(self):
        raw = socket.create_connection((self.ip, 443), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def deliver(endpoint, payload, delivery_id):
    parsed, ip = public_target(
        endpoint.url
    )  # Resolve again for each attempt; pin validated IP.
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    timestamp = int(time.time())
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "AgentPass/0.1",
        "X-AgentPass-Delivery": delivery_id,
        "X-AgentPass-Signature": f"t={timestamp},v1={sign(decrypt(endpoint.secret_ciphertext), timestamp, body)}",
    }
    conn = (
        PinnedHTTPS(parsed.hostname, ip)
        if ip
        else http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=5)
    )
    try:
        conn.request(
            "POST",
            (parsed.path or "/") + ("?" + parsed.query if parsed.query else ""),
            body=body,
            headers=headers,
        )
        response = conn.getresponse()
        code = response.status
        response.read(4096)
        return code
    finally:
        conn.close()


def work_once():
    # Database lock claims one delivery across any number of workers. Bounded network timeout.
    with SessionLocal.begin() as db:
        row = db.scalar(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.status.in_(["pending", "retry"]),
                WebhookDelivery.next_attempt_at <= now(),
            )
            .order_by(WebhookDelivery.created_at)
            .with_for_update(skip_locked=True)
        )
        if not row:
            return False
        endpoint = db.get(WebhookEndpoint, row.endpoint_id)
        if not endpoint.active:
            row.status = "disabled"
            return True
        row.attempts += 1
        try:
            row.response_status = deliver(endpoint, row.payload, row.id)
            if 200 <= row.response_status < 300:
                row.status = "delivered"
                row.last_error = None
                return True
            row.last_error = "HTTP " + str(row.response_status)
        except Exception as error:
            # Never persist exception strings which can contain URL credentials.
            row.last_error = type(error).__name__
        row.status = "failed" if row.attempts >= 5 else "retry"
        row.next_attempt_at = now() + timedelta(seconds=15 * 2 ** (row.attempts - 1))
    return True


def maintenance():
    from .policy import expire_for_mandate

    with SessionLocal.begin() as db:
        ids = list(db.scalars(select(Mandate.id)))
    for mid in ids:
        with SessionLocal.begin() as db:
            m = db.get(Mandate, mid)
            db.scalar(select(Agent).where(Agent.id == m.agent_id).with_for_update())
            m = db.scalar(select(Mandate).where(Mandate.id == mid).with_for_update())
            expire_for_mandate(db, m)
    with SessionLocal.begin() as db:
        from sqlalchemy import delete

        db.execute(
            delete(RateWindow).where(RateWindow.window < int(time.time()) // 60 - 5)
        )


if __name__ == "__main__":
    import logging, signal, threading, os
    from .execution import dispatch_once
    from .models import WorkerHeartbeat
    from sqlalchemy.dialects.postgresql import insert

    logging.basicConfig(level=logging.INFO)
    cycles = 0
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while not stop.is_set():
        try:
            with SessionLocal.begin() as db:
                heartbeat = insert(WorkerHeartbeat).values(id='worker:'+str(os.getpid()), observed_at=now())
                db.execute(heartbeat.on_conflict_do_update(index_elements=['id'], set_={'observed_at':now()}))
            worked = dispatch_once()
            worked = work_once() or worked
            cycles += 1
            if cycles % 12 == 0:
                maintenance()
        except Exception:
            logging.error(json.dumps({"event": "worker.error"}))
            worked = False
        stop.wait(0.2 if worked else 5)
