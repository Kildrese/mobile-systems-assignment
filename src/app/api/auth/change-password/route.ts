import { changePassword as changePasswordContract } from "@/lib/api/contracts";
import { ERRORS, handle } from "@/lib/api/handler";
import { changePassword } from "@/lib/services/account";

export const POST = handle(changePasswordContract)(async ({ session, body }) => {
  const result = await changePassword(session.session.token, body);
  if (!result.ok) return { status: 403, body: ERRORS.INVALID_PASSWORD };
  return { status: 200, body: { token: result.token } };
});
