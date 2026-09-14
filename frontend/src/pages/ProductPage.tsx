import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { cartApi, catalogApi } from "../api/endpoints";
import { ErrorMessage, InfoMessage, MoneyText, Spinner } from "../components/common";
import { useAuth } from "../hooks/useAuth";
import { useCartBadge } from "../hooks/useCartBadge";
import type { Product, Variant } from "../types/api";

export default function ProductPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { refresh } = useCartBadge();
  const [product, setProduct] = useState<Product | null>(null);
  const [variant, setVariant] = useState<Variant | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [error, setError] = useState<unknown>(null);
  const [added, setAdded] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    catalogApi
      .product(Number(id))
      .then((p) => {
        setProduct(p);
        setVariant(p.variants.find((v) => v.is_active && v.available > 0) ?? p.variants[0] ?? null);
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <Spinner />;
  if (!product) return <ErrorMessage error={error} />;

  const addToCart = async () => {
    if (!variant) return;
    setError(null);
    setAdded(true);
    try {
      await cartApi.addItem(variant.id, quantity);
      await refresh();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <div className="product-detail">
      <Link to="/" className="muted">
        ← Back to catalog
      </Link>
      <div className="card">
        <div className="muted">
          {product.brand} · {product.category_name}
        </div>
        <h1 data-testid="product-name">{product.name}</h1>
        <p>{product.description}</p>

        <h2>Choose a variant</h2>
        <div className="variant-list" data-testid="variant-list">
          {product.variants.map((v) => (
            <label
              key={v.id}
              className={`variant-option ${variant?.id === v.id ? "selected" : ""} ${
                !v.is_active || v.available === 0 ? "disabled" : ""
              }`}
              data-testid={`variant-${v.sku}`}
            >
              <input
                type="radio"
                name="variant"
                checked={variant?.id === v.id}
                onChange={() => setVariant(v)}
                disabled={!v.is_active || v.available === 0}
              />
              <span className="variant-name">{v.name}</span>
              <span className="muted">{v.sku}</span>
              <MoneyText value={v.price_with_vat} />
              <span className={v.available > 0 ? "stock-ok" : "stock-out"} data-testid={`stock-${v.sku}`}>
                {v.available > 0 ? `${v.available} available` : "out of stock"}
              </span>
            </label>
          ))}
        </div>

        <ErrorMessage error={error} />
        {added && (
          <InfoMessage>
            Added to cart.{" "}
            <button type="button" className="linklike" onClick={() => navigate("/cart")} data-testid="go-to-cart">
              Go to cart →
            </button>
          </InfoMessage>
        )}

        {user?.role === "customer" ? (
          <div className="add-to-cart-row">
            <input
              type="number"
              min={1}
              max={10}
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value))}
              data-testid="quantity-input"
            />
            <button
              type="button"
              onClick={addToCart}
              disabled={!variant || variant.available === 0}
              data-testid="add-to-cart"
            >
              Add to cart
            </button>
            <span className="muted">Prices include VAT.</span>
          </div>
        ) : (
          <InfoMessage>Sign in as a customer to order.</InfoMessage>
        )}
      </div>
    </div>
  );
}
