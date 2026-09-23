import { healthCheck } from "@/lib/api/contracts";
import { handle } from "@/lib/api/handler";

// Liveness only: no database access.
export const GET = handle(healthCheck)(async () => ({
  status: 200,
  body: { status: "ok" },
}));
