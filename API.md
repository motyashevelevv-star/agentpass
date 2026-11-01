# REST API v1

Полная исполняемая спецификация: http://localhost:8000/v1/docs и `/v1/openapi.json`. Через frontend proxy доступны `/api/v1/docs` и `/api/v1/openapi.json`. API принимает/возвращает JSON. В MVP новые мандаты поддерживают RUB; намерение с иной валютой будет DENY. Все суммы — целые минимальные единицы валюты: `800000` = 8 000 ₽.

## Аутентификация и роли

- Пользователь: `POST /v1/auth/login`, HttpOnly `ap_session`, cookie `ap_csrf`. Все изменения сессией требуют `X-CSRF-Token` из `ap_csrf`. Origin должен входить в серверный allowlist: `WEB_ORIGIN`; в sandbox с локальным origin также разрешены localhost/127.0.0.1/terminal.local с той же схемой и портом. Для production дополнительных алиасов нет.
- Новый пользователь (только при ALLOW_PUBLIC_REGISTRATION=true): `POST /v1/auth/register`, имя, email, пароль ≥12 символов, название организации; получает роль owner собственной организации.
- Агент: `Authorization: Bearer ap_sk_sandbox_…`. Ключ привязан к одному agent/creator/org и имеет scopes `intents:write`, `intents:read`. Ключ не может создавать мандаты, менять аккаунт или подтверждать свои операции.
- `X-Organization-ID` выбирает организацию только из членств пользователя. Ключ использует свою организацию независимо от этого заголовка.
- owner управляет участниками; developer — собственными агентами/мандатами и org developer-инструментами; viewer читает собственные данные без финансовых изменений. Platform admin — отдельный флаг для технической консоли, а не автоматический доступ к чужим пользовательским мандатам.

## Основные endpoints

| Группа | Операции |
|---|---|
| `/v1/auth` | login/register/me/logout |
| `/v1/agents` | GET список; POST регистрация; PATCH `/{id}/status?status=active\|paused` |
| `/v1/mandates` | GET список с usage; POST; PUT `/{id}` полной версии правил; POST `/{id}/revoke`; GET `/{id}/versions` |
| `/v1/intents` | POST намерение; GET список/`/{id}`; POST `/{id}/execute`; POST `/{id}/cancel` |
| `/v1/evaluations` | GET история; POST `/preview` (user developer/owner, без создания intent/резерва) |
| `/v1/approvals` | GET история; POST `/{id}/resolve` с action approve/reject; только владелец операции |
| `/v1/transactions` | GET подтверждённые test purchases (simulated / external_test) |
| `/v1/audit-events` | GET журнал; org owner видит org audit, остальные — собственные действия |
| `/v1/analytics` | GET показатели и тренд; `days=1..90`, по умолчанию 7 |
| `/v1/developer/api-keys` | GET; POST name/agent_id/expires_days 1..90; DELETE `/{id}` (отзыв) |
| `/v1/developer/projects` | GET/POST проекты |
| `/v1/developer/requests` | GET технический журнал организации |
| `/v1/organizations` | POST организация; GET/POST `/members`; DELETE `/members/{id}` |
| `/v1/webhooks` | GET/POST; DELETE `/{id}` (отключение); POST `/{id}/test`; GET `/deliveries`, `/receipts`, `/config` |
| `/v1/security` | GET sessions; DELETE `/sessions/{id}`; POST `/password` |
| `/v1/settings/profile` | PATCH name |
| `/v1/catalog`, `/v1/console/run` | Тестовый каталог; интерпретация запроса и симуляция через тот же engine |
| `/v1/sandbox/demo` | POST независимый demo-набор; sandbox only |
| `/v1/sandbox/access` | GET публичный флаг доступности быстрого входа; не выполняет авторизацию и не выдаёт секреты |
| `/v1/admin` | GET organizations/metrics/events/requests; PATCH `/organizations/{id}?status=active\|suspended` |
| `/health` | Проверка доступности БД, режима и окружения |

Списки с pagination принимают `limit=1..100`, `offset>=0`; ответ `{items,total,limit,offset}`. Небольшие конфигурационные списки (keys/projects/webhooks/members/sessions/versions) возвращают `items`; они не используют общий pagination envelope. `/intents` также принимает decision и search по продавцу/описанию.

## Payment Intent

```json
{
  "agent_id": "YOUR_AGENT_ID",
  "mandate_id": "YOUR_MANDATE_ID",
  "merchant": "Soundstore",
  "merchant_id": "catalog:soundstore",
  "order_id": "order-unique-001",
  "category": "electronics",
  "amount": 800000,
  "currency": "RUB",
  "description": "Soundcore Life Q30",
  "idempotency_key": "shopping-unique-request-001",
  "timestamp": "2026-10-12T12:00:00Z",
  "structured_metadata": {"product_id": "soundcore-q30"}
}
```

`timestamp` должен содержать часовой пояс и быть в пределах 5 минут от времени сервера при первом запросе. Используйте актуальное время, не копируйте дату примера. Дополнительные поля запрещены. Metadata ограничена 4 KiB; известные секретные ключи (pan/cvv/cvc/card_number/password/api_key), включая вложенные, отклоняются. Секреты нельзя передавать в свободном тексте или произвольных полях.

`Idempotency-Key` в header необязателен; если он присутствует, должен совпадать с body. Повтор требует **точно того же body**, включая timestamp и metadata. Новый body с прежним ключом возвращает 409. Отзыв/истечение исходного мандата не создаёт новое разрешение при повторе: возвращается сохранённая операция, execute заново проверяет актуальность.

Сокращённая форма ответа (реальный API также возвращает контекст намерения):

```json
{
  "id": "SERVER_GENERATED_INTENT_ID",
  "decision": "APPROVE",
  "status": "authorized",
  "reasons": [{"code": "POLICY_MATCH", "message": "Операция соответствует всем правилам"}],
  "evaluated_version": 1,
  "approval": null,
  "reservation": {"id": "RESERVATION_ID", "status": "held", "amount": 800000, "expires_at": "…"},
  "transaction": null
}
```

POST создаёт намерение и возвращает HTTP 201 даже для ASK/DENY. Business DENY — успешная оценка, не HTTP ошибка. APPROVE ещё не покупка. Legacy sandbox `/execute` выполняет симуляцию и возвращает transaction/receipt; новый путь использует grant/execution API ниже. ASK возвращает approval с ID и сроком. После user resolve агент получает актуальный результат через GET/polling или webhook, затем запрашивает grant.

## Подтверждение

```http
POST /v1/approvals/{id}/resolve
X-CSRF-Token: <csrf-cookie>
Content-Type: application/json
```

```json
{"action":"approve"}
```

При успешном согласии статус intent — authorized и создан резерв. Повторное подтверждение — HTTP 409 `APPROVAL_ALREADY_RESOLVED`. Если правила/бюджет изменились, возвращается intent DENY с актуальными reasons; если время истекло — DENY/expired. Ответом служит итог операции, а не обещание исполнения.

## Ошибки и throttling

```json
{"error":{"code":"IDEMPOTENCY_CONFLICT","message":"Ключ уже использован с другим запросом","request_id":"…"}}
```

Валидация — 422 с безопасным списком fields; аутентификация — 401; отсутствие роли — 403; чужой owner/org/agent resource — 404; конфликт состояния — 409; rate limit — 429 с `Retry-After: 60`; слишком большой body — 413; непредвиденная ошибка — 500 со стабильным code и request_id, без SQL/stack trace в ответе. Request ID также в `X-Request-ID`.

БД атомарно считает минутные окна: по умолчанию 120 запросов на user/API key; login — 10 на пару IP+email и 30 на IP, register — 5 на IP. Ограничения действуют на нескольких процессах. Для внешнего пилота нужен дополнительный edge rate limit по IP и общий ingress budget.

## Webhooks

События: `intent.evaluated`, `approval.resolved`, `approval.expired`, `intent.expired`, `intent.cancelled`, `intent.invalidated`, `transaction.simulated`, `sandbox.test`. Содержимое фиксируется в outbox вместе с бизнес-транзакцией.

Headers:

```text
X-AgentPass-Delivery: <delivery UUID>
X-AgentPass-Signature: t=<Unix seconds>,v1=<hex HMAC-SHA256>
```

Подписываются bytes `timestamp + '.' + raw_body`. Проверяйте signature constant-time, допускайте время ±300 секунд и дедуплицируйте delivery ID. Повторная доставка одного event может быть допустима. Secrets выдаются при создании/ротации endpoint; в БД ciphertext Fernet.

Публичный URL — HTTPS:443; без credentials, fragment, приватных IP и redirects. Каждый retry повторно разрешает DNS и соединяется с проверенным IP. `WEBHOOK_HOST_ALLOWLIST` дополнительно ограничивает домены. В sandbox `/webhooks/config` возвращает единственный разрешённый локальный HTTP receiver; он действительно принимает HTTP, проверяет подпись и записывает receipt. Исключение отключено вне sandbox.

## SDK

`@agentpass/sdk` находится в monorepo и пока не опубликован в npm. `npm run build -w packages/sdk-typescript` создаёт JS и d.ts. Методы: createIntent/getIntent/listIntents/executeIntent/cancelIntent/listAgents/listMandates/waitForDecision. Есть timeout, AbortSignal для ожидания и типизированный AgentPassError. Секрет передавайте через env/secret manager, не frontend bundle. Примеры TypeScript и Python представлены в Developer Portal; `infra/verify-sdk.mjs` и `infra/smoke.py` проверяют SDK через живой API.

## Additive execution API (совместимость v1 сохранена)

`merchant_id` и `order_id` добавлены в IntentIn; sandbox допускает отсутствие для старых клиентов, pilot/production требуют оба. Пустые/окружённые пробелами IDs запрещены. После создания критические параметры intent неизменяемы в БД. Новый `decision_kind` возвращает APPROVE/ASK_USER/DENY; legacy `decision=ASK` сохранён. Intent view дополнен `execution`.

| Endpoint | Кто / результат |
|---|---|
| POST `/v1/intents/{id}/execution-grant` | agent key или owner/developer; `{provider:"local_simulator"}` по умолчанию, либо yookassa_sandbox если включён |
| POST `/v1/executions` | executor key; в sandbox также owner/developer session. Body `{grant_token:"..."}`; 201 queued или прежняя execution при повторе |
| GET `/v1/executions/{id}` | Тот же owner/org/agent; scopes payments:read для ключа |
| POST `/v1/executions/{id}/reconcile` | executor/owner/developer; планирует сверку, не обещает success; 409 при активном lease |
| POST `/v1/developer/api-keys/{id}/rotate` | Session создателя, step-up; старый key немедленно отозван, replacement secret показывается один раз |
| POST `/v1/webhooks/{id}/rotate-secret` | Org developer/owner session, step-up; secret меняется немедленно, dual-secret grace нет |
| GET `/v1/security/mfa` | User session, статус подключения |
| POST `/v1/security/mfa/enroll` | `{password:"current password"}`; возвращает secret/provisioning_uri для первого подключения |
| POST `/v1/security/mfa/confirm` | `{code:"123456"}`; активирует TOTP, отзывает другие sessions |
| GET `/live`, `/ready` | Process / database + ожидаемый schema revision; ready при ошибке 503 |
| GET `/v1/admin/operations` | Platform admin; heartbeat, unknown, quarantine, webhook dead letters |
| POST `/v1/providers/yookassa/callback` | Только enabled TEST provider; untrusted hint → authenticated refetch, 202; без доверия статусу в body |

Grant response: `{id,intent_id,provider,expires_at,grant_token,single_use:true}`. TTL по умолчанию 120 s, максимум 300 s и не дольше reservation TTL. Token не писать в логи. Подпись связывает frozen identity и payment fields; один intent имеет один grant и одну execution. Повтор выпуска до потребления/истечения возвращает тот же token; после — 409, нужен новый intent и оценка. Отзыв/изменение мандата проверяется при выдаче, потреблении и первой отправке worker.

Executor key создаётся с `purpose:"executor"`, scopes `intents:read,payments:read,payments:execute`; agent key по умолчанию не может submit execution. Executor не может create intent, выпускать grant, подтверждать ASK или управлять мандатами. В pilot user session/agent key не могут исполнять grant. Legacy `/intents/{id}/execute` в pilot/production даёт 403 и предназначен для прежней локальной симуляции.

Execution states: queued → dispatching → pending/unknown/succeeded/cancelled. Intent states дополнены executing/payment_pending/payment_unknown. Provider `test=true` подтверждён + hash/amount/currency/ID совпадают + terminal success — только тогда создаётся transaction. Unknown удерживает inflight резерв без истечения до сверки; 10 попыток требуют ручного reconcile/verified callback. Отзыв мандата не отменяет уже отправленный checkout.

Для MFA login принимает `mfa_code`; approval resolve и password change тоже принимают `mfa_code` в body. Создание/редактирование мандата, создание/ротация API key, ротация webhook secret используют `X-MFA-Code`. Backend требует step-up при включённой MFA или REQUIRE_MFA=true. Код одноразовый на пользователя: дождитесь следующего, если предыдущий уже использован. Ошибки: MFA_ENROLLMENT_REQUIRED, MFA_REQUIRED, MFA_INVALID_OR_REPLAYED. Frontend показывает отдельное окно. Insecure reset/recovery API отсутствует.

Новые события: execution.queued, execution.unknown, execution.cancelled, payment.test_succeeded; transaction.simulated сохранено. Audit содержит grant/claim/reconcile/callback/rotation действия. Public provider refund/cancel orchestration отсутствует, несмотря на методы PaymentProvider.

SDK добавляет requestExecutionGrant/submitExecution/getExecution/reconcileExecution и session-only registerAgent/createMandate/createApiKey/revokeMandate/listAuditEvents. Пример без Concierge: [examples/external-agent](examples/external-agent/README.md). Детали внешнего подключения и границы NOT VERIFIED: [PAYMENT_SANDBOX](docs/PAYMENT_SANDBOX.md).
