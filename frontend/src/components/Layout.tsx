/** App shell: role-aware navigation + content outlet. */

import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { useCartBadge } from "../hooks/useCartBadge";

function navClass({ isActive }: { isActive: boolean }) {
  return isActive ? "nav-link active" : "nav-link";
}

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { count } = useCartBadge();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand" data-testid="brand">
          Alya<span>FIIT</span>
        </Link>
        <nav className="nav">
          {user?.role === "customer" && (
            <>
              <NavLink to="/" end className={navClass} data-testid="nav-catalog">
                Catalog
              </NavLink>
              <NavLink to="/cart" className={navClass} data-testid="nav-cart">
                Cart{count > 0 ? <span className="cart-badge" data-testid="cart-badge">{count}</span> : null}
              </NavLink>
              <NavLink to="/orders" className={navClass} data-testid="nav-orders">
                My orders
              </NavLink>
            </>
          )}
          {(user?.role === "warehouse_staff" || user?.role === "administrator") && (
            <>
              <NavLink to="/warehouse" end className={navClass} data-testid="nav-warehouse">
                Work queue
              </NavLink>
              <NavLink to="/warehouse/inventory" className={navClass} data-testid="nav-inventory">
                Inventory
              </NavLink>
            </>
          )}
          {(user?.role === "support_agent" || user?.role === "administrator") && (
            <NavLink to="/support" className={navClass} data-testid="nav-support">
              Support
            </NavLink>
          )}
          {user?.role === "administrator" && (
            <>
              <NavLink to="/admin/report" className={navClass} data-testid="nav-report">
                Report
              </NavLink>
              <NavLink to="/admin/products" className={navClass} data-testid="nav-admin-products">
                Products
              </NavLink>
              <NavLink to="/admin/coupons" className={navClass} data-testid="nav-admin-coupons">
                Coupons
              </NavLink>
              <NavLink to="/admin/users" className={navClass} data-testid="nav-admin-users">
                Users
              </NavLink>
              <NavLink to="/admin/audit" className={navClass} data-testid="nav-admin-audit">
                Audit
              </NavLink>
            </>
          )}
        </nav>
        <div className="topbar-user">
          {user ? (
            <>
              <span className="muted" data-testid="current-user">
                {user.full_name} · {user.role.replaceAll("_", " ")}
              </span>
              <button type="button" onClick={handleLogout} data-testid="logout-button">
                Sign out
              </button>
            </>
          ) : (
            <Link to="/login" data-testid="nav-login">
              Sign in
            </Link>
          )}
        </div>
      </header>
      <main className="content">
        <Outlet />
      </main>
      <footer className="footer muted">
        Alya-FIIT · internal build
      </footer>
    </div>
  );
}
