"use client";
import { useState } from "react";
import {
  Search,
  Download,
  ArrowUpRight,
  ShieldCheck,
  Clock,
  Check,
  CheckCheck,
  X,
  Bot,
  ArrowRight,
  FileText,
  Wallet,
  Info,
} from "lucide-react";
import Link from "next/link";
import { api, money, date, category, statusName } from "@/lib/api";
import type { Page, Intent, Agent, Approval } from "@/lib/types";
import { useResource, useAction, useApp } from "./context";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";
import {
  PageTitle,
  Panel,
  Badge,
  Loading,
  Failure,
  Empty,
  Pager,
  CopyButton,
} from "./shared";
export function TransactionsPage() {
  const [offset, setOffset] = useState(0);
  const [decision, setDecision] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Intent | null>(null);
  const { notify } = useApp();
  const q = useResource<Page<Intent>>(
    `/v1/intents?limit=15&offset=${offset}${decision ? "&decision=" + decision : ""}&search=${encodeURIComponent(search)}`,
    10000,
  );
  const agents = useResource<Page<Agent>>("/v1/agents");
  function exportCsv() {
    const escape = (v: string) => {
      const safe = /^[\s=+@-]/.test(v) ? "'" + v : v;
      return '"' + safe.replaceAll('"', '""') + '"';
    };
    const csv =
      "id,description,merchant,amount_minor,currency,decision,status\n" +
      (q.data?.items || [])
        .map((i) =>
          [
            i.id,
            escape(i.description),
            escape(i.merchant),
            i.amount,
            i.currency,
            i.decision,
            i.status,
          ].join(","),
        )
        .join("\n");
    const url = URL.createObjectURL(
      new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "agentpass-intents-page.csv";
    a.click();
    URL.revokeObjectURL(url);
    notify("Текущая страница экспортирована");
  }
  return (
    <>
      <PageTitle
        title="Операции"
        description="Намерения, решения и подтверждённые результаты тестового исполнения."
        action={
          <Button
            variant="outline"
            onClick={exportCsv}
            disabled={!q.data?.items.length}
          >
            <Download size={16} />
            Экспорт страницы
          </Button>
        }
      />
      <Panel>
        <div className="table-toolbar">
          <div className="search-input">
            <Search size={16} />
            <input
              placeholder="Поиск по продавцу или описанию…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setOffset(0);
              }}
              aria-label="Поиск операций"
            />
          </div>
          <div className="segmented">
            {[
              ["", "Все"],
              ["APPROVE", "APPROVE"],
              ["ASK", "ASK"],
              ["DENY", "DENY"],
            ].map(([v, l]) => (
              <button
                key={v}
                className={decision === v ? "selected" : ""}
                onClick={() => {
                  setDecision(v);
                  setOffset(0);
                }}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
        {q.isPending ? (
          <Loading />
        ) : q.error ? (
          <Failure error={q.error} retry={() => q.refetch()} />
        ) : q.data.items.length ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Операция / продавец</th>
                    <th>Агент</th>
                    <th>Сумма</th>
                    <th>Решение</th>
                    <th>Исполнение</th>
                    <th>Дата</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {q.data.items.map((i) => (
                    <tr
                      className="clickable"
                      key={i.id}
                      onClick={() => setSelected(i)}
                    >
                      <td>
                        <div className="merchant-cell">
                          <span className="merchant-avatar">
                            {i.merchant[0]}
                          </span>
                          <div>
                            <button
                              className="table-title"
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelected(i);
                              }}
                            >
                              {i.description || i.merchant}
                            </button>
                            <small>
                              {i.merchant} · {category(i.category)}
                            </small>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className="agent-cell">
                          <Bot size={14} />
                          {agents.data?.items.find((a) => a.id === i.agent_id)
                            ?.name || "Агент"}
                        </span>
                      </td>
                      <td className="amount">{money(i.amount, i.currency)}</td>
                      <td>
                        <Badge value={i.decision} />
                      </td>
                      <td>
                        <span className="subtle-status">
                          {statusName(i.status)}
                        </span>
                      </td>
                      <td className="muted-text">{date(i.created_at, true)}</td>
                      <td>
                        <ArrowUpRight size={15} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              total={q.data.total}
              offset={offset}
              limit={15}
              setOffset={setOffset}
            />
          </>
        ) : (
          <Empty
            title={search ? "Операции не найдены" : "Нет операций"}
            description="Отправьте намерение из Agent Console или API Playground."
            action={
              <Button asChild variant="outline">
                <Link href="/console">
                  Открыть агента
                  <ArrowRight size={14} />
                </Link>
              </Button>
            }
          />
        )}
      </Panel>
      <IntentDetail intent={selected} close={() => setSelected(null)} />
    </>
  );
}
export function IntentDetail({
  intent,
  close,
}: {
  intent: Intent | null;
  close: () => void;
}) {
  return (
    <Modal
      open={!!intent}
      onOpenChange={close}
      title="Детали операции"
      description="Разрешение операции и её исполнение — отдельные стадии."
    >
      {intent && <IntentDetailBody initial={intent} />}
    </Modal>
  );
}
function IntentDetailBody({ initial }: { initial: Intent }) {
  const q = useResource<Intent>(`/v1/intents/${initial.id}`, 5000);
  const i = q.data || initial;
  const { me } = useApp();
  const execute = useAction<Intent, void>(
    () => api(`/v1/intents/${i.id}/execute`, { method: "POST" }),
    "Симуляция выполнена",
  );
  const cancel = useAction<Intent, void>(
    () => api(`/v1/intents/${i.id}/cancel`, { method: "POST" }),
    "Операция отменена, резерв освобождён",
  );
  return (
    <>
      <div className="intent-detail-hero">
        <span className="merchant-avatar large">{i.merchant[0]}</span>
        <div>
          <h3>{i.description || i.merchant}</h3>
          <p>
            {i.merchant} · {category(i.category)}
          </p>
        </div>
        <strong>{money(i.amount, i.currency)}</strong>
      </div>
      <div className="detail-grid">
        <div>
          <small>Решение</small>
          <Badge value={i.decision} />
        </div>
        <div>
          <small>Исполнение</small>
          <Badge value={i.status} />
        </div>
        <div>
          <small>Версия правил</small>
          <strong>v{i.evaluated_version}</strong>
        </div>
        <div>
          <small>Создана</small>
          <strong>{date(i.created_at, true)}</strong>
        </div>
      </div>
      <div className="decision-reasons">
        {i.reasons.map((r) => (
          <div key={r.code}>
            <ShieldCheck size={16} />
            <span>
              {r.message}
              <code>{r.code}</code>
            </span>
          </div>
        ))}
      </div>
      <div className="info-banner"><ShieldCheck size={16} /><span>Источник решения: Policy Engine · мандат v{i.evaluated_version}{i.approval ? ` · согласие: ${statusName(i.approval.status)}` : ' · автоматическая проверка'}</span></div>
      {i.execution && <div className="settings-rows">
        <div><span>Режим</span><strong>{i.execution.provider==='local_simulator'?'Локальная симуляция':'ЮKassa · внешний тестовый checkout'}</strong></div>
        <div><span>Исполнитель</span><strong>{statusName(i.execution.status)}</strong></div>
        <div><span>Статус провайдера</span><strong>{i.execution.provider_status || 'Ещё не подтверждён'}</strong></div>
        <div><span>Попытки / код ошибки</span><code>{i.execution.attempts} / {i.execution.last_error || '—'}</code></div>
        <div><span>Order ID</span><code>{i.order_id || 'Legacy sandbox'}</code></div>
        {i.execution.confirmation_url && <div><a className="text-link" href={i.execution.confirmation_url} target="_blank" rel="noreferrer">Открыть тестовый checkout</a></div>}
      </div>}
      {i.reservation && (
        <div className="info-banner">
          <Wallet size={16} />
          <span>
            Резерв: {statusName(i.reservation.status)}. До{" "}
            {i.reservation.status==='inflight'?'сверки провайдера':date(i.reservation.expires_at, true)}.
          </span>
        </div>
      )}
      {i.transaction && (
        <div className="receipt">
          <FileText size={18} />
          <div>
            <strong>{i.transaction.status==='external_test'?'Подтверждение внешнего тестового платежа':'Чек симулированной покупки'}</strong>
            <code>{i.transaction.receipt}</code>
          </div>
        </div>
      )}
      <div className="id-box">
        <code>{i.id}</code>
        <CopyButton text={i.id} label="ID" />
      </div>
      <Button variant="outline" onClick={()=>{
        const url=URL.createObjectURL(new Blob([JSON.stringify(i,null,2)],{type:'application/json'}));
        const a=document.createElement('a');a.href=url;a.download=`agentpass-${i.id}.json`;a.click();URL.revokeObjectURL(url);
      }}><Download size={14} />Экспорт деталей JSON</Button>
      <div className="form-footer">
        {["authorized", "pending"].includes(i.status) &&
          me.role !== "viewer" && (
            <Button
              variant="outline"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              Отменить операцию
            </Button>
          )}
        {i.status === "authorized" && me.role !== "viewer" && ['sandbox','development'].includes(me.environment) && (
          <Button disabled={execute.isPending} onClick={() => execute.mutate()}>
            Симулировать покупку
          </Button>
        )}
        {i.status === "pending" && (
          <Button asChild>
            <Link href="/approvals">
              К подтверждению
              <ArrowRight size={14} />
            </Link>
          </Button>
        )}
      </div>
      {q.error && <Failure error={q.error} />}
    </>
  );
}
export function ApprovalsPage() {
  const q = useResource<Page<Approval>>("/v1/approvals?limit=100", 5000);
  const agents = useResource<Page<Agent>>("/v1/agents");
  const [tab, setTab] = useState("pending");
  const [selected, setSelected] = useState<Approval | null>(null);
  const { me } = useApp();
  const action = useAction<Intent, { id: string; action: string }>(
    (v) =>
      api(`/v1/approvals/${v.id}/resolve`, {
        method: "POST",
        body: JSON.stringify({ action: v.action }),
      }),
    "Решение сохранено",
  );
  const rows =
    q.data?.items.filter((a) =>
      tab === "pending" ? a.status === "pending" : a.status !== "pending",
    ) || [];
  return (
    <>
      <PageTitle
        title="Подтверждения"
        description="Только вы решаете, может ли агент выйти за порог автоматического разрешения."
      />
      <div className="page-toolbar">
        <div className="segmented">
          <button
            className={tab === "pending" ? "selected" : ""}
            onClick={() => setTab("pending")}
          >
            Ожидают ответа
            <span>
              {q.data?.items.filter((a) => a.status === "pending").length || 0}
            </span>
          </button>
          <button
            className={tab === "history" ? "selected" : ""}
            onClick={() => setTab("history")}
          >
            История решений
          </button>
        </div>
        <span className="muted-text">
          <Clock size={14} />
          Срок подтверждения — 15 минут
        </span>
      </div>
      <div className="info-banner">
        <Info size={17} />
        <span>
          После согласия система повторно проверит мандат и бюджет.
          Подтверждение создаёт разрешение; агент исполняет покупку отдельно.
        </span>
      </div>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <Failure error={q.error} />
      ) : rows.length ? (
        <div className="approval-list">
          {rows.map((a) => {
            const i = a.intent;
            const expired = new Date(a.expires_at) <= new Date();
            return (
              <Panel key={a.id}>
                <div className="approval-main">
                  <span className="approval-icon">
                    <CheckCheck size={23} />
                  </span>
                  <div className="approval-info">
                    <div>
                      <h2>{i.description || "Финансовая операция"}</h2>
                      <Badge
                        value={
                          expired && a.status === "pending"
                            ? "expired"
                            : a.status
                        }
                      />
                    </div>
                    <p>
                      <Bot size={14} />
                      {agents.data?.items.find((x) => x.id === i.agent_id)
                        ?.name || "ИИ-агент"}{" "}
                      <span>→</span> {i.merchant}
                    </p>
                    <small>{i.reasons.map((r) => r.message).join(" · ")}</small>
                  </div>
                  <div className="approval-amount">
                    <strong>{money(i.amount, i.currency)}</strong>
                    <span>{category(i.category)}</span>
                  </div>
                </div>
                <div className="approval-footer">
                  <span>
                    <Clock size={13} />
                    {a.status === "pending"
                      ? `Действует до ${date(a.expires_at, true)}`
                      : `Решение ${date(a.resolved_at || a.created_at, true)}`}
                  </span>
                  <div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setSelected(a)}
                    >
                      Детали
                    </Button>
                    {a.status === "pending" &&
                      !expired &&
                      me.role !== "viewer" && (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={action.isPending}
                            onClick={() =>
                              action.mutate({ id: a.id, action: "reject" })
                            }
                          >
                            <X size={14} />
                            Отклонить
                          </Button>
                          <Button
                            size="sm"
                            disabled={action.isPending}
                            onClick={() =>
                              action.mutate({ id: a.id, action: "approve" })
                            }
                          >
                            <Check size={14} />
                            Подтвердить
                          </Button>
                        </>
                      )}
                  </div>
                </div>
              </Panel>
            );
          })}
        </div>
      ) : (
        <Panel>
          <Empty
            title={
              tab === "pending" ? "Всё под контролем" : "История пока пуста"
            }
            description={
              tab === "pending"
                ? "Нет запросов, ожидающих вашего подтверждения."
                : "Принятые решения будут сохранены здесь."
            }
          />
        </Panel>
      )}
      <IntentDetail
        intent={selected?.intent || null}
        close={() => setSelected(null)}
      />
    </>
  );
}
