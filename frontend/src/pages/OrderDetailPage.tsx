import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { ordersApi } from "../api/endpoints";
import {
  ErrorMessage,
  InfoMessage,
  MoneyText,
  Spinner,
  StatusBadge,
  formatDateTime,
} from "../components/common";
import type { OrderDetail } from "../types/api";

export default function OrderDetailPage() {
  const { id } = useParams();
  const location = useLocation() as { state?: { justPlaced?: boolean } };
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [actionError, setActionError] = useState<unknown>(null);
  const [reason, setReason] = useState("");

  const load = useCallback(() => {
    ordersApi.detail(Number(id)).then(setOrder).catch(setError);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorMessage error={error} />;
  if (!order) return <Spinner />;

  const act = async (call: () => Promise<unknown>) => {
    setActionError(null);
    try {
      await call();
      load();
    } catch (err) {
      setActionError(err);
    }
  };

  const can = (event: string) => order.allowed_events.includes(event);
  const failedPayment = order.payments.find((p) => p.status === "declined" || p.status === "timeout");

  return (
    <div>
      <Link to="/orders" className="muted">
        ← My orders
      </Link>
      <div className="order-header">
        <h1 data-testid="order-number">{order.order_number}</h1>
        <StatusBadge status={order.status} />
      </div>

      {location.state?.justPlaced && order.status === "PAID" && (
        <InfoMessage>
          <span data-testid="order-confirmation">
            Thank you! Your payment was authorized and the order is confirmed.
          </span>
        </InfoMessage>
      )}
      {order.status === "PAYMENT_FAILED" && (
        <div className="alert alert-error" data-testid="payment-failed-box">
          The payment was not completed
          {failedPayment ? ` (${failedPayment.status})` : ""}. No money was taken and the
          reserved items were released back to stock. Your cart is untouched — you can{" "}
          <Link to="/cart">try again</Link>.
        </div>
      )}
      {order.status === "SHIPPED" && order.expected_delivery && (
        <InfoMessage>
          Estimated delivery: <strong data-testid="expected-delivery">{order.expected_delivery}</strong>
        </InfoMessage>
      )}

      <div className="order-layout">
        <div className="card">
          <h2>Items</h2>
          <table className="table" data-testid="order-items">
            <thead>
              <tr>
                <th>Item</th>
                <th>Unit (net)</th>
                <th>Qty</th>
                <th>Discount</th>
                <th>VAT</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {order.items.map((item) => (
                <tr key={item.variant_id}>
                  <td>
                    <div>{item.product_name}</div>
                    <div className="muted">{item.sku}</div>
                  </td>
                  <td>
                    <MoneyText value={item.unit_price} />
                  </td>
                  <td>{item.quantity}</td>
                  <td>
                    <MoneyText value={item.discount_amount} />
                  </td>
                  <td>
                    <MoneyText value={item.vat_amount} />
                  </td>
                  <td>
                    <MoneyText value={item.line_total} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="summary-row">
            <span>Subtotal (net)</span>
            <MoneyText value={order.subtotal} />
          </div>
          <div className="summary-row">
            <span>Discount {order.coupon_code ? `(${order.coupon_code})` : ""}</span>
            <span>
              −<MoneyText value={order.discount_total} />
            </span>
          </div>
          <div className="summary-row">
            <span>VAT</span>
            <MoneyText value={order.vat_total} />
          </div>
          <div className="summary-row total">
            <span>Total</span>
            <span data-testid="order-total">
              <MoneyText value={order.grand_total} />
            </span>
          </div>
        </div>

        <div>
          <div className="card">
            <h2>Delivery</h2>
            <p data-testid="order-address">
              {order.ship_to_name}
              <br />
              {order.ship_street}
              <br />
              {order.ship_zip} {order.ship_city}, {order.ship_country}
            </p>
          </div>

          {(can("cancel") || can("request_cancel") || can("request_return")) && (
            <div className="card" data-testid="order-actions">
              <h2>Actions</h2>
              <ErrorMessage error={actionError} />
              <label>
                Reason (optional)
                <input value={reason} onChange={(e) => setReason(e.target.value)} data-testid="action-reason" />
              </label>
              {can("cancel") && (
                <button
                  type="button"
                  onClick={() => void act(() => ordersApi.cancel(order.id, reason))}
                  data-testid="cancel-order"
                >
                  Cancel order
                </button>
              )}
              {can("request_cancel") && (
                <button
                  type="button"
                  onClick={() => void act(() => ordersApi.requestCancel(order.id, reason))}
                  data-testid="request-cancel"
                >
                  Request cancellation
                </button>
              )}
              {can("request_return") && (
                <button
                  type="button"
                  onClick={() => void act(() => ordersApi.requestReturn(order.id, reason))}
                  data-testid="request-return"
                >
                  Request return
                </button>
              )}
            </div>
          )}

          <div className="card">
            <h2>History</h2>
            <ul className="timeline" data-testid="order-history">
              {order.status_history.map((entry, index) => (
                <li key={index}>
                  <span className="muted">{formatDateTime(entry.created_at)}</span>{" "}
                  {entry.from_status ? `${entry.from_status} → ` : ""}
                  <strong>{entry.to_status}</strong>
                  {entry.note ? <span className="muted"> — {entry.note}</span> : null}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
