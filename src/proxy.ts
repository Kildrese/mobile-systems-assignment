// Optimistic route protection: a page request without a `session` cookie is
// redirected to `/login?next=<path>` before anything renders. This only checks
// that the cookie exists (no database work here, it runs on every request);
// `requireSession()` in `src/lib/session.ts` does the real check.
//
// It also passes the current path and query to Server Components as the
// `x-pathname` request header, so `requireSession()` can build `next`.
import { NextResponse, type NextRequest } from "next/server";

// Kept in sync with `SESSION_COOKIE` in `src/lib/session.ts`, which is
// server-only and can't be imported here.
const SESSION_COOKIE = "session";

const PUBLIC_PAGES = new Set(["/login", "/register"]);

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const path = pathname + search;

  if (!PUBLIC_PAGES.has(pathname) && !request.cookies.has(SESSION_COOKIE)) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", path);
    return NextResponse.redirect(login);
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-pathname", path);
  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: [
    // Everything except API routes, Next internals, the public health check
    // and API reference, and files with an extension (public assets).
    "/((?!api(?:/|$)|_next/|favicon\\.ico$|healthz$|docs$|.*\\.[^/]+$).*)",
  ],
};
