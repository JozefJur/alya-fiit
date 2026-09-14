/** Typed API surface used by the pages (one function per endpoint). */

import type {
  AdminUser,
  ApiUser,
  AuditEntry,
  Cart,
  Category,
  Coupon,
  ImportResult,
  InventorySalesReport,
  NotificationEntry,
  OrderDetail,
  OrderRequestInfo,
  OrderSummary,
  Product,
  ProductPage,
  StockLevel,
  StockMovement,
  TokenResponse,
} from "../types/api";
import { api } from "./client";

// ---- auth -----------------------------------------------------------------

export const authApi = {
  login: (email: string, password: string) =>
    api.post<TokenResponse>("/api/auth/login", { email, password }),
  me: () => api.get<ApiUser>("/api/auth/me"),
};

// ---- catalog --------------------------------------------------------------

export interface CatalogFilters {
  search?: string;
  category_id?: number;
  brand?: string;
  price_min?: string;
  price_max?: string;
  in_stock_only?: boolean;
  sort?: string;
  page?: number;
  page_size?: number;
}

export const catalogApi = {
  categories: () => api.get<Category[]>("/api/catalog/categories"),
  brands: () => api.get<{ brands: string[] }>("/api/catalog/brands"),
  products: (filters: CatalogFilters) =>
    api.get<ProductPage>("/api/catalog/products", { ...filters }),
  product: (id: number) => api.get<Product>(`/api/catalog/products/${id}`),
};

// ---- cart & checkout ------------------------------------------------------

export interface CheckoutPayload {
  payment_token: string;
  address: { name: string; street: string; city: string; zip_code: string; country: string };
  coupon_code?: string | null;
}

export const cartApi = {
  get: () => api.get<Cart>("/api/cart"),
  addItem: (variant_id: number, quantity: number) =>
    api.post<Cart>("/api/cart/items", { variant_id, quantity }),
  updateItem: (variantId: number, quantity: number) =>
    api.patch<Cart>(`/api/cart/items/${variantId}`, { quantity }),
  removeItem: (variantId: number) => api.delete<Cart>(`/api/cart/items/${variantId}`),
  clear: () => api.delete<Cart>("/api/cart"),
  applyCoupon: (code: string) => api.post<Cart>("/api/cart/coupon", { code }),
  removeCoupon: () => api.delete<Cart>("/api/cart/coupon"),
  checkout: (payload: CheckoutPayload) => api.post<OrderDetail>("/api/orders/checkout", payload),
};

// ---- customer orders ------------------------------------------------------

export const ordersApi = {
  list: () => api.get<OrderSummary[]>("/api/orders"),
  detail: (id: number) => api.get<OrderDetail>(`/api/orders/${id}`),
  cancel: (id: number, reason: string) =>
    api.post<OrderDetail>(`/api/orders/${id}/cancel`, { reason }),
  requestCancel: (id: number, reason: string) =>
    api.post<OrderRequestInfo>(`/api/orders/${id}/request-cancel`, { reason }),
  requestReturn: (id: number, reason: string) =>
    api.post<OrderRequestInfo>(`/api/orders/${id}/request-return`, { reason }),
  myNotifications: () => api.get<NotificationEntry[]>("/api/notifications/mine"),
};

// ---- warehouse ------------------------------------------------------------

export const warehouseApi = {
  queue: () => api.get<OrderSummary[]>("/api/warehouse/orders"),
  startPicking: (id: number) => api.post<OrderDetail>(`/api/warehouse/orders/${id}/start-picking`),
  markReady: (id: number) => api.post<OrderDetail>(`/api/warehouse/orders/${id}/mark-ready`),
  ship: (id: number) => api.post<OrderDetail>(`/api/warehouse/orders/${id}/ship`),
  markDelivered: (id: number) =>
    api.post<OrderDetail>(`/api/warehouse/orders/${id}/mark-delivered`),
  receiveReturn: (id: number) =>
    api.post<OrderDetail>(`/api/warehouse/orders/${id}/receive-return`),
  inventory: () => api.get<StockLevel[]>("/api/warehouse/inventory"),
  adjust: (variant_id: number, quantity_change: number, reason: string) =>
    api.post<StockLevel>("/api/warehouse/inventory/adjust", {
      variant_id,
      quantity_change,
      reason,
    }),
  setThreshold: (variant_id: number, low_stock_threshold: number | null) =>
    api.post<StockLevel>("/api/warehouse/inventory/threshold", {
      variant_id,
      low_stock_threshold,
    }),
  movements: (variantId: number) =>
    api.get<StockMovement[]>(`/api/warehouse/inventory/${variantId}/movements`),
};

// ---- support --------------------------------------------------------------

export const supportApi = {
  orders: () => api.get<OrderSummary[]>("/api/support/orders"),
  order: (id: number) => api.get<OrderDetail>(`/api/support/orders/${id}`),
  cancel: (id: number, reason: string) =>
    api.post<OrderDetail>(`/api/support/orders/${id}/cancel`, { reason }),
  refund: (id: number) => api.post<OrderDetail>(`/api/support/orders/${id}/refund`),
  requests: () => api.get<OrderRequestInfo[]>("/api/support/requests"),
  approve: (id: number, note: string) =>
    api.post<OrderRequestInfo>(`/api/support/requests/${id}/approve`, { note }),
  reject: (id: number, note: string) =>
    api.post<OrderRequestInfo>(`/api/support/requests/${id}/reject`, { note }),
};

// ---- admin ----------------------------------------------------------------

export const adminApi = {
  categories: () => api.get<Category[]>("/api/admin/categories"),
  products: (query: { search?: string; category_id?: number; page?: number; page_size?: number }) =>
    api.get<ProductPage>("/api/admin/products", { ...query }),
  createProduct: (payload: Record<string, unknown>) =>
    api.post<Product>("/api/admin/products", payload),
  updateProduct: (id: number, payload: Record<string, unknown>) =>
    api.patch<Product>(`/api/admin/products/${id}`, payload),
  createVariant: (productId: number, payload: Record<string, unknown>) =>
    api.post<Product>(`/api/admin/products/${productId}/variants`, payload),
  updateVariant: (variantId: number, payload: Record<string, unknown>) =>
    api.patch<Product>(`/api/admin/variants/${variantId}`, payload),
  importProducts: (file: File) =>
    api.upload<{ created: number }>("/api/admin/products/import", file),
  coupons: () => api.get<Coupon[]>("/api/admin/coupons"),
  createCoupon: (payload: Record<string, unknown>) =>
    api.post<Coupon>("/api/admin/coupons", payload),
  setCouponActive: (id: number, is_active: boolean) =>
    api.patch<Coupon>(`/api/admin/coupons/${id}`, { is_active }),
  users: () => api.get<AdminUser[]>("/api/admin/users"),
  updateUser: (id: number, payload: { role?: string; is_active?: boolean }) =>
    api.patch<AdminUser>(`/api/admin/users/${id}`, payload),
  importInventory: (file: File) => api.upload<ImportResult>("/api/admin/inventory/import", file),
  exportInventory: () => api.get<string>("/api/admin/inventory/export.csv"),
  report: (query: { from: string; to: string; category_id?: number }) =>
    api.get<InventorySalesReport>("/api/admin/reports/inventory-sales", { ...query }),
  reportCsv: (query: { from: string; to: string; category_id?: number }) =>
    api.get<string>("/api/admin/reports/inventory-sales.csv", { ...query }),
  auditLog: (query: { entity_type?: string; entity_id?: string; limit?: number }) =>
    api.get<AuditEntry[]>("/api/admin/audit-log", { ...query }),
  notifications: () => api.get<NotificationEntry[]>("/api/admin/notifications"),
};
