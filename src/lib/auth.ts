import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { bearer } from "better-auth/plugins";
import { getDb } from "@/db";
import * as schema from "@/db/schema";

function createAuth() {
  const secret = process.env.BETTER_AUTH_SECRET;
  if (!secret) {
    throw new Error(
      "BETTER_AUTH_SECRET is missing. Copy .env.example to .env and set BETTER_AUTH_SECRET.",
    );
  }

  return betterAuth({
    secret,
    // On Vercel preview deployments BETTER_AUTH_URL is unset, so fall back to
    // the deployment's own URL.
    baseURL:
      process.env.BETTER_AUTH_URL ??
      (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : undefined),
    database: drizzleAdapter(getDb(), { provider: "pg", schema }),
    emailAndPassword: {
      enabled: true,
      autoSignIn: false,
      minPasswordLength: 8,
    },
    session: {
      // Better Auth rejects `changePassword` for sessions older than
      // `freshAge` (default 1 day) with SESSION_NOT_FRESH. We ask for the
      // current password instead, which is a stronger check than session age.
      // `changePassword` is the only "sensitive" endpoint we call.
      freshAge: 0,
    },
    user: {
      additionalFields: {
        firstName: { type: "string", required: true, input: true },
        lastName: { type: "string", required: true, input: true },
      },
    },
    advanced: {
      database: { generateId: "uuid" },
    },
    plugins: [bearer()],
  });
}

export type Auth = ReturnType<typeof createAuth>;

// Built lazily (like getDb) so importing this module doesn't need env vars,
// e.g. during `next build`. One instance per process, also across hot reloads.
const globalForAuth = globalThis as unknown as { auth?: Auth };

export function getAuth(): Auth {
  globalForAuth.auth ??= createAuth();
  return globalForAuth.auth;
}
