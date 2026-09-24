// The web UI's session: a `session` cookie holding the Better Auth session
// token. This is the only module that reads or writes that cookie. The JSON
// API never looks at it (it is bearer-only, see `@/lib/api/handler`).
import "server-only";
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";
import { PUBLIC_PAGES, SESSION_COOKIE } from "@/lib/app";
import { getSessionByToken, type Session } from "@/lib/auth";

// Only callable from Server Actions and route handlers.
export async function setSessionCookie(token: string, expiresAt: Date): Promise<void> {
  (await cookies()).set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure: process.env.NODE_ENV === "production",
    expires: expiresAt,
  });
}

export async function clearSessionCookie(): Promise<void> {
  (await cookies()).delete(SESSION_COOKIE);
}

export async function getSessionToken(): Promise<string | null> {
  return (await cookies()).get(SESSION_COOKIE)?.value ?? null;
}

// The signed-in session, or null when the cookie is missing or its session is
// unknown, expired or revoked. Cached so it runs once per request.
export const getCurrentSession = cache(async (): Promise<Session | null> => {
  const token = await getSessionToken();
  // Same lookup as the API: the token goes to Better Auth as a bearer header.
  return token ? getSessionByToken(token) : null;
});

// The signed-in session, or a redirect to `/login?next=<current path>`.
// The path comes from the `x-pathname` header set by `src/proxy.ts`.
export async function requireSession(): Promise<Session> {
  const session = await getCurrentSession();
  if (session) return session;

  const next = safeNext((await headers()).get("x-pathname"));
  redirect(`/login?next=${encodeURIComponent(next)}`);
}

// `value` if it is a same-site relative path that isn't an auth page, else
// `/`. Rejects `//host` and `/\host` (browsers treat both as another host)
// and control characters (browsers strip tabs and newlines, which could turn
// `/\t/host` into `//host`).
export function safeNext(value: unknown): string {
  if (typeof value !== "string") return "/";
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return "/";
  if (/[\u0000-\u001f\u007f\\]/.test(value)) return "/";

  const base = "http://same-site.invalid";
  let url: URL;
  try {
    url = new URL(value, base);
  } catch {
    return "/";
  }
  if (url.origin !== base) return "/";
  const path = url.pathname.replace(/\/+$/, "") || "/";
  if (PUBLIC_PAGES.has(path)) return "/";
  return value;
}
