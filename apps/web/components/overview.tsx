"use client";
import { useState } from "react";
import Link from "next/link";
import {
  ArrowUpRight,
  ArrowRight,
  Plus,
  Bot,
  ArrowLeftRight,
  Wallet,
  CheckCheck,
  ShieldCheck,
  ChevronDown,
  Clock,
  Code2,
  FileCheck2,
  Download,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from "recharts";
import { useResource, useApp } from "./context";
import type { Analytics, Page, Intent, Agent } from "@/lib/types";
import { money, date, category } from "@/lib/api";
import { Button } from "./ui/button";
import { PageTitle, Panel, Badge, Loading, Failure, Empty } from "./shared";
import { IntentDetail } from "./transactions";
const colors = ["#27836a", "#dda34d", "#cf6a65"];
export function SpendChart({ data }: { data: Analytics["trend"] }) {
  return (
    <div className="spend-chart">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 14, right: 14, left: -10, bottom: 0 }}
        >
          <defs>
            <linearGradient id="spendFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#27836a" stopOpacity={0.14} />
              <stop offset="100%" stopColor="#27836a" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="3 4"
            vertical={false}
            stroke="var(--border)"
          />
          <XAxis
            dataKey="date"
            tickFormatter={(v) => date(v)}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11, fill: "var(--muted)" }}
            dy={10}
            minTickGap={25}
          />
          <YAxis
            tickFormatter={(v) => `${v / 100000}k`}
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11, fill: "var(--muted)" }}
          />
          <Tooltip
            formatter={(v) => money(Number(v))}
            labelFormatter={(v) => date(String(v))}
            contentStyle={{
              background: "var(--panel)",
              border: "1px solid var(--border)",
              borderRadius: 10,
              fontSize: 12,
            }}
          />
          <Area
            type="monotone"
            dataKey="amount"
            isAnimationActive={false}
            name="Симулированные расходы"
            stroke="#27836a"
            strokeWidth={2.4}
            fill="url(#spendFill)"
            activeDot={{ r: 5, strokeWidth: 3, stroke: "var(--panel)" }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
export function Overview() {
  const { me } = useApp();
  const [days, setDays] = useState(7);
  const analytics = useResource<Analytics>(`/v1/analytics?days=${days}`, 15000);
  const intents = useResource<Page<Intent>>("/v1/intents?limit=5", 15000);
  const agents = useResource<Page<Agent>>("/v1/agents");
  const [selected, setSelected] = useState<Intent | null>(null);
  if (analytics.isPending) return <Loading />;
  if (analytics.error)
    return (
      <Failure error={analytics.error} retry={() => analytics.refetch()} />
    );
  const a = analytics.data;
  const totalBudget = a.budgets.reduce((sum, b) => sum + b.daily_limit, 0);
  const used = a.budgets.reduce((sum, b) => sum + b.usage.daily, 0);
  const periodSpend = a.trend.reduce((sum, x) => sum + x.amount, 0);
  return (
    <>
      <PageTitle
        eyebrow="ВАШИ АГЕНТЫ ПОД КОНТРОЛЕМ"
        title="Обзор"
        description="Финансовые полномочия, решения и активность в одном месте."
        action={
          <Button asChild>
            <Link href="/mandates?create=1">
              <Plus size={16} />
              Создать мандат
            </Link>
          </Button>
        }
      />
      <div className="overview-notice">
        <div className="notice-icon">
          <ShieldCheck size={19} />
        </div>
        <p>
          <strong>Делегируйте действия. Сохраняйте контроль.</strong>
          <span>
            Каждая операция проходит проверку правил перед исполнением.
          </span>
        </p>
        <Link href="/console">
          Попробовать агента
          <ArrowUpRight size={16} />
        </Link>
      </div>
      <div className="metric-grid">
        <Metric
          label="Активные агенты"
          value={String(a.active_agents)}
          icon={<Bot size={17} />}
          foot="Зарегистрированы и активны"
        />
        <Metric
          label="Проверено операций"
          value={String(a.total)}
          icon={<ArrowLeftRight size={17} />}
          foot={`${a.initial_decisions.APPROVE || 0} разрешено · ${a.initial_decisions.DENY || 0} отклонено`}
        />
        <Metric
          label="Расходы в sandbox"
          value={money(a.spent)}
          icon={<Wallet size={17} />}
          foot={`${money(a.reserved)} зарезервировано`}
        />
        <Metric
          label="Ждут подтверждения"
          value={String(a.pending)}
          icon={<CheckCheck size={17} />}
          foot={
            a.pending ? (
              <Link href="/approvals">
                Перейти к запросам <ArrowRight size={12} />
              </Link>
            ) : (
              "Все запросы обработаны"
            )
          }
          warning={a.pending > 0}
        />
      </div>
      <div className="overview-middle">
        <Panel
          title="Динамика расходов"
          description="Только исполненные симулированные покупки"
          action={
            <select
              aria-label="Период графика"
              className="compact-select"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              <option value={7}>Последние 7 дней</option>
              <option value={30}>Последние 30 дней</option>
            </select>
          }
        >
          <div className="chart-head">
            <span>{money(periodSpend)}</span>
            <small>
              <i />
              Симулированные расходы, RUB
            </small>
          </div>
          <SpendChart data={a.trend} />
        </Panel>
        <Panel
          title="Дневной бюджет"
          action={
            <Link
              className="icon-link"
              href="/mandates"
              aria-label="Открыть мандаты"
            >
              <ArrowUpRight size={17} />
            </Link>
          }
        >
          <div className="budget-total">
            <span>{money(used)}</span>
            <small>из {money(totalBudget)}</small>
          </div>
          <div className="budget-progress">
            <span
              style={{
                width: `${Math.min(100, totalBudget ? (used / totalBudget) * 100 : 0)}%`,
              }}
            />
          </div>
          <div className="budget-caption">
            <span>Использовано и зарезервировано</span>
            <strong>
              {totalBudget ? Math.round((used / totalBudget) * 100) : 0}%
            </strong>
          </div>
          <div className="budget-list">
            {a.budgets.slice(0, 3).map((b) => (
              <div key={b.id}>
                <span className="mini-agent">
                  <Bot size={15} />
                </span>
                <div>
                  <strong>{b.name}</strong>
                  <small>
                    {money(b.usage.daily, b.currency)} /{" "}
                    {money(b.daily_limit, b.currency)}
                  </small>
                </div>
                <div className="tiny-progress">
                  <span
                    style={{
                      width: `${Math.min(100, (b.usage.daily / b.daily_limit) * 100)}%`,
                    }}
                  />
                </div>
              </div>
            ))}
            {!a.budgets.length && (
              <p className="muted-text">
                Создайте мандат, чтобы задать бюджет.
              </p>
            )}
          </div>
          <div className="budget-reset">
            <Clock size={13} />
            Обновление в 00:00 UTC
          </div>
        </Panel>
      </div>
      <Panel
        title="Последние операции"
        description="Намерения агентов и решения Policy Engine"
        action={
          <Link className="text-link" href="/transactions">
            Все операции
            <ArrowRight size={14} />
          </Link>
        }
        className="operations-panel"
      >
        {intents.error ? (
          <Failure error={intents.error} />
        ) : intents.data?.items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Операция / продавец</th>
                  <th>Агент</th>
                  <th>Сумма</th>
                  <th>Решение</th>
                  <th>Время</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {intents.data.items.map((i) => (
                  <tr
                    key={i.id}
                    onClick={() => setSelected(i)}
                    className="clickable"
                  >
                    <td>
                      <div className="merchant-cell">
                        <span className="merchant-avatar">{i.merchant[0]}</span>
                        <div>
                          <strong>{i.description || i.merchant}</strong>
                          <small>
                            {i.merchant} · {category(i.category)}
                          </small>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="agent-cell">
                        <Bot size={14} />
                        {agents.data?.items.find((x) => x.id === i.agent_id)
                          ?.name || "ИИ-агент"}
                      </span>
                    </td>
                    <td className="amount">{money(i.amount, i.currency)}</td>
                    <td>
                      <Badge value={i.decision} />
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
        ) : (
          <Empty
            title="Пока нет операций"
            description="Отправьте первый запрос через Agent Console."
            action={
              <Button asChild variant="outline">
                <Link href="/console">Открыть Agent Console</Link>
              </Button>
            }
          />
        )}
      </Panel>
      <div className="overview-bottom">
        <Panel
          title="Ваши агенты"
          action={
            <Link className="text-link" href="/agents">
              Управление
              <ArrowRight size={14} />
            </Link>
          }
        >
          {agents.data?.items.length ? (
            <div className="agent-summary-list">
              {agents.data.items.slice(0, 3).map((agent) => (
                <Link key={agent.id} href="/agents">
                  <span className="agent-icon">
                    <Bot size={21} />
                  </span>
                  <div>
                    <strong>{agent.name}</strong>
                    <small>{agent.description || "Финансовый ИИ-агент"}</small>
                  </div>
                  <Badge value={agent.status} />
                </Link>
              ))}
            </div>
          ) : (
            <Empty
              title="Подключите первого агента"
              description="Задайте имя и создайте финансовые полномочия."
            />
          )}
        </Panel>
        <Link className="developer-card" href="/developer">
          <div className="developer-card-icon">
            <Code2 size={21} />
          </div>
          <span className="eyebrow">ДЛЯ РАЗРАБОТЧИКОВ</span>
          <h2>Подключите своего агента</h2>
          <p>
            API, SDK и sandbox для безопасной
            <br />
            интеграции финансовых действий.
          </p>
          <span className="text-link">
            Открыть Developer Portal
            <ArrowUpRight size={15} />
          </span>
          <div className="code-decoration">
            <span>await</span> agentpass.intents.create(…)
          </div>
        </Link>
      </div>
      <IntentDetail intent={selected} close={() => setSelected(null)} />
    </>
  );
}
function Metric({
  label,
  value,
  icon,
  foot,
  warning = false,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  foot: React.ReactNode;
  warning?: boolean;
}) {
  return (
    <div className={`metric-card ${warning ? "metric-warning" : ""}`}>
      <div className="metric-label">
        {label}
        <span>{icon}</span>
      </div>
      <strong className="metric-value">{value}</strong>
      <div className="metric-foot">{foot}</div>
    </div>
  );
}
export function AnalyticsPage() {
  const [days, setDays] = useState(7);
  const q = useResource<Analytics>(`/v1/analytics?days=${days}`);
  const { notify } = useApp();
  if (q.isPending) return <Loading />;
  if (q.error) return <Failure error={q.error} />;
  const a = q.data;
  const pie = ["APPROVE", "ASK", "DENY"].map((name, i) => ({
    name,
    value: a.initial_decisions[name] || 0,
    color: colors[i],
  }));
  function exportCsv() {
    const body =
      "date,amount_minor,currency\n" +
      a.trend.map((x) => `${x.date},${x.amount},RUB`).join("\n");
    const url = URL.createObjectURL(
      new Blob(["\uFEFF" + body], { type: "text/csv;charset=utf-8;" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "agentpass-spending.csv";
    anchor.click();
    URL.revokeObjectURL(url);
    notify("Отчёт экспортирован");
  }
  return (
    <>
      <PageTitle
        title="Аналитика"
        description="Реальные записи sandbox. Все суммы расходов — в рублях."
        action={
          <Button variant="outline" onClick={exportCsv}>
            <Download size={16} />
            Экспорт CSV
          </Button>
        }
      />
      <div className="metric-grid">
        <Metric
          label="Операции"
          value={String(a.total)}
          icon={<ArrowLeftRight size={17} />}
          foot={`${a.evaluations} проверок правил`}
        />
        <Metric
          label="Исполнено"
          value={money(a.spent)}
          icon={<Wallet size={17} />}
          foot="Симулированные покупки, RUB"
        />
        <Metric
          label="Разрешения"
          value={String(a.initial_decisions.APPROVE || 0)}
          icon={<ShieldCheck size={17} />}
          foot="Решение при первом запросе"
        />
        <Metric
          label="Запросы согласия"
          value={String(a.initial_decisions.ASK || 0)}
          icon={<CheckCheck size={17} />}
          foot={`${a.pending} ожидают решения`}
        />
      </div>
      <div className="analytics-grid">
        <Panel
          title="Расходы по дням"
          action={
            <select
              className="compact-select"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              aria-label="Период"
            >
              <option value={7}>7 дней</option>
              <option value={30}>30 дней</option>
            </select>
          }
        >
          <SpendChart data={a.trend} />
        </Panel>
        <Panel
          title="Решения при первом запросе"
          description="APPROVE / ASK / DENY"
        >
          {a.total ? (
            <div className="decision-chart">
              <div className="donut">
                <ResponsiveContainer width="100%" height={190}>
                  <PieChart>
                    <Pie
                      data={pie}
                      dataKey="value"
                      innerRadius={58}
                      outerRadius={78}
                      stroke="var(--panel)"
                      strokeWidth={5}
                    >
                      {pie.map((x) => (
                        <Cell key={x.name} fill={x.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: "var(--panel)",
                        borderRadius: 8,
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="donut-label">
                  <strong>{a.total}</strong>
                  <span>операций</span>
                </div>
              </div>
              <div className="chart-legend">
                {pie.map((x) => (
                  <div key={x.name}>
                    <i style={{ background: x.color }} />
                    <span>{x.name}</span>
                    <strong>{x.value}</strong>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <Empty description="После первого запроса появится распределение решений." />
          )}
        </Panel>
        <Panel title="Категории расходов" description="Исполненные покупки">
          {a.categories.length ? (
            <div className="category-list">
              {a.categories.map((c) => (
                <div key={c.name}>
                  <span>{category(c.name)}</span>
                  <strong>{money(c.amount)}</strong>
                  <div className="budget-progress">
                    <span
                      style={{
                        width: `${a.spent ? (c.amount / a.spent) * 100 : 0}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty description="Исполненные операции ещё не появились." />
          )}
        </Panel>
        <Panel title="Причины отказов">
          {a.decline_reasons.length ? (
            <div className="reason-list">
              {a.decline_reasons.map((r) => (
                <div key={r.name}>
                  <span>{r.name}</span>
                  <strong>{r.count}</strong>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="Отказов нет"
              description="Ни одна операция ещё не была отклонена."
            />
          )}
        </Panel>
        <Panel title="Активность агентов">
          {a.agent_activity.map((x) => (
            <div className="activity-row" key={x.name}>
              <Bot size={18} />
              <span>{x.name}</span>
              <strong>{x.count} операций</strong>
            </div>
          ))}
        </Panel>
        <Panel
          title="История подтверждений"
          description="Одноразовые решения с повторной проверкой правил"
        >
          <div className="inline-info">
            <CheckCheck size={25} />
            <div>
              <strong>{a.initial_decisions.ASK || 0} запросов создано</strong>
              <p>{a.pending} ожидают ответа пользователя.</p>
              <Link className="text-link" href="/approvals">
                Открыть историю
                <ArrowRight size={14} />
              </Link>
            </div>
          </div>
        </Panel>
      </div>
    </>
  );
}
