import { APIError } from "better-auth/api";
import { eq } from "drizzle-orm";
import { getDb } from "@/db";
import { user } from "@/db/schema";
import { register } from "@/lib/api/contracts";
import { errorBody, handle } from "@/lib/api/handler";
import { getAuth } from "@/lib/auth";

const EMAIL_TAKEN = errorBody("EMAIL_TAKEN", "Email is already registered");

async function emailTaken(email: string): Promise<boolean> {
  const rows = await getDb()
    .select({ id: user.id })
    .from(user)
    .where(eq(user.email, email))
    .limit(1);
  return rows.length > 0;
}

export const POST = handle(register)(async ({ body }) => {
  const { password, firstName, lastName } = body;
  // Better Auth stores emails lowercased.
  const email = body.email.toLowerCase();

  // With autoSignIn off, Better Auth answers a duplicate sign-up with a fake
  // success, so check first (see design D6).
  if (await emailTaken(email)) return { status: 409, body: EMAIL_TAKEN };

  try {
    const { user: created } = await getAuth().api.signUpEmail({
      body: { email, password, firstName, lastName, name: `${firstName} ${lastName}` },
    });
    return { status: 201, body: created };
  } catch (err) {
    // Lost a race with a concurrent sign-up for the same email.
    if (err instanceof APIError && (await emailTaken(email))) {
      return { status: 409, body: EMAIL_TAKEN };
    }
    throw err;
  }
});
