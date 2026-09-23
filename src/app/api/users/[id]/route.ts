import { eq, sql } from "drizzle-orm";
import { getDb } from "@/db";
import { user } from "@/db/schema";
import { deleteUser, getUser, updateUser } from "@/lib/api/contracts";
import { handle, NOT_FOUND, type Session } from "@/lib/api/handler";

// Users may only touch their own account. Anyone else's id gets the same 404
// as an id that doesn't exist, and the check runs before any DB lookup so the
// two cases can't be told apart.
function isSelf(session: Session, id: string): boolean {
  return id.toLowerCase() === session.user.id.toLowerCase();
}

export const GET = handle(getUser)(async ({ session, params }) => {
  if (!isSelf(session, params.id)) return { status: 404, body: NOT_FOUND };

  const [row] = await getDb().select().from(user).where(eq(user.id, session.user.id));
  if (!row) return { status: 404, body: NOT_FOUND };
  return { status: 200, body: row };
});

export const PATCH = handle(updateUser)(async ({ session, params, body }) => {
  if (!isSelf(session, params.id)) return { status: 404, body: NOT_FOUND };

  // Column references in SET read the pre-update values, so `name` is built
  // from the new value when given and the stored one otherwise.
  const firstName = body.firstName !== undefined ? sql`${body.firstName}` : sql`${user.firstName}`;
  const lastName = body.lastName !== undefined ? sql`${body.lastName}` : sql`${user.lastName}`;

  const [row] = await getDb()
    .update(user)
    .set({
      firstName: body.firstName,
      lastName: body.lastName,
      name: sql`${firstName} || ' ' || ${lastName}`,
      updatedAt: new Date(),
    })
    .where(eq(user.id, session.user.id))
    .returning();
  if (!row) return { status: 404, body: NOT_FOUND };
  return { status: 200, body: row };
});

export const DELETE = handle(deleteUser)(async ({ session, params }) => {
  if (!isSelf(session, params.id)) return { status: 404, body: NOT_FOUND };

  // Cascades to the user's accounts and sessions, revoking every token.
  const deleted = await getDb()
    .delete(user)
    .where(eq(user.id, session.user.id))
    .returning({ id: user.id });
  if (deleted.length === 0) return { status: 404, body: NOT_FOUND };
  return { status: 204 };
});
