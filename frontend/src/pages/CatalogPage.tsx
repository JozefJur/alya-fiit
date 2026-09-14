import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { catalogApi } from "../api/endpoints";
import type { CatalogFilters } from "../api/endpoints";
import { EmptyState, ErrorMessage, MoneyText, Pagination, Spinner } from "../components/common";
import type { Category, ProductPage } from "../types/api";

const PAGE_SIZE = 12;

export default function CatalogPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [filters, setFilters] = useState<CatalogFilters>({ sort: "name", page: 1 });
  const [searchInput, setSearchInput] = useState("");
  const [result, setResult] = useState<ProductPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    catalogApi.categories().then(setCategories).catch(() => setCategories([]));
    catalogApi.brands().then((r) => setBrands(r.brands)).catch(() => setBrands([]));
  }, []);

  // Changing a filter starts a new request while the previous one may still be
  // in flight; without this guard a slower earlier response would overwrite the
  // newer results.
  const requestId = useRef(0);

  const load = useCallback(async (current: CatalogFilters) => {
    const thisRequest = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const page = await catalogApi.products({ ...current, page_size: PAGE_SIZE });
      if (thisRequest === requestId.current) setResult(page);
    } catch (err) {
      if (thisRequest === requestId.current) setError(err);
    } finally {
      if (thisRequest === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(filters);
  }, [filters, load]);

  const update = (patch: Partial<CatalogFilters>) =>
    setFilters((prev) => ({ ...prev, ...patch, page: patch.page ?? 1 }));

  return (
    <div>
      <h1>Catalog</h1>
      <div className="filters card" data-testid="catalog-filters">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            update({ search: searchInput });
          }}
        >
          <input
            type="search"
            placeholder="Search by name or brand…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            data-testid="search-input"
          />
          <button type="submit" data-testid="search-submit">
            Search
          </button>
        </form>
        <select
          value={filters.category_id ?? ""}
          onChange={(e) =>
            update({ category_id: e.target.value ? Number(e.target.value) : undefined })
          }
          data-testid="filter-category"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          value={filters.brand ?? ""}
          onChange={(e) => update({ brand: e.target.value || undefined })}
          data-testid="filter-brand"
        >
          <option value="">All brands</option>
          {brands.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
        <input
          type="number"
          min={0}
          placeholder="Min €"
          value={filters.price_min ?? ""}
          onChange={(e) => update({ price_min: e.target.value || undefined })}
          data-testid="filter-price-min"
        />
        <input
          type="number"
          min={0}
          placeholder="Max €"
          value={filters.price_max ?? ""}
          onChange={(e) => update({ price_max: e.target.value || undefined })}
          data-testid="filter-price-max"
        />
        <label className="checkbox">
          <input
            type="checkbox"
            checked={filters.in_stock_only ?? false}
            onChange={(e) => update({ in_stock_only: e.target.checked })}
            data-testid="filter-in-stock"
          />
          In stock
        </label>
        <select
          value={filters.sort}
          onChange={(e) => update({ sort: e.target.value })}
          data-testid="filter-sort"
        >
          <option value="name">Name</option>
          <option value="price_asc">Price ↑</option>
          <option value="price_desc">Price ↓</option>
          <option value="newest">Newest</option>
        </select>
      </div>

      <ErrorMessage error={error} />
      {loading && <Spinner />}
      {!loading && result && result.items.length === 0 && (
        <EmptyState>No products match your search.</EmptyState>
      )}
      {!loading && result && result.items.length > 0 && (
        <>
          <div className="product-grid" data-testid="product-grid">
            {result?.items.map((product) => {
              const fromPrice = product.variants
                .filter((v) => v.is_active)
                .map((v) => v.price_with_vat)
                .sort((a, b) => Number(a) - Number(b))[0];
              const anyAvailable = product.variants.some((v) => v.is_active && v.available > 0);
              return (
                <Link
                  key={product.id}
                  to={`/products/${product.id}`}
                  className="card product-card"
                  data-testid={`product-card-${product.id}`}
                >
                  <div className="muted">{product.brand}</div>
                  <h3>{product.name}</h3>
                  <div className="muted">{product.category_name}</div>
                  <div className="product-card-footer">
                    {fromPrice ? (
                      <span>
                        from <MoneyText value={fromPrice} />
                      </span>
                    ) : (
                      <span className="muted">no variants</span>
                    )}
                    <span className={anyAvailable ? "stock-ok" : "stock-out"}>
                      {anyAvailable ? "in stock" : "out of stock"}
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
          {result && (
            <Pagination
              page={result.page}
              pageSize={result.page_size}
              total={result.total}
              onPage={(page) => setFilters((prev) => ({ ...prev, page }))}
            />
          )}
        </>
      )}
    </div>
  );
}
