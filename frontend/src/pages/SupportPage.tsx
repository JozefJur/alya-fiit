import { useCallback, useEffect, useState } from "react";

import { supportApi } from "../api/endpoints";
import {
  EmptyState,
  ErrorMessage,
  MoneyText,
  Spinner,
  StatusBadge,
  formatDateTime,
} from "../components/common";
import type { OrderRequestInfo, OrderSummary } from "../types/api";

export default function SupportPage() {
  const [requests, setRequests] = useState<OrderRequestInfo[] | null>(null);
  const [orders, setOrders] = useState<OrderSummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState("");

  const load = useCallback(() => {
    supportApi.requests().then(setRequests).catch(setError);
    supportApi.orders().then(setOrders).catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (call: () => Promise<unknown>) => {
    setError(null);
    try {
      await call();
      load();
    } catch (err) {
      setError(err);
    }
  };

  if (!requests || !orders) return error ? <ErrorMessage error={error} /> : <Spinner />;

  const refundable = orders.filter((o) => o.status === "RETURNED");
  const cancellable = orders.filter(
    (o) => o.status === "PENDING_PAYMENT" || o.status === "PAID"
  );

  return (
    <div>
      <h1>Support</h1>
      <ErrorMessage error={error} />

      <h2>Pending requests</h2>
      {requests.length === 0 ? (
        <EmptyState>No pending cancellation or return requests.</EmptyState>
      ) : (
        <table className="table" data-testid="requests-table">
          <thead>
            <tr>
              <th>Order</th>
              <th>Type</th>
              <th>Reason</th>
              <th>Requested</th>
              <th>Decision note</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {requests.map((request) => (
              <tr key={request.id} data-testid={`request-row-${request.id}`}>
                <td>{request.order_number}</td>
                <td>
                  <span className="badge badge-warn">{request.request_type}</span>
                </td>
                <td>{request.reason || <span className="muted">—</span>}</td>
                <td>{formatDateTime(request.created_at)}</td>
                <td>
                  <input
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="optional note"
                    data-testid={`note-${request.id}`}
                  />
                </td>
                <td>
                  <button
                    type="button"
                    onClick={() => void act(() => supportApi.approve(request.id, note))}
                    data-testid={`approve-${request.id}`}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className="linklike"
                    onClick={() => void act(() => supportApi.reject(request.id, note))}
                    data-testid={`reject-${request.id}`}
                  >
                    Reject
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {refundable.length > 0 && (
        <>
          <h2>Returned orders awaiting refund</h2>
          <table className="table" data-testid="refundable-table">
            <tbody>
              {refundable.map((order) => (
                <tr key={order.id}>
                  <td>{order.order_number}</td>
                  <td>
                    <MoneyText value={order.grand_total} />
                  </td>
                  <td>
                    <button
                      type="button"
                      onClick={() => void act(() => supportApi.refund(order.id))}
                      data-testid={`refund-${order.order_number}`}
                    >
                      Refund
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h2>All orders</h2>
      <table className="table" data-testid="support-orders">
        <thead>
          <tr>
            <th>Order</th>
            <th>Customer</th>
            <th>Created</th>
            <th>Total</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr key={order.id} data-testid={`support-order-${order.order_number}`}>
              <td>{order.order_number}</td>
              <td className="muted">{order.customer_email ?? order.customer_id}</td>
              <td>{formatDateTime(order.created_at)}</td>
              <td>
                <MoneyText value={order.grand_total} />
              </td>
              <td>
                <StatusBadge status={order.status} />
              </td>
              <td>
                {cancellable.some((o) => o.id === order.id) && (
                  <button
                    type="button"
                    className="linklike"
                    onClick={() => void act(() => supportApi.cancel(order.id, "Support cancellation"))}
                    data-testid={`support-cancel-${order.order_number}`}
                  >
                    Cancel
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
