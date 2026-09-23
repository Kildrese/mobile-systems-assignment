import { me } from "@/lib/api/contracts";
import { handle } from "@/lib/api/handler";

export const GET = handle(me)(async ({ session }) => ({
  status: 200,
  body: session.user,
}));
