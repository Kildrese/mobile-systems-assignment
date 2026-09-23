// Account rules shared by the JSON API route handlers and the web UI's Server
// Actions, so the two can't drift apart. Plain functions: no HTTP, no forms.
// Each returns `{ ok: true, … }` or `{ ok: false, code }`; callers map `code`
// to a status (API) or a field error (UI). Input is already validated with
// the Zod schemas in `@/lib/api/contracts`.
import "server-only";
import type { APIError } from "better-auth/api";
import { and, eq, sql } from "drizzle-orm";
import { getDb } from "@/db";
import { account, session, user, type User } from "@/db/schema";
import { getAuth } from "@/lib/auth";

type Failure<C extends string> = { ok: false; code: C };

// By shape, not `instanceof`: Next can bundle Better Auth into more than one
// layer (e.g. route handlers vs Server Actions), each with its own APIError
// class, so `instanceof` misses errors thrown by the other copy.
export function isAPIError(err: unknown): err is APIError {
  return err instanceof Error && err.name === "APIError" && typeof (err as APIError).statusCode === "number";
}

const bearer = (token: string) => new Headers({ authorization: `Bearer ${token}` });

async function emailTaken(email: string): Promise<boolean> {
  const rows = await getDb()
    .select({ id: user.id })
    .from(user)
    .where(eq(user.email, email))
    .limit(1);
  return rows.length > 0;
}

// Better Auth's sign-in and change-password results don't include the
// session's expiry, which the web cookie needs.
async function sessionExpiry(token: string): Promise<Date> {
  const [row] = await getDb()
    .select({ expiresAt: session.expiresAt })
    .from(session)
    .where(eq(session.token, token));
  if (!row) throw new Error("Session not found right after it was created");
  return row.expiresAt;
}

export async function registerUser(input: {
  email: string;
  password: string;
  firstName: string;
  lastName: string;
}): Promise<{ ok: true; user: User } | Failure<"EMAIL_TAKEN">> {
  const { password, firstName, lastName } = input;
  // Better Auth stores emails lowercased.
  const email = input.email.toLowerCase();

  // With autoSignIn off, Better Auth answers a duplicate sign-up with a fake
  // success, so check first.
  if (await emailTaken(email)) return { ok: false, code: "EMAIL_TAKEN" };

  try {
    const { user: created } = await getAuth().api.signUpEmail({
      body: { email, password, firstName, lastName, name: `${firstName} ${lastName}` },
    });
    return { ok: true, user: created as User };
  } catch (err) {
    // Lost a race with a concurrent sign-up for the same email.
    if (isAPIError(err) && (await emailTaken(email))) {
      return { ok: false, code: "EMAIL_TAKEN" };
    }
    throw err;
  }
}

export async function signIn(input: {
  email: string;
  password: string;
}): Promise<
  { ok: true; token: string; expiresAt: Date; user: User } | Failure<"INVALID_CREDENTIALS">
> {
  try {
    // Better Auth's response headers (including Set-Cookie) are dropped: only
    // the token is used.
    const { token, user: signedIn } = await getAuth().api.signInEmail({
      body: { email: input.email, password: input.password },
    });
    return { ok: true, token, expiresAt: await sessionExpiry(token), user: signedIn as User };
  } catch (err) {
    // Same code for unknown email and wrong password.
    if (isAPIError(err) && err.statusCode < 500) {
      return { ok: false, code: "INVALID_CREDENTIALS" };
    }
    throw err;
  }
}

// Revokes only this session. A token that is already gone is a no-op.
export async function signOut(token: string): Promise<{ ok: true }> {
  await getAuth().api.signOut({ headers: bearer(token) });
  return { ok: true };
}

export async function updateName(
  userId: string,
  input: { firstName?: string; lastName?: string },
): Promise<{ ok: true; user: User } | Failure<"NOT_FOUND">> {
  // Column references in SET read the pre-update values, so `name` is built
  // from the new value when given and the stored one otherwise.
  const firstName = input.firstName !== undefined ? sql`${input.firstName}` : sql`${user.firstName}`;
  const lastName = input.lastName !== undefined ? sql`${input.lastName}` : sql`${user.lastName}`;

  const [row] = await getDb()
    .update(user)
    .set({
      firstName: input.firstName,
      lastName: input.lastName,
      name: sql`${firstName} || ' ' || ${lastName}`,
      updatedAt: new Date(),
    })
    .where(eq(user.id, userId))
    .returning();
  if (!row) return { ok: false, code: "NOT_FOUND" };
  return { ok: true, user: row };
}

function isUniqueViolation(err: unknown): boolean {
  // postgres-js errors carry the SQLSTATE in `code`; Drizzle may wrap them.
  for (let e = err; e instanceof Error; e = e.cause) {
    if ((e as { code?: unknown }).code === "23505") return true;
  }
  return false;
}

// Implemented here rather than with Better Auth's `changeEmail`, which
// silently succeeds when the email is taken and doesn't ask for a password.
// Order: password (INVALID_PASSWORD), then same email (no-op), then uniqueness
// (EMAIL_TAKEN), so a wrong password can't probe which emails exist.
export async function changeEmail(
  userId: string,
  input: { newEmail: string; currentPassword: string },
): Promise<
  { ok: true; user: User } | Failure<"INVALID_PASSWORD" | "EMAIL_TAKEN" | "NOT_FOUND">
> {
  const db = getDb();
  const [row] = await db
    .select({ user, hash: account.password })
    .from(user)
    .leftJoin(account, and(eq(account.userId, user.id), eq(account.providerId, "credential")))
    .where(eq(user.id, userId));
  if (!row) return { ok: false, code: "NOT_FOUND" };

  const ctx = await getAuth().$context;
  const valid =
    row.hash !== null &&
    (await ctx.password.verify({ hash: row.hash, password: input.currentPassword }));
  if (!valid) return { ok: false, code: "INVALID_PASSWORD" };

  const email = input.newEmail.toLowerCase();
  if (email === row.user.email) return { ok: true, user: row.user };

  try {
    const [updated] = await db
      .update(user)
      .set({ email, updatedAt: new Date() })
      .where(eq(user.id, userId))
      .returning();
    if (!updated) return { ok: false, code: "NOT_FOUND" };
    return { ok: true, user: updated };
  } catch (err) {
    // The unique constraint decides, so there's no check-then-write race.
    if (isUniqueViolation(err)) return { ok: false, code: "EMAIL_TAKEN" };
    throw err;
  }
}

// Revokes every session of the user (including `token`'s) and returns a new
// one. `session.freshAge: 0` in `auth.ts` keeps Better Auth from rejecting
// sessions older than a day.
export async function changePassword(
  token: string,
  input: { currentPassword: string; newPassword: string },
): Promise<{ ok: true; token: string; expiresAt: Date } | Failure<"INVALID_PASSWORD">> {
  try {
    const result = await getAuth().api.changePassword({
      headers: bearer(token),
      body: {
        currentPassword: input.currentPassword,
        newPassword: input.newPassword,
        revokeOtherSessions: true,
      },
    });
    if (!result.token) throw new Error("changePassword returned no token");
    return { ok: true, token: result.token, expiresAt: await sessionExpiry(result.token) };
  } catch (err) {
    if (isAPIError(err) && err.body?.code === "INVALID_PASSWORD") {
      return { ok: false, code: "INVALID_PASSWORD" };
    }
    throw err;
  }
}

// Cascades to the user's accounts and sessions, revoking every token.
export async function deleteAccount(userId: string): Promise<{ ok: true } | Failure<"NOT_FOUND">> {
  const deleted = await getDb()
    .delete(user)
    .where(eq(user.id, userId))
    .returning({ id: user.id });
  if (deleted.length === 0) return { ok: false, code: "NOT_FOUND" };
  return { ok: true };
}
