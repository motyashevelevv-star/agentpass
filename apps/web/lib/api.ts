"use client";
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
let stepUpHandler: (() => Promise<string>) | null = null;
export function registerStepUp(handler: (() => Promise<string>) | null) {
  stepUpHandler = handler;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  const csrf =
    typeof document !== "undefined"
      ? document.cookie
          .split("; ")
          .find((x) => x.startsWith("ap_csrf="))
          ?.split("=")[1]
      : undefined;
  if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  const org =
    typeof window !== "undefined"
      ? localStorage.getItem("agentpass-org")
      : null;
  if (org && !headers.has("X-Organization-ID"))
    headers.set("X-Organization-ID", org);
  const res = await fetch(`/api${path}`, {
    ...options,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  let data;
  try {
    data = await res.json();
  } catch {
    throw new ApiError(
      "API_UNAVAILABLE",
      "Сервис временно недоступен. Повторите запрос.",
      res.status,
    );
  }
  if (!res.ok && data.error?.code === 'MFA_REQUIRED' && stepUpHandler && !headers.has('X-MFA-Code') && path !== '/v1/auth/login') {
    const code = await stepUpHandler();
    headers.set('X-MFA-Code', code);
    let body = options.body;
    if (typeof body === 'string' && (path.endsWith('/resolve') || path === '/v1/security/password')) {
      body = JSON.stringify({ ...JSON.parse(body), mfa_code: code });
    }
    return api<T>(path, { ...options, headers, body });
  }
  if (!res.ok)
    throw new ApiError(
      data.error?.code || "REQUEST_FAILED",
      data.error?.message || "Не удалось выполнить запрос",
      res.status,
    );
  return data as T;
}
export const money = (amount: number, currency = "RUB") =>
  new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency,
    maximumFractionDigits: amount % 100 ? 2 : 0,
  }).format(amount / 100);
export const date = (value: string, withTime = false) =>
  new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(new Date(value));
export const category = (name: string) =>
  ({
    electronics: "Электроника",
    travel: "Путешествия",
    software: "ПО и сервисы",
    food: "Продукты",
  })[name] || name;
export const statusName = (name: string) =>
  ({
    active: "Активен",
    paused: "Приостановлен",
    revoked: "Отозван",
    authorized: "Разрешена",
    pending: "Ожидает",
    denied: "Отклонена",
    completed: "Исполнена",
    cancelled: "Отменена",
    expired: "Истекла",
    approved: "Подтверждён",
    rejected: "Отклонён",
    invalidated: "Недействителен",
    held: "Зарезервирован",
    consumed: "Использован",
    released: "Освобождён",
    delivered: "Доставлен",
    retry: "Повтор",
    failed: "Ошибка",
    disabled: "Отключён",
    suspended: "Приостановлена",
    simulated: "Симуляция",
    external_test: "Внешний тестовый платёж",
    inflight: "Удерживается до сверки",
    executing: "Передана исполнителю",
    payment_pending: "Ожидает провайдера",
    payment_unknown: "Нужна сверка",
    queued: "В очереди",
    dispatching: "Отправляется",
    unknown: "Неизвестен — резерв удерживается",
    succeeded: "Подтверждено провайдером",
    refunded: "Возвращено",
  })[name] || name;
