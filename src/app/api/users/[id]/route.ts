import { eq } from "drizzle-orm";
import { getDb } from "@/db";
import { user } from "@/db/schema";
import { deleteUser, getUser, updateUser } from "@/lib/api/contracts";
import { ERRORS, handle } from "@/lib/api/handler";
import type { Session } from "@/lib/auth";
import { deleteAccount, updateProfile } from "@/lib/services/account";

// Users may only touch their own account. Anyone else's id gets the same 404
// as an id that doesn't exist, and the check runs before any DB lookup so the
// two cases can't be told apart.
function isSelf(session: Session, id: string): boolean {
  return id.toLowerCase() === session.user.id.toLowerCase();
}

export const GET = handle(getUser)(async ({ session, params }) => {
  if (!isSelf(session, params.id)) return { status: 404, body: ERRORS.NOT_FOUND };

  const [row] = await getDb().select().from(user).where(eq(user.id, session.user.id));
  if (!row) return { status: 404, body: ERRORS.NOT_FOUND };
  return { status: 200, body: row };
});

export const PATCH = handle(updateUser)(async ({ session, params, body }) => {
  if (!isSelf(session, params.id)) return { status: 404, body: ERRORS.NOT_FOUND };

  const result = await updateProfile(session.user.id, body);
  if (result.ok) return { status: 200, body: result.user };
  switch (result.code) {
    case "USERNAME_TAKEN":
      return { status: 409, body: ERRORS.USERNAME_TAKEN };
    case "NOT_FOUND":
      return { status: 404, body: ERRORS.NOT_FOUND };
  }
});

export const DELETE = handle(deleteUser)(async ({ session, params }) => {
  if (!isSelf(session, params.id)) return { status: 404, body: ERRORS.NOT_FOUND };

  const result = await deleteAccount(session.user.id);
  if (!result.ok) return { status: 404, body: ERRORS.NOT_FOUND };
  return { status: 204 };
});
