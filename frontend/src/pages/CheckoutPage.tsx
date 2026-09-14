import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { cartApi } from "../api/endpoints";
import { ErrorMessage, MoneyText, Spinner } from "../components/common";
import { useCartBadge } from "../hooks/useCartBadge";
import type { Cart } from "../types/api";

/** ZIP digit counts for the countries the shop delivers to (mirrors the server). */
const ZIP_LENGTH: Record<string, number> = { SK: 5, CZ: 5, AT: 4, HU: 4, PL: 5, DE: 5 };

export default function CheckoutPage() {
  const navigate = useNavigate();
  const { refresh } = useCartBadge();

  const [cart, setCart] = useState<Cart | null>(null);
  const [loadingCart, setLoadingCart] = useState(true);

  const [name, setName] = useState("");
  const [street, setStreet] = useState("");
  const [city, setCity] = useState("");
  const [zip, setZip] = useState("");
  const [country, setCountry] = useState("SK");
  const [paymentToken, setPaymentToken] = useState("tok-success");

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [staleCartNotice, setStaleCartNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    cartApi
      .get()
      .then((c) => {
        setCart(c);
        if (c.items.length === 0) navigate("/cart", { replace: true });
      })
      .catch(setError)
      .finally(() => setLoadingCart(false));
  }, [navigate]);

  const validate = (): boolean => {
    const errors: Record<string, string> = {};
    if (!name.trim()) {
      errors.name = "Enter the recipient name.";
    } else if (name.trim().length < 2) {
      errors.name = "The name looks too short.";
    }
    if (!street.trim()) errors.street = "Enter the street and number.";
    if (!city.trim()) errors.city = "Enter the city.";

    const normalizedCountry = country.trim().toUpperCase();
    const expectedZipLength = ZIP_LENGTH[normalizedCountry];
    if (!normalizedCountry) {
      errors.country = "Choose a country.";
    } else if (expectedZipLength === undefined) {
      errors.country = `We do not ship to ${normalizedCountry}.`;
    }
    const digits = zip.replace(/\s/g, "");
    if (!digits) {
      errors.zip = "Enter the ZIP code.";
    } else if (!/^\d+$/.test(digits)) {
      errors.zip = "The ZIP code may only contain digits.";
    } else if (expectedZipLength !== undefined && digits.length !== expectedZipLength) {
      errors.zip = `A ${normalizedCountry} ZIP code has ${expectedZipLength} digits.`;
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const submit = async () => {
    setError(null);
    setStaleCartNotice(null);
    if (!validate()) return;
    setSubmitting(true);
    try {
      const order = await cartApi.checkout({
        payment_token: paymentToken,
        address: {
          name: name.trim(),
          street: street.trim(),
          city: city.trim(),
          zip_code: zip.replace(/\s/g, ""),
          country: country.trim().toUpperCase(),
        },
        coupon_code: cart?.coupon_code ?? undefined,
      });
      await refresh();
      navigate(`/orders/${order.id}`, { state: { justPlaced: true } });
    } catch (err) {
      setError(err);
      if (err instanceof ApiError) {
        // Map what the server rejected back onto the form fields.
        const field = typeof err.details.field === "string" ? err.details.field : null;
        if (field) {
          const key = field === "zip_code" ? "zip" : field;
          setFieldErrors((prev) => ({ ...prev, [key]: err.message }));
        }
        if (err.code === "validation_error" && Array.isArray(err.details.errors)) {
          const mapped: Record<string, string> = {};
          for (const item of err.details.errors as { loc?: unknown[]; msg?: string }[]) {
            const location = Array.isArray(item.loc) ? item.loc : [];
            const last = location[location.length - 1];
            if (typeof last === "string" && item.msg) {
              mapped[last === "zip_code" ? "zip" : last] = item.msg;
            }
          }
          if (Object.keys(mapped).length > 0) {
            setFieldErrors((prev) => ({ ...prev, ...mapped }));
          }
        }
        // Stock and pricing problems mean the cart is out of date — refetch it
        // and tell the customer what changed.
        if (
          err.code === "insufficient_stock" ||
          err.code === "product_not_available" ||
          err.code === "validation_error" ||
          err.code === "coupon_not_eligible"
        ) {
          try {
            const fresh = await cartApi.get();
            const previousTotal = cart?.grand_total;
            setCart(fresh);
            if (previousTotal && previousTotal !== fresh.grand_total) {
              setStaleCartNotice(
                `The total changed from ${previousTotal} € to ${fresh.grand_total} € while you were checking out.`
              );
            } else if (fresh.problems.length > 0) {
              setStaleCartNotice(fresh.problems.map((problem) => problem.message).join(" "));
            }
            if (fresh.items.length === 0) navigate("/cart", { replace: true });
          } catch {
            /* keep the current cart view */
          }
        }
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (loadingCart) return <Spinner />;
  if (!cart) return <ErrorMessage error={error} />;

  return (
    <div>
      <h1>Checkout</h1>
      <div className="checkout-layout">
        <div className="card">
          <h2>Delivery address</h2>
          <label>
            Recipient name
            <input value={name} onChange={(e) => setName(e.target.value)} data-testid="address-name" />
            {fieldErrors.name && <span className="field-error">{fieldErrors.name}</span>}
          </label>
          <label>
            Street and number
            <input value={street} onChange={(e) => setStreet(e.target.value)} data-testid="address-street" />
            {fieldErrors.street && <span className="field-error">{fieldErrors.street}</span>}
          </label>
          <div className="field-row">
            <label>
              City
              <input value={city} onChange={(e) => setCity(e.target.value)} data-testid="address-city" />
              {fieldErrors.city && <span className="field-error">{fieldErrors.city}</span>}
            </label>
            <label>
              ZIP
              <input value={zip} onChange={(e) => setZip(e.target.value)} data-testid="address-zip" />
              {fieldErrors.zip && <span className="field-error">{fieldErrors.zip}</span>}
            </label>
            <label>
              Country
              <select
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                data-testid="address-country"
              >
                {Object.keys(ZIP_LENGTH).map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </select>
              {fieldErrors.country && <span className="field-error">{fieldErrors.country}</span>}
            </label>
          </div>

          <h2>Payment</h2>
          <p className="muted">
            Payments run against the sandbox provider — pick the outcome to simulate.
          </p>
          <div className="payment-options" data-testid="payment-options">
            <label className={paymentToken === "tok-success" ? "selected" : ""}>
              <input
                type="radio"
                name="payment"
                checked={paymentToken === "tok-success"}
                onChange={() => setPaymentToken("tok-success")}
                data-testid="pay-success"
              />
              Simulated card — <strong>authorized</strong>
            </label>
            <label className={paymentToken === "tok-declined" ? "selected" : ""}>
              <input
                type="radio"
                name="payment"
                checked={paymentToken === "tok-declined"}
                onChange={() => setPaymentToken("tok-declined")}
                data-testid="pay-declined"
              />
              Simulated card — <strong>declined</strong>
            </label>
            <label className={paymentToken === "tok-timeout" ? "selected" : ""}>
              <input
                type="radio"
                name="payment"
                checked={paymentToken === "tok-timeout"}
                onChange={() => setPaymentToken("tok-timeout")}
                data-testid="pay-timeout"
              />
              Simulated card — <strong>timeout</strong>
            </label>
          </div>
        </div>

        <div className="card cart-summary">
          <h2>Order summary</h2>
          {cart.items.map((line) => (
            <div className="summary-row" key={line.variant_id}>
              <span>
                {line.quantity}× {line.product_name}
              </span>
              <MoneyText value={line.line_total} />
            </div>
          ))}
          <hr />
          <div className="summary-row">
            <span>Subtotal (net)</span>
            <MoneyText value={cart.subtotal} />
          </div>
          <div className="summary-row">
            <span>Discount {cart.coupon_code ? `(${cart.coupon_code})` : ""}</span>
            <span>
              −<MoneyText value={cart.discount_total} />
            </span>
          </div>
          <div className="summary-row">
            <span>VAT</span>
            <MoneyText value={cart.vat_total} />
          </div>
          <div className="summary-row total">
            <span>Total to pay</span>
            <span data-testid="checkout-total">
              <MoneyText value={cart.grand_total} />
            </span>
          </div>

          <ErrorMessage error={error} />
          {staleCartNotice && (
            <div className="alert alert-warn" data-testid="stale-cart-notice">
              {staleCartNotice}
            </div>
          )}
          <button
            type="button"
            className="primary"
            onClick={() => void submit()}
            disabled={submitting}
            data-testid="place-order"
          >
            {submitting ? "Processing payment…" : "Place order and pay"}
          </button>
          <Link to="/cart" className="muted">
            ← Back to cart
          </Link>
        </div>
      </div>
    </div>
  );
}
