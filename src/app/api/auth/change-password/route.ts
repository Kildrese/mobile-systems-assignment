import { changePassword as changePasswordContract } from "@/lib/api/contracts";
import { errorBody, handle } from "@/lib/api/handler";
import { changePassword } from "@/lib/services/account";

const INVALID_PASSWORD = errorBody("INVALID_PASSWORD", "Current password is incorrect");

export const POST = handle(changePasswordContract)(async ({ session, body }) => {
  const result = await changePassword(session.session.token, body);
  if (!result.ok) return { status: 403, body: INVALID_PASSWORD };
  return { status: 200, body: { token: result.token } };
});
