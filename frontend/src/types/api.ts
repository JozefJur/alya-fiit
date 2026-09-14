/** TypeScript mirrors of the backend API DTOs (money values arrive as strings). */

export type Role = "customer" | "warehouse_staff" | "administrator" | "support_agent";

export interface ApiUser {
  id: number;
  email: string;
  full_name: string;
  role: Role;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: ApiUser;
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  description: string;
  is_active: boolean;
}

export interface Variant {
  id: number;
  sku: string;
  name: string;
  attributes: Record<string, string>;
  price: string;
  price_with_vat: string;
  is_active: boolean;
  available: number;
}

export interface Product {
  id: number;
  name: string;
  slug: string;
  description: string;
  brand: string;
  category_id: number;
  category_name: string;
  base_price: string;
  vat_rate: string;
  is_active: boolean;
  variants: Variant[];
}

export interface ProductPage {
  items: Product[];
  total: number;
  page: number;
  page_size: number;
}

export interface CartLine {
  variant_id: number;
  product_id: number;
  product_name: string;
  sku: string;
  quantity: number;
  unit_price: string;
  line_net: string;
  discount: string;
  vat: string;
  line_total: string;
}

export interface CartProblem {
  variant_id: number;
  code: string;
  message: string;
}

export interface Cart {
  id: number;
  items: CartLine[];
  subtotal: string;
  discount_total: string;
  vat_total: string;
  grand_total: string;
  coupon_code: string | null;
  coupon_error: string | null;
  problems: CartProblem[];
}

export type OrderStatus =
  | "DRAFT"
  | "PENDING_PAYMENT"
  | "PAID"
  | "PICKING"
  | "READY_TO_SHIP"
  | "SHIPPED"
  | "DELIVERED"
  | "CANCELLED"
  | "PAYMENT_FAILED"
  | "CANCEL_REQUESTED"
  | "RETURN_REQUESTED"
  | "RETURN_APPROVED"
  | "RETURNED"
  | "REFUNDED";

export interface OrderItem {
  variant_id: number;
  product_name: string;
  sku: string;
  unit_price: string;
  vat_rate: string;
  quantity: number;
  discount_amount: string;
  vat_amount: string;
  line_total: string;
}

export interface OrderHistoryEntry {
  from_status: OrderStatus | null;
  to_status: OrderStatus;
  event: string;
  actor_user_id: number | null;
  note: string;
  created_at: string;
}

export interface Payment {
  id: number;
  amount: string;
  status: string;
  idempotency_key: string;
  gateway_reference: string | null;
  created_at: string;
}

export interface OrderSummary {
  id: number;
  order_number: string;
  status: OrderStatus;
  grand_total: string;
  created_at: string;
  items_count: number;
  customer_id: number;
  customer_email: string | null;
}

export interface OrderDetail {
  id: number;
  order_number: string;
  customer_id: number;
  status: OrderStatus;
  subtotal: string;
  discount_total: string;
  vat_total: string;
  grand_total: string;
  coupon_code: string | null;
  ship_to_name: string;
  ship_street: string;
  ship_city: string;
  ship_zip: string;
  ship_country: string;
  created_at: string;
  shipped_at: string | null;
  delivered_at: string | null;
  expected_delivery: string | null;
  items: OrderItem[];
  status_history: OrderHistoryEntry[];
  payments: Payment[];
  allowed_events: string[];
}

export interface OrderRequestInfo {
  id: number;
  order_id: number;
  order_number: string;
  request_type: "cancel" | "return";
  reason: string;
  status: "pending" | "approved" | "rejected";
  requested_by: number;
  created_at: string;
  decided_at: string | null;
  decision_note: string;
}

export interface StockLevel {
  variant_id: number;
  sku: string;
  product_name: string;
  variant_name: string;
  on_hand: number;
  reserved: number;
  available: number;
  low_stock_threshold: number;
  is_low_stock: boolean;
}

export interface StockMovement {
  id: number;
  variant_id: number;
  movement_type: string;
  quantity: number;
  reason: string;
  reference: string | null;
  actor_user_id: number | null;
  created_at: string;
}

export interface Coupon {
  id: number;
  code: string;
  discount_type: "percent" | "fixed";
  value: string;
  valid_from: string;
  valid_until: string;
  min_cart_total: string | null;
  max_uses: number | null;
  used_count: number;
  category_id: number | null;
  is_active: boolean;
}

export interface AdminUser {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface AuditEntry {
  id: number;
  actor_user_id: number | null;
  action: string;
  entity_type: string;
  entity_id: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface NotificationEntry {
  id: number;
  recipient_user_id: number;
  notification_type: string;
  subject: string;
  body: string;
  status: string;
  created_at: string;
}

export interface ReportVariantRow {
  variant_id: number;
  sku: string;
  product_id: number;
  product_name: string;
  quantity_sold: number;
  revenue: string;
  discount: string;
  on_hand: number;
  reserved: number;
  available: number;
  low_stock_threshold: number;
  is_low_stock: boolean;
}

export interface InventorySalesReport {
  period: { from: string; to: string };
  summary: {
    orders_total: number;
    orders_revenue: number;
    orders_cancelled: number;
    orders_refunded: number;
    revenue: string;
    discount_total: string;
    average_order_value: string;
    total_on_hand: number;
    total_reserved: number;
    total_available: number;
  };
  variants: ReportVariantRow[];
  low_stock: {
    variant_id: number;
    sku: string;
    product_name: string;
    available: number;
    low_stock_threshold: number;
  }[];
  top_products: { product_id: number; product_name: string; quantity_sold: number; revenue: string }[];
  high_cancellation_products: {
    product_id: number;
    product_name: string;
    orders: number;
    cancelled: number;
    ratio: string;
  }[];
}

export interface ImportResult {
  applied: number;
  unchanged: number;
  movements: number;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> };
}
