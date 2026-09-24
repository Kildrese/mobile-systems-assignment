// Client-side route protection. It only decides what to show: every
// protected endpoint checks the token itself.
import { Navigate, Outlet, useLocation, useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/use-auth";
import { safeNext } from "@/lib/safe-next";

function Loading() {
  return (
    <div className="flex min-h-svh items-center justify-center text-sm text-muted-foreground" role="status">
      Loading…
    </div>
  );
}

function LoadError({ retry }: { retry: () => void }) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-4 p-6 text-center">
      <p className="text-sm text-muted-foreground">Couldn&apos;t reach the server.</p>
      <Button variant="outline" onClick={retry}>
        Try again
      </Button>
    </div>
  );
}

// Signed-in pages. Without a token, goes to /login?next=<this page> without
// calling the API.
export function RequireAuth() {
  const { status, retry } = useAuth();
  const location = useLocation();

  if (status === "signed-out") {
    const next = safeNext(location.pathname + location.search);
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  if (status === "loading") return <Loading />;
  if (status === "error") return <LoadError retry={retry} />;
  return <Outlet />;
}

// /login and /register. A signed-in user goes on to `next`; a stale token is
// removed by the 401 and the form is shown.
export function PublicOnly() {
  const { status } = useAuth();
  const [params] = useSearchParams();

  if (status === "signed-in") return <Navigate to={safeNext(params.get("next"))} replace />;
  if (status === "loading") return <Loading />;
  return <Outlet />;
}
