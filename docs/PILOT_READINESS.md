# Pilot readiness — проверяемое состояние

## Исходная точка, 2026-10-29

Восстановлен пользовательский `AgentPass-Mac.zip`, SHA-256 `d5f15c2410ab94d671bd1f7e68c3b43fc54edce5ecd70a80742c5650fc4a674d`. Архив неизменён; Git metadata в нём нет. Восстановленное дерево сохранено baseline-коммитом `ac9b15b`. Пользовательских незакоммиченных правок в импортированной копии нет. Исходные SQL миграции применены к новым отдельным sandbox/test БД; реальных пользовательских данных архив не содержит.

Проверено до изменений: 62 pytest tests passed (53.09 s, PostgreSQL 16), strict TypeScript web/SDK passed, SDK и Next.js production builds passed. HTTP SDK smoke: 14 проверок passed; Playwright baseline: 6 passed (1.1 min). Это результаты до изменения кода, не вывод из документации.

## Реализовано в исходном коде

- Детерминированные лимиты и APPROVE/ASK/DENY; UTC бюджеты, advisory/idempotency и agent→mandate locks.
- Одноразовый ASK, повторная проверка правил, освобождение резервов, отдельная симуляция с уникальным чеком.
- Session/CSRF, RBAC, app-level owner/tenant/agent isolation, хеши API keys, отзыв участника/ключа.
- PostgreSQL audit trigger и transactional webhook outbox, pinned HTTPS egress/HMAC/retries, 4 API-backed интерфейса.

## Обнаруженные риски и приоритет

| Приоритет | Проверяемое наблюдение | Исправление/критерий |
|---|---|---|
| P0 | Нет отдельного исполнения по подписанному grant; intent не имеет merchant/order ID, поля не защищены DB trigger | Неизменяемые поля, DB constraints, одноразовый grant, replay/concurrency/tamper regression |
| P0 | `ENVIRONMENT` произвольная строка, pilot не исключает seed-аккаунты/стандартные passwords/runtime superuser | Fail-closed pilot configuration и startup DB checks |
| P0 | Нет MFA/step-up, открытая регистрация, нет key/secret rotation API | Практический step-up и ротация; enterprise federation отдельно NOT VERIFIED |
| P0 | Tenant isolation только application-level, составных финансовых tenant FKs нет | Cross-tenant DB integrity + exhaustive authorization tests; отдельный runtime role/RLS review |
| P1 | `/execute` создаёт только локальный simulated receipt; нет внешней платёжной операции/unknown/reconciliation | Provider interface, durable operation ID, simulator, timeout recovery, no success without provider evidence |
| P3 | Webhook row lock держится при I/O; нет lease/worker heartbeat/recovery runbook | Bounded claim/retry diagnostics, pilot operational acceptance |

## Границы и блокеры банковского пилота

Реальных банковских адаптеров, merchant attestation, сертификации, независимого pentest, HA/load SLO и подтверждённого backup restore нет. Нет проведённых интервью и подтверждённого интереса какого-либо банка. Existing merchant/category поступают от агента; независимая проверка этих данных требует согласованного доверенного источника. Audit trigger не WORM и не защищает от администратора БД.

До подключения банка нужны согласованные тестовые API/credentials, модель подтверждения и границы ответственности, egress/identity/DB roles, независимый review. Не считать внешний провайдер VERIFIED по unit/mock tests. Здесь не разворачивается публичный production и не проводятся реальные платежи.

## Приёмка текущей итерации

1. Все baseline tests и UI contracts сохраняются.
2. Изменить сумму/merchant/order/tenant одобренного intent нельзя; grant проверяет frozen snapshot и актуальные полномочия.
3. Параллельные вызовы и retries дают одну execution/provider idempotency identity.
4. Timeout/unknown не создаёт успешный receipt и не освобождает неопределённый бюджет.
5. Pilot не стартует с известными demo accounts/unsafe settings.
6. Новый код покрыт regression/API/concurrency/provider/SDK/E2E проверками; результаты и ограничения перечислены отдельно.

## Реализовано в итерации 2026-10-30

- `grants.py`, immutable DB triggers: короткоживущий HMAC Execution Grant, hash/claims, однократное потребление; merchant_id/order_id и frozen request snapshot. Legacy поля/API сохранены.
- `execution.py`, `payments/*`: transactional queue, commit до I/O, lease fencing, provider journal/idempotency/reconcile. Timeout/crash/неизвестное состояние не создаёт ложный успех и не освобождает inflight.
- MFA enrollment/login/step-up с replay counter, immediate API-key/webhook-secret rotation, pilot config/startup fail-closed, составные financial tenant FKs. Offline OIDC assertion validator подготовлен; полного SSO нет.
- SDK grant/executor/control-plane methods, самостоятельный external-agent CLI, LLM proposal boundary + deterministic fallback. Нет внешнего LLM вызова.
- UI: MFA setup/step-up, executor key/rotation, provider lifecycle/reason codes/version/approval, JSON export, worker/unknown/dead-letter diagnostics. Design и четыре интерфейса сохранены.
- `/live`, `/ready`, worker heartbeat/retry/quarantine, graceful worker stop, onboarding CLI и operations/backup runbook. Новый код и миграция не удаляют старые данные.
- ЮKassa официальный TEST redirect adapter: конфигурация отключена, contract/API integration tests используют MockTransport. Реальное внешнее соединение **NOT VERIFIED**; bank adapter не реализован.

## Проверки текущего этапа

| Проверка | Результат |
|---|---|
| `PYTHONPATH=apps/api .venv/bin/pytest apps/api/tests -q` | 114 passed (исходные 62 + 52 новых), 1 Starlette/httpx deprecation warning |
| `npm run typecheck`, `npm run build` | web strict TS / SDK / Next production: passed |
| `PLAYWRIGHT_CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e` | 8 passed, включая 6 исходных, grant/worker и MFA/step-up |
| `PYTHONPATH=apps/api .venv/bin/alembic -c apps/api/alembic.ini check` | no new upgrade operations; новая миграция применена в sandbox/test и чистом Compose |
| `.venv/bin/python infra/smoke.py` | 14 passed, реальный HTTP/SDK/signed webhook |
| `.venv/bin/python infra/verify-pilot-sdk.py` | 16 passed, отдельные agent/executor keys, ASK, replay, worker, revoke |
| Docker Compose `up --build -d --wait` | 4 healthy services на отдельных портах/новой БД; smoke 14 + SDK 16 passed против контейнеров |
| `node examples/external-agent/run.mjs` | Самостоятельный пример: local provider succeeded, реальные API/worker; ключи после проверки отозваны |
| `pg_dump -Fc` → `pg_restore --no-owner` | Новая изолированная БД, revision dbfc8b45cfa9, финансовые связи сохранены; не подтверждает DR/PITR/RPO/RTO |

Во время первого расширенного E2E: 7 passed/1 failed из-за штатного registration rate limit. Тест научен ждать Retry-After, лимит продукта не ослаблен. Затем исправлен select locator нового MFA сценария; финальный полный прогон успешен. Ошибки не скрыты и тесты не удалены. GitHub Actions workflow дополнен SDK check, но удалённый GitHub runner здесь не запускался.

## Готовность и следующий допуск

| Область | Оценка по критериям |
|---|---|
| Техническая демонстрация | Локально воспроизводима: чистый Compose, все исходные сценарии, SDK/worker/grants, migration, tests |
| Безопасность ядра | Критическая локальная цепочка усилена и покрыта regression; независимой банковской оценки нет |
| Внешняя интеграция | Интерфейс и TEST adapter подготовлены; реальные credentials/checkout/callback NOT VERIFIED |
| Эксплуатация | Базовая диагностика/retry/restore проверены; HA, load SLO, PITR/DR, alerting не подтверждены |
| Банковский пилот | Пригодно для технического обсуждения и согласования ограниченного пилота; подключение банка заблокировано до согласования и закрытия нижеперечисленных условий |

Приоритет до внешнего допуска: (1) bank/test credentials + trusted merchant/order/category source, (2) независимый security/tenant/runtime-role/egress review, (3) согласованный IAM/SSO/MFA recovery/onboarding, (4) совместные timeout/reconciliation и нагрузочные/restore acceptance tests. RLS/WORM/KMS, production refund orchestration, four-eyes и SLO остаются в [Product Gaps](bank-pilot/08-product-gaps.md).

Отзыв линейризуется до commit первого dispatch claim. После commit исполнение уже начато, неизвестный результат удерживает бюджет; отзыв не является отменой у провайдера. Один grant не создаёт две покупки, но новые independent intents с разными idempotency keys не дедуплицируются по order_id — интегратор обязан корректно вести свою идентичность заказа.

Пакет обсуждения с банком: [bank-pilot](bank-pilot/01-executive-technical-summary.md). Это не сертификация и не разрешение на банковский production или реальные деньги.
