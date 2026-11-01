# Модель данных

PostgreSQL 16; SQLAlchemy 2, миграции Alembic. UUID-подобные идентификаторы — строки длиной 36. Даты — `timestamptz`. Суммы — `bigint` в минимальных единицах валюты. JSON используется для версионированных правил, списков категорий/продавцов и ограниченной metadata, а не для хранения всего финансового состояния одной записью.

| Таблица | Связи и важные ограничения |
|---|---|
| users | Уникальный email, scrypt hash, отдельный platform_admin |
| organizations | active/suspended |
| organization_members | FK org/user; уникальная пара; owner/developer/viewer |
| projects | Организация, название |
| agents | Организация, владелец, необязательный проект; active/paused |
| mandates | Владелец/org/agent; валюта, категории, allow/deny; пять положительных лимитов; valid_until > valid_from; active/revoked |
| mandate_versions | FK mandate; уникальная пара mandate/version; снимок правил |
| payment_intents | FK owner/org/agent/mandate; положительная сумма; уникальные agent/idempotency_key; fingerprint body; decision/status, metadata |
| policy_evaluations | FK intent/org; stage initial/approval/execution/expiry/revocation; решение, объяснение, rule_version |
| budget_reservations | Уникальный intent; FK mandate; amount > 0; held/consumed/released/expired; expires_at |
| approval_requests | Уникальный intent; FK owner/org; pending/approved/rejected/expired/invalidated; expires_at/resolved_at |
| simulated_transactions | Уникальные intent и receipt; сумма, валюта, simulated |
| api_keys | FK org/creator/agent; уникальный SHA-256 hash; prefix/scopes/expiry/revocation/last_used |
| sessions | FK user; уникальный hash токена, hash CSRF, expiry/revocation |
| webhook_endpoints | FK org; URL, Fernet ciphertext signing secret, active |
| webhook_deliveries | FK org/endpoint; immutable event body, attempts/status/next_attempt/error/HTTP |
| webhook_receipts | Delivery ID как дедупликационный PK; FK org/endpoint; event/body_hash; только локальный sandbox receiver |
| audit_events | org/actor/action/resource/details/time; trigger запрещает UPDATE/DELETE |
| request_logs | org или NULL для неаутентифицированных; route template, request ID, status, duration; без body/headers |
| rate_windows | Составной PK key/window; атомарный UPSERT count; окна по минутам |

Индексы присутствуют на FK tenant/owner/agent/mandate, на `(org, created_at)` намерений, `(mandate, status, created_at)` резервов и `(status, next_attempt_at)` outbox. Уникальные ограничения предотвращают повторные резервы, подтверждения и транзакции.

Tenant/owner/agent matching проверяется сервером при каждом доступе и изменении; PostgreSQL RLS и составные tenant foreign keys пока не реализованы. Это отражено в SECURITY как работа перед банковским пилотом. FK защищают существование ссылок; прямой привилегированный SQL не является разрешённым способом записи бизнес-данных.

Webhook receipt намеренно не ссылается FK на delivery: sender держит row lock во время HTTP, а receiver должен независимо подтвердить получение без ожидания этой блокировки. Сам delivery ID и event ID проверяются по существующей записи outbox.

Схема воспроизводится только через сохранённые миграции. Тесты требуют отдельную БД `_test` и очищают её через TRUNCATE; пользовательская sandbox БД не затрагивается.

## Pilot migration dbfc8b45cfa9

- users: encrypted active/pending TOTP seeds, replay counter.
- payment_intents: nullable merchant_id/order_id для совместимости; pilot требует оба; immutable trigger защищает входные параметры.
- execution_grants: уникальный intent/token hash, signed claims, expiry/consumed_at; immutable trigger.
- payment_executions: уникальные intent/grant/provider idempotency key, frozen request snapshot, lease fencing, attempts, due time, provider evidence/status.
- simulator_payments: отдельный durable provider journal, unique key/hash/receipt, без внешнего платежа.
- worker_heartbeats: дата последнего наблюдения процесса.
- reservation status inflight: не освобождается по TTL и учитывается во всех бюджетных окнах до подтверждения.
- transactions status external_test означает подтверждённый test=true результат внешней песочницы; не реальный платёж.

Составные FK дополнительно связывают tenant/owner/agent финансовой цепочки и точную сумму reservation с intent. Downgrade новой миграции запрещён при наличии execution history: нельзя удалять неопределённые операции. Старые миграции и данные сохраняются; для отката приложения предпочитайте forward fix. Нет RLS и уникальности order_id между разными намерениями: новые idempotency keys означают независимые проверки.
