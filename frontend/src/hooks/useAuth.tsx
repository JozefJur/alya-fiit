/** Auth context: current user, login/logout, token persistence. */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { getToken, setToken } from "../api/client";
import { authApi } from "../api/endpoints";
import type { ApiUser } from "../types/api";

interface AuthState {
  user: ApiUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<ApiUser>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<ApiUser | null>(null);
  const [loading, setLoading] = useState<boolean>(() => getToken() !== null);

  useEffect(() => {
    let cancelled = false;
    if (getToken()) {
      authApi
        .me()
        .then((me) => {
          if (!cancelled) setUser(me);
        })
        .catch(() => {
          if (!cancelled) {
            setToken(null);
            setUser(null);
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await authApi.login(email, password);
    setToken(response.access_token);
    setUser(response.user);
    return response.user;
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}

/** Landing route for each role after login. */
export function homeFor(role: string): string {
  switch (role) {
    case "warehouse_staff":
      return "/warehouse";
    case "support_agent":
      return "/support";
    case "administrator":
      return "/admin/report";
    default:
      return "/";
  }
}
