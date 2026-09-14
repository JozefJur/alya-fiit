import { useCallback, useEffect, useRef, useState } from "react";

import { adminApi } from "../api/endpoints";
import { ErrorMessage, InfoMessage, Pagination, Spinner } from "../components/common";
import type { Category, Product, ProductPage } from "../types/api";

export default function AdminProductsPage() {
  const [result, setResult] = useState<ProductPage | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [showNewProduct, setShowNewProduct] = useState(false);

  const productFileRef = useRef<HTMLInputElement>(null);
  const inventoryFileRef = useRef<HTMLInputElement>(null);

  // Filter changes start a new request while the previous one may still be in
  // flight; without this guard a slower earlier response overwrites the newer
  // results (the list would show the unfiltered page after a search).
  const requestId = useRef(0);

  const load = useCallback(() => {
    const thisRequest = ++requestId.current;
    adminApi
      .products({ search: search || undefined, page, page_size: 20 })
      .then((page) => {
        if (thisRequest === requestId.current) setResult(page);
      })
      .catch((err) => {
        if (thisRequest === requestId.current) setError(err);
      });
  }, [search, page]);

  useEffect(() => {
    load();
    adminApi.categories().then(setCategories).catch(() => setCategories([]));
  }, [load]);

  const act = async (call: () => Promise<unknown>, success?: string) => {
    setError(null);
    setMessage(null);
    try {
      await call();
      if (success) setMessage(success);
      load();
    } catch (err) {
      setError(err);
    }
  };

  const uploadFile = async (
    ref: React.RefObject<HTMLInputElement | null>,
    call: (file: File) => Promise<unknown>,
    label: string
  ) => {
    const file = ref.current?.files?.[0];
    if (!file) return;
    await act(async () => {
      const outcome = (await call(file)) as Record<string, number>;
      setMessage(`${label}: ${JSON.stringify(outcome)}`);
      if (ref.current) ref.current.value = "";
    });
  };

  return (
    <div>
      <h1>Products</h1>
      <ErrorMessage error={error} />
      {message && <InfoMessage>{message}</InfoMessage>}

      <div className="filters card">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            load();
          }}
        >
          <input
            type="search"
            placeholder="Search products…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            data-testid="admin-search"
          />
          <button type="submit">Search</button>
        </form>
        <button type="button" onClick={() => setShowNewProduct((v) => !v)} data-testid="new-product-toggle">
          {showNewProduct ? "Hide form" : "New product"}
        </button>
        <div className="io-controls">
          <label className="file-label">
            Product CSV import
            <input type="file" accept=".csv" ref={productFileRef} data-testid="product-import-file" />
          </label>
          <button
            type="button"
            onClick={() => void uploadFile(productFileRef, adminApi.importProducts, "Products imported")}
            data-testid="product-import-submit"
          >
            Import products
          </button>
          <label className="file-label">
            Inventory CSV import
            <input type="file" accept=".csv" ref={inventoryFileRef} data-testid="inventory-import-file" />
          </label>
          <button
            type="button"
            onClick={() => void uploadFile(inventoryFileRef, adminApi.importInventory, "Inventory imported")}
            data-testid="inventory-import-submit"
          >
            Import inventory
          </button>
          <button
            type="button"
            onClick={() =>
              void act(async () => {
                const csv = await adminApi.exportInventory();
                const blob = new Blob([csv], { type: "text/csv" });
                const link = document.createElement("a");
                link.href = URL.createObjectURL(blob);
                link.download = "inventory.csv";
                link.click();
                URL.revokeObjectURL(link.href);
              })
            }
            data-testid="inventory-export"
          >
            Export inventory CSV
          </button>
        </div>
      </div>

      {showNewProduct && (
        <NewProductForm
          categories={categories}
          onCreate={(payload) => void act(() => adminApi.createProduct(payload), "Product created.")}
        />
      )}

      {!result ? (
        <Spinner />
      ) : (
        <>
          <table className="table" data-testid="admin-products-table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Category</th>
                <th>Base price (net)</th>
                <th>VAT</th>
                <th>Active</th>
                <th>Variants</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {result.items.map((product) => (
                <ProductRow
                  key={product.id}
                  product={product}
                  expanded={expanded === product.id}
                  onToggle={() => setExpanded(expanded === product.id ? null : product.id)}
                  onAct={act}
                />
              ))}
            </tbody>
          </table>
          <Pagination page={result.page} pageSize={result.page_size} total={result.total} onPage={setPage} />
        </>
      )}
    </div>
  );
}

function ProductRow({
  product,
  expanded,
  onToggle,
  onAct,
}: {
  product: Product;
  expanded: boolean;
  onToggle: () => void;
  onAct: (call: () => Promise<unknown>, success?: string) => Promise<void>;
}) {
  const [price, setPrice] = useState(product.base_price);
  const [sku, setSku] = useState("");
  const [variantName, setVariantName] = useState("");
  const [delta, setDelta] = useState("0");
  const [initialStock, setInitialStock] = useState(0);

  return (
    <>
      <tr data-testid={`admin-product-${product.id}`} className={product.is_active ? "" : "row-inactive"}>
        <td>
          <div>{product.name}</div>
          <div className="muted">{product.brand}</div>
        </td>
        <td>{product.category_name}</td>
        <td>
          <input
            className="price-input"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            data-testid={`price-input-${product.id}`}
          />
          <button
            type="button"
            className="linklike"
            onClick={() =>
              void onAct(() => adminApi.updateProduct(product.id, { base_price: price }), "Price updated.")
            }
            data-testid={`price-save-${product.id}`}
          >
            Save
          </button>
        </td>
        <td>{(Number(product.vat_rate) * 100).toFixed(0)} %</td>
        <td>
          <button
            type="button"
            className="linklike"
            onClick={() =>
              void onAct(
                () => adminApi.updateProduct(product.id, { is_active: !product.is_active }),
                product.is_active ? "Product deactivated." : "Product activated."
              )
            }
            data-testid={`toggle-active-${product.id}`}
          >
            {product.is_active ? "✔ active" : "✖ inactive"}
          </button>
        </td>
        <td>{product.variants.length}</td>
        <td>
          <button type="button" className="linklike" onClick={onToggle} data-testid={`expand-${product.id}`}>
            {expanded ? "Hide" : "Variants"}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="variant-row">
          <td colSpan={7}>
            <table className="table inner-table">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Name</th>
                  <th>Price delta</th>
                  <th>Gross price</th>
                  <th>Available</th>
                  <th>Active</th>
                </tr>
              </thead>
              <tbody>
                {product.variants.map((variant) => (
                  <tr key={variant.id}>
                    <td>{variant.sku}</td>
                    <td>{variant.name}</td>
                    <td>{variant.price !== product.base_price ? "≠0" : "0"}</td>
                    <td>{variant.price_with_vat} €</td>
                    <td>{variant.available}</td>
                    <td>
                      <button
                        type="button"
                        className="linklike"
                        onClick={() =>
                          void onAct(
                            () => adminApi.updateVariant(variant.id, { is_active: !variant.is_active }),
                            "Variant updated."
                          )
                        }
                        data-testid={`variant-toggle-${variant.sku}`}
                      >
                        {variant.is_active ? "✔" : "✖"}
                      </button>
                    </td>
                  </tr>
                ))}
                <tr>
                  <td>
                    <input placeholder="SKU" value={sku} onChange={(e) => setSku(e.target.value)} data-testid={`new-variant-sku-${product.id}`} />
                  </td>
                  <td>
                    <input placeholder="Name" value={variantName} onChange={(e) => setVariantName(e.target.value)} />
                  </td>
                  <td>
                    <input placeholder="Δ price" value={delta} onChange={(e) => setDelta(e.target.value)} />
                  </td>
                  <td />
                  <td>
                    <input
                      type="number"
                      min={0}
                      value={initialStock}
                      onChange={(e) => setInitialStock(Number(e.target.value))}
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      onClick={() =>
                        void onAct(
                          () =>
                            adminApi.createVariant(product.id, {
                              sku,
                              name: variantName,
                              price_delta: delta,
                              initial_on_hand: initialStock,
                            }),
                          "Variant created."
                        )
                      }
                      data-testid={`new-variant-save-${product.id}`}
                    >
                      Add
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}

function NewProductForm({
  categories,
  onCreate,
}: {
  categories: Category[];
  onCreate: (payload: Record<string, unknown>) => void;
}) {
  const [name, setName] = useState("");
  const [brand, setBrand] = useState("");
  const [categoryId, setCategoryId] = useState<number | "">("");
  const [basePrice, setBasePrice] = useState("");
  const [description, setDescription] = useState("");

  return (
    <div className="card" data-testid="new-product-form">
      <h2>New product</h2>
      <div className="field-row">
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} data-testid="np-name" />
        </label>
        <label>
          Brand
          <input value={brand} onChange={(e) => setBrand(e.target.value)} data-testid="np-brand" />
        </label>
        <label>
          Category
          <select
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value ? Number(e.target.value) : "")}
            data-testid="np-category"
          >
            <option value="">Choose…</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Base price (net €)
          <input value={basePrice} onChange={(e) => setBasePrice(e.target.value)} data-testid="np-price" />
        </label>
      </div>
      <label>
        Description
        <input value={description} onChange={(e) => setDescription(e.target.value)} data-testid="np-description" />
      </label>
      <button
        type="button"
        onClick={() =>
          onCreate({
            name,
            brand,
            category_id: categoryId,
            base_price: basePrice,
            description,
          })
        }
        data-testid="np-save"
      >
        Create product
      </button>
    </div>
  );
}
