"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ShieldCheck,
  KeyRound,
  Monitor,
  LogOut,
  Clock,
  User,
  Save,
  Check,
  Lock,
  Activity,
  Server,
  Globe,
  Database,
  Plus,
  ArrowUpRight,
  AlertCircle,
} from "lucide-react";
import { api, date } from "@/lib/api";
import type { Page, Audit, Organization } from "@/lib/types";
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
} from "./shared";
import { RequestTable } from "./developer";
export function SecurityPage() {
  const [password, setPassword] = useState(false);
  const sessions = useResource<{
    items: {
      id: string;
      created_at: string;
      expires_at: string;
      current: boolean;
    }[];
  }>("/v1/security/sessions");
  const [offset, setOffset] = useState(0);
  const audits = useResource<Page<Audit>>(
    `/v1/audit-events?limit=12&offset=${offset}`,
  );
  const router = useRouter();
  const revoke = useAction<unknown, string>(
    (id) => api(`/v1/security/sessions/${id}`, { method: "DELETE" }),
    "Сессия отозвана",
  );
  const change = useAction<
    unknown,
    { current_password: string; new_password: string }
  >(
    (v) =>
      api("/v1/security/password", { method: "POST", body: JSON.stringify(v) }),
    "Пароль изменён. Остальные сессии отозваны.",
  );
  return (
    <>
      <PageTitle
        title="Безопасность"
        description="Контролируйте сессии, учётные данные и журнал действий."
      />
      <div className="security-grid">
        <Panel
          title="Защита аккаунта"
          description="Серверная авторизация и принцип минимальных привилегий"
        >
          <div className="security-control">
            <span className="agent-icon">
              <KeyRound size={21} />
            </span>
            <div>
              <strong>Пароль</strong>
              <small>Хеширование scrypt с индивидуальной солью</small>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPassword(true)}
            >
              Изменить
            </Button>
          </div>
          <div className="security-control">
            <span className="agent-icon">
              <Lock size={21} />
            </span>
            <div>
              <strong>Защита сессии</strong>
              <small>HttpOnly · SameSite · CSRF token</small>
            </div>
            <Badge value="active" />
          </div>
          <div className="security-control">
            <span className="agent-icon">
              <ShieldCheck size={21} />
            </span>
            <div>
              <strong>Доступ агентов</strong>
              <small>Изолированные API-ключи с ограниченным сроком</small>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/developer/keys")}
            >
              Ключи
            </Button>
          </div>
        </Panel>
        <Panel
          title="Активные сессии"
          description="Сессия действует не более 12 часов"
        >
          {sessions.isPending ? (
            <Loading />
          ) : sessions.error ? (
            <Failure error={sessions.error} />
          ) : (
            sessions.data.items.map((s) => (
              <div className="session-row" key={s.id}>
                <Monitor size={21} />
                <div>
                  <strong>
                    {s.current ? "Текущая сессия" : "Другая сессия"}
                  </strong>
                  <small>Создана {date(s.created_at, true)}</small>
                  <small>Истекает {date(s.expires_at, true)}</small>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={revoke.isPending}
                  onClick={() => revoke.mutate(s.id)}
                >
                  <LogOut size={14} />
                  Завершить
                </Button>
              </div>
            ))
          )}
        </Panel>
      </div>
      <MFASettings />
      <AuditTable q={audits} offset={offset} setOffset={setOffset} limit={12} />
      <Modal
        open={password}
        onOpenChange={setPassword}
        title="Изменить пароль"
        description="После смены пароля остальные сессии будут завершены."
      >
        <form
          className="form-stack"
          onSubmit={async (e) => {
            e.preventDefault();
            const d = new FormData(e.currentTarget);
            try {
              await change.mutateAsync({
                current_password: String(d.get("current_password")),
                new_password: String(d.get("new_password")),
              });
              setPassword(false);
            } catch {}
          }}
        >
          <label>
            Текущий пароль
            <input
              type="password"
              name="current_password"
              autoComplete="current-password"
              required
            />
          </label>
          <label>
            Новый пароль
            <input
              type="password"
              name="new_password"
              minLength={12}
              maxLength={128}
              autoComplete="new-password"
              required
            />
          </label>
          <p className="form-help">Не менее 12 символов.</p>
          <div className="form-footer">
            <Button disabled={change.isPending}>Изменить пароль</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
function MFASettings() {
  const state=useResource<{enabled:boolean}>('/v1/security/mfa');
  const [enrollment,setEnrollment]=useState<{secret:string;provisioning_uri:string}|null>(null);
  const enroll=useAction<{secret:string;provisioning_uri:string},string>(password=>api('/v1/security/mfa/enroll',{method:'POST',body:JSON.stringify({password})}));
  const confirm=useAction<unknown,string>(code=>api('/v1/security/mfa/confirm',{method:'POST',body:JSON.stringify({code})}),'MFA подключена. Дождитесь следующего кода перед новым действием.');
  return <Panel title="Двухфакторная аутентификация" description="TOTP · одноразовый код для входа и чувствительных действий">
    <div className="padded">
      {state.isPending ? <Loading /> : state.error ? <Failure error={state.error} /> : state.data.enabled ? <p>Приложение-аутентификатор подключено. Автоматического сброса MFA нет: восстановление требует проверки владельца оператором.</p> : enrollment ? <>
        <p>Добавьте запись AgentPass в приложение-аутентификатор. Сохраните секрет в защищённом месте.</p>
        <div className="secret-box"><code>{enrollment.secret}</code></div>
        <form className="form-stack" onSubmit={async e=>{e.preventDefault();const code=String(new FormData(e.currentTarget).get('code'));try{await confirm.mutateAsync(code);setEnrollment(null);}catch{}}}>
          <label>Код из приложения<input name="code" inputMode="numeric" pattern="[0-9]{6}" autoComplete="one-time-code" required /></label>
          <div className="form-footer"><Button disabled={confirm.isPending}>Подключить MFA</Button></div>
        </form>
      </> : <form className="form-stack" onSubmit={async e=>{e.preventDefault();const password=String(new FormData(e.currentTarget).get('password'));try{setEnrollment(await enroll.mutateAsync(password));}catch{}}}>
        <label>Текущий пароль<input type="password" name="password" autoComplete="current-password" required /></label>
        <div className="form-footer"><Button disabled={enroll.isPending}>Настроить MFA</Button></div>
      </form>}
    </div>
  </Panel>;
}
export function SettingsPage() {
  const { me } = useApp();
  const save = useAction<unknown, string>(
    (name) =>
      api("/v1/settings/profile", {
        method: "PATCH",
        body: JSON.stringify({ name }),
      }),
    "Профиль обновлён",
  );
  const router = useRouter();
  return (
    <>
      <PageTitle
        title="Настройки"
        description="Профиль и параметры рабочего пространства."
      />
      <div className="settings-layout">
        <Panel title="Профиль" description="Ваше имя отображается в интерфейсе">
          <form
            className="form-stack padded"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate(String(new FormData(e.currentTarget).get("name")));
            }}
          >
            <div className="profile-avatar">
              {me.user.name
                .split(" ")
                .map((x) => x[0])
                .slice(0, 2)
                .join("")}
            </div>
            <label>
              Имя
              <input
                name="name"
                defaultValue={me.user.name}
                required
                maxLength={100}
              />
            </label>
            <label>
              Email
              <input value={me.user.email} readOnly />
              <small>
                Идентификатор аккаунта. Изменение email в MVP не поддерживается.
              </small>
            </label>
            <div className="form-footer">
              <Button disabled={save.isPending}>
                <Save size={15} />
                Сохранить профиль
              </Button>
            </div>
          </form>
        </Panel>
        <div>
          <Panel title="Рабочее пространство">
            <div className="settings-rows">
              <div>
                <span>Организация</span>
                <strong>
                  {
                    me.organizations.find((x) => x.id === me.organization_id)
                      ?.name
                  }
                </strong>
              </div>
              <div>
                <span>Роль</span>
                <strong>
                  {me.role === "owner"
                    ? "Владелец"
                    : me.role === "developer"
                      ? "Разработчик"
                      : "Наблюдатель"}
                </strong>
              </div>
              <div>
                <span>Язык интерфейса</span>
                <strong>Русский</strong>
              </div>
              <div>
                <span>Часовой пояс бюджетов</span>
                <strong>UTC</strong>
              </div>
              <div>
                <span>Окружение</span>
                <strong>{me.environment}</strong>
              </div>
            </div>
            <div className="padded">
              <Button
                variant="outline"
                onClick={() => router.push("/developer/organizations")}
              >
                <Globe size={15} />
                Организации и участники
              </Button>
            </div>
          </Panel>
          <Panel title="Финансовая безопасность">
            <div className="inline-info">
              <ShieldCheck size={26} />
              <div>
                <strong>AgentPass не хранит деньги</strong>
                <p>
                  Платформа проверяет полномочия и ведёт аудит. Все покупки в
                  системе тестовые; реальных списаний нет.
                </p>
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
function AuditTable({
  q,
  offset,
  setOffset,
  limit = 15,
}: {
  q: { isPending: boolean; error: Error | null; data?: Page<Audit> };
  offset: number;
  setOffset: (n: number) => void;
  limit?: number;
}) {
  const [selected, setSelected] = useState<Audit | null>(null);
  return (
    <>
      <Panel
        title="Журнал аудита"
        description="Автор, действие и ресурс для каждой значимой операции"
      >
        {q.isPending ? (
          <Loading />
        ) : q.error ? (
          <Failure error={q.error} />
        ) : q.data?.items.length ? (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Событие</th>
                    <th>Автор</th>
                    <th>Ресурс</th>
                    <th>Дата</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {q.data.items.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <button
                          className="table-title"
                          onClick={() => setSelected(a)}
                        >
                          {a.action}
                        </button>
                      </td>
                      <td>
                        <code>{a.actor_id.slice(0, 12)}…</code>
                      </td>
                      <td>
                        <code>{a.resource_id.slice(0, 12)}…</code>
                      </td>
                      <td>{date(a.created_at, true)}</td>
                      <td>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label="Детали события"
                          onClick={() => setSelected(a)}
                        >
                          <ArrowUpRight size={15} />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager
              total={q.data.total}
              offset={offset}
              limit={limit}
              setOffset={setOffset}
            />
          </>
        ) : (
          <Empty
            title="Журнал пока пуст"
            description="Значимые действия будут автоматически записаны."
          />
        )}
      </Panel>
      <Modal
        open={!!selected}
        onOpenChange={() => setSelected(null)}
        title="Событие аудита"
        description={selected?.action}
      >
        <pre className="json-output">{JSON.stringify(selected, null, 2)}</pre>
      </Modal>
    </>
  );
}
interface Metrics {
  organizations: number;
  requests_24h: number;
  errors_24h: number;
  denied_requests_24h: number;
  average_latency_ms: number;
  webhook_backlog: number;
  database: string;
  environment: string;
  payment_mode: string;
}
export function AdminConsole() {
  const { me } = useApp();
  const [tab, setTab] = useState("overview");
  if (!me.user.platform_admin)
    return (
      <Failure
        error={
          new Error("Admin Console доступен только администратору платформы.")
        }
      />
    );
  return (
    <>
      <PageTitle
        eyebrow="PLATFORM OPERATIONS"
        title="Admin Console"
        description="Организации, системные события и диагностика sandbox."
      />
      <div className="section-tabs">
        {[
          ["overview", "Мониторинг"],
          ["organizations", "Организации"],
          ["requests", "API и ошибки"],
          ["events", "События безопасности"],
          ["sandbox", "Sandbox"],
        ].map(([v, l]) => (
          <button
            key={v}
            className={tab === v ? "active" : ""}
            onClick={() => setTab(v)}
          >
            {l}
          </button>
        ))}
      </div>
      {tab === "overview" ? (
        <AdminOverview />
      ) : tab === "organizations" ? (
        <AdminOrganizations />
      ) : tab === "requests" ? (
        <RequestTable admin />
      ) : tab === "events" ? (
        <AdminEvents />
      ) : (
        <SandboxManagement />
      )}
    </>
  );
}
function AdminOverview() {
  const q = useResource<Metrics>("/v1/admin/metrics", 10000);
  if (q.isPending) return <Loading />;
  if (q.error) return <Failure error={q.error} />;
  const m = q.data;
  return (
    <>
      <OperationsPanel />
      <div className="metric-grid">
        {[
          ["Организации", m.organizations],
          ["Запросы за 24 ч", m.requests_24h],
          ["Ошибки 5xx", m.errors_24h],
          ["Средняя задержка", `${m.average_latency_ms} ms`],
        ].map(([l, v]) => (
          <div className="metric-card" key={l}>
            <div className="metric-label">
              {l}
              <Activity size={16} />
            </div>
            <strong className="metric-value">{v}</strong>
            <small className="muted-text">Из записей PostgreSQL</small>
          </div>
        ))}
      </div>
      <div className="security-grid">
        <Panel title="Техническое состояние">
          <div className="settings-rows">
            <div>
              <span>
                <Database size={16} />
                PostgreSQL
              </span>
              <Badge value={m.database} />
            </div>
            <div>
              <span>
                <Globe size={16} />
                Окружение
              </span>
              <strong>{m.environment}</strong>
            </div>
            <div>
              <span>
                <WalletIcon />
                Платежи
              </span>
              <strong>Только тестовые операции</strong>
            </div>
            <div>
              <span>Webhook очередь</span>
              <strong>{m.webhook_backlog}</strong>
            </div>
          </div>
        </Panel>
        <Panel title="Контроль доступа">
          <div className="settings-rows">
            <div>
              <span>401 / 403 / 429 за 24 часа</span>
              <strong>{m.denied_requests_24h}</strong>
            </div>
            <div>
              <span>Ошибки сервера 5xx</span>
              <strong>{m.errors_24h}</strong>
            </div>
          </div>
          <div className="padded muted-text">
            Детали доступны в журнале API. Содержимое запросов и секреты не
            записываются.
          </div>
        </Panel>
      </div>
    </>
  );
}
function OperationsPanel(){
  const q=useResource<{workers:{id:string;observed_at:string;stale:boolean}[];execution_unknown:number;execution_quarantined:number;webhook_dead_letter:number}>('/v1/admin/operations',10000);
  return <Panel title="Worker и сверка операций">
    {q.isPending?<Loading />:q.error?<Failure error={q.error}/>:<div className="settings-rows">
      <div><span>Неопределённый результат</span><strong>{q.data.execution_unknown}</strong></div>
      <div><span>Требуют ручной сверки после 10 попыток</span><strong>{q.data.execution_quarantined}</strong></div>
      <div><span>Webhook dead letters</span><strong>{q.data.webhook_dead_letter}</strong></div>
      {q.data.workers.length?q.data.workers.map(w=><div key={w.id}><span>{w.id}</span><strong>{w.stale?'Нет heartbeat > 90 с':`Heartbeat ${date(w.observed_at,true)}`}</strong></div>):<p>Worker ещё не зарегистрирован</p>}
    </div>}
  </Panel>;
}
function WalletIcon() {
  return <Lock size={16} />;
}
function AdminOrganizations() {
  const q = useResource<Page<Organization>>("/v1/admin/organizations");
  const [target, setTarget] = useState<Organization | null>(null);
  const action = useAction<unknown, { id: string; status: string }>(
    (v) =>
      api(`/v1/admin/organizations/${v.id}?status=${v.status}`, {
        method: "PATCH",
      }),
    "Статус организации обновлён",
  );
  return (
    <>
      <Panel title="Организации платформы">
        {q.isPending ? (
          <Loading />
        ) : q.error ? (
          <Failure error={q.error} />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Организация</th>
                  <th>ID</th>
                  <th>Статус</th>
                  <th>Управление</th>
                </tr>
              </thead>
              <tbody>
                {q.data.items.map((o) => (
                  <tr key={o.id}>
                    <td>
                      <strong>{o.name}</strong>
                    </td>
                    <td>
                      <code>{o.id.slice(0, 16)}…</code>
                    </td>
                    <td>
                      <Badge value={o.status} />
                    </td>
                    <td>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setTarget(o)}
                      >
                        {o.status === "active"
                          ? "Приостановить"
                          : "Активировать"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Modal
        open={!!target}
        onOpenChange={() => setTarget(null)}
        title={
          target?.status === "active"
            ? "Приостановить организацию"
            : "Активировать организацию"
        }
        description="Приостановка блокирует обращения пользователей и API-ключей организации."
      >
        <p>{target?.name}</p>
        <div className="form-footer">
          <Button variant="outline" onClick={() => setTarget(null)}>
            Отмена
          </Button>
          <Button
            disabled={action.isPending}
            onClick={async () => {
              try {
                await action.mutateAsync({
                  id: target!.id,
                  status: target!.status === "active" ? "suspended" : "active",
                });
                setTarget(null);
              } catch {}
            }}
          >
            Подтвердить
          </Button>
        </div>
      </Modal>
    </>
  );
}
function AdminEvents() {
  const [offset, setOffset] = useState(0);
  const q = useResource<Page<Audit>>(
    `/v1/admin/events?limit=15&offset=${offset}`,
    10000,
  );
  return <AuditTable q={q} offset={offset} setOffset={setOffset} />;
}
function SandboxManagement() {
  const router = useRouter();
  const {me}=useApp();
  const action = useAction<unknown, void>(
    () => api("/v1/sandbox/demo", { method: "POST" }),
    "Новый демо-сценарий создан",
  );
  if (!['sandbox','development'].includes(me.environment)) return <Panel title="Sandbox отключён"><p className="padded">Создание демо-данных недоступно в этом окружении.</p></Panel>;
  return (
    <Panel
      title="Управление sandbox"
      description="Новые демо-агенты с независимыми мандатами и бюджетами"
    >
      <div className="docs-content">
        <div className="info-banner">
          <AlertCircle size={17} />
          <span>
            Данные существующих демонстраций и журнал аудита сохраняются.
          </span>
        </div>
        <h3>Демонстрационный набор</h3>
        <p>
          Personal Shopping Assistant · лимит 15 000 ₽ · дневной бюджет 25 000 ₽
          · подтверждение от 10 000 ₽ · электроника · срок 30 дней.
        </p>
        <Button
          disabled={action.isPending}
          onClick={async () => {
            try {
              await action.mutateAsync();
              router.push("/console");
            } catch {}
          }}
        >
          <Plus size={15} />
          Создать демо-набор
        </Button>
      </div>
    </Panel>
  );
}
