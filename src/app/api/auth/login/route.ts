import { login } from "@/lib/api/contracts";
import { ERRORS, handle } from "@/lib/api/handler";
import { signIn } from "@/lib/services/account";

export const POST = handle(login)(async ({ body }) => {
  const result = await signIn(body);
  if (!result.ok) return { status: 401, body: ERRORS.INVALID_CREDENTIALS };
  return { status: 200, body: { token: result.token, user: result.user } };
});
