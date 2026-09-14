import { Navigate, Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import Protected from "./components/Protected";
import { AuthProvider } from "./hooks/useAuth";
import { CartBadgeProvider } from "./hooks/useCartBadge";
import AdminAuditPage from "./pages/AdminAuditPage";
import AdminCouponsPage from "./pages/AdminCouponsPage";
import AdminProductsPage from "./pages/AdminProductsPage";
import AdminReportPage from "./pages/AdminReportPage";
import AdminUsersPage from "./pages/AdminUsersPage";
import CartPage from "./pages/CartPage";
import CatalogPage from "./pages/CatalogPage";
import CheckoutPage from "./pages/CheckoutPage";
import LoginPage from "./pages/LoginPage";
import OrderDetailPage from "./pages/OrderDetailPage";
import OrdersPage from "./pages/OrdersPage";
import ProductPage from "./pages/ProductPage";
import SupportPage from "./pages/SupportPage";
import WarehouseInventoryPage from "./pages/WarehouseInventoryPage";
import WarehousePage from "./pages/WarehousePage";

export default function App() {
  return (
    <AuthProvider>
      <CartBadgeProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<CatalogPage />} />
            <Route path="/products/:id" element={<ProductPage />} />
            <Route
              path="/cart"
              element={
                <Protected roles={["customer"]}>
                  <CartPage />
                </Protected>
              }
            />
            <Route
              path="/checkout"
              element={
                <Protected roles={["customer"]}>
                  <CheckoutPage />
                </Protected>
              }
            />
            <Route
              path="/orders"
              element={
                <Protected roles={["customer"]}>
                  <OrdersPage />
                </Protected>
              }
            />
            <Route
              path="/orders/:id"
              element={
                <Protected>
                  <OrderDetailPage />
                </Protected>
              }
            />
            <Route
              path="/warehouse"
              element={
                <Protected roles={["warehouse_staff", "administrator"]}>
                  <WarehousePage />
                </Protected>
              }
            />
            <Route
              path="/warehouse/inventory"
              element={
                <Protected roles={["warehouse_staff", "administrator"]}>
                  <WarehouseInventoryPage />
                </Protected>
              }
            />
            <Route
              path="/support"
              element={
                <Protected roles={["support_agent", "administrator"]}>
                  <SupportPage />
                </Protected>
              }
            />
            <Route
              path="/admin/report"
              element={
                <Protected roles={["administrator"]}>
                  <AdminReportPage />
                </Protected>
              }
            />
            <Route
              path="/admin/products"
              element={
                <Protected roles={["administrator"]}>
                  <AdminProductsPage />
                </Protected>
              }
            />
            <Route
              path="/admin/coupons"
              element={
                <Protected roles={["administrator"]}>
                  <AdminCouponsPage />
                </Protected>
              }
            />
            <Route
              path="/admin/users"
              element={
                <Protected roles={["administrator"]}>
                  <AdminUsersPage />
                </Protected>
              }
            />
            <Route
              path="/admin/audit"
              element={
                <Protected roles={["administrator"]}>
                  <AdminAuditPage />
                </Protected>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </CartBadgeProvider>
    </AuthProvider>
  );
}
