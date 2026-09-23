import { changeEmail as changeEmailContract } from "@/lib/api/contracts";
import { errorBody, handle } from "@/lib/api/handler";
import { changeEmail } from "@/lib/services/account";

const INVALID_PASSWORD = errorBody("INVALID_PASSWORD", "Current password is incorrect");
const EMAIL_TAKEN = errorBody("EMAIL_TAKEN", "Email is already registered");

export const POST = handle(changeEmailContract)(async ({ session, body }) => {
  const result = await changeEmail(session.user.id, body);
  if (result.ok) return { status: 200, body: result.user };
  switch (result.code) {
    case "INVALID_PASSWORD":
      return { status: 403, body: INVALID_PASSWORD };
    case "EMAIL_TAKEN":
      return { status: 409, body: EMAIL_TAKEN };
    case "NOT_FOUND":
      // The user was deleted between the session check and now.
      return { status: 401, body: errorBody("UNAUTHORIZED", "Authentication required") };
  }
});
