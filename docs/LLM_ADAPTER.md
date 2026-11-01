# Интерпретатор намерений

`apps/api/agentpass/interpreter.py` содержит рабочий deterministic fallback и границу StructuredLLMInterpreter. `/v1/console/run` по умолчанию явно использует DeterministicInterpreter; внешние вызовы модели не выполняются.

Внешний клиент реализует `propose_json(prompt, catalog) -> dict`. Допустим только `{product_id, budget_minor}`. Pydantic запрещает дополнительные поля, включая decision/mandate_id; resolver проверяет товар в каталоге и цену в предложенном бюджете. Цена/merchant/category берутся из серверного каталога, а не из свободного ответа модели. Затем обычный IntentIn проходит неизменённый Policy Engine.

Модель не получает user session, executor key, grant signing key, доступ к БД или инструментам изменения мандата. Она не подтверждает ASK и не принимает окончательное финансовое решение. Семантическая верность интерпретации естественного языка не гарантируется одной схемой — перед внешним пилотом нужны UX review предложения и проверки prompt injection/ошибочного выбора товара.

Подключение согласованного внешнего клиента потребует явного выбора interpreter в backend composition root, secret manager, timeouts/privacy policy, contract tests и отдельного E2E с test credentials. Автоматического переключения по произвольному URL/ключу в этом выпуске нет. Не представлять protocol/mock tests как выполненный вызов LLM.

`tests/test_interpreter.py`: deterministic 12 000 ₽ → реальный каталог, отказ от неизвестного товара, превышенного бюджета и попыток передать financial decision/rule identity. Внешний модельный провайдер **NOT VERIFIED / NOT CONNECTED**.
