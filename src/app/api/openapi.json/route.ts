import { buildOpenApiDocument } from "@/lib/api/openapi";

// The document only depends on the contracts, so it is built once at build time.
export const dynamic = "force-static";

export function GET() {
  return Response.json(buildOpenApiDocument());
}
