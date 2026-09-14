import { useCallback, useEffect, useState } from "react";

import { warehouseApi } from "../api/endpoints";
import {
  EmptyState,
  ErrorMessage,
  MoneyText,
  Spinner,
  StatusBadge,
  formatDateTime,
} from "../components/common";
import type { OrderStatus, OrderSummary } from "../types/api";

const NEXT_ACTION: Partial<
  Record<OrderStatus, { label: string; testid: string; call: (id: number) => Promise<unknown> }>
> = {
  PAID: { label: "Start picking", testid: "start-picking", call: warehouseApi.startPicking },
  PICKING: { label: "Mark ready", testid: "mark-ready", call: warehouseApi.markReady },
  READY_TO_SHIP: { label: "Ship", testid: "ship", call: warehouseApi.ship },
  SHIPPED: { label: "Mark delivered", testid: "mark-delivered", call: warehouseApi.markDelivered },
  RETURN_APPROVED: {
    label: "Receive return",
    testid: "receive-return",
    call: warehouseApi.receiveReturn,
  },
};

export default function WarehousePage() {
  const [orders, setOrders] = useState<OrderSummary[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    warehouseApi.queue().then(setOrders).catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!orders) return error ? <ErrorMessage error={error} /> : <Spinner />;

  const act = async (call: (id: number) => Promise<unknown>, id: number) => {
    setError(null);
    try {
      await call(id);
      load();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <div>
      <h1>Warehouse work queue</h1>
      <ErrorMessage error={error} />
      {orders.length === 0 ? (
        <EmptyState>No orders waiting for the warehouse.</EmptyState>
      ) : (
        <table className="table" data-testid="warehouse-queue">
          <thead>
            <tr>
              <th>Order</th>
              <th>Customer</th>
              <th>Created</th>
              <th>Items</th>
              <th>Total</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => {
              const action = NEXT_ACTION[order.status];
              return (
                <tr key={order.id} data-testid={`queue-row-${order.order_number}`}>
                  <td>{order.order_number}</td>
                  <td className="muted">{order.customer_email ?? order.customer_id}</td>
                  <td>{formatDateTime(order.created_at)}</td>
                  <td>{order.items_count}</td>
                  <td>
                    <MoneyText value={order.grand_total} />
                  </td>
                  <td>
                    <StatusBadge status={order.status} />
                  </td>
                  <td>
                    {action ? (
                      <button
                        type="button"
                        onClick={() => void act(action.call, order.id)}
                        data-testid={`${action.testid}-${order.order_number}`}
                      >
                        {action.label}
                      </button>
                    ) : (
                      <span className="muted" data-testid={`waiting-${order.order_number}`}>
                        waiting for support
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
