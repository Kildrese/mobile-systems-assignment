import { PUBLIC_PAGES } from "@/lib/app";

// `value` if it is a same-site relative path that isn't an auth page, else
// `/`. Rejects `//host` and `/\host` (browsers treat both as another host)
// and control characters (browsers strip tabs and newlines, which could turn
// `/\t/host` into `//host`).
export function safeNext(value: unknown): string {
  if (typeof value !== "string") return "/";
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return "/";
  // eslint-disable-next-line no-control-regex
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

// `/login` or `/register`, carrying `next` unless it is the default.
export function authHref(page: "/login" | "/register", next: string): string {
  return next === "/" ? page : `${page}?next=${encodeURIComponent(next)}`;
}
