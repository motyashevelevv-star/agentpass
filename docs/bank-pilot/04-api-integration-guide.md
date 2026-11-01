# Подключение внешнего агента

Источник истины — [API.md](../../API.md), live `/v1/docs`, [SDK example](../../examples/external-agent/README.md). Все суммы — целые копейки, RUB.

1. Owner/developer session регистрирует агента `POST /v1/agents`, создаёт `POST /v1/mandates`. Мандат с лимитами/категориями принадлежит конкретному пользователю и агенту.
2. Создаёт два ключа `POST /v1/developer/api-keys`: `purpose=agent` и `purpose=executor`. Чувствительные действия требуют MFA. Исполнитель хранится отдельно от AI runtime.
3. Агент вызывает `POST /v1/intents` с merchant_id/order_id, amount/currency, timestamp, стабильным idempotency_key. Повторять нужно всё исходное тело, включая timestamp; изменённое тело даёт 409.
4. `decision_kind=ASK_USER` (legacy `decision=ASK`) означает ожидание владельца. Пользователь подтверждает конкретный approval в Dashboard; API key этого делать не может. Агент опрашивает getIntent/waitForDecision. DENY не исполняется.
5. Для authorized intent агент получает `POST /v1/intents/{id}/execution-grant`. TTL по умолчанию 120 секунд. Новый grant после истечения не выдаётся: требуется новый intent/проверка.
6. Доверенный executor отправляет grant в `POST /v1/executions`. Повторы возвращают ту же execution. Worker выполняет I/O. `GET /v1/executions/{id}` возвращает queued/pending/unknown/succeeded и provider status.
7. `unknown` требует сверки и удерживает бюджет. Разрешён ручной `POST .../reconcile`, который только планирует повторную сверку. Не создавайте вместо этого новую покупку.
8. Владелец просматривает audit, receipt и JSON export; отзывает `POST /v1/mandates/{id}/revoke`.

Запускаемая проверка `python infra/verify-pilot-sdk.py` создаёт отдельного тестового агента/мандат и проверяет весь local workflow через SDK/API/worker. Это не запрос к ЮKassa.
