"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Code2,
  KeyRound,
  Plus,
  Copy,
  ExternalLink,
  Play,
  Trash2,
  Globe,
  Folder,
  ArrowUpRight,
  ShieldCheck,
  Terminal,
  BookOpen,
  Activity,
  Check,
  Send,
} from "lucide-react";
import { api, date, money } from "@/lib/api";
import type {
  Page,
  Agent,
  Mandate,
  ApiKey,
  Webhook,
  Delivery,
  RequestLog,
  Intent,
  Organization,
} from "@/lib/types";
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
  CopyButton,
  Pager,
} from "./shared";
import { IntentDetail } from "./transactions";
const tabs = [
  ["", "Обзор"],
  ["projects", "Проекты"],
  ["keys", "API-ключи"],
  ["playground", "Playground"],
  ["requests", "API-запросы"],
  ["webhooks", "Webhooks"],
  ["docs", "Документация"],
  ["organizations", "Организации"],
];
export function DeveloperPortal() {
  const path = usePathname();
  const current = path.split("/")[2] || "";
  const { me } = useApp();
  if (me.role === "viewer")
    return (
      <Failure
        error={
          new Error("Раздел доступен разработчикам и владельцам организации.")
        }
      />
    );
  return (
    <>
      <PageTitle
        eyebrow="BUILD WITH AGENTPASS"
        title="Developer Portal"
        description="Интегрируйте финансовые полномочия в своего ИИ-агента."
        action={
          <Button variant="outline" asChild>
            <a href="/api/v1/docs" target="_blank" rel="noreferrer">
              <ExternalLink size={15} />
              OpenAPI
            </a>
          </Button>
        }
      />
      <div className="section-tabs">
        {tabs.map(([v, l]) => (
          <Link
            key={v}
            className={v === current ? "active" : ""}
            href={v ? `/developer/${v}` : "/developer"}
          >
            {l}
          </Link>
        ))}
      </div>
      {current === "" ? (
        <DeveloperOverview />
      ) : current === "projects" ? (
        <Projects />
      ) : current === "keys" ? (
        <Keys />
      ) : current === "playground" ? (
        <Playground />
      ) : current === "requests" ? (
        <RequestTable />
      ) : current === "webhooks" ? (
        <Webhooks />
      ) : current === "docs" ? (
        <Docs />
      ) : current === "organizations" ? (
        <Organizations />
      ) : (
        <Empty title="Раздел не найден" />
      )}
    </>
  );
}
function DeveloperOverview() {
  const keys = useResource<{ items: ApiKey[] }>("/v1/developer/api-keys");
  const projects = useResource<{ items: { id: string }[] }>(
    "/v1/developer/projects",
  );
  const logs = useResource<Page<RequestLog>>("/v1/developer/requests?limit=5");
  return (
    <>
      <div className="developer-intro">
        <span className="developer-card-icon">
          <Code2 size={25} />
        </span>
        <div>
          <h2>Три строки до безопасного действия</h2>
          <p>
            Зарегистрируйте агента, задайте мандат и отправьте Payment Intent.
            <br />
            AgentPass проверит полномочия до исполнения.
          </p>
          <Button asChild>
            <Link href="/developer/playground">
              Открыть Playground
              <ArrowUpRight size={15} />
            </Link>
          </Button>
        </div>
        <pre>
          <span>const</span> decision = <span>await</span> agentpass{".\n"}{" "}
          .createIntent(paymentIntent);{"\n\n"}
          <span>if</span> (decision.decision === <em>"APPROVE"</em>){"\n"}{" "}
          <span>await</span> agentpass.requestExecutionGrant(decision.id);
        </pre>
      </div>
      <div className="developer-quick-grid">
        {[
          [
            "API-ключи",
            `${keys.data?.items.filter((k) => !k.revoked_at).length || 0} активных ключей`,
            "keys",
            KeyRound,
          ],
          [
            "Проекты",
            `${projects.data?.items.length || 0} проектов в организации`,
            "projects",
            Folder,
          ],
          [
            "API-запросы",
            `${logs.data?.total || 0} запросов в журнале`,
            "requests",
            Activity,
          ],
        ].map(([title, description, url, Icon]) => {
          const I = Icon as typeof KeyRound;
          return (
            <Link
              key={String(title)}
              className="quick-card"
              href={"/developer/" + url}
            >
              <I size={21} />
              <h3>{String(title)}</h3>
              <p>{String(description)}</p>
              <ArrowUpRight size={16} />
            </Link>
          );
        })}
      </div>
      <Panel
        title="Последние запросы"
        action={
          <Link className="text-link" href="/developer/requests">
            Все запросы
            <ArrowUpRight size={14} />
          </Link>
        }
      >
        {logs.data?.items.length ? (
          <LogsTable items={logs.data.items} />
        ) : (
          <Empty
            title="Пока нет запросов"
            description="Запустите запрос в Playground."
          />
        )}
      </Panel>
    </>
  );
}
function Projects() {
  const q = useResource<{
    items: { id: string; name: string; created_at: string }[];
  }>("/v1/developer/projects");
  const [open, setOpen] = useState(false);
  const action = useAction<unknown, string>(
    (name) =>
      api("/v1/developer/projects", {
        method: "POST",
        body: JSON.stringify({ name }),
      }),
    "Проект создан",
  );
  return (
    <>
      <div className="page-toolbar">
        <h2>Проекты sandbox</h2>
        <Button onClick={() => setOpen(true)}>
          <Plus size={15} />
          Создать проект
        </Button>
      </div>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <Failure error={q.error} />
      ) : q.data.items.length ? (
        <div className="project-grid">
          {q.data.items.map((p) => (
            <Panel key={p.id}>
              <Folder size={23} className="accent-text" />
              <h2>{p.name}</h2>
              <p className="muted-text">Создан {date(p.created_at)}</p>
              <div className="id-box">
                <code>{p.id.slice(0, 20)}…</code>
                <CopyButton text={p.id} label="ID" />
              </div>
              <Button asChild variant="outline" size="sm">
                <Link href="/agents">
                  Зарегистрировать агента
                  <ArrowUpRight size={14} />
                </Link>
              </Button>
            </Panel>
          ))}
        </div>
      ) : (
        <Panel>
          <Empty
            title="Создайте первый проект"
            description="Группируйте агентов по интеграциям."
          />
        </Panel>
      )}
      <Modal open={open} onOpenChange={setOpen} title="Новый проект">
        <form
          className="form-stack"
          onSubmit={async (e) => {
            e.preventDefault();
            const d = new FormData(e.currentTarget);
            try {
              await action.mutateAsync(String(d.get("name")));
              setOpen(false);
            } catch {}
          }}
        >
          <label>
            Название
            <input
              name="name"
              placeholder="Shopping Sandbox"
              required
              maxLength={100}
            />
          </label>
          <div className="form-footer">
            <Button disabled={action.isPending}>Создать проект</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
function Keys() {
  const q = useResource<{ items: ApiKey[] }>("/v1/developer/api-keys");
  const agents = useResource<Page<Agent>>("/v1/agents");
  const [open, setOpen] = useState(false);
  const [secret, setSecret] = useState("");
  const [revoke, setRevoke] = useState<ApiKey | null>(null);
  const create = useAction<ApiKey, { name: string; agent_id: string; purpose:string }>((v) =>
    api("/v1/developer/api-keys", { method: "POST", body: JSON.stringify(v) }),
  );
  const remove = useAction<unknown, string>(
    (id) => api(`/v1/developer/api-keys/${id}`, { method: "DELETE" }),
    "Ключ отозван",
  );
  const rotate=useAction<ApiKey,string>(id=>api(`/v1/developer/api-keys/${id}/rotate`,{method:'POST'}),'Предыдущий ключ отозван');
  return (
    <>
      <div className="page-toolbar">
        <h2>API-ключи</h2>
        <Button onClick={() => setOpen(true)}>
          <Plus size={15} />
          Создать ключ
        </Button>
      </div>
      <div className="info-banner">
        <KeyRound size={17} />
        <span>
          Ключ привязан к одному агенту, действует 30 дней и показывается только
          один раз. В базе хранится SHA-256 хеш.
        </span>
      </div>
      <Panel>
        {q.isPending ? (
          <Loading />
        ) : q.error ? (
          <Failure error={q.error} />
        ) : q.data.items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Название</th>
                  <th>Ключ</th>
                  <th>Агент</th>
                  <th>Истекает</th>
                  <th>Статус</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {q.data.items.map((k) => (
                  <tr key={k.id}>
                    <td>
                      <strong>{k.name}</strong>
                      <small>{k.scopes.includes('payments:execute')?'Доверенный исполнитель':'Агент · без права исполнения'}</small>
                    </td>
                    <td>
                      {!k.revoked_at && new Date(k.expires_at)>new Date() && <Button size="sm" variant="outline" disabled={rotate.isPending} onClick={async()=>{try{setSecret((await rotate.mutateAsync(k.id)).secret || '');}catch{}}}>Ротация</Button>}
                      <code>{k.prefix}…</code>
                    </td>
                    <td>
                      {agents.data?.items.find((a) => a.id === k.agent_id)
                        ?.name || k.agent_id.slice(0, 8)}
                    </td>
                    <td>{date(k.expires_at)}</td>
                    <td>
                      <Badge
                        value={
                          k.revoked_at
                            ? "revoked"
                            : new Date(k.expires_at) < new Date()
                              ? "expired"
                              : "active"
                        }
                      />
                    </td>
                    <td>
                      {!k.revoked_at && (
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label={`Отозвать ${k.name}`}
                          onClick={() => setRevoke(k)}
                        >
                          <Trash2 size={16} />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="Создайте ключ для агента"
            description="Используйте Bearer-аутентификацию для запросов к API."
          />
        )}
      </Panel>
      <Modal open={open} onOpenChange={setOpen} title="Новый sandbox API-ключ">
        <form
          className="form-stack"
          onSubmit={async (e) => {
            e.preventDefault();
            const d = new FormData(e.currentTarget);
            try {
              const r = await create.mutateAsync({
                name: String(d.get("name")),
                agent_id: String(d.get("agent_id")),
                purpose: String(d.get('purpose')),
              });
              setSecret(r.secret || "");
              setOpen(false);
            } catch {}
          }}
        >
          <label>
            Название
            <input
              name="name"
              placeholder="Local integration"
              required
              maxLength={100}
            />
          </label>
          <label>
            Агент
            <select name="agent_id" required>
              <option value="">Выберите агента</option>
              {agents.data?.items.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
          <label>Назначение<select name="purpose"><option value="agent">Агент · намерения и запрос grant</option><option value="executor">Доверенный исполнитель · исполнение grant</option></select></label>
          <p className="form-help">Ключ исполнителя храните отдельно от агента и LLM. Ключи не дают права подтверждать ASK.</p>
          <div className="form-footer">
            <Button disabled={create.isPending}>Создать API-ключ</Button>
          </div>
        </form>
      </Modal>
      <SecretModal
        secret={secret}
        setSecret={setSecret}
        title="Сохраните API-ключ"
      />
      <Modal
        open={!!revoke}
        onOpenChange={() => setRevoke(null)}
        title="Отозвать API-ключ"
        description="Все следующие запросы с этим ключом будут отклонены."
      >
        <p>{revoke?.name}</p>
        <div className="form-footer">
          <Button variant="outline" onClick={() => setRevoke(null)}>
            Отмена
          </Button>
          <Button
            variant="destructive"
            disabled={remove.isPending}
            onClick={async () => {
              try {
                await remove.mutateAsync(revoke!.id);
                setRevoke(null);
              } catch {}
            }}
          >
            Отозвать ключ
          </Button>
        </div>
      </Modal>
    </>
  );
}
function SecretModal({
  secret,
  setSecret,
  title,
}: {
  secret: string;
  setSecret: (s: string) => void;
  title: string;
}) {
  return (
    <Modal
      open={!!secret}
      onOpenChange={() => setSecret("")}
      title={title}
      description="Секрет показывается один раз. Скопируйте его в защищённое хранилище."
    >
      <div className="secret-box">
        <code>{secret}</code>
      </div>
      <div className="form-footer">
        <CopyButton text={secret} />
        <Button onClick={() => setSecret("")}>Сохранён</Button>
      </div>
    </Modal>
  );
}
function Playground() {
  const mandates = useResource<Page<Mandate>>("/v1/mandates");
  const [mandate, setMandate] = useState("");
  const [amount, setAmount] = useState(8000);
  const [body, setBody] = useState("");
  const [mode, setMode] = useState("preview");
  const [key, setKey] = useState("");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const { notify } = useApp();
  const [selected, setSelected] = useState<Intent | null>(null);
  const m = mandates.data?.items.find((x) => x.id === mandate);
  useEffect(() => {
    if (!mandate && mandates.data?.items[0])
      setMandate(mandates.data.items[0].id);
  }, [mandates.data, mandate]);
  function generate() {
    if (!m) return;
    setBody(
      JSON.stringify(
        {
          agent_id: m.agent_id,
          mandate_id: m.id,
          merchant: "Soundstore",
          category: "electronics",
          amount: Math.round(amount * 100),
          currency: m.currency,
          description: "Playground payment intent",
          idempotency_key: crypto.randomUUID(),
          timestamp: new Date().toISOString(),
          structured_metadata: { source: "playground" },
        },
        null,
        2,
      ),
    );
  }
  useEffect(() => {
    generate();
  }, [mandate, amount]);
  const action = useAction<Record<string, unknown>, Record<string, unknown>>(
    (v) =>
      api(mode === "preview" ? "/v1/evaluations/preview" : "/v1/intents", {
        method: "POST",
        body: JSON.stringify(v),
        ...(key ? { headers: { Authorization: `Bearer ${key}` } } : {}),
      }),
  );
  async function submit() {
    try {
      const value = JSON.parse(body);
      const r = await action.mutateAsync(value);
      setResult(r);
    } catch (e) {
      if (e instanceof SyntaxError)
        notify("JSON содержит синтаксическую ошибку", true);
    }
  }
  return (
    <div className="playground-grid">
      <Panel
        title="Запрос"
        description="Все проверки выполняются настоящим backend"
      >
        <div className="form-stack padded">
          <div className="form-grid">
            <label>
              Мандат
              <select
                value={mandate}
                onChange={(e) => setMandate(e.target.value)}
              >
                {mandates.data?.items.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} · v{m.version}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Сумма, ₽
              <input
                type="number"
                min={1}
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
              />
            </label>
          </div>
          <div className="segmented">
            <button
              className={mode === "preview" ? "selected" : ""}
              onClick={() => {
                setMode("preview");
                setResult(null);
              }}
            >
              Проверка правил
            </button>
            <button
              className={mode === "create" ? "selected" : ""}
              onClick={() => {
                setMode("create");
                setResult(null);
              }}
            >
              Создать Intent
            </button>
          </div>
          <div className="endpoint">
            <span>POST</span>
            <code>
              {mode === "preview" ? "/v1/evaluations/preview" : "/v1/intents"}
            </code>
          </div>
          <label>
            JSON body
            <textarea
              className="code-editor"
              spellCheck={false}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={17}
            />
          </label>
          {mode === "create" && (
            <label>
              Bearer API-ключ (необязательно)
              <input
                type="password"
                value={key}
                autoComplete="off"
                onChange={(e) => setKey(e.target.value)}
                placeholder="Пусто — пользовательская сессия"
              />
            </label>
          )}
          <div className="playground-actions">
            <Button variant="outline" onClick={generate}>
              Новый idempotency key
            </Button>
            <Button disabled={!m || action.isPending} onClick={submit}>
              <Play size={15} />
              {action.isPending ? "Проверяем…" : "Отправить запрос"}
            </Button>
          </div>
          <p className="form-help">
            Проверка правил не создаёт операцию или резерв. «Создать Intent»
            сохраняет намерение и резервирует бюджет при APPROVE.
          </p>
        </div>
      </Panel>
      <Panel
        title="Ответ сервера"
        action={result && <Badge value={String(result.decision)} />}
      >
        {result ? (
          <div className="padded">
            <pre className="json-output">{JSON.stringify(result, null, 2)}</pre>
            <CopyButton text={JSON.stringify(result, null, 2)} />
            {typeof result.id === "string" && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelected(result as unknown as Intent)}
              >
                Детали и исполнение
                <ArrowUpRight size={14} />
              </Button>
            )}
          </div>
        ) : action.error ? (
          <div className="padded">
            <Failure error={action.error} />
          </div>
        ) : (
          <Empty
            title="Готов к проверке"
            description="Отправьте запрос, чтобы увидеть решение и объяснение правил."
          />
        )}
      </Panel>
      <IntentDetail intent={selected} close={() => setSelected(null)} />
    </div>
  );
}
export function RequestTable({ admin = false }: { admin?: boolean }) {
  const [offset, setOffset] = useState(0);
  const q = useResource<Page<RequestLog>>(
    `/v1/${admin ? "admin" : "developer"}/requests?limit=20&offset=${offset}`,
    10000,
  );
  return (
    <Panel
      title="Журнал API-запросов"
      description="Без содержимого запросов, ключей и чувствительных данных"
    >
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <Failure error={q.error} />
      ) : q.data.items.length ? (
        <>
          <LogsTable items={q.data.items} />
          <Pager
            total={q.data.total}
            offset={offset}
            limit={20}
            setOffset={setOffset}
          />
        </>
      ) : (
        <Empty description="Запросы появятся после обращения к API." />
      )}
    </Panel>
  );
}
function LogsTable({ items }: { items: RequestLog[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Метод</th>
            <th>Endpoint</th>
            <th>Статус</th>
            <th>Время</th>
            <th>Request ID</th>
            <th>Дата</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.id}>
              <td>
                <span className="method-badge">{r.method}</span>
              </td>
              <td>
                <code>{r.path}</code>
              </td>
              <td>
                <span
                  className={`badge ${r.status_code < 400 ? "success" : "danger"}`}
                >
                  {r.status_code}
                </span>
              </td>
              <td>{r.duration_ms} ms</td>
              <td>
                <code>{r.request_id.slice(0, 8)}</code>
              </td>
              <td className="muted-text">{date(r.created_at, true)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Webhooks() {
  const config = useResource<{ sandbox_receiver_url: string | null }>(
    "/v1/webhooks/config",
  );
  const receipts = useResource<{
    items: { id: string; event: string; created_at: string }[];
  }>("/v1/webhooks/receipts", 5000);
  const [url, setUrl] = useState("");
  const q = useResource<{ items: Webhook[] }>("/v1/webhooks");
  const deliveries = useResource<Page<Delivery>>(
    "/v1/webhooks/deliveries?limit=20",
    5000,
  );
  const [open, setOpen] = useState(false);
  const [secret, setSecret] = useState("");
  const create = useAction<Webhook, { name: string; url: string }>((v) =>
    api("/v1/webhooks", { method: "POST", body: JSON.stringify(v) }),
  );
  const disable = useAction<unknown, string>(
    (id) => api(`/v1/webhooks/${id}`, { method: "DELETE" }),
    "Endpoint отключён",
  );
  const rotate=useAction<Webhook,string>(id=>api(`/v1/webhooks/${id}/rotate-secret`,{method:'POST'}));
  const test = useAction<unknown, string>(
    (id) => api(`/v1/webhooks/${id}/test`, { method: "POST" }),
    "Тестовое событие поставлено в очередь",
  );
  return (
    <>
      <div className="page-toolbar">
        <h2>Webhook endpoints</h2>
        <Button onClick={() => setOpen(true)}>
          <Plus size={15} />
          Добавить endpoint
        </Button>
      </div>
      <div className="info-banner">
        <ShieldCheck size={17} />
        <span>
          HTTPS · HMAC-SHA256 · 5 попыток с увеличением интервала · защита от
          локальных адресов
        </span>
      </div>
      <Panel>
        {q.isPending ? (
          <Loading />
        ) : q.error ? (
          <Failure error={q.error} />
        ) : q.data.items.length ? (
          <div className="webhook-list">
            {q.data.items.map((w) => (
              <div key={w.id}>
                <span className="agent-icon">
                  <Globe size={21} />
                </span>
                <div>
                  <strong>{w.name}</strong>
                  <code>{w.url}</code>
                </div>
                <Badge value={w.active ? "active" : "disabled"} />
                {w.active && (
                  <>
                    <Button variant="outline" size="sm" disabled={rotate.isPending} onClick={async()=>{try{setSecret((await rotate.mutateAsync(w.id)).secret || '');}catch{}}}>Сменить секрет</Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={test.isPending}
                      onClick={() => test.mutate(w.id)}
                    >
                      <Send size={13} />
                      Тест
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      disabled={disable.isPending}
                      aria-label="Отключить endpoint"
                      onClick={() => disable.mutate(w.id)}
                    >
                      <Trash2 size={16} />
                    </Button>
                  </>
                )}
              </div>
            ))}
          </div>
        ) : (
          <Empty
            title="Подключите события к вашему сервису"
            description="Получайте решения, подтверждения и результаты симулированных покупок."
          />
        )}
      </Panel>
      <Panel title="Доставки" description="История попыток и диагностика HTTP">
        {deliveries.error ? (
          <Failure error={deliveries.error} />
        ) : deliveries.data?.items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Delivery ID</th>
                  <th>Статус</th>
                  <th>Попытки</th>
                  <th>HTTP</th>
                  <th>Диагностика</th>
                  <th>Дата</th>
                </tr>
              </thead>
              <tbody>
                {deliveries.data.items.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <code>{d.id.slice(0, 8)}</code>
                    </td>
                    <td>
                      <Badge value={d.status} />
                    </td>
                    <td>{d.attempts} / 5</td>
                    <td>{d.response_status || "—"}</td>
                    <td>{d.last_error || "—"}</td>
                    <td>{date(d.created_at, true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty description="Создайте endpoint и отправьте тестовое событие." />
        )}
      </Panel>
      <Modal
        open={open}
        onOpenChange={setOpen}
        title="Добавить webhook endpoint"
      >
        <form
          className="form-stack"
          onSubmit={async (e) => {
            e.preventDefault();
            const d = new FormData(e.currentTarget);
            try {
              const r = await create.mutateAsync({
                name: String(d.get("name")),
                url: String(d.get("url")),
              });
              setSecret(r.secret || "");
              setOpen(false);
            } catch {}
          }}
        >
          <label>
            Название
            <input name="name" required maxLength={100} />
          </label>
          <label>
            Публичный HTTPS URL
            <input
              type="url"
              name="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/agentpass/webhook"
              required
            />
          </label>
          {config.data?.sandbox_receiver_url && (
            <Button
              type="button"
              variant="outline"
              onClick={() => setUrl(config.data!.sandbox_receiver_url!)}
            >
              Использовать локальный receiver
            </Button>
          )}
          <p className="form-help">
            Публичные endpoints: HTTPS, без приватных IP и redirects. Исключение
            sandbox — фиксированный локальный receiver с проверкой подписи.
          </p>
          <div className="form-footer">
            <Button disabled={create.isPending}>Добавить endpoint</Button>
          </div>
        </form>
      </Modal>
      <SecretModal
        secret={secret}
        setSecret={setSecret}
        title="Сохраните секрет подписи"
      />
      {!!receipts.data?.items.length && (
        <Panel
          title="Получено sandbox receiver"
          description="Настоящие HTTP-запросы с проверенной HMAC-подписью"
        >
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Delivery ID</th>
                  <th>Событие</th>
                  <th>Подпись</th>
                  <th>Дата</th>
                </tr>
              </thead>
              <tbody>
                {receipts.data.items.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <code>{r.id.slice(0, 8)}</code>
                    </td>
                    <td>{r.event}</td>
                    <td>
                      <Badge value="APPROVE" />
                    </td>
                    <td>{date(r.created_at, true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </>
  );
}
function Organizations() {
  const { me } = useApp();
  const [open, setOpen] = useState(false);
  const [memberOpen, setMemberOpen] = useState(false);
  const create = useAction<unknown, string>(
    (name) =>
      api("/v1/organizations", {
        method: "POST",
        body: JSON.stringify({ name }),
      }),
    "Организация создана. Выберите её в меню пространства.",
  );
  const members = useResource<{
    items: { id: string; name: string; email: string; role: string }[];
  }>("/v1/organizations/members");
  const add = useAction<unknown, { email: string; role: string }>(
    (v) =>
      api("/v1/organizations/members", {
        method: "POST",
        body: JSON.stringify(v),
      }),
    "Участник добавлен",
  );
  const remove = useAction<unknown, string>(
    (id) => api(`/v1/organizations/members/${id}`, { method: "DELETE" }),
    "Участник удалён",
  );
  return (
    <>
      <div className="page-toolbar">
        <h2>Ваши организации</h2>
        <Button onClick={() => setOpen(true)}>
          <Plus size={15} />
          Создать организацию
        </Button>
      </div>
      <Panel>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Организация</th>
                <th>Ваша роль</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {me.organizations.map((o) => (
                <tr key={o.id}>
                  <td>
                    <strong>{o.name}</strong>
                    {o.id === me.organization_id && (
                      <span className="badge muted">Текущая</span>
                    )}
                  </td>
                  <td>
                    {o.role === "owner"
                      ? "Владелец"
                      : o.role === "developer"
                        ? "Разработчик"
                        : "Наблюдатель"}
                  </td>
                  <td>
                    <Badge value={o.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      {me.role === "owner" && (
        <Panel
          title="Участники текущей организации"
          description="Пользователь должен сначала зарегистрироваться"
          action={
            <Button
              variant="outline"
              size="sm"
              onClick={() => setMemberOpen(true)}
            >
              <Plus size={14} />
              Добавить
            </Button>
          }
        >
          {members.error ? (
            <Failure error={members.error} />
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Пользователь</th>
                    <th>Email</th>
                    <th>Роль</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {members.data?.items.map((m) => (
                    <tr key={m.id}>
                      <td>{m.name}</td>
                      <td>{m.email}</td>
                      <td>{m.role}</td>
                      <td>
                        {m.role !== "owner" && (
                          <Button
                            size="icon"
                            variant="ghost"
                            aria-label="Удалить участника"
                            disabled={remove.isPending}
                            onClick={() => remove.mutate(m.id)}
                          >
                            <Trash2 size={15} />
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      )}
      <Modal open={open} onOpenChange={setOpen} title="Новая организация">
        <form
          className="form-stack"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await create.mutateAsync(
                String(new FormData(e.currentTarget).get("name")),
              );
              setOpen(false);
            } catch {}
          }}
        >
          <label>
            Название
            <input name="name" required maxLength={100} />
          </label>
          <div className="form-footer">
            <Button disabled={create.isPending}>Создать</Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={memberOpen}
        onOpenChange={setMemberOpen}
        title="Добавить участника"
      >
        <form
          className="form-stack"
          onSubmit={async (e) => {
            e.preventDefault();
            const d = new FormData(e.currentTarget);
            try {
              await add.mutateAsync({
                email: String(d.get("email")),
                role: String(d.get("role")),
              });
              setMemberOpen(false);
            } catch {}
          }}
        >
          <label>
            Email зарегистрированного пользователя
            <input type="email" name="email" required />
          </label>
          <label>
            Роль
            <select name="role">
              <option value="developer">Разработчик</option>
              <option value="viewer">Наблюдатель</option>
            </select>
          </label>
          <p className="form-help">
            Финансовые полномочия и операции изолированы по владельцу. Членство
            не открывает чужие мандаты.
          </p>
          <div className="form-footer">
            <Button disabled={add.isPending}>Добавить</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
function Docs() {
  const [lang, setLang] = useState("typescript");
  const code =
    lang === "typescript"
      ? `import { AgentPass } from '@agentpass/sdk';\n\nconst ap = new AgentPass({\n  baseUrl: 'http://localhost:8000',\n  apiKey: process.env.AGENTPASS_API_KEY!,\n});\n\nconst intent = await ap.createIntent({\n  agent_id: 'YOUR_AGENT_ID',\n  mandate_id: 'YOUR_MANDATE_ID',\n  merchant: 'Soundstore',\n  category: 'electronics',\n  amount: 800000, // 8 000 ₽ в копейках\n  currency: 'RUB',\n  description: 'Soundcore Life Q30',\n  idempotency_key: crypto.randomUUID(),\n  timestamp: new Date().toISOString(),\n  structured_metadata: {},\n});\n\nif (intent.decision === 'APPROVE') {\n  const grant = await ap.requestExecutionGrant(intent.id);\n  // Отдельный доверенный компонент, не LLM:\n  const executor = new AgentPass({baseUrl: 'http://localhost:8000',\n    apiKey: process.env.AGENTPASS_EXECUTOR_KEY!});\n  const operation = await executor.submitExecution(grant.grant_token);\n  // Poll executor.getExecution(operation.id); success только от provider\n}\n// ASK: waitForDecision(id), затем grant + trusted executor\n// DENY: reasons содержит объяснение`
      : `import os, uuid, datetime, httpx\n\nclient = httpx.Client(\n    base_url='http://localhost:8000',\n    headers={'Authorization': 'Bearer ' +\n             os.environ['AGENTPASS_API_KEY']},\n)\nresponse = client.post('/v1/intents', json={\n    'agent_id': 'YOUR_AGENT_ID',\n    'mandate_id': 'YOUR_MANDATE_ID',\n    'merchant': 'Soundstore',\n    'category': 'electronics',\n    'amount': 800000,\n    'currency': 'RUB',\n    'description': 'Soundcore Life Q30',\n    'idempotency_key': str(uuid.uuid4()),\n    'timestamp': datetime.datetime.now(\n        datetime.timezone.utc).isoformat(),\n    'structured_metadata': {},\n})\nresponse.raise_for_status()\nintent = response.json()\nif intent['decision'] == 'APPROVE':\n    client.post('/v1/intents/' + intent['id']\n                + '/execute').raise_for_status()`;
  return (
    <div className="docs-layout">
      <div>
        <Panel title="Быстрый старт" description="Sandbox API v1">
          <div className="docs-content">
            <ol>
              <li>
                <strong>Зарегистрируйте агента</strong>
                <p>Создайте идентичность в разделе «Мои агенты».</p>
              </li>
              <li>
                <strong>Создайте мандат</strong>
                <p>Задайте лимиты, категории, продавцов и порог согласия.</p>
              </li>
              <li>
                <strong>Выпустите API-ключ</strong>
                <p>Ключ привязан к агенту и имеет ограниченный срок.</p>
              </li>
              <li>
                <strong>Отправьте Payment Intent</strong>
                <p>
                  Сначала получите решение. Исполняйте покупку отдельным
                  запросом.
                </p>
              </li>
            </ol>
            <div className="info-banner">
              <ShieldCheck size={17} />
              <span>
                Идемпотентный повтор требует идентичного body, включая
                timestamp. ASK не резервирует бюджет.
              </span>
            </div>
            <Button asChild variant="outline">
              <a href="/api/v1/openapi.json" target="_blank" rel="noreferrer">
                Схема OpenAPI
                <ExternalLink size={14} />
              </a>
            </Button>
          </div>
        </Panel>
        <Panel title="Решения и жизненный цикл">
          <div className="docs-content">
            {[
              [
                "APPROVE",
                "Создан логический резерв. Выпустите короткий grant и передайте отдельному доверенному исполнителю; разрешение ещё не платёж.",
              ],
              [
                "ASK",
                "Подтверждение действительно 15 минут. После согласия правила и бюджеты проверяются заново.",
              ],
              [
                "DENY",
                "Бюджет не зарезервирован. Причины отказа возвращаются в reasons.",
              ],
            ].map(([d, t]) => (
              <div className="doc-decision" key={d}>
                <Badge value={d} />
                <p>{t}</p>
              </div>
            ))}
            <p>
              Отмена освобождает резерв. Повторное исполнение возвращает прежний
              результат. Повторное подтверждение возвращает 409.
            </p>
          </div>
        </Panel>
      </div>
      <Panel title="Пример интеграции" action={<CopyButton text={code} />}>
        <div className="code-tabs">
          <button
            className={lang === "typescript" ? "active" : ""}
            onClick={() => setLang("typescript")}
          >
            TypeScript SDK
          </button>
          <button
            className={lang === "python" ? "active" : ""}
            onClick={() => setLang("python")}
          >
            Python
          </button>
        </div>
        <pre className="integration-code">{code}</pre>
      </Panel>
    </div>
  );
}
