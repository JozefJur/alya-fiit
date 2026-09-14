/** Route guard: requires login, optionally a specific role set. */

import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "../hooks/useAuth";
import type { Role } from "../types/api";
import { Spinner } from "./common";

export default function Protected({
  roles,
  children,
}: {
  roles?: Role[];
  children: ReactNode;
}) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Spinner />;
  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  if (roles && !roles.includes(user.role)) {
    return (
      <div className="alert alert-error" data-testid="forbidden">
        You do not have access to this section.
      </div>
    );
  }
  return <>{children}</>;
}
