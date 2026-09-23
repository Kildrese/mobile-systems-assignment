import { APIError } from "better-auth/api";
import { login } from "@/lib/api/contracts";
import { errorBody, handle } from "@/lib/api/handler";
import { getAuth } from "@/lib/auth";

// Same body for unknown email and wrong password.
const INVALID_CREDENTIALS = errorBody("INVALID_CREDENTIALS", "Invalid email or password");

export const POST = handle(login)(async ({ body }) => {
  try {
    // Better Auth's response headers (including Set-Cookie) are dropped: only
    // the token in the JSON body is returned.
    const { token, user } = await getAuth().api.signInEmail({
      body: { email: body.email, password: body.password },
    });
    return { status: 200, body: { token, user } };
  } catch (err) {
    if (err instanceof APIError && err.statusCode < 500) {
      return { status: 401, body: INVALID_CREDENTIALS };
    }
    throw err;
  }
});
