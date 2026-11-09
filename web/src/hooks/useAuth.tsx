import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import * as authApi from "../api/auth";
import { resetLiveStore } from "./useLiveStore";
import { adoptAccountZone } from "../lib/accountZone";
import type { CurrentUser } from "../api/types";

interface AuthState {
  user: CurrentUser | null;
  loading: boolean;
}

interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// The account's time zone after a sign-in: from the answer when it carries one, else from GET /api/auth/me.
function syncZone(user: CurrentUser): void {
  if (user.timezone !== undefined) {
    void adoptAccountZone(user.timezone);
    return;
  }
  authApi.me()
    .then((current) => { if (current) void adoptAccountZone(current.timezone); })
    .catch((err: unknown) => console.warn("Roost could not read the account's time zone.", err));
}

// Resolves the session once on mount via GET /api/auth/me (contract:
// 200 {id,username,timezone} or 401) — Login redirects unauthenticated visitors,
// RequireAuth (App.tsx) redirects back once `user` is null and loading
// is done.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ user: null, loading: true });

  useEffect(() => {
    authApi
      .me()
      .then((user) => {
        // The zone is set before the first signed-in render, so every time shows on the account's clock.
        if (user) void adoptAccountZone(user.timezone);
        setState({ user, loading: false });
      })
      .catch(() => setState({ user: null, loading: false }));
  }, []);

  const value: AuthContextValue = {
    ...state,
    login: async (username, password) => {
      const user = await authApi.login(username, password);
      // Drop any live-store connection/cache left over from a previous
      // session on this tab before the new session's Layout creates a
      // fresh one (see useLiveStore.ts's resetLiveStore docstring).
      resetLiveStore();
      setState({ user, loading: false });
      syncZone(user);
    },
    register: async (username, password) => {
      const user = await authApi.register(username, password);
      resetLiveStore();
      setState({ user, loading: false });
      syncZone(user);
    },
    logout: async () => {
      await authApi.logout();
      resetLiveStore();
      setState({ user: null, loading: false });
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
