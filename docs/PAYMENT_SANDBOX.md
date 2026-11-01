# Payment providers и внешний TEST checkout

По умолчанию используется `local_simulator`: долговечный PostgreSQL journal, idempotent create/authorize/status/cancel/refund/reconcile. Ни денег, ни карточных данных нет. Старый `/execute` доступен только sandbox/development и использует этот провайдер.

Новый `PaymentProvider` — строгие Pydantic PaymentRequest/ProviderPayment и операции create/authorize/status/cancel/refund/reconcile/callback. Provider I/O идёт через committed execution queue. Public execution API пока оркестрирует create/status/reconcile; cancel/refund методы адаптера не имеют отдельного пользовательского workflow и не должны вызываться вручную мимо аудируемой orchestration в банковском пилоте.

## ЮKassa: NOT VERIFIED

Адаптер написан по официальной документации, прочитанной 2026-10-29:

- [API](https://yookassa.ru/developers/api)
- [Тестирование](https://yookassa.ru/developers/payment-acceptance/testing-and-going-live/testing)
- [Формат взаимодействия / идемпотентность](https://yookassa.ru/developers/using-api/interaction-format)
- [Уведомления](https://yookassa.ru/developers/using-api/webhooks)
- [Быстрый старт](https://yookassa.ru/developers/payment-acceptance/getting-started/quick-start)

Это обычный redirect checkout с `capture=true`, не автономное списание агентом и не доступ к банковскому счёту. Basic Auth — shop ID/secret. AgentPass дополнительно принимает только test-prefixed credentials, каждый ответ обязан содержать `test=true` и соответствующий recipient. Live keys запрещены. Реальный test shop/credentials не предоставлены, внешнее соединение, checkout и доставка callback **NOT VERIFIED**. MockTransport contract tests этого статуса не меняют.

Подключение оператором:

1. Создать официальный тестовый магазин по процедуре провайдера; получить только test credentials через согласованное защищённое хранилище. Не вводить реальные карты/данные.
2. Настроить `YOOKASSA_SANDBOX_ENABLED=true`, `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` и HTTPS `PAYMENT_RETURN_URL` в окружении API **и worker**. Restart требуется. Никогда не коммитить `.env`.
3. Согласовать HTTPS ingress для `POST /v1/providers/yookassa/callback` и уведомления payment.succeeded/payment.canceled/payment.waiting_for_capture в настройках test shop. Публичное размещение в этой задаче не выполнялось.
4. Создать intent с `merchant_id=yookassa:SHOP_ID`, новым `order_id`, RUB и подтверждённым пользователем мандатом. Получить grant с `provider=yookassa_sandbox`, передать отдельному executor key.
5. Poll execution до provider confirmation_url; открыть стандартный TEST checkout человеком. После подтверждения система принимает успех только через аутентифицированный provider response/refetch с точным hash/amount/currency/test recipient. `YKTEST-...` — ссылка-подтверждение, не фискальный чек.
6. Совместно проверить pending/canceled/succeeded, повтор webhook, ошибку/тайм-аут и reconcile; сохранить обезличенные свидетельства. Только после этого отметить соединение VERIFIED для конкретной конфигурации.

Провайдер не документирует HMAC-подпись notification в выбранной схеме; AgentPass не выдумывает её. Incoming callback — подсказка ID/intent. Авторитет — authenticated GET к фиксированному API endpoint. Чужой hash/amount/recipient отклоняется. Повтор callback не создаёт вторую transaction. Callback не даёт право создать payment.

Если create завершился неоднозначным timeout без payment ID, adapter **не создаёт новый checkout**. Budget остаётся inflight; нужен проверенный callback либо согласованный операторский поиск у провайдера. Ручной reconcile без ID не угадывает статус. Retry после истечения provider idempotency window также не создаёт новую покупку. Это намеренный безопасный stop, требующий операционного процесса.

Refund/cancel поддержка ограничена возможностями провайдера: cancel не отменяет уже захваченный платёж; refund требует confirmed succeeded. Автономного public refund workflow и сверки частичных возвратов нет. Не заявлять их завершённой интеграцией.
