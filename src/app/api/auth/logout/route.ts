import { logout } from "@/lib/api/contracts";
import { handle } from "@/lib/api/handler";
import { signOut } from "@/lib/services/account";

export const POST = handle(logout)(async ({ session }) => {
  await signOut(session.session.token);
  return { status: 204 };
});
