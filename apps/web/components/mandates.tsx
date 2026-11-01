"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Plus,
  Bot,
  ArrowUpRight,
  FileCheck2,
  ShieldCheck,
  MoreHorizontal,
  Calendar,
  Wallet,
  Check,
  History,
  Pause,
  Play,
  Pencil,
  Trash2,
} from "lucide-react";
import { api, money, date, category } from "@/lib/api";
import type { Page, Agent, Mandate } from "@/lib/types";
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
} from "./shared";
const formSchema = z.object({
  name: z.string().min(1, "Введите название"),
  agent_id: z.string().min(1, "Выберите агента"),
  per_transaction: z
    .number()
    .positive("Сумма должна быть положительной")
    .max(1e9),
  daily_limit: z.number().positive(),
  weekly_limit: z.number().positive(),
  monthly_limit: z.number().positive(),
  approval_threshold: z.number().positive(),
  currency: z.string().length(3),
  valid_from: z.string().min(1),
  valid_until: z.string().min(1),
  categories: z.array(z.string()).min(1, "Выберите хотя бы одну категорию"),
  merchant_allowlist: z.string(),
  merchant_denylist: z.string(),
});
type FormValues = z.infer<typeof formSchema>;
export function AgentsPage() {
  const q = useResource<Page<Agent>>("/v1/agents");
  const m = useResource<Page<Mandate>>("/v1/mandates");
  const { me } = useApp();
  const [open, setOpen] = useState(false);
  const [project, setProject] = useState("");
  const projects = useResource<{ items: { id: string; name: string }[] }>(
    "/v1/developer/projects",
  );
  const action = useAction<
    Agent,
    { name: string; description: string; project_id: string | null }
  >(
    (value) =>
      api("/v1/agents", { method: "POST", body: JSON.stringify(value) }),
    "Агент зарегистрирован",
  );
  const status = useAction<Agent, { id: string; status: string }>(
    (v) =>
      api(`/v1/agents/${v.id}/status?status=${v.status}`, { method: "PATCH" }),
    "Статус агента обновлён",
  );
  return (
    <>
      <PageTitle
        title="Мои агенты"
        description="Управляйте агентами и их финансовыми полномочиями."
        action={
          me.role !== "viewer" && (
            <Button onClick={() => setOpen(true)}>
              <Plus size={16} />
              Подключить агента
            </Button>
          )
        }
      />
      <div className="info-banner">
        <ShieldCheck size={18} />
        <span>
          Агент может действовать только в рамках активного мандата. API-ключ
          привязан к конкретному агенту.
        </span>
      </div>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <Failure error={q.error} />
      ) : q.data.items.length ? (
        <div className="agent-grid">
          {q.data.items.map((a) => {
            const list = m.data?.items.filter((x) => x.agent_id === a.id) || [];
            return (
              <Panel key={a.id}>
                <div className="agent-card-head">
                  <span className="agent-icon large">
                    <Bot size={26} />
                  </span>
                  <Badge value={a.status} />
                </div>
                <h2>{a.name}</h2>
                <p className="agent-description">
                  {a.description || "У агента пока нет описания."}
                </p>
                <div className="agent-meta">
                  <span>Активные мандаты</span>
                  <strong>
                    {list.filter((x) => x.status === "active").length}
                  </strong>
                </div>
                <div className="agent-meta">
                  <span>Подключён</span>
                  <strong>{date(a.created_at)}</strong>
                </div>
                <div className="id-box">
                  <code>{a.id.slice(0, 18)}…</code>
                  <CopyButton text={a.id} label="ID" />
                </div>
                <div className="card-actions">
                  <Button asChild variant="outline" size="sm">
                    <Link href={`/mandates?agent=${a.id}`}>
                      <FileCheck2 size={14} />
                      Полномочия
                    </Link>
                  </Button>
                  {me.role !== "viewer" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={status.isPending}
                      onClick={() =>
                        status.mutate({
                          id: a.id,
                          status: a.status === "active" ? "paused" : "active",
                        })
                      }
                    >
                      {a.status === "active" ? (
                        <Pause size={14} />
                      ) : (
                        <Play size={14} />
                      )}{" "}
                      {a.status === "active" ? "Приостановить" : "Активировать"}
                    </Button>
                  )}
                </div>
              </Panel>
            );
          })}
        </div>
      ) : (
        <Panel>
          <Empty
            title="Подключите первого агента"
            description="Зарегистрируйте агента, затем задайте финансовый мандат."
            action={
              <Button onClick={() => setOpen(true)}>
                <Plus size={16} />
                Подключить агента
              </Button>
            }
          />
        </Panel>
      )}
      <Modal
        open={open}
        onOpenChange={setOpen}
        title="Подключить агента"
        description="Создайте идентичность для агента. Полномочия задаются отдельным мандатом."
      >
        <form
          className="form-stack"
          onSubmit={async (e) => {
            e.preventDefault();
            const d = new FormData(e.currentTarget);
            try {
              await action.mutateAsync({
                name: String(d.get("name")),
                description: String(d.get("description")),
                project_id: project || null,
              });
              setOpen(false);
            } catch {}
          }}
        >
          <label>
            Название
            <input
              name="name"
              required
              maxLength={100}
              placeholder="Personal Shopping Assistant"
            />
          </label>
          <label>
            Описание
            <textarea
              name="description"
              maxLength={500}
              placeholder="Какие задачи выполняет агент?"
            />
          </label>
          <label>
            Проект
            <select
              value={project}
              onChange={(e) => setProject(e.target.value)}
            >
              <option value="">Без проекта</option>
              {projects.data?.items.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <div className="form-footer">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Отмена
            </Button>
            <Button disabled={action.isPending}>Зарегистрировать</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
export function MandatesPage() {
  const q = useResource<Page<Mandate>>("/v1/mandates", 15000);
  const agents = useResource<Page<Agent>>("/v1/agents");
  const params = useSearchParams();
  const { me } = useApp();
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState<Mandate | null>(null);
  const [revoke, setRevoke] = useState<Mandate | null>(null);
  const [history, setHistory] = useState<Mandate | null>(null);
  const [filter, setFilter] = useState("all");
  useEffect(() => {
    if (params.get("create")) setOpen(true);
  }, [params]);
  const revokeAction = useAction<unknown, string>(
    (id) => api(`/v1/mandates/${id}/revoke`, { method: "POST" }),
    "Полномочия отозваны. Неисполненные резервы освобождены.",
  );
  const list =
    q.data?.items.filter(
      (m) =>
        (filter === "all" || m.status === filter) &&
        (!params.get("agent") || m.agent_id === params.get("agent")),
    ) || [];
  return (
    <>
      <PageTitle
        title="Мандаты"
        description="Определите, что агент может делать с вашим финансовым бюджетом."
        action={
          me.role !== "viewer" && (
            <Button
              onClick={() => {
                setEdit(null);
                setOpen(true);
              }}
            >
              <Plus size={16} />
              Создать мандат
            </Button>
          )
        }
      />
      <div className="page-toolbar">
        <div className="segmented">
          {[
            ["all", "Все мандаты"],
            ["active", "Активные"],
            ["revoked", "Отозванные"],
          ].map(([v, l]) => (
            <button
              key={v}
              className={filter === v ? "selected" : ""}
              onClick={() => setFilter(v)}
            >
              {l}
              {v === "all" && <span>{q.data?.total || 0}</span>}
            </button>
          ))}
        </div>
        <span className="muted-text">Правила проверяются на сервере</span>
      </div>
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <Failure error={q.error} />
      ) : list.length ? (
        <div className="mandate-grid">
          {list.map((m) => (
            <Panel
              key={m.id}
              className={m.status === "revoked" ? "revoked-card" : ""}
            >
              <div className="mandate-card-head">
                <span className="mandate-icon">
                  <FileCheck2 size={22} />
                </span>
                <Badge
                  value={
                    new Date(m.valid_until) < new Date() ? "expired" : m.status
                  }
                />
              </div>
              <h2>{m.name}</h2>
              <div className="mandate-agent">
                <Bot size={14} />
                {m.agent_name}
                <span>v{m.version}</span>
              </div>
              <div className="mandate-rule-grid">
                <div>
                  <small>Лимит операции</small>
                  <strong>{money(m.per_transaction, m.currency)}</strong>
                </div>
                <div>
                  <small>Дневной бюджет</small>
                  <strong>{money(m.daily_limit, m.currency)}</strong>
                </div>
                <div>
                  <small>Подтверждение от</small>
                  <strong>{money(m.approval_threshold, m.currency)}</strong>
                </div>
                <div>
                  <small>Действует до</small>
                  <strong>{date(m.valid_until)}</strong>
                </div>
              </div>
              <div className="mandate-categories">
                {m.categories.map((c) => (
                  <span key={c}>{category(c)}</span>
                ))}
              </div>
              <div className="budget-caption">
                <span>Бюджет сегодня</span>
                <strong>
                  {money(m.usage.daily, m.currency)} /{" "}
                  {money(m.daily_limit, m.currency)}
                </strong>
              </div>
              <div className="budget-progress">
                <span
                  style={{
                    width: `${Math.min(100, (m.usage.daily / m.daily_limit) * 100)}%`,
                  }}
                />
              </div>
              <div className="card-actions">
                {m.status === "active" && me.role !== "viewer" && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setEdit(m);
                      setOpen(true);
                    }}
                  >
                    <Pencil size={13} />
                    Изменить
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => setHistory(m)}>
                  <History size={14} />
                  История
                </Button>
                {m.status === "active" && me.role !== "viewer" && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="danger-text"
                    onClick={() => setRevoke(m)}
                  >
                    Отозвать
                  </Button>
                )}
              </div>
            </Panel>
          ))}
        </div>
      ) : (
        <Panel>
          <Empty
            title="Нет мандатов"
            description="Создайте правила для финансовых действий агента."
            action={
              <Button onClick={() => setOpen(true)}>
                <Plus size={16} />
                Создать мандат
              </Button>
            }
          />
        </Panel>
      )}
      <Modal
        open={open}
        onOpenChange={setOpen}
        title={edit ? "Изменить мандат" : "Новый мандат"}
        description="Суммы вводятся в рублях. Изменение правил создаёт новую версию."
        wide
      >
        <MandateForm
          key={edit?.id || "new"}
          mandate={edit}
          agents={agents.data?.items || []}
          initialAgent={params.get("agent") || ""}
          done={() => setOpen(false)}
        />
      </Modal>
      <Modal
        open={!!revoke}
        onOpenChange={() => setRevoke(null)}
        title="Отозвать полномочия"
        description="Агент потеряет доступ. Ожидающие операции будут отклонены, их резервы — освобождены."
      >
        <p>
          Мандат: <strong>{revoke?.name}</strong>
        </p>
        <div className="form-footer">
          <Button variant="outline" onClick={() => setRevoke(null)}>
            Отмена
          </Button>
          <Button
            variant="destructive"
            disabled={revokeAction.isPending}
            onClick={async () => {
              try {
                await revokeAction.mutateAsync(revoke!.id);
                setRevoke(null);
              } catch {}
            }}
          >
            Отозвать мандат
          </Button>
        </div>
      </Modal>
      {history && (
        <VersionHistory mandate={history} close={() => setHistory(null)} />
      )}
    </>
  );
}
function MandateForm({
  mandate,
  agents,
  initialAgent,
  done,
}: {
  mandate: Mandate | null;
  agents: Agent[];
  initialAgent: string;
  done: () => void;
}) {
  const defaults: FormValues = {
    name: mandate?.name || "Покупки электроники",
    agent_id: mandate?.agent_id || initialAgent || agents[0]?.id || "",
    per_transaction: (mandate?.per_transaction || 1500000) / 100,
    daily_limit: (mandate?.daily_limit || 2500000) / 100,
    weekly_limit: (mandate?.weekly_limit || 10000000) / 100,
    monthly_limit: (mandate?.monthly_limit || 25000000) / 100,
    approval_threshold: (mandate?.approval_threshold || 1000000) / 100,
    currency: mandate?.currency || "RUB",
    valid_from:
      mandate?.valid_from.slice(0, 10) || new Date().toISOString().slice(0, 10),
    valid_until:
      mandate?.valid_until.slice(0, 10) ||
      new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10),
    categories: mandate?.categories || ["electronics"],
    merchant_allowlist: mandate?.merchant_allowlist.join(", ") || "",
    merchant_denylist: mandate?.merchant_denylist.join(", ") || "",
  };
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: defaults,
  });
  const action = useAction<unknown, FormValues>(
    (v) => {
      const values = {
        ...v,
        valid_from: new Date(v.valid_from + "T00:00:00Z").toISOString(),
        valid_until: new Date(v.valid_until + "T23:59:59Z").toISOString(),
        merchant_allowlist: v.merchant_allowlist
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean),
        merchant_denylist: v.merchant_denylist
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean),
      };
      for (const key of [
        "per_transaction",
        "daily_limit",
        "weekly_limit",
        "monthly_limit",
        "approval_threshold",
      ] as const)
        values[key] = Math.round(v[key] * 100);
      return api(mandate ? `/v1/mandates/${mandate.id}` : "/v1/mandates", {
        method: mandate ? "PUT" : "POST",
        body: JSON.stringify(values),
      });
    },
    mandate ? "Правила обновлены" : "Мандат создан",
  );
  useEffect(() => {
    if (!form.getValues("agent_id") && agents[0])
      form.setValue("agent_id", agents[0].id);
  }, [agents, form]);
  const cats = form.watch("categories");
  return (
    <form
      onSubmit={form.handleSubmit(async (v) => {
        try {
          await action.mutateAsync(v);
          done();
        } catch {}
      })}
      className="form-stack"
    >
      <div className="form-grid">
        <label>
          Название мандата
          <input {...form.register("name")} maxLength={100} />
        </label>
        <label>
          Агент
          <select {...form.register("agent_id")} disabled={!!mandate}>
            <option value="">Выберите агента</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!agents.length && (
        <div className="info-banner">
          Сначала <Link href="/agents">зарегистрируйте агента</Link>.
        </div>
      )}
      <div className="form-section-label">
        <Wallet size={15} />
        Лимиты и подтверждение
      </div>
      <div className="form-grid">
        {[
          ["per_transaction", "Лимит одной операции, ₽"],
          ["daily_limit", "Дневной бюджет, ₽"],
          ["weekly_limit", "Недельный бюджет, ₽"],
          ["monthly_limit", "Месячный бюджет, ₽"],
          ["approval_threshold", "Подтверждение от, ₽"],
        ].map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              type="number"
              step="0.01"
              min="0.01"
              {...form.register(key as "per_transaction", {
                valueAsNumber: true,
              })}
            />
          </label>
        ))}
        <label>
          Действует с (UTC)
          <input type="date" {...form.register("valid_from")} />
        </label>
        <label>
          Действует до (UTC)
          <input
            type="date"
            {...form.register("valid_until")}
            min={new Date().toISOString().slice(0, 10)}
          />
        </label>
      </div>
      <div className="form-section-label">
        <ShieldCheck size={15} />
        Разрешённые категории
      </div>
      <div className="category-options">
        {["electronics", "travel", "software", "food"].map((c) => (
          <button
            type="button"
            key={c}
            aria-pressed={cats.includes(c)}
            className={cats.includes(c) ? "selected" : ""}
            onClick={() =>
              form.setValue(
                "categories",
                cats.includes(c) ? cats.filter((x) => x !== c) : [...cats, c],
                { shouldValidate: true },
              )
            }
          >
            {cats.includes(c) && <Check size={13} />} {category(c)}
          </button>
        ))}
      </div>
      <div className="form-grid">
        <label>
          Разрешённые продавцы
          <input
            placeholder="Все продавцы (пустой список)"
            {...form.register("merchant_allowlist")}
          />
        </label>
        <label>
          Запрещённые продавцы
          <input
            placeholder="Названия через запятую"
            {...form.register("merchant_denylist")}
          />
        </label>
      </div>
      <p className="form-help">
        Списки продавцов нечувствительны к регистру. Запрет имеет приоритет.
        Валюта: {form.watch("currency")}. Дневной, недельный и месячный бюджеты
        считаются по UTC.
      </p>
      {Object.keys(form.formState.errors).length > 0 && (
        <div role="alert" className="error-message">
          Проверьте название, агента, категории и положительные суммы.
        </div>
      )}
      <div className="form-footer">
        <Button type="button" variant="outline" onClick={done}>
          Отмена
        </Button>
        <Button disabled={action.isPending || !agents.length}>
          {action.isPending
            ? "Сохраняем…"
            : mandate
              ? "Сохранить правила"
              : "Создать мандат"}
        </Button>
      </div>
    </form>
  );
}
function VersionHistory({
  mandate,
  close,
}: {
  mandate: Mandate;
  close: () => void;
}) {
  const q = useResource<{
    items: {
      id: string;
      version: number;
      created_at: string;
      rules: Mandate;
    }[];
  }>(`/v1/mandates/${mandate.id}/versions`);
  return (
    <Modal
      open
      onOpenChange={close}
      title="История правил"
      description={mandate.name}
    >
      {q.isPending ? (
        <Loading />
      ) : q.error ? (
        <Failure error={q.error} />
      ) : (
        q.data.items.map((v) => (
          <div className="version-row" key={v.id}>
            <span className="version-number">v{v.version}</span>
            <div>
              <strong>
                Лимит {money(v.rules.per_transaction)} · бюджет{" "}
                {money(v.rules.daily_limit)}
              </strong>
              <p>
                {date(v.created_at, true)} ·{" "}
                {v.rules.status === "revoked"
                  ? "Полномочия отозваны"
                  : "Правила сохранены"}
              </p>
            </div>
          </div>
        ))
      )}
    </Modal>
  );
}
