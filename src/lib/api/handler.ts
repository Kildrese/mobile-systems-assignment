// `handle(contract, fn)` turns a contract and a handler into a Next.js route
// handler. It is the one place that enforces the API's rules:
//   - protected routes need a valid `Authorization: Bearer` token (else 401)
//   - params and bodies are validated against the contract (else 404 / 400)
//   - responses are parsed through the contract's allow-list schema, so fields
//     like password hashes can never leak
//   - unexpected errors become an opaque 500
import type { z } from "zod";
import { getSessionByToken, type Session } from "@/lib/auth";
import type { Contract, ErrorCode, ErrorResponse } from "./contracts";

type Responses<C extends Contract> = C["responses"];
type Status<C extends Contract> = keyof Responses<C> & number;

// What a handler may return: one of the contract's statuses, with a body
// matching that status's schema (or no body when it has none, e.g. 204).
export type HandlerResult<C extends Contract> = {
  [S in Status<C>]: Responses<C>[S] extends { schema: infer Schema extends z.ZodType }
    ? { status: S; body: z.input<Schema> }
    : { status: S; body?: undefined };
}[Status<C>];

type HandlerInput<C extends Contract> = {
  req: Request;
  session: C["auth"] extends true ? Session : null;
  params: C["params"] extends z.ZodType ? z.output<C["params"]> : undefined;
  body: C["body"] extends z.ZodType ? z.output<C["body"]> : undefined;
};

type RouteContext = { params: Promise<Record<string, string | string[] | undefined>> };

type ErrorBody = z.input<typeof ErrorResponse>;

function errorBody(
  code: z.output<typeof ErrorCode>,
  message: string,
  details?: NonNullable<ErrorBody["error"]["details"]>,
): ErrorBody {
  return { error: { code, message, ...(details ? { details } : {}) } };
}

// Every error body a route returns, so the same case always gets the same
// message. NOT_FOUND is shared by "not yours / doesn't exist / not a UUID".
export const ERRORS = {
  NOT_FOUND: errorBody("NOT_FOUND", "Not found"),
  UNAUTHORIZED: errorBody("UNAUTHORIZED", "Authentication required"),
  // Same body for unknown email and wrong password.
  INVALID_CREDENTIALS: errorBody("INVALID_CREDENTIALS", "Invalid email or password"),
  INVALID_PASSWORD: errorBody("INVALID_PASSWORD", "Current password is incorrect"),
  EMAIL_TAKEN: errorBody("EMAIL_TAKEN", "Email is already registered"),
  INTERNAL: errorBody("INTERNAL", "Internal server error"),
};

function json(status: number, body: unknown): Response {
  return Response.json(body, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

function validationError(message: string, issues: z.core.$ZodIssue[] = []) {
  // Only path, code and Zod's own message; never the input value.
  const details = issues.map((i) => ({
    path: i.path.map((p) => (typeof p === "symbol" ? String(p) : p)),
    code: i.code,
    message: i.message,
  }));
  return json(400, errorBody("VALIDATION_ERROR", message, details));
}

// Bearer-only: cookies and every other header are ignored.
async function resolveSession(req: Request): Promise<Session | null> {
  const match = /^Bearer ([^\s]+)$/i.exec(req.headers.get("authorization") ?? "");
  return match ? getSessionByToken(match[1]) : null;
}

async function readJson(req: Request): Promise<{ ok: true; value: unknown } | { ok: false }> {
  const type = req.headers.get("content-type") ?? "";
  if (!/^application\/json\s*(;|$)/i.test(type)) return { ok: false };
  try {
    return { ok: true, value: await req.json() };
  } catch {
    return { ok: false };
  }
}

// Curried (`handle(contract)(fn)`) so `C` is fixed before `fn` is checked;
// otherwise TypeScript widens the returned `status` literals to `number`.
export function handle<const C extends Contract>(contract: C) {
  return (fn: (input: HandlerInput<C>) => Promise<HandlerResult<C>>) =>
    async (req: Request, ctx: RouteContext): Promise<Response> => {
    try {
      let session: Session | null = null;
      if (contract.auth) {
        session = await resolveSession(req);
        if (!session) return json(401, ERRORS.UNAUTHORIZED);
      }

      let params: unknown = undefined;
      if (contract.params) {
        const parsed = contract.params.safeParse(await ctx.params);
        // The only path param is a user id; an invalid one can't be yours.
        if (!parsed.success) return json(404, ERRORS.NOT_FOUND);
        params = parsed.data;
      }

      let body: unknown = undefined;
      if (contract.body) {
        const raw = await readJson(req);
        if (!raw.ok) {
          return validationError("Request body must be valid JSON (Content-Type: application/json)");
        }
        const parsed = contract.body.safeParse(raw.value);
        if (!parsed.success) {
          return validationError("Request body failed validation", parsed.error.issues);
        }
        body = parsed.data;
      }

      const result = await fn({ req, session, params, body } as HandlerInput<C>);

      const spec = contract.responses[result.status];
      if (!spec) {
        throw new Error(`${contract.operationId}: status ${result.status} is not in the contract`);
      }
      if (!spec.schema) return new Response(null, { status: result.status });
      // Strips anything not in the response schema (the allow-list).
      return json(result.status, spec.schema.parse(result.body));
    } catch (err) {
      // Log the error, never the request body.
      console.error(`[api] ${contract.method.toUpperCase()} ${contract.path} failed:`, err);
      return json(500, ERRORS.INTERNAL);
    }
    };
}
