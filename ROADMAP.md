# Развитие и банковский пилот

## Демонстрационный MVP (реализовано)

Четыре интерфейса, организации/проекты/роли, сессии и ключи, мандаты/версии, deterministic engine, PostgreSQL reservation, ASK, симулированное исполнение, аудит, аналитика, OpenAPI, SDK, webhook outbox/receiver, Docker и CI.

## Перед пилотом с банком

1. Совместно определить trust boundary: кто подтверждает merchant/category/amount, кто исполняет платёж, что означает банковский статус и как связывается authorization с неизменяемым банковским Payment Intent.
2. Подключить тестовый банковский адаптер без реальных денег: подпись/аутентификация, idempotency provider, settlement/reconciliation, отмена/возврат, повторные события и аварийное восстановление.
3. Завершить enterprise SSO/OIDC/PKCE, phishing-resistant MFA, восстановление аккаунта и four-eyes повышение лимитов. TOTP/step-up и lifecycle участников уже реализованы.
4. Усилить изоляцию: PostgreSQL RLS, составные tenant FKs, отдельная migration role и runtime role, защищённые admin credentials, формальный RBAC review.
5. Вывести секреты в KMS/Vault, добавить ротацию API/webhook keys и управление сертификатами. Подключить egress proxy/allowlist и согласовать обработку DNS/сетевых политик.
6. Провести независимый threat review и pentest: tenant escape, гонки, replay, webhook SSRF, injection, takeover, действия DB administrator.
7. Нагрузочно проверить целевые SLO, конкуренцию нескольких API/worker, длинные очереди, деградацию и сбои БД. Ввести leases, retry/dead-letter UI, tracing/Prometheus, метрики worker heartbeat и alerting.
8. Проверить backup/restore, PITR, retention, удаление персональных данных и экспорт аудита в независимое WORM-хранилище. Организовать runbooks и response process.
9. Согласовать юридическую модель, договоры, согласия пользователя, хранение данных и требования регулятора. Соответствие подтверждать только после отдельного аудита.

## После пилота

Версионированные policy DSL/шаблоны, бюджеты уровня организации и счёта, расширенный merchant registry, несколько валют с раздельной аналитикой, подписанные capability tokens, модели agent-to-agent delegation, SDK Python, SSE и полноценная локализация. Подключение LLM — только для интерпретации намерения, без права определять финансовый verdict.

Приоритет определяется результатами customer development: число агентов, частота ASK, время ответа пользователя, false-deny причины, интеграционные затраты, требования банка к подтверждению и аудиту.

Текущая итерация и открытые production gaps: [PILOT_READINESS](docs/PILOT_READINESS.md), [bank-pilot Product Gaps](docs/bank-pilot/08-product-gaps.md). Не переводить статус внешних соединений из NOT VERIFIED по mock tests.
