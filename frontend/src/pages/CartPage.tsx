import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { cartApi } from "../api/endpoints";
import { EmptyState, ErrorMessage, MoneyText, Spinner } from "../components/common";
import { useCartBadge } from "../hooks/useCartBadge";
import type { Cart } from "../types/api";

export default function CartPage() {
  const navigate = useNavigate();
  const { refresh } = useCartBadge();
  const [cart, setCart] = useState<Cart | null>(null);
  const [couponInput, setCouponInput] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);

  const sync = (next: Cart) => {
    setCart(next);
    void refresh();
  };

  useEffect(() => {
    cartApi
      .get()
      .then(setCart)
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);

  const run = async (action: () => Promise<Cart>) => {
    setError(null);
    try {
      sync(await action());
    } catch (err) {
      setError(err);
      try {
        sync(await cartApi.get());
      } catch {
        /* keep previous view */
      }
    }
  };

  if (loading) return <Spinner />;
  if (!cart) return <ErrorMessage error={error} />;

  return (
    <div>
      <h1>Your cart</h1>
      <ErrorMessage error={error} />
      {cart.problems.length > 0 && (
        <div className="alert alert-warn" data-testid="cart-problems">
          {cart.problems.map((p) => (
            <div key={`${p.variant_id}-${p.code}`}>{p.message}</div>
          ))}
        </div>
      )}
      {cart.items.length === 0 ? (
        <EmptyState>
          Your cart is empty. <Link to="/">Browse the catalog →</Link>
        </EmptyState>
      ) : (
        <div className="cart-layout">
          <table className="table" data-testid="cart-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Unit (net)</th>
                <th>Qty</th>
                <th>Discount</th>
                <th>VAT</th>
                <th>Total</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {cart.items.map((line) => (
                <tr key={line.variant_id} data-testid={`cart-line-${line.sku}`}>
                  <td>
                    <div>{line.product_name}</div>
                    <div className="muted">{line.sku}</div>
                  </td>
                  <td>
                    <MoneyText value={line.unit_price} />
                  </td>
                  <td>
                    <input
                      type="number"
                      min={0}
                      max={10}
                      value={line.quantity}
                      onChange={(e) =>
                        void run(() => cartApi.updateItem(line.variant_id, Number(e.target.value)))
                      }
                      data-testid={`quantity-${line.sku}`}
                    />
                  </td>
                  <td>
                    <MoneyText value={line.discount} />
                  </td>
                  <td>
                    <MoneyText value={line.vat} />
                  </td>
                  <td>
                    <MoneyText value={line.line_total} />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="linklike"
                      onClick={() => void run(() => cartApi.removeItem(line.variant_id))}
                      data-testid={`remove-${line.sku}`}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="card cart-summary" data-testid="cart-summary">
            <h2>Summary</h2>
            <div className="summary-row">
              <span>Subtotal (net)</span>
              <MoneyText value={cart.subtotal} />
            </div>
            <div className="summary-row">
              <span>Discount</span>
              <span data-testid="summary-discount">
                −<MoneyText value={cart.discount_total} />
              </span>
            </div>
            <div className="summary-row">
              <span>VAT</span>
              <MoneyText value={cart.vat_total} />
            </div>
            <div className="summary-row total">
              <span>Total</span>
              <span data-testid="summary-total">
                <MoneyText value={cart.grand_total} />
              </span>
            </div>

            <div className="coupon-box">
              {cart.coupon_code ? (
                <div className="coupon-applied" data-testid="coupon-applied">
                  Coupon <strong>{cart.coupon_code}</strong>
                  <button
                    type="button"
                    className="linklike"
                    onClick={() => void run(() => cartApi.removeCoupon())}
                    data-testid="remove-coupon"
                  >
                    remove
                  </button>
                </div>
              ) : (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (couponInput.trim()) {
                      void run(() => cartApi.applyCoupon(couponInput.trim()));
                    }
                  }}
                >
                  <input
                    type="text"
                    placeholder="Coupon code"
                    value={couponInput}
                    onChange={(e) => setCouponInput(e.target.value)}
                    data-testid="coupon-input"
                  />
                  <button type="submit" data-testid="apply-coupon">
                    Apply
                  </button>
                </form>
              )}
              {cart.coupon_error && (
                <div className="alert alert-warn" data-testid="coupon-error">
                  {cart.coupon_error}
                </div>
              )}
            </div>

            <button
              type="button"
              className="primary"
              onClick={() => navigate("/checkout")}
              disabled={cart.items.length === 0 || cart.problems.length > 0}
              data-testid="go-checkout"
            >
              Checkout →
            </button>
            <button
              type="button"
              className="linklike"
              onClick={() => void run(() => cartApi.clear())}
              data-testid="clear-cart"
            >
              Empty the cart
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
