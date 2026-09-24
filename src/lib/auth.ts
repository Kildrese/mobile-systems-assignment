import { betterAuth } from "better-auth";
import type { APIError } from "better-auth/api";
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

export type Session = NonNullable<Awaited<ReturnType<Auth["api"]["getSession"]>>>;

// By shape, not `instanceof`: Next can bundle Better Auth into more than one
// layer (e.g. route handlers vs Server Actions), each with its own APIError
// class, so `instanceof` misses errors thrown by the other copy.
export function isAPIError(err: unknown): err is APIError {
  return err instanceof Error && err.name === "APIError" && typeof (err as APIError).statusCode === "number";
}

export const bearerHeaders = (token: string) => new Headers({ authorization: `Bearer ${token}` });

// The session for a token, or null when it is unknown, expired or revoked.
// Both the API (bearer header) and the web UI (cookie) resolve sessions here.
export async function getSessionByToken(token: string): Promise<Session | null> {
  try {
    return await getAuth().api.getSession({ headers: bearerHeaders(token) });
  } catch (err) {
    if (isAPIError(err)) return null;
    throw err;
  }
}
