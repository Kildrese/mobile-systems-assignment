import { register } from "@/lib/api/contracts";
import { ERRORS, handle } from "@/lib/api/handler";
import { registerUser } from "@/lib/services/account";

export const POST = handle(register)(async ({ body }) => {
  const result = await registerUser(body);
  if (!result.ok) return { status: 409, body: ERRORS.EMAIL_TAKEN };
  return { status: 201, body: result.user };
});
