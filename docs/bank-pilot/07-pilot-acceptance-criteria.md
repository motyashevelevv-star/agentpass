# Предлагаемые критерии приёмки

Критерии требуют согласования с партнёром; они не являются принятыми банком нормативами.

| Проверка | Измеримый результат |
|---|---|
| Воспроизводимость | Развёртывание из чистого checkout по README; migration head, /ready и worker heartbeat |
| Decision | 8k APPROVE, 12k ASK_USER + одноразовое согласие, 18k DENY на одинаковых правилах |
| Budget | При ≥20 конкурентных попытках дневной consumed+held+inflight не превышает лимит; число платежей сверяется с provider journal |
| Replay | ≥20 повторов intent/grant/execution создают одну execution и один provider payment для этого разрешения |
| Binding | Подмена amount/currency/merchant/order/tenant/agent/version отклонена; DB trigger и API regression |
| Timeout/crash | Сбой до/после provider response не создаёт ложного success; unknown удерживает резерв, reconcile подтверждает единственный результат |
| Isolation | Отдельные owner/tenant/agent/executor principals не получают чужие ресурсы; отрицательные API tests |
| Access | Step-up, session/key revoke и rotation проверены; unsafe pilot config не запускается |
| Evidence | Для каждого success есть связанный provider status/test flag/hash, execution ID, intent ID, audit и receipt |
| External | Проверка с официальными test credentials, callback/retry и reconcile выполнена совместно; до этого NOT VERIFIED |

Latency/throughput, доступность, RPO/RTO и retention необходимо определить до пилота и измерить на согласованной инфраструктуре. Unit/mock tests не подтверждают эти SLO. Независимый security review и закрытие согласованных P0 — обязательный допуск, а не вывод из зелёной CI.
