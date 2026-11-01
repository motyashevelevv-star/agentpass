# Внешний агент без Concierge

Node.js 22+ (проект проверен на Node 24). Сначала запустите API/PostgreSQL/worker по корневому README, затем `npm ci && npm run build -w packages/sdk-typescript` из корня. Для одного запуска в Docker локальный Node не нужен; этот пример запускается разработчиком отдельно.

В Dashboard создайте агента и мандат. В Developer Portal → API-ключи выпустите два ключа для этого агента: «Агент» и «Доверенный исполнитель». Не передавайте executor key в LLM или стороннюю среду агента. Все значения ниже — собственные тестовые ключи, не production credentials.

```bash
export AGENTPASS_URL=http://localhost:8000
export AGENTPASS_AGENT_ID=YOUR_AGENT_ID
export AGENTPASS_MANDATE_ID=YOUR_MANDATE_ID
# Ввод без сохранения секрета в истории команд:
read -r -s AGENTPASS_API_KEY
export AGENTPASS_API_KEY
read -r -s AGENTPASS_EXECUTOR_KEY
export AGENTPASS_EXECUTOR_KEY
node examples/external-agent/run.mjs
```

В zsh на Mac вместо `read -r -s NAME` можно использовать `read -s NAME`. Секреты не выводятся в stdout. Файл example не вызывает `/console/run` и не использует локальные mock responses: SDK отправляет настоящий Intent, получает grant, executor передаёт его worker и читает состояние из БД через API.

По умолчанию сумма 800000 копеек (8 000 ₽). `AMOUNT_MINOR=1200000 node examples/external-agent/run.mjs` показывает ASK_USER: подтвердите запрос в Dashboard, пример продолжит polling. `AMOUNT_MINOR=1800000` покажет DENY при лимите операции 15 000 ₽. Используйте новый мандат для повторной демонстрации или учитывайте остаток дневного бюджета.

Коды выхода: 0 — simulator подтвердил успех; 2 — нет разрешения; 3 — результат не завершён/нужна сверка. При unknown не создавайте новую покупку автоматически. Повтор HTTP execution с тем же grant возвращает прежний execution ID. Сохранение исходного intent body/idempotency key и operation ID между рестартами — ответственность внешнего агента; минимальный CLI-пример этого не автоматизирует.

Для программного onboarding SDK поддерживает `registerAgent`, `createMandate`, `createApiKey`, `revokeMandate`, `listAuditEvents` через owner/developer session. Node options: `{baseUrl, session:{cookie, csrfToken, mfaCode:async()=>freshCode}}`. Это control plane: agent key не может менять мандат или подтверждать согласие. Не храните cookie в репозитории. Исполняемый полный onboarding/ASK/grant/revoke тест: `.venv/bin/python infra/verify-pilot-sdk.py`; он использует тестовую owner session и отдельные ресурсы.
