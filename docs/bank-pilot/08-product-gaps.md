# Незавершённые возможности

Блокеры подключения ограниченного внешнего пилота:

1. Нет банковского adapter и согласованного доверенного merchant/category/order source. ЮKassa — только стандартный TEST checkout, соединение NOT VERIFIED.
2. Нет законченного enterprise OIDC authorization-code/PKCE/state/provisioning/recovery flow. Offline validator не является SSO-интеграцией.
3. Нужны независимый pentest/tenant review, runtime DB roles/network review; RLS не включён, WORM/KMS/HSM нет.
4. Требуется совместный тест ambiguous timeout с внешним провайдером и операторский процесс связывания неизвестного payment ID. Автоматически повторно создавать такой checkout запрещено.

Перед production дополнительно:

- Полноценный cancel/refund workflow и reconciliation отчёты. Методы адаптера есть, публичной orchestration API возвратов нет.
- Four-eyes повышение полномочий, project-level RBAC, централизованный account budget, merchant attestation; order_id uniqueness между отдельными intent не реализована.
- Grant signing keyring/grace rotation, Fernet re-encryption и MFA recovery с верификацией владельца; phishing-resistant MFA.
- Webhook delivery leases, distributed observability/tracing/alerts, p95/p99 нагрузка, HA/PITR/DR drill и согласованные SLO.
- Строгая CSP с nonce, данные/retention/export policy, юридические договорённости и независимые подтверждения применимых требований.
- Полная локализация; LLM клиент не подключён. Реализована только безопасная граница предложений и deterministic fallback.

Не заявляется PCI DSS, соответствие требованиям Банка России, интерес ВТБ или право на реальные платежи. Это техническая база для согласования пилота, не банковский production.
