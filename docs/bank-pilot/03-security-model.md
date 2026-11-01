# Модель безопасности

| Граница / угроза | Реализованная защита | Остаточный риск |
|---|---|---|
| Agent → Intent: ложный merchant/category | tenant/owner/agent checks, строгая схема, сумма minor units, fingerprint, DB immutable trigger | Категория и свободное имя продавца предоставляются интегратором; нужна независимая attestation |
| Intent → Decision: replay / budget race | advisory idempotency lock, unique key, одинаковый financial lock order, atomic reserve | Разные idempotency keys — разные намерения; order_id не глобально уникален |
| ASK → Approval: self-approval / повтор | Только user session, CSRF, TTL, одноразовое согласие, повторная проверка правил/лимитов, TOTP step-up | TOTP не phishing-resistant; нет four-eyes |
| Decision → Grant: подмена параметров | HMAC capability, 120 s, hash в БД, immutable claims, связаны tenant/owner/agent/intent/merchant/order/amount/currency/version/provider | Симметричный signer доверенный; нет HSM и независимого public-key verifier |
| Grant → Executor: двойная покупка | Atomic consume + unique intent/grant/execution; отдельный executor scope | Утечка обоих ключей позволяет новые операции в рамках мандата |
| Executor → Provider: timeout/crash | Committed outbox, stable provider key, lease fencing, reconcile first, unknown удерживает inflight | Без provider ID неоднозначный внешний checkout требует callback/оператора, не пересоздаётся |
| Provider → Audit: forged success | test=true/recipient/hash/amount/currency/payment ID validation; callback authenticated refetch | Реальное внешнее соединение NOT VERIFIED; bank API не подключён |
| Tenant escape | backend RBAC и owner/org checks, composite financial FKs, cross-tenant regression | PostgreSQL RLS нет; privileged DBA остаётся доверенным |
| Webhook egress / replay | public IP pinning, TLS hostname, no redirect, HMAC/timestamp/delivery dedup, retries | Требуется egress review в сети банка; consumer сам дедуплицирует |

Пароли scrypt, session/key hashes, HttpOnly/SameSite/CSRF, Origin allowlist, body/rate limits и маскирование логов сохранены. TOTP seeds и webhook secrets шифруются Fernet. Rotation endpoint немедленно отзывает старый API key/endpoint secret; согласуйте обновление consumer, периода двух секретов нет. Неиспользованные grants после смены signing key недействительны.

Pilot fail-closed требует HTTPS, MFA, закрытой регистрации, отдельного signing key, strong DB credentials/TLS, runtime роли без superuser/BYPASSRLS/schema ownership и отсутствия известных seed accounts. Создание аккаунта — offline CLI оператора, MFA enrolment после первого входа. OIDC assertion validator проверяет подпись/issuer/audience/nonce/expiry, но login/PKCE/provisioning не реализованы.

Audit append-only для обычной runtime роли; не WORM, DBA может менять схему. Отзыв мандата блокирует будущую отправку, но не отменяет уже инициированный checkout. Unknown не освобождается по TTL. Нет формальной сертификации, независимого pentest или production approval. Полная модель: [SECURITY.md](../../SECURITY.md).
