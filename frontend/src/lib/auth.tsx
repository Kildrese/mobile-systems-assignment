// Who is signed in. The token lives in localStorage (see token.ts); the user
// comes from `GET /api/auth/me`, cached by TanStack Query.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useCallback,
  useEffect,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import {
  getCurrentUserOptions,
  getCurrentUserQueryKey,
} from "@/api/@tanstack/react-query.gen";
import type { User } from "@/api/types.gen";
import { AuthContext, type AuthState } from "@/lib/use-auth";
import { getToken, setToken, subscribeToken } from "@/lib/token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const token = useSyncExternalStore(subscribeToken, getToken);
  const query = useQuery({ ...getCurrentUserOptions(), enabled: token !== null, retry: false });

  // Cached data belongs to the token that fetched it.
  useEffect(() => {
    if (token === null) queryClient.removeQueries();
  }, [token, queryClient]);

  const signIn = useCallback(
    (newToken: string, user?: User) => {
      queryClient.removeQueries();
      if (user) queryClient.setQueryData(getCurrentUserQueryKey(), user);
      setToken(newToken);
    },
    [queryClient],
  );
  const signOut = useCallback(() => setToken(null), []);
  const setUser = useCallback(
    (user: User) => queryClient.setQueryData(getCurrentUserQueryKey(), user),
    [queryClient],
  );
  const { refetch } = query;
  const retry = useCallback(() => void refetch(), [refetch]);

  const status: AuthState["status"] =
    token === null
      ? "signed-out"
      : query.data
        ? "signed-in"
        : query.isError
          ? "error"
          : "loading";

  const value = useMemo(
    () => ({ status, user: query.data, retry, signIn, signOut, setUser }),
    [status, query.data, retry, signIn, signOut, setUser],
  );
  return <AuthContext value={value}>{children}</AuthContext>;
}
