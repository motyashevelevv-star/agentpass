# Эксплуатация ограниченного пилота

`infra/compose.yml` — локальный sandbox, не шаблон банковского production. Не удаляйте volume и не запускайте reset/truncate над пользовательской БД. Новая миграция добавляет таблицы/ограничения, не пересоздаёт существующие данные. При нарушенных исторических tenant связях она должна остановиться: сначала расследовать данные, не удалять их ради миграции.

## Окружения и доступ

- development/sandbox: loopback, local simulator, необязательный seed. Mac launcher сохраняет конфигурацию и volume.
- pilot/production: конфигурация fail-closed. Нужны HTTPS/secure cookie, `ALLOW_PUBLIC_REGISTRATION=false`, `REQUIRE_MFA=true`, `SEED_DEMO=false`, пустой DEMO_PASSWORD, отдельный EXECUTION_SIGNING_KEY длиной ≥32 и key ID, DB password ≥24, sslmode=verify-full, webhook hostname allowlist. Live payment adapter отсутствует даже при environment=production.
- API startup запрещает runtime superuser/BYPASSRLS, владельца public tables и известные seed accounts. Не используйте sandbox DB/credentials. Runtime роль не должна иметь CREATE/TRUNCATE/DDL; migrator — отдельный offline principal. Compose по умолчанию эти роли не разделяет, поэтому pilot таким compose не стартует успешно.

Пример прав после миграции отдельной migrator ролью (DBA согласует имена/схемы и создаёт роли через secret manager, не копирует пароли из документа):

```sql
GRANT CONNECT ON DATABASE agentpass_pilot TO agentpass_runtime;
GRANT USAGE ON SCHEMA public TO agentpass_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO agentpass_runtime;
REVOKE UPDATE, DELETE ON audit_events FROM agentpass_runtime;
REVOKE ALL ON alembic_version FROM agentpass_runtime;
GRANT SELECT ON alembic_version TO agentpass_runtime;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Роль runtime не должна наследовать migrator/owner. PostgreSQL RLS не реализован; это остаточная угроза и предмет отдельного review. Default privileges для новых миграций задаёт DBA. API/worker запускаются без `alembic upgrade` в runtime command; schema migration — отдельный release шаг. TLS CA и сеть согласуются с банком.

Onboarding оператора после согласования личности: `PYTHONPATH=apps/api .venv/bin/python infra/provision_pilot.py --email USER --name NAME --organization ORG`. CLI требует ENVIRONMENT=pilot, спрашивает пароль через getpass, не перезаписывает существующий аккаунт/MFA. `--platform-admin` — отдельное явное решение оператора. Проверка корпоративного email вне системы; SSO/provisioning не завершены. После первого входа подключить MFA в Security. Автоматического MFA/password recovery нет.

## Диагностика и восстановление задач

`/live` — process liveness. `/ready` проверяет DB/таблицу исполнения и ожидаемый schema revision. Не выдаёт информацию о секретах. `/health` сохранён для совместимости. Platform admin `/v1/admin/operations` показывает heartbeat (stale >90 s), unknown, quarantine (≥10 попыток) и webhook failed. Это диагностические счётчики, не alerting/SLO stack.

Execution lease 30 s, provider timeout 5 s. Worker после crash забирает истёкший lease, сначала сверяет provider identity. Retry backoff 2^attempt, cap 300 s; после 10 попыток требуется ручной reconcile/проверенный callback. Не изменять статус unknown напрямую в SQL и не освобождать inflight по времени: платёж мог состояться. До повторного намерения подтвердить отмену/результат исходного у провайдера.

Webhook delivery: 5 попыток, затем failed/dead letter. Consumer проверяет HMAC/time/delivery ID и дедуплицирует. Автоматического replay dead letters API нет; оператор исследует ошибку и использует согласованный повтор события без новой покупки. Secret rotation немедленная: заранее согласовать окно переключения consumer; dual-secret grace нет.

Worker SIGTERM/SIGINT прекращает новые циклы после текущего bounded вызова; lease позволяет восстановить незавершённый execution. При shutdown API используйте штатный graceful timeout Uvicorn, затем остановку worker. JSON request logging не включает body/Authorization/cookies/provider error bodies. Request IDs создаёт сервер; распределённого tracing нет.

## Backup/restore

Для изолированного sandbox с запущенным compose (пример; путь dump содержит данные и должен храниться защищённо):

```bash
umask 077
docker compose --env-file .env -f infra/compose.yml exec -T db pg_dump -U agentpass -Fc agentpass > agentpass-backup.dump
# Только новая отдельная база, НЕ существующий пользовательский том:
docker compose --env-file .env -f infra/compose.yml exec -T db createdb -U agentpass agentpass_restore
docker compose --env-file .env -f infra/compose.yml exec -T db pg_restore -U agentpass -d agentpass_restore --no-owner < agentpass-backup.dump
```

Для pilot: encrypted backups, secret manager backup ENCRYPTION_KEY и signing configuration, off-host retention, PITR и регулярный drill. Потеря Fernet key делает MFA/webhook secrets нечитаемыми. Восстановление старой БД без provider reconciliation может повторно исполнить операцию: **сначала остановить dispatch**, сверить внешний журнал и неопределённые платежи. Stable provider key не даёт бессрочной внешней гарантии после disaster recovery. RPO/RTO не подтверждены.

Нагрузочные p95/p99/SLO, HA, failover и полноценный disaster recovery drill ещё не проверены. Concurrency regression проверяет корректность бюджетов и replay на PostgreSQL, но не заменяет эксплуатационные испытания.
