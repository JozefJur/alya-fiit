/** Shared cart-badge state: item count refreshed after cart mutations. */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { cartApi } from "../api/endpoints";
import { useAuth } from "./useAuth";

interface CartBadgeState {
  count: number;
  refresh: () => Promise<void>;
}

const CartBadgeContext = createContext<CartBadgeState>({
  count: 0,
  refresh: async () => undefined,
});

export function CartBadgeProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [count, setCount] = useState(0);

  const refresh = useCallback(async () => {
    try {
      const cart = await cartApi.get();
      setCount(cart.items.reduce((sum, line) => sum + line.quantity, 0));
    } catch {
      setCount(0);
    }
  }, []);

  useEffect(() => {
    if (user?.role === "customer") {
      void refresh();
    } else {
      setCount(0);
    }
  }, [user, refresh]);

  const value = useMemo(() => ({ count, refresh }), [count, refresh]);
  return <CartBadgeContext.Provider value={value}>{children}</CartBadgeContext.Provider>;
}

export function useCartBadge(): CartBadgeState {
  return useContext(CartBadgeContext);
}
