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
    baseURL: process.env.BETTER_AUTH_URL,
    database: drizzleAdapter(getDb(), { provider: "pg", schema }),
    emailAndPassword: {
      enabled: true,
      autoSignIn: false,
      minPasswordLength: 8,
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
// e.g. during `next build`. Reused across hot reloads in development.
const globalForAuth = globalThis as unknown as { auth?: Auth };

export function getAuth(): Auth {
  const auth = globalForAuth.auth ?? createAuth();
  if (process.env.NODE_ENV !== "production") globalForAuth.auth = auth;
  return auth;
}
