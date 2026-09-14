import { useCallback, useEffect, useState } from "react";

import { adminApi } from "../api/endpoints";
import { ErrorMessage, Spinner, formatDateTime } from "../components/common";
import type { Category, Coupon } from "../types/api";

export default function AdminCouponsPage() {
  const [coupons, setCoupons] = useState<Coupon[] | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [error, setError] = useState<unknown>(null);

  const [code, setCode] = useState("");
  const [type, setType] = useState<"percent" | "fixed">("percent");
  const [value, setValue] = useState("10");
  const [validFrom, setValidFrom] = useState(new Date().toISOString().slice(0, 10));
  const [validUntil, setValidUntil] = useState(
    new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10)
  );
  const [minTotal, setMinTotal] = useState("");
  const [maxUses, setMaxUses] = useState("");
  const [categoryId, setCategoryId] = useState<number | "">("");

  const load = useCallback(() => {
    adminApi.coupons().then(setCoupons).catch(setError);
  }, []);

  useEffect(() => {
    load();
    adminApi.categories().then(setCategories).catch(() => setCategories([]));
  }, [load]);

  if (!coupons) return error ? <ErrorMessage error={error} /> : <Spinner />;

  const create = async () => {
    setError(null);
    try {
      await adminApi.createCoupon({
        code,
        discount_type: type,
        value,
        valid_from: `${validFrom}T00:00:00`,
        valid_until: `${validUntil}T23:59:59`,
        min_cart_total: minTotal || null,
        max_uses: maxUses ? Number(maxUses) : null,
        category_id: categoryId === "" ? null : categoryId,
      });
      setCode("");
      load();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <div>
      <h1>Coupons</h1>
      <ErrorMessage error={error} />

      <div className="card" data-testid="new-coupon-form">
        <h2>New coupon</h2>
        <div className="field-row">
          <label>
            Code
            <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} data-testid="coupon-code" />
          </label>
          <label>
            Type
            <select value={type} onChange={(e) => setType(e.target.value as "percent" | "fixed")} data-testid="coupon-type">
              <option value="percent">% of eligible subtotal</option>
              <option value="fixed">fixed € amount</option>
            </select>
          </label>
          <label>
            Value
            <input value={value} onChange={(e) => setValue(e.target.value)} data-testid="coupon-value" />
          </label>
          <label>
            Valid from
            <input type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
          </label>
          <label>
            Valid until
            <input type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} data-testid="coupon-until" />
          </label>
          <label>
            Min cart total (net €)
            <input value={minTotal} onChange={(e) => setMinTotal(e.target.value)} placeholder="none" data-testid="coupon-min" />
          </label>
          <label>
            Max uses
            <input value={maxUses} onChange={(e) => setMaxUses(e.target.value)} placeholder="unlimited" />
          </label>
          <label>
            Category restriction
            <select
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : "")}
              data-testid="coupon-category"
            >
              <option value="">none</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <button type="button" onClick={() => void create()} data-testid="coupon-save">
          Create coupon
        </button>
      </div>

      <table className="table" data-testid="coupons-table">
        <thead>
          <tr>
            <th>Code</th>
            <th>Discount</th>
            <th>Validity</th>
            <th>Min total</th>
            <th>Uses</th>
            <th>Category</th>
            <th>Active</th>
          </tr>
        </thead>
        <tbody>
          {coupons.map((coupon) => (
            <tr key={coupon.id} data-testid={`coupon-row-${coupon.code}`}>
              <td>
                <strong>{coupon.code}</strong>
              </td>
              <td>
                {coupon.discount_type === "percent" ? `${Number(coupon.value)} %` : `${coupon.value} €`}
              </td>
              <td className="muted">
                {formatDateTime(coupon.valid_from).split(",")[0]} – {formatDateTime(coupon.valid_until).split(",")[0]}
              </td>
              <td>{coupon.min_cart_total ? `${coupon.min_cart_total} €` : "—"}</td>
              <td>
                {coupon.used_count}
                {coupon.max_uses ? ` / ${coupon.max_uses}` : ""}
              </td>
              <td>{categories.find((c) => c.id === coupon.category_id)?.name ?? "—"}</td>
              <td>
                <button
                  type="button"
                  className="linklike"
                  onClick={() => {
                    setError(null);
                    adminApi
                      .setCouponActive(coupon.id, !coupon.is_active)
                      .then(load)
                      .catch(setError);
                  }}
                  data-testid={`coupon-toggle-${coupon.code}`}
                >
                  {coupon.is_active ? "✔ active" : "✖ inactive"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
