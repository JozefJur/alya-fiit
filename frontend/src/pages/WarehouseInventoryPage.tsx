import { useCallback, useEffect, useState } from "react";

import { warehouseApi } from "../api/endpoints";
import { ErrorMessage, Spinner } from "../components/common";
import type { StockLevel } from "../types/api";

export default function WarehouseInventoryPage() {
  const [levels, setLevels] = useState<StockLevel[] | null>(null);
  const [filter, setFilter] = useState("");
  const [lowOnly, setLowOnly] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [adjusting, setAdjusting] = useState<StockLevel | null>(null);
  const [change, setChange] = useState(0);
  const [reason, setReason] = useState("");

  const load = useCallback(() => {
    warehouseApi.inventory().then(setLevels).catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!levels) return error ? <ErrorMessage error={error} /> : <Spinner />;

  const visible = levels.filter(
    (level) =>
      (!lowOnly || level.is_low_stock) &&
      (filter === "" ||
        level.sku.toLowerCase().includes(filter.toLowerCase()) ||
        level.product_name.toLowerCase().includes(filter.toLowerCase()))
  );

  const submitAdjust = async () => {
    if (!adjusting) return;
    setError(null);
    try {
      await warehouseApi.adjust(adjusting.variant_id, change, reason);
      setAdjusting(null);
      setChange(0);
      setReason("");
      load();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <div>
      <h1>Inventory</h1>
      <div className="filters card">
        <input
          type="search"
          placeholder="Filter by SKU or product…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          data-testid="inventory-filter"
        />
        <label className="checkbox">
          <input
            type="checkbox"
            checked={lowOnly}
            onChange={(e) => setLowOnly(e.target.checked)}
            data-testid="inventory-low-only"
          />
          Low stock only
        </label>
      </div>
      <ErrorMessage error={error} />

      {adjusting && (
        <div className="card adjust-box" data-testid="adjust-box">
          <h2>
            Adjust stock — {adjusting.sku} ({adjusting.product_name})
          </h2>
          <p className="muted">
            On hand {adjusting.on_hand}, reserved {adjusting.reserved}. A reason is required and
            every change is audited.
          </p>
          <div className="field-row">
            <label>
              Change (±)
              <input
                type="number"
                value={change}
                onChange={(e) => setChange(Number(e.target.value))}
                data-testid="adjust-change"
              />
            </label>
            <label>
              Reason
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Stocktake correction"
                data-testid="adjust-reason"
              />
            </label>
          </div>
          <button type="button" onClick={() => void submitAdjust()} data-testid="adjust-submit">
            Apply adjustment
          </button>
          <button type="button" className="linklike" onClick={() => setAdjusting(null)}>
            Cancel
          </button>
        </div>
      )}

      <table className="table" data-testid="inventory-table">
        <thead>
          <tr>
            <th>SKU</th>
            <th>Product</th>
            <th>On hand</th>
            <th>Reserved</th>
            <th>Available</th>
            <th>Threshold</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {visible.map((level) => (
            <tr
              key={level.variant_id}
              className={level.is_low_stock ? "row-low" : ""}
              data-testid={`stock-row-${level.sku}`}
            >
              <td>{level.sku}</td>
              <td>
                {level.product_name} <span className="muted">{level.variant_name}</span>
              </td>
              <td>{level.on_hand}</td>
              <td>{level.reserved}</td>
              <td data-testid={`available-${level.sku}`}>{level.available}</td>
              <td>
                {level.low_stock_threshold}
                {level.is_low_stock && (
                  <span className="badge badge-warn" data-testid={`low-${level.sku}`}>
                    LOW
                  </span>
                )}
              </td>
              <td>
                <button
                  type="button"
                  className="linklike"
                  onClick={() => setAdjusting(level)}
                  data-testid={`adjust-${level.sku}`}
                >
                  Adjust
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
