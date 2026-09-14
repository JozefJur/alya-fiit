/** Small shared presentational components. */

import type { ReactNode } from "react";

import { ApiError } from "../api/client";
import type { OrderStatus } from "../types/api";

export function MoneyText({ value }: { value: string }) {
  return <span className="money">{value} €</span>;
}

const STATUS_TONE: Record<OrderStatus, string> = {
  DRAFT: "muted",
  PENDING_PAYMENT: "warn",
  PAID: "ok",
  PICKING: "info",
  READY_TO_SHIP: "info",
  SHIPPED: "info",
  DELIVERED: "ok",
  CANCELLED: "muted",
  PAYMENT_FAILED: "error",
  CANCEL_REQUESTED: "warn",
  RETURN_REQUESTED: "warn",
  RETURN_APPROVED: "info",
  RETURNED: "info",
  REFUNDED: "muted",
};

export function StatusBadge({ status }: { status: OrderStatus }) {
  return (
    <span className={`badge badge-${STATUS_TONE[status] ?? "muted"}`} data-testid="status-badge">
      {status.replaceAll("_", " ")}
    </span>
  );
}

export function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null;
  let message = "Something went wrong.";
  if (error instanceof ApiError || error instanceof Error) {
    message = error.message;
  }
  return (
    <div className="alert alert-error" role="alert" data-testid="error-message">
      {message}
    </div>
  );
}

export function InfoMessage({ children }: { children: ReactNode }) {
  return (
    <div className="alert alert-info" data-testid="info-message">
      {children}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="empty-state" data-testid="empty-state">
      {children}
    </p>
  );
}

export function Spinner() {
  return (
    <p className="muted" data-testid="loading">
      Loading…
    </p>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="pagination" data-testid="pagination">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
        data-testid="pagination-prev"
      >
        ‹ Prev
      </button>
      <span>
        Page {page} / {pages}
      </span>
      <button
        type="button"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
        data-testid="pagination-next"
      >
        Next ›
      </button>
    </div>
  );
}

export function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value.endsWith("Z") ? value : `${value}Z`).toLocaleString();
}
