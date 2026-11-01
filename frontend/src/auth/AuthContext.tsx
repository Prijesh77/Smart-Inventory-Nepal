/**
 * Login state for the whole app.
 *
 * The token is kept in memory and in sessionStorage, so a page refresh keeps
 * you logged in but closing the tab logs you out. Tokens expire after
 * 60 minutes on the server; any 401 response logs the user out here.
 * (A production system would prefer an HttpOnly cookie, which page scripts
 * cannot read. That is listed as a limitation in docs/18.)
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, ApiError, setAuthToken, setUnauthorizedHandler } from "../api/client";
import type { Role, TokenResponse, User } from "../api/types";

const STORAGE_KEY = "smart-inventory.token";

interface AuthState {
  user: User | null;
  loading: boolean;               // true while checking a stored token at start-up
  login: (email: string, password: string) => Promise<void>;
  logout: (reason?: string) => void;
  notice: string | null;          // e.g. "Session expired" shown on the login page
  can: (...roles: Role[]) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

function readStoredToken(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;                  // storage blocked (private mode etc.): just log in again
  }
}

function storeToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(STORAGE_KEY, token);
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore: the in-memory token still works for this page */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  const logout = useCallback((reason?: string) => {
    setAuthToken(null);
    storeToken(null);
    setUser(null);
    setNotice(reason ?? null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => logout("Your session has expired. Please log in again."));
    const stored = readStoredToken();
    if (!stored) {
      setLoading(false);
      return;
    }
    setAuthToken(stored);
    api.get<User>("/auth/me")
      .then(setUser)
      .catch((err) => {
        // A 401 is already handled (with its message) by the handler above.
        if (!(err instanceof ApiError && err.status === 401)) {
          logout("Could not check your login. Please log in again.");
        }
      })
      .finally(() => setLoading(false));
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const login = useCallback(async (email: string, password: string) => {
    // The login endpoint uses the standard OAuth2 form: the email goes in "username".
    const data = await api.postForm<TokenResponse>("/auth/login", new URLSearchParams({ username: email, password }));
    setAuthToken(data.access_token);
    storeToken(data.access_token);
    setNotice(null);
    setUser(data.user);
  }, []);

  const value = useMemo<AuthState>(() => ({
    user, loading, login, logout, notice,
    can: (...roles) => !!user && roles.includes(user.role),
  }), [user, loading, login, logout, notice]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** True when the logged-in user's shop holds synthetic demo data (false outside a provider, e.g. in tests). */
export function useIsDemoShop(): boolean {
  return useContext(AuthContext)?.user?.shop.is_demo ?? false;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
