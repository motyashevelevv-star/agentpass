# Модель угроз и безопасность

Версия — локальный sandbox MVP, без заявления о PCI DSS, соответствии требованиям ЦБ РФ или банковской production-готовности. Формальный аудит не проводился. AgentPass не хранит банковские счета, PAN/CVV и не выполняет реальное списание.

## Trust boundary

Пользователь задаёт полномочия и подтверждает конкретное намерение. Агент потенциально ошибочен или скомпрометирован. Engine не доверяет ему в вопросах права на операцию, но merchant/category/amount пока поступают от самого интегратора. Sandbox каталог фиксирован. Для реального банка данные должны быть подтверждены платёжным провайдером и связаны с неизменяемым исполняемым intent; иначе агент может лгать о категории или продавце.

## Реализованные меры

| Угроза | Мера |
|---|---|
| Кража пароля из БД | scrypt n=16384/r=8/p=1, случайная соль; пароль не возвращается API |
| Кража session DB dump | Случайный 256-bit токен, SHA-256 hash в БД; HttpOnly cookie, 12 часов, отзыв, ротация при login |
| CSRF | SameSite=Lax, проверка `X-CSRF-Token` по хешу, Origin allowlist для изменяющих запросов |
| Tenant escape / IDOR | Серверные owner/org/agent проверки, membership lookup; чужие финансовые ресурсы дают 404 |
| Самоподтверждение агента | Agent-bound API key не допускается к user-only approval endpoints |
| Утечка API key | Высокоэнтропийный ключ; хранится только SHA-256, prefix, срок/scopes; выдача один раз |
| Race / double budget spend | `FOR UPDATE` mandate lock, общий порядок блокировок, единый commit резерва и verdict |
| Replay intent | Timestamp ±5 минут при первом запросе, уникальные agent/idempotency_key, fingerprint идентичного тела |
| Replay approval / execution | Approval привязан к intent, срок 15 минут, одноразовый статус; уникальные reserve/approval/transaction для intent |
| Отзыв во время действий | Отзыв мандата использует те же locks, освобождает held и инвалидирует pending; исполнение проверяет version/status |
| SQL injection | Параметризованные SQLAlchemy queries; search экранирует wildcard; суммы/входы Pydantic |
| Webhook forgery/replay | HMAC-SHA256, timestamp, delivery ID; receiver constant-time verify и дедупликация |
| Webhook SSRF | Публичные HTTPS:443, DNS/IP проверка каждой попытки, IP pinning с TLS hostname, без redirects/credentials |
| Утечка webhook secret | Fernet ciphertext; постоянный ключ только в env; секрет показывается один раз |
| Утечка в логах | Только route template/method/status/duration/request_id; без body/header/key/token; безопасные error_class вместо текстов исключений |
| Rate abuse | Атомарные минутные окна PostgreSQL, специальные login/register ограничения; body ≤64 KiB |
| Изменение аудита | Нет API изменения; PostgreSQL trigger запрещает UPDATE/DELETE обычными statements |
| Frame embedding | Frontend X-Frame-Options DENY, nosniff, same-origin referrer policy и ограниченная Permissions-Policy |

Обычные пользователи не получают platform_admin при регистрации. В sandbox admin создаётся seed отдельно. Owner управляет org members; developer видит developer telemetry/webhook delivery своей организации, но не получает чужие пользовательские мандаты/намерения. API-key listAgents/listMandates и операции ограничены его агентом. Последующее выполнение платежа реальным банком не реализовано.

Кнопки быстрого sandbox-входа используют обычный `/v1/auth/login`, создают штатную сессию и не обходят RBAC/CSRF. Они доступны только при sandbox + seed + стандартном demo-пароле. Для локального sandbox origin разрешены алиасы localhost/127.0.0.1/terminal.local с совпадающими схемой и портом; для внешнего origin и production разрешён только явно настроенный origin.

Ключи сериализуются с отзывом через row lock. Организация получает shared lock на время аутентифицированной транзакции, поэтому suspension ждёт уже начатые действия. Отзыв сессии блокирует последующие запросы; уже проверенный запрос может закончиться. Пароль меняется после проверки текущего; другие сессии отзываются.

В sandbox существует одно узкое сетевое исключение: конфигурационный `SANDBOX_RECEIVER_URL` собственного API допускает HTTP/private host. Пользователь не может произвольно разрешить private URLs через API. Receiver принимает только существующие outbox deliveries соответствующего endpoint, проверяет HMAC/time/event ID и ведёт receipt. Вне sandbox исключение выключено; deployment admin должен корректно задать URL.

## Оставшиеся риски

- Полного enterprise SSO/OIDC, recovery/email verification и управления credential breach нет. TOTP MFA/step-up реализованы; offline OIDC assertion validator не заменяет login flow. Pilot запрещает self-registration; создание аккаунтов — offline operator CLI.
- Tenant isolation на уровне приложения, без PostgreSQL RLS. Добавлены составные tenant FKs для финансовой цепочки Agent → Mandate → Intent → Approval/Reservation/Transaction/Grant/Execution. Runtime и migration roles в Compose используют один DB credential. Перед пилотом — разделение ролей, RLS и review всех access paths.
- Audit trigger не защищает от DB owner/superuser: они могут отключить trigger, изменить схему или выполнить TRUNCATE. Независимого WORM/подписанной цепочки нет.
- Текстовые поля и произвольная metadata могут содержать секреты, если интегратор нарушает контракт. Reserved sensitive keys отклоняются, но универсального DLP/распознавания PAN в тексте нет. Не передавайте карточные или банковские секреты.
- `ENCRYPTION_KEY` из env нужно сохранять между рестартами. KMS/HSM и ротация отсутствуют; потеря ключа делает existing webhook secrets нечитаемыми. Кража конфигурации вместе с БД раскрывает signing secrets.
- Один скомпрометированный агент может создавать разные намерения в рамках лимита: идемпотентность предотвращает повторы одного запроса, не отличает новые злоумышленные намерения. Нужны attestation, monitoring и user-triggered revoke.
- HMAC обеспечивает аутентичность webhook, не юридическую неотказуемость. Внешний receiver обязан сам проверять время и delivery deduplication.
- Pinned HTTPS public delivery использует прямое исходящее соединение; в сети, допускающей только proxy, потребуется согласованный egress adapter. Локальный receiver и Compose-демо работают без внешней сети после сборки.
- Нет разграничения полномочий на уровне отдельного project, двух лиц для повышения лимита, глобального бюджета аккаунта или лимита нескольких мандатов.
- Rate limit user/key не заменяет ingress DDoS/WAF. Login ограничен IP+email и общим IP окном; необходимы ingress CPU/DDoS budget и trusted proxy configuration. Сроки и rate cleanup требуют worker для оперативного отображения, но engine проверяет expiry самостоятельно.
- Next.js inline scripts и клиентская архитектура требуют отдельной строгой CSP с nonce перед внешним pilot. Полного XSS security audit не было; React экранирует текст, user HTML не исполняется.
- Метрики не являются observability stack: есть worker heartbeat/unknown/dead-letter диагностика, но нет tracing, alerting, проверенного HA, PITR и disaster recovery. Runbook backup/restore не является подтверждением RPO/RTO.

## Внешний пилот

HTTPS, `COOKIE_SECURE=true`, точный `WEB_ORIGIN`, `SEED_DEMO=false`, уникальные credential/secret manager, публичный webhook host allowlist, отдельные DB roles, резервные копии, выделенная сеть и независимый pentest. Реальные платежи подключать только после согласования immutable intent binding, банковской аутентификации и reconciliation.

Об обнаруженных проблемах сообщайте команде через приватный канал организации; публичного security mailbox для этого локального репозитория нет.

Удаление участника блокируется с его запросами через membership row lock и отзывает его API-ключи. Ключ дополнительно проверяет актуальное членство и роль создателя при каждом запросе; viewer или удалённый участник не сохраняет агентский доступ. Порядок auth locks: организация → членство → ключ.

Отключение `SEED_DEMO` не удаляет существующие demo/admin учётные записи. Внешний пилот должен использовать новую БД без seed ; запуск pilot с известными seed email блокируется, даже при отключённом seed.

## Новая граница исполнения

Подробная модель цепочки, защита grant и остаточные риски: [Security Model](docs/bank-pilot/03-security-model.md). Intent защищён DB trigger и fingerprint; grant HMAC связан с owner/org/agent/merchant/order/amount/currency/version/provider. Только worker вызывает внешний провайдер после commit. Unknown удерживает inflight-бюджет без TTL до подтверждённой сверки. Отзыв блокирует действие до commit первого dispatch claim. После этого исполнение считается начатым и отзыв не отменяет checkout внешнего провайдера. Не передавайте executor key или grant в LLM.

Ротация API-key/endpoint secret немедленно отзывает старый материал. Секрет подписи grant ротируется конфигурацией с новым key ID; неиспользованные старые grant становятся недействительными, автоматического keyring/grace window нет. Для Fernet нужен отдельный план re-encryption, KMS/HSM не реализован. TOTP seed шифруется, код сериализован и одноразовый; это не phishing-resistant MFA. Возвраты/отмены провайдера доступны на уровне адаптера, публичного refund workflow пока нет.
