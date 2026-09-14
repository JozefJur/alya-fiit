import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ordersApi } from "../api/endpoints";
import {
  EmptyState,
  ErrorMessage,
  MoneyText,
  Spinner,
  StatusBadge,
  formatDateTime,
} from "../components/common";
import type { OrderSummary } from "../types/api";

export default function OrdersPage() {
  const [orders, setOrders] = useState<OrderSummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    ordersApi.list().then(setOrders).catch(setError);
  }, []);

  if (error) return <ErrorMessage error={error} />;
  if (!orders) return <Spinner />;

  return (
    <div>
      <h1>My orders</h1>
      {orders.length === 0 ? (
        <EmptyState>
          You have no orders yet. <Link to="/">Find something →</Link>
        </EmptyState>
      ) : (
        <table className="table" data-testid="orders-table">
          <thead>
            <tr>
              <th>Order</th>
              <th>Created</th>
              <th>Items</th>
              <th>Total</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.id} data-testid={`order-row-${order.order_number}`}>
                <td>
                  <Link to={`/orders/${order.id}`} data-testid={`order-link-${order.order_number}`}>
                    {order.order_number}
                  </Link>
                </td>
                <td>{formatDateTime(order.created_at)}</td>
                <td>{order.items_count}</td>
                <td>
                  <MoneyText value={order.grand_total} />
                </td>
                <td>
                  <StatusBadge status={order.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
