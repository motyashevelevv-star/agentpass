"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ShieldCheck,
  KeyRound,
  Check,
  Command,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "./ui/button";
import type { Agent, Page } from "@/lib/types";
export function Login() {
  const router = useRouter();
  const [register, setRegister] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [quickLogin, setQuickLogin] = useState(false);
  useEffect(() => {
    api<{ quick_login: boolean }>("/v1/sandbox/access")
      .then((config) => setQuickLogin(config.quick_login))
      .catch(() => {});
  }, []);
  async function enterSandbox(fullAccess: boolean) {
    setPending(true);
    setError("");
    try {
      localStorage.removeItem("agentpass-org");
      await api("/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: fullAccess ? "admin@agentpass.local" : "demo@agentpass.local",
          password: "AgentPass-demo-2026!",
        }),
      });
      if (fullAccess) {
        const agents = await api<Page<Agent>>("/v1/agents?limit=1");
        if (agents.total === 0)
          await api("/v1/sandbox/demo", { method: "POST" });
      }
      router.push("/overview");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setPending(true);
    setError("");
    const data = new FormData(e.currentTarget);
    try {
      localStorage.removeItem("agentpass-org");
      await api(register ? "/v1/auth/register" : "/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: data.get("email"),
          password: data.get("password"),
          ...(!register && data.get('mfa_code') ? {mfa_code:data.get('mfa_code')} : {}),
          ...(register
            ? {
                name: data.get("name"),
                organization_name: data.get("organization_name"),
              }
            : {}),
        }),
      });
      router.push("/overview");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="login-page">
      <div className="login-story">
        <div className="brand">
          <span className="brand-icon">
            <Command size={24} />
          </span>
          agentpass<span className="brand-dot">.</span>
        </div>
        <div className="login-pitch">
          <span className="eyebrow">ФИНАНСОВАЯ ИНФРАСТРУКТУРА ДЛЯ ИИ</span>
          <h1>
            Автономность агента.
            <br />
            Контроль за вами.
          </h1>
          <p>
            Делегируйте финансовые полномочия,
            <br />
            задавайте правила и доверяйте каждому решению.
          </p>
          <div className="policy-visual">
            <div className="pv-header">
              <ShieldCheck size={22} />
              <span>Проверка полномочий</span>
              <span className="live-dot" />
            </div>
            {[
              "Агент аутентифицирован",
              "Операция в пределах бюджета",
              "Правила мандата соблюдены",
            ].map((x) => (
              <div className="pv-row" key={x}>
                <Check size={17} />
                {x}
              </div>
            ))}
            <div className="pv-result">
              APPROVE <span>Детерминированное решение</span>
            </div>
          </div>
        </div>
        <div className="login-foot">
          AgentPass Sandbox <span>Никаких реальных списаний</span>
        </div>
      </div>
      <main className="login-form">
        <span className="login-symbol">
          <KeyRound size={24} />
        </span>
        <h2>{register ? "Создайте рабочее пространство" : "С возвращением"}</h2>
        <p>
          {register
            ? "Ваши агенты. Ваши правила."
            : "Войдите, чтобы управлять полномочиями агентов."}
        </p>
        <form onSubmit={submit}>
          {register && (
            <>
              <label>
                Ваше имя
                <input name="name" required maxLength={100} />
              </label>
              <label>
                Организация
                <input name="organization_name" required maxLength={100} />
              </label>
            </>
          )}
          <label>
            Email
            <input
              type="email"
              name="email"
              defaultValue={register ? "" : "demo@agentpass.local"}
              required
              autoComplete="username"
            />
          </label>
          <label>
            Пароль
            <input
              type="password"
              name="password"
              required
              minLength={register ? 12 : 1}
              maxLength={128}
              autoComplete={register ? "new-password" : "current-password"}
            />
          </label>
          {!register && <label>Код MFA, если подключён<input name="mfa_code" inputMode="numeric" pattern="[0-9]{6}" autoComplete="one-time-code" /></label>}
          {error && (
            <div role="alert" className="error-message">
              {error}
            </div>
          )}
          <Button disabled={pending} className="full">
            {pending
              ? "Подождите…"
              : register
                ? "Создать аккаунт"
                : "Войти в AgentPass"}
            <ArrowRight size={16} />
          </Button>
        </form>
        <button
          className="text-button"
          onClick={() => {
            setRegister(!register);
            setError("");
          }}
        >
          {register
            ? "Уже есть аккаунт? Войти"
            : "Нет аккаунта? Зарегистрироваться"}
        </button>
        {quickLogin && !register && <div className="demo-credentials">
          <span className="badge muted">SANDBOX</span>
          <p>Откройте все четыре интерфейса с правами администратора.</p>
          <div className="form-stack">
            <Button
              type="button"
              disabled={pending}
              onClick={() => enterSandbox(true)}
            >
              Открыть полный sandbox
              <ArrowRight size={16} />
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={pending}
              onClick={() => enterSandbox(false)}
            >
              Войти как пользователь
            </Button>
          </div>
          <p>
            Демо: <strong>demo@agentpass.local</strong>
            <br />
            Пароль: <code>AgentPass-demo-2026!</code>
          </p>
          <small>
            Администратор: admin@agentpass.local
            <br />
            Тот же пароль в локальном sandbox.
          </small>
        </div>}
      </main>
    </div>
  );
}
