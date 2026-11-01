"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Send,
  ArrowRight,
  Check,
  ShieldCheck,
  Clock,
  X,
  Headphones,
  Terminal,
  Plus,
  RotateCcw,
  Info,
} from "lucide-react";
import { api, money } from "@/lib/api";
import type {
  Page,
  Mandate,
  Product,
  ConsoleResult,
  Intent,
} from "@/lib/types";
import { useResource, useAction, useApp } from "./context";
import { Button } from "./ui/button";
import { PageTitle, Panel, Badge, Loading, Failure, Empty } from "./shared";
export function AgentConsole() {
  const mandates = useResource<Page<Mandate>>("/v1/mandates");
  const catalog = useResource<{ items: Product[] }>("/v1/catalog");
  const [mandate, setMandate] = useState("");
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState<ConsoleResult | null>(null);
  const { me } = useApp();
  const active =
    mandates.data?.items.filter(
      (m) =>
        m.status === "active" &&
        new Date(m.valid_from) <= new Date() &&
        new Date(m.valid_until) > new Date(),
    ) || [];
  useEffect(() => {
    if (!mandate && active[0]) setMandate(active[0].id);
  }, [mandates.data, mandate]);
  const run = useAction<
    ConsoleResult,
    { prompt: string; mandate_id: string; idempotency_key: string }
  >((v) => api("/v1/console/run", { method: "POST", body: JSON.stringify(v) }));
  const demo = useAction<{ mandate: Mandate }, void>(
    () => api("/v1/sandbox/demo", { method: "POST" }),
    "Созданы новый агент и мандат с независимым бюджетом",
  );
  const m = active.find((x) => x.id === mandate);
  async function submit(text: string) {
    if (!mandate) return;
    setPrompt(text);
    setResult(null);
    try {
      const r = await run.mutateAsync({
        prompt: text,
        mandate_id: mandate,
        idempotency_key: crypto.randomUUID(),
      });
      setResult(r);
    } catch {}
  }
  return (
    <>
      <PageTitle
        eyebrow="ИНТЕРАКТИВНЫЙ SANDBOX"
        title="Agent Console"
        description="Покупка на естественном языке. Каждое решение принимает настоящий Policy Engine."
        action={
          me.role !== "viewer" && ['sandbox','development'].includes(me.environment) && (
            <Button
              variant="outline"
              disabled={demo.isPending}
              onClick={async () => {
                try {
                  const r = await demo.mutateAsync();
                  setMandate(r.mandate.id);
                  setResult(null);
                } catch {}
              }}
            >
              <Plus size={15} />
              Новый демо-бюджет
            </Button>
          )
        }
      />
      <div className="console-layout">
        <Panel className="console-main">
          <div className="console-agent-bar">
            <span className="agent-icon">
              <Bot size={22} />
            </span>
            <div>
              <strong>Personal Shopping Assistant</strong>
              <small>Детерминированный каталог · симуляция платежей</small>
            </div>
            <span className="badge muted">DEMO</span>
          </div>
          <div className="console-conversation">
            <div className="agent-message">
              <Bot size={17} />
              <div>
                <strong>Готов помочь с покупкой.</strong>
                <p>
                  Укажите товар и бюджет. Я подберу вариант из каталога, проверю
                  полномочия и выполню разрешённую симуляцию.
                </p>
                <div className="prompt-suggestions">
                  {[
                    ["8 000", "Купи наушники до 8 000 рублей"],
                    ["12 000", "Купи наушники до 12 000 рублей"],
                    ["18 000", "Купи наушники до 18 000 рублей"],
                  ].map(([price, text]) => (
                    <button
                      key={price}
                      disabled={!m || run.isPending || me.role === "viewer"}
                      onClick={() => submit(text)}
                    >
                      Наушники до {price} ₽<ArrowUpRightIcon />
                    </button>
                  ))}
                </div>
              </div>
            </div>
            {run.isPending && (
              <div className="console-running">
                <Loading />
                <p>Каталог → Payment Intent → Policy Engine</p>
              </div>
            )}
            {run.error && <Failure error={run.error} />}{" "}
            {result && <div className="user-message">{prompt}</div>}
            {result && (
              <ConsoleResultView key={result.intent.id} result={result} />
            )}
          </div>
          <form
            className="console-input"
            onSubmit={(e) => {
              e.preventDefault();
              submit(prompt);
            }}
          >
            <input
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Купи мне наушники до 15 000 рублей…"
              aria-label="Запрос агенту"
              minLength={2}
              maxLength={1000}
              required
              disabled={me.role === "viewer"}
            />
            <Button
              size="icon"
              aria-label="Отправить запрос"
              disabled={!m || run.isPending || me.role === "viewer"}
            >
              <Send size={17} />
            </Button>
          </form>
          <div className="console-disclaimer">
            <ShieldCheck size={12} />
            Агент не принимает финансовые решения. Это делает Policy Engine.
          </div>
        </Panel>
        <div className="console-side">
          <Panel title="Активные полномочия" action={<ShieldCheck size={18} />}>
            <label className="mandate-select">
              Мандат
              <select
                value={mandate}
                onChange={(e) => {
                  setMandate(e.target.value);
                  setResult(null);
                }}
              >
                <option value="">Выберите мандат</option>
                {active.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name} · {x.agent_name}
                  </option>
                ))}
              </select>
            </label>
            {m ? (
              <>
                <div className="console-rules">
                  <div>
                    <span>Одна операция</span>
                    <strong>{money(m.per_transaction)}</strong>
                  </div>
                  <div>
                    <span>Дневной бюджет</span>
                    <strong>{money(m.daily_limit)}</strong>
                  </div>
                  <div>
                    <span>Использовано сегодня</span>
                    <strong>{money(m.usage.daily)}</strong>
                  </div>
                  <div>
                    <span>Подтверждение от</span>
                    <strong>{money(m.approval_threshold)}</strong>
                  </div>
                  <div>
                    <span>Категория</span>
                    <strong>{m.categories.join(", ")}</strong>
                  </div>
                </div>
                <Link className="text-link" href="/mandates">
                  Изменить полномочия
                  <ArrowRight size={14} />
                </Link>
              </>
            ) : (
              <Empty
                title="Нет активного мандата"
                description="Создайте полномочия или новый демо-бюджет."
              />
            )}
          </Panel>
          <Panel title="Тестовый каталог">
            <div className="catalog-list">
              {catalog.data?.items.map((p) => (
                <button
                  key={p.id}
                  disabled={!m || run.isPending || me.role === "viewer"}
                  onClick={() =>
                    submit(
                      `Купи ${p.id === "logitech-mx" ? "мышь" : "наушники"} до ${p.amount / 100} рублей`,
                    )
                  }
                >
                  <div
                    className="catalog-product"
                    style={{ background: p.color }}
                  >
                    <Headphones size={21} />
                  </div>
                  <div>
                    <strong>{p.name}</strong>
                    <small>{p.merchant}</small>
                  </div>
                  <span>{money(p.amount)}</span>
                </button>
              ))}
            </div>
          </Panel>
          <div className="console-info">
            <Info size={16} />
            <p>
              Каталог тестовый. Интерпретатор использует названия товаров и
              бюджет, без внешнего LLM. Реальных списаний нет.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
function ArrowUpRightIcon() {
  return <ArrowRight size={13} />;
}
function ConsoleResultView({ result }: { result: ConsoleResult }) {
  const client = useQueryClient();
  const { me } = useApp();
  const q = useQuery<Intent>({
    queryKey: [me.organization_id, "console-intent", result.intent.id],
    queryFn: () => api(`/v1/intents/${result.intent.id}`),
    initialData: result.intent,
    refetchInterval: (query) =>
      query.state.data?.status === "pending" ||
      query.state.data?.status === "authorized"
        ? 2000
        : false,
  });
  const [attempted, setAttempted] = useState(false);
  const execute = useAction<Intent, void>(() =>
    api(`/v1/intents/${result.intent.id}/execute`, { method: "POST" }),
  );
  const i = q.data;
  useEffect(() => {
    if (i.status === "authorized" && !attempted && ['sandbox','development'].includes(me.environment)) {
      setAttempted(true);
      execute
        .mutateAsync()
        .then((data) =>
          client.setQueryData(
            [me.organization_id, "console-intent", result.intent.id],
            data,
          ),
        )
        .catch(() => {});
    }
  }, [i.status, attempted]);
  return (
    <div className="agent-message result-message">
      <Bot size={17} />
      <div>
        <div className="result-product">
          <span
            className="catalog-product"
            style={{ background: result.product.color }}
          >
            <Headphones size={25} />
          </span>
          <div>
            <strong>{result.product.name}</strong>
            <small>{result.product.details}</small>
          </div>
          <strong>{money(result.product.amount)}</strong>
        </div>
        <div className="execution-steps">
          <div>
            <Check size={13} />
            <span>Намерение распознано</span>
            <small>Бюджет {money(result.interpreted_budget)}</small>
          </div>
          <div>
            <Check size={13} />
            <span>Payment Intent создан</span>
            <small>{i.id.slice(0, 8)}</small>
          </div>
          <div>
            <Check size={13} />
            <span>Policy Engine · v{i.evaluated_version}</span>
            <Badge value={i.decision} />
          </div>
          <div>
            {i.status === "completed" ? (
              <Check size={13} />
            ) : i.status === "pending" ? (
              <Clock size={13} />
            ) : (
              <X size={13} />
            )}
            <span>
              {i.status === "completed"
                ? "Покупка симулирована"
                : i.status === "pending"
                  ? "Ожидаю вашего согласия"
                  : i.status === "authorized"
                    ? (['sandbox','development'].includes(me.environment) ? "Выполняю симуляцию" : "Разрешено · ожидает доверенного исполнителя")
                    : "Операция не исполнена"}
            </span>
          </div>
        </div>
        <div className={`result-explanation ${i.decision.toLowerCase()}`}>
          {i.reasons.map((r) => (
            <p key={r.code}>{r.message}</p>
          ))}
          {i.status === "completed" && (
            <small>
              Сохранён чек {i.transaction?.receipt.slice(0, 20)}… Реальных
              списаний нет.
            </small>
          )}
          {i.status === "pending" && (
            <Button variant="outline" size="sm" asChild>
              <Link href="/approvals" target="_blank">
                Открыть подтверждения
                <ArrowRight size={14} />
              </Link>
            </Button>
          )}
        </div>
        {q.error && <Failure error={q.error} />}{" "}
        {execute.error && <Failure error={execute.error} />}
      </div>
    </div>
  );
}
