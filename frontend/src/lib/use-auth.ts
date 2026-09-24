// The auth context's shape and hooks; the provider is in auth.tsx.
import { createContext, useContext } from "react";
import type { User } from "@/api/types.gen";

export type AuthState = {
  // "signed-out": no token. "loading": a token, user not loaded yet.
  // "error": the user couldn't be loaded for a reason other than a 401
  // (a 401 removes the token, which makes the state "signed-out").
  status: "signed-out" | "loading" | "signed-in" | "error";
  user: User | undefined;
  retry: () => void;
  // Stores the token; pass the user when the response included it, to skip
  // a `GET /api/auth/me`.
  signIn: (token: string, user?: User) => void;
  signOut: () => void;
  setUser: (user: User) => void;
};

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth must be used inside <AuthProvider>");
  return auth;
}

// For pages behind RequireAuth, where the user is always loaded.
export function useUser(): User {
  const { user } = useAuth();
  if (!user) throw new Error("useUser must be used inside <RequireAuth>");
  return user;
}
