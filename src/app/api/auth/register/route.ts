import { register } from "@/lib/api/contracts";
import { errorBody, handle } from "@/lib/api/handler";
import { registerUser } from "@/lib/services/account";

const EMAIL_TAKEN = errorBody("EMAIL_TAKEN", "Email is already registered");

export const POST = handle(register)(async ({ body }) => {
  const result = await registerUser(body);
  if (!result.ok) return { status: 409, body: EMAIL_TAKEN };
  return { status: 201, body: result.user };
});
