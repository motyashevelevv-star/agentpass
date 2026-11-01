"use client";
import {
  AlertCircle,
  ArrowUpRight,
  Check,
  Clock,
  ShieldX,
  Copy,
  ChevronLeft,
  ChevronRight,
  LoaderCircle,
} from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./ui/button";
import { useApp } from "./context";
import { statusName } from "@/lib/api";
export function Badge({ value }: { value: string }) {
  const approved = [
    "APPROVE",
    "active",
    "approved",
    "authorized",
    "completed",
    "delivered",
    "connected",
    "simulated",
  ].includes(value);
  const ask = ["ASK", "pending", "held", "retry"].includes(value);
  const deny = [
    "DENY",
    "denied",
    "rejected",
    "failed",
    "revoked",
    "suspended",
  ].includes(value);
  return (
    <span
      className={`badge ${approved ? "success" : ask ? "warning" : deny ? "danger" : "muted"}`}
    >
      {value === "APPROVE" ? (
        <Check size={12} />
      ) : value === "ASK" ? (
        <Clock size={12} />
      ) : value === "DENY" ? (
        <ShieldX size={12} />
      ) : (
        <i />
      )}
      {["APPROVE", "ASK", "DENY"].includes(value) ? value : statusName(value)}
    </span>
  );
}
export function PageTitle({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function Panel({
  title,
  description,
  action,
  children,
  className = "",
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-heading">
          <div>
            <h2>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function Empty({
  title = "Пока нет записей",
  description = "Новые операции появятся здесь.",
  action,
}: {
  title?: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <ArrowUpRight size={23} />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading">
      <LoaderCircle size={22} className="spin" />
      <span>Загружаем данные…</span>
    </div>
  );
}
export function Failure({
  error,
  retry,
}: {
  error: Error | null;
  retry?: () => void;
}) {
  return (
    <div role="alert" className="error-message">
      <AlertCircle size={18} />
      {error?.message || "Данные недоступны"}
      {retry && (
        <Button variant="outline" size="sm" onClick={retry}>
          Повторить
        </Button>
      )}
    </div>
  );
}
export function CopyButton({
  text,
  label = "Копировать",
}: {
  text: string;
  label?: string;
}) {
  const { notify } = useApp();
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          notify("Скопировано");
        } catch {
          notify("Буфер обмена недоступен", true);
        }
      }}
    >
      <Copy size={14} />
      {label}
    </Button>
  );
}
export function Pager({
  total,
  offset,
  limit,
  setOffset,
}: {
  total: number;
  offset: number;
  limit: number;
  setOffset: (n: number) => void;
}) {
  return (
    <div className="pager">
      <span>
        {total
          ? `${offset + 1}–${Math.min(total, offset + limit)} из ${total}`
          : "0 записей"}
      </span>
      <div>
        <Button
          size="icon"
          variant="outline"
          aria-label="Предыдущая страница"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - limit))}
        >
          <ChevronLeft size={16} />
        </Button>
        <Button
          size="icon"
          variant="outline"
          aria-label="Следующая страница"
          disabled={offset + limit >= total}
          onClick={() => setOffset(offset + limit)}
        >
          <ChevronRight size={16} />
        </Button>
      </div>
    </div>
  );
}
