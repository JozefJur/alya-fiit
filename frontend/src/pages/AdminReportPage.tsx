import { useCallback, useEffect, useState } from "react";

import { adminApi } from "../api/endpoints";
import { ErrorMessage, Spinner } from "../components/common";
import type { Category, InventorySalesReport } from "../types/api";

function isoDaysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

export default function AdminReportPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [from, setFrom] = useState(isoDaysAgo(30));
  const [to, setTo] = useState(isoDaysAgo(0));
  const [categoryId, setCategoryId] = useState<number | undefined>();
  const [report, setReport] = useState<InventorySalesReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    adminApi.categories().then(setCategories).catch(() => setCategories([]));
  }, []);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    const started = performance.now();
    try {
      setReport(await adminApi.report({ from, to, category_id: categoryId }));
      setElapsedMs(Math.round(performance.now() - started));
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [from, to, categoryId]);

  useEffect(() => {
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial load only
  }, []);

  const downloadCsv = async () => {
    const csv = await adminApi.reportCsv({ from, to, category_id: categoryId });
    const blob = new Blob([csv], { type: "text/csv" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `inventory-sales-${from}-${to}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <div>
      <h1>Inventory &amp; sales report</h1>
      <div className="filters card">
        <label>
          From
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} data-testid="report-from" />
        </label>
        <label>
          To
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} data-testid="report-to" />
        </label>
        <select
          value={categoryId ?? ""}
          onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : undefined)}
          data-testid="report-category"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <button type="button" onClick={() => void run()} disabled={loading} data-testid="report-run">
          {loading ? "Computing…" : "Run report"}
        </button>
        <button type="button" onClick={() => void downloadCsv()} disabled={!report} data-testid="report-csv">
          Download CSV
        </button>
        {elapsedMs !== null && (
          <span className="muted" data-testid="report-elapsed">
            computed in {elapsedMs} ms
          </span>
        )}
      </div>
      <ErrorMessage error={error} />
      {loading && <Spinner />}

      {report && !loading && (
        <>
          <div className="tiles" data-testid="report-summary">
            <div className="tile">
              <div className="tile-value" data-testid="summary-revenue">{report.summary.revenue} €</div>
              <div className="muted">Revenue ({report.summary.orders_revenue} orders)</div>
            </div>
            <div className="tile">
              <div className="tile-value">{report.summary.average_order_value} €</div>
              <div className="muted">Average order value</div>
            </div>
            <div className="tile">
              <div className="tile-value">{report.summary.discount_total} €</div>
              <div className="muted">Discounts given</div>
            </div>
            <div className="tile">
              <div className="tile-value">
                {report.summary.orders_cancelled} / {report.summary.orders_refunded}
              </div>
              <div className="muted">Cancelled / refunded</div>
            </div>
            <div className="tile">
              <div className="tile-value">{report.summary.total_available}</div>
              <div className="muted">Units available</div>
            </div>
          </div>

          <div className="report-columns">
            <div className="card">
              <h2>Top products</h2>
              <table className="table" data-testid="top-products">
                <tbody>
                  {report.top_products.map((entry) => (
                    <tr key={entry.product_id}>
                      <td>{entry.product_name}</td>
                      <td>{entry.quantity_sold} pcs</td>
                      <td>{entry.revenue} €</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card">
              <h2>Low stock ({report.low_stock.length})</h2>
              <table className="table" data-testid="low-stock">
                <tbody>
                  {report.low_stock.slice(0, 12).map((row) => (
                    <tr key={row.variant_id}>
                      <td>{row.sku}</td>
                      <td>{row.product_name}</td>
                      <td>
                        {row.available} / threshold {row.low_stock_threshold}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {report.high_cancellation_products.length > 0 && (
              <div className="card">
                <h2>High cancellation rate</h2>
                <table className="table" data-testid="high-cancellation">
                  <tbody>
                    {report.high_cancellation_products.map((row) => (
                      <tr key={row.product_id}>
                        <td>{row.product_name}</td>
                        <td>
                          {row.cancelled}/{row.orders} orders
                        </td>
                        <td>{row.ratio}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <h2>Per variant</h2>
          <div className="table-scroll">
            <table className="table" data-testid="report-variants">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Product</th>
                  <th>Sold</th>
                  <th>Revenue</th>
                  <th>Discount</th>
                  <th>On hand</th>
                  <th>Reserved</th>
                  <th>Available</th>
                  <th>Low?</th>
                </tr>
              </thead>
              <tbody>
                {report.variants.slice(0, 100).map((row) => (
                  <tr key={row.variant_id}>
                    <td>{row.sku}</td>
                    <td>{row.product_name}</td>
                    <td>{row.quantity_sold}</td>
                    <td>{row.revenue} €</td>
                    <td>{row.discount} €</td>
                    <td>{row.on_hand}</td>
                    <td>{row.reserved}</td>
                    <td>{row.available}</td>
                    <td>{row.is_low_stock ? "⚠" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {report.variants.length > 100 && (
            <p className="muted">Showing first 100 of {report.variants.length} variants — use the CSV export for the full data.</p>
          )}
        </>
      )}
    </div>
  );
}
