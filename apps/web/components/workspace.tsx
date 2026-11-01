"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Command,
  LayoutDashboard,
  Bot,
  FileCheck2,
  ArrowLeftRight,
  CheckCheck,
  ChartNoAxesCombined,
  ShieldCheck,
  Settings,
  Code2,
  Terminal,
  Search,
  ChevronDown,
  ChevronRight,
  Sun,
  Moon,
  Plus,
  Bell,
  ExternalLink,
  LogOut,
  Menu,
  X,
  ArrowUpRight,
  Check,
  AlertCircle,
  BookOpen,
} from "lucide-react";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { api, ApiError } from "@/lib/api";
import type { Me, Page, Agent, Mandate } from "@/lib/types";
import { AppContext, useResource, useAction } from "./context";
import { Button } from "./ui/button";
import { Modal } from "./ui/dialog";
import { Loading, Failure } from "./shared";
import { Overview, AnalyticsPage } from "./overview";
import { AgentsPage, MandatesPage } from "./mandates";
import { TransactionsPage, ApprovalsPage } from "./transactions";
import { AgentConsole } from "./agent-console";
import { DeveloperPortal } from "./developer";
import { SecurityPage, SettingsPage, AdminConsole } from "./settings";
import { StepUp } from './step-up';
const nav = [
  { path: "/overview", title: "Обзор", icon: LayoutDashboard },
  { path: "/agents", title: "Мои агенты", icon: Bot },
  { path: "/mandates", title: "Мандаты", icon: FileCheck2 },
  { path: "/transactions", title: "Операции", icon: ArrowLeftRight },
  { path: "/approvals", title: "Подтверждения", icon: CheckCheck },
  { path: "/analytics", title: "Аналитика", icon: ChartNoAxesCombined },
];
const secondary = [
  { path: "/security", title: "Безопасность", icon: ShieldCheck },
  { path: "/settings", title: "Настройки", icon: Settings },
];
export function Workspace() {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5000,
            retry: false,
            refetchOnWindowFocus: true,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <StepUp />
      <Shell />
    </QueryClientProvider>
  );
}
function Shell() {
  const path = usePathname();
  const router = useRouter();
  const client = useQueryClient();
  const query = useQuery<Me>({
    queryKey: ["me"],
    queryFn: () => api("/v1/auth/me"),
    retry: false,
  });
  const [toast, setToast] = useState<{
    message: string;
    error?: boolean;
  } | null>(null);
  const [dark, setDark] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [search, setSearch] = useState(false);
  useEffect(() => {
    const theme = localStorage.getItem("agentpass-theme") === "dark";
    setDark(theme);
    document.documentElement.dataset.theme = theme ? "dark" : "light";
  }, []);
  useEffect(() => {
    if (query.error instanceof ApiError && query.error.status === 401)
      router.replace("/login");
  }, [query.error, router]);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearch(true);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  useEffect(() => {
    setMobile(false);
  }, [path]);
  const notify = (message: string, error = false) =>
    setToast({ message, error });
  if (query.isPending) return <Loading />;
  if (query.error)
    return (
      <main className="standalone">
        <Failure
          error={query.error}
          retry={() => {
            localStorage.removeItem("agentpass-org");
            query.refetch();
          }}
        />
        <Link href="/login">Войти заново</Link>
      </main>
    );
  const me = query.data;
  const active =
    [...nav, ...secondary].find((x) => path === x.path)?.title ||
    (path.startsWith("/developer")
      ? "Developer Portal"
      : path === "/console"
        ? "Agent Console"
        : path.startsWith("/admin")
          ? "Admin Console"
          : "Страница");
  return (
    <AppContext.Provider value={{ me, notify }}>
      <div className="app-shell">
        {mobile && (
          <button
            className="sidebar-backdrop"
            aria-label="Закрыть меню"
            onClick={() => setMobile(false)}
          />
        )}
        <aside className={`sidebar ${mobile ? "sidebar-open" : ""}`}>
          <Link className="brand" href="/overview">
            <span className="brand-icon">
              <Command size={23} />
            </span>
            agentpass<span className="brand-dot">.</span>
          </Link>
          <Dropdown.Root>
            <Dropdown.Trigger className="workspace-switch">
              <span className="org-avatar">
                {
                  me.organizations.find((x) => x.id === me.organization_id)
                    ?.name[0]
                }
              </span>
              <span>
                <strong>
                  {
                    me.organizations.find((x) => x.id === me.organization_id)
                      ?.name
                  }
                </strong>
                <small>Рабочее пространство</small>
              </span>
              <ChevronDown size={15} />
            </Dropdown.Trigger>
            <Dropdown.Portal>
              <Dropdown.Content className="dropdown" sideOffset={6}>
                {me.organizations.map((org) => (
                  <Dropdown.Item
                    key={org.id}
                    onSelect={() => {
                      localStorage.setItem("agentpass-org", org.id);
                      client.removeQueries({
                        predicate: (q) => q.queryKey[0] !== "me",
                      });
                      query.refetch();
                    }}
                  >
                    <span>{org.name}</span>
                    {org.id === me.organization_id && <Check size={15} />}
                  </Dropdown.Item>
                ))}
                <Dropdown.Separator />
                <Dropdown.Item
                  onSelect={() => router.push("/developer/organizations")}
                >
                  <Plus size={15} />
                  Создать организацию
                </Dropdown.Item>
              </Dropdown.Content>
            </Dropdown.Portal>
          </Dropdown.Root>
          <div className="nav-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
          <nav>
            {nav.map((item) => (
              <Link
                key={item.path}
                className={`nav-item ${path === item.path ? "active" : ""}`}
                href={item.path}
              >
                <item.icon size={18} />
                <span>{item.title}</span>
                {item.path === "/approvals" && <PendingBadge />}
              </Link>
            ))}
          </nav>
          <div className="nav-divider" />
          <nav>
            {secondary.map((item) => (
              <Link
                key={item.path}
                className={`nav-item ${path === item.path ? "active" : ""}`}
                href={item.path}
              >
                <item.icon size={18} />
                {item.title}
              </Link>
            ))}
          </nav>
          <div className="nav-label nav-label-second">ИНСТРУМЕНТЫ</div>
          <nav>
            {me.role !== "viewer" && (
              <Link
                className={`nav-item ${path.startsWith("/developer") ? "active" : ""}`}
                href="/developer"
              >
                <Code2 size={18} />
                <span>Developer Portal</span>
                <ArrowUpRight size={14} />
              </Link>
            )}
            <Link
              className={`nav-item ${path === "/console" ? "active" : ""}`}
              href="/console"
            >
              <Terminal size={18} />
              <span>Agent Console</span>
              <span className="nav-tag">DEMO</span>
            </Link>
            {me.user.platform_admin && (
              <Link
                className={`nav-item ${path.startsWith("/admin") ? "active" : ""}`}
                href="/admin"
              >
                <ShieldCheck size={18} />
                Admin Console
              </Link>
            )}
          </nav>
          <div className="sidebar-bottom">
            <div className="sandbox-note">
              <span className="live-dot" />
              <strong>{me.environment} environment</strong>
              <p>
                Тестовые операции.
                <br />
                Реальные деньги не списываются.
              </p>
              <Link href="/developer/docs">
                Документация
                <ArrowUpRight size={13} />
              </Link>
            </div>
            <Dropdown.Root>
              <Dropdown.Trigger className="account-button">
                <span className="user-avatar">
                  {me.user.name
                    .split(" ")
                    .map((x) => x[0])
                    .slice(0, 2)
                    .join("")}
                </span>
                <span>
                  <strong>{me.user.name}</strong>
                  <small>
                    {me.role === "owner"
                      ? "Владелец"
                      : me.role === "developer"
                        ? "Разработчик"
                        : "Наблюдатель"}
                  </small>
                </span>
                <ChevronDown size={14} />
              </Dropdown.Trigger>
              <Dropdown.Portal>
                <Dropdown.Content className="dropdown" sideOffset={6}>
                  <Dropdown.Item onSelect={() => router.push("/settings")}>
                    <Settings size={15} />
                    Профиль
                  </Dropdown.Item>
                  <Dropdown.Item
                    onSelect={async () => {
                      try {
                        await api("/v1/auth/logout", { method: "POST" });
                        client.clear();
                        router.push("/login");
                      } catch (e) {
                        notify((e as Error).message, true);
                      }
                    }}
                  >
                    <LogOut size={15} />
                    Выйти
                  </Dropdown.Item>
                </Dropdown.Content>
              </Dropdown.Portal>
            </Dropdown.Root>
          </div>
        </aside>
        <div className="main-shell">
          <header className="topbar">
            <div className="breadcrumbs">
              <button
                className="icon-button mobile-menu"
                aria-label="Открыть меню"
                onClick={() => setMobile(true)}
              >
                <Menu size={20} />
              </button>
              <span>Рабочее пространство</span>
              <ChevronRight size={14} />
              <strong>{active}</strong>
            </div>
            <div className="topbar-actions">
              <button
                className="search-trigger"
                onClick={() => setSearch(true)}
              >
                <Search size={16} />
                <span>Поиск</span>
                <kbd>⌘ K</kbd>
              </button>
              <span className="environment-badge">
                <i />
                {me.environment === 'sandbox' ? 'Sandbox' : me.environment}
              </span>
              <button
                aria-label={dark ? "Светлая тема" : "Тёмная тема"}
                className="icon-button"
                onClick={() => {
                  setDark(!dark);
                  document.documentElement.dataset.theme = !dark
                    ? "dark"
                    : "light";
                  localStorage.setItem(
                    "agentpass-theme",
                    !dark ? "dark" : "light",
                  );
                }}
              >
                {dark ? <Sun size={18} /> : <Moon size={18} />}
              </button>
              <Link
                href="/approvals"
                className="icon-button notification-button"
                aria-label="Подтверждения"
              >
                <Bell size={18} />
                <PendingDot />
              </Link>
            </div>
          </header>
          <main className="main-content">
            {path === "/overview" ? (
              <Overview />
            ) : path === "/agents" ? (
              <AgentsPage />
            ) : path === "/mandates" ? (
              <MandatesPage />
            ) : path === "/transactions" ? (
              <TransactionsPage />
            ) : path === "/approvals" ? (
              <ApprovalsPage />
            ) : path === "/analytics" ? (
              <AnalyticsPage />
            ) : path === "/console" ? (
              <AgentConsole />
            ) : path.startsWith("/developer") ? (
              <DeveloperPortal />
            ) : path === "/security" ? (
              <SecurityPage />
            ) : path === "/settings" ? (
              <SettingsPage />
            ) : path.startsWith("/admin") ? (
              <AdminConsole />
            ) : (
              <div className="empty">
                <h1>Страница не найдена</h1>
                <Link href="/overview">Вернуться к обзору</Link>
              </div>
            )}
            <footer className="app-footer">
              <span>
                <span className="live-dot" /> Все решения сохраняются в журнале
                аудита
              </span>
              <span>
                AgentPass <span className="muted-text">/</span> {me.environment} v0.1
              </span>
            </footer>
          </main>
        </div>
      </div>
      {toast && (
        <div
          role={toast.error ? "alert" : "status"}
          className={`toast ${toast.error ? "toast-error" : ""}`}
        >
          {toast.error ? <AlertCircle size={18} /> : <Check size={18} />}
          <span>{toast.message}</span>
          <button
            aria-label="Закрыть уведомление"
            onClick={() => setToast(null)}
          >
            <X size={16} />
          </button>
        </div>
      )}
      <SearchModal open={search} setOpen={setSearch} />
    </AppContext.Provider>
  );
}
function PendingBadge() {
  const q = useResource<{ pending: number }>("/v1/analytics", 15000);
  return q.data?.pending ? (
    <span className="nav-count">{q.data.pending}</span>
  ) : null;
}
function PendingDot() {
  const q = useResource<{ pending: number }>("/v1/analytics", 15000);
  return q.data?.pending ? <i /> : null;
}
function SearchModal({
  open,
  setOpen,
}: {
  open: boolean;
  setOpen: (open: boolean) => void;
}) {
  const [text, setText] = useState("");
  const agents = useResource<Page<Agent>>("/v1/agents");
  const mandates = useResource<Page<Mandate>>("/v1/mandates");
  const router = useRouter();
  const options = [
    ...nav,
    ...secondary,
    { path: "/console", title: "Agent Console" },
    { path: "/developer", title: "Developer Portal" },
    ...(agents.data?.items || []).map((a) => ({
      path: "/agents",
      title: a.name,
    })),
    ...(mandates.data?.items || []).map((a) => ({
      path: "/mandates",
      title: a.name,
    })),
  ].filter((x) => x.title.toLowerCase().includes(text.toLowerCase()));
  return (
    <Modal
      open={open}
      onOpenChange={setOpen}
      title="Поиск по рабочему пространству"
      description="Разделы, агенты и мандаты."
    >
      <div className="search-input">
        <Search size={18} />
        <input
          placeholder="Найти агента или раздел…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>
      <div className="search-results">
        {options.map((x, i) => (
          <button
            key={i}
            onClick={() => {
              router.push(x.path);
              setOpen(false);
            }}
          >
            {x.title}
            <ArrowUpRight size={15} />
          </button>
        ))}
        {!options.length && <p>Ничего не найдено</p>}
      </div>
    </Modal>
  );
}
