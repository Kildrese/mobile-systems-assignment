import { login } from "@/lib/api/contracts";
import { errorBody, handle } from "@/lib/api/handler";
import { signIn } from "@/lib/services/account";

// Same body for unknown email and wrong password.
const INVALID_CREDENTIALS = errorBody("INVALID_CREDENTIALS", "Invalid email or password");

export const POST = handle(login)(async ({ body }) => {
  const result = await signIn(body);
  if (!result.ok) return { status: 401, body: INVALID_CREDENTIALS };
  return { status: 200, body: { token: result.token, user: result.user } };
});
