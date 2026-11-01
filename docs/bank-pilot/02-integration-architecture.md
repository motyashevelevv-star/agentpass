# Интеграционная архитектура

Текущий исполняемый путь:

```text
Owner session + MFA → mandate/version → Policy Engine ← agent key + intent
                                     ↓
                         APPROVE / ASK → human approval → re-evaluate
                                     ↓
                         signed short-lived Execution Grant
                                     ↓
                  trusted executor key → durable execution queue
                                     ↓
                 worker claim/commit → PaymentProvider → evidence/refetch
                                     ↓
                    reconcile → transaction / retained unknown budget
                                     ↓
                            audit + signed webhook outbox
```

AI-агент не получает executor key. Выдача ключа исполнителя и управление мандатом — control plane пользователя. В pilot исполнение с user/agent credentials запрещено. Provider I/O выполняется после commit claim, вне финансовых locks. При сбое следующая попытка использует тот же provider key и reconcile; неопределённость не считается успехом.

Возможная банковская интеграция — предположение для обсуждения: банк предоставляет согласованный test API и доверенную идентичность продавца/заказа, executor проверяет grant и обращается к нему; банковский статус подтверждается через подписанный callback и/или аутентифицированный status API. Формат grant, ключи, сеть, юридические основания, step-up и ответственность требуют согласования. Наличие у конкретного банка такого API здесь не утверждается.

ЮKassa adapter реализует стандартный redirect test checkout, не автономное списание со счёта и не банковскую интеграцию. Для него callback не имеет придуманной HMAC-подписи: уведомление только запускает проверку через аутентифицированный API.
