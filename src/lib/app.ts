export const APP_NAME = "Mobile Systems";

// Shared by `src/lib/session.ts` (server-only) and `src/proxy.ts`, which can't
// import server-only modules.
export const SESSION_COOKIE = "session";
export const PUBLIC_PAGES = new Set(["/login", "/register"]);
