// The API contract: one Zod schema per request body, path params and response
// status. The same schemas validate requests, shape responses (unknown keys are
// stripped) and generate the OpenAPI document.
//
// This module must only import `zod` and `zod-openapi` so the OpenAPI script
// can load it without a database, env vars or Next.js.
import "zod-openapi";
import { z } from "zod";

// ---------------------------------------------------------------------------
// Shared schemas
// ---------------------------------------------------------------------------

// Handlers return `Date`s (from Drizzle and Better Auth); `Response.json`
// serializes them as ISO strings.
const Timestamp = z.date().meta({
  override: { type: "string", format: "date-time" },
});

const Name = z.string().trim().min(1).max(100);

export const User = z
  .object({
    id: z.uuid(),
    email: z.email(),
    firstName: z.string(),
    lastName: z.string(),
    createdAt: Timestamp,
    updatedAt: Timestamp,
  })
  .meta({ id: "User", description: "A user. Never includes credentials." });

export const ErrorCode = z
  .enum([
    "VALIDATION_ERROR",
    "UNAUTHORIZED",
    "INVALID_CREDENTIALS",
    "NOT_FOUND",
    "EMAIL_TAKEN",
    "INTERNAL",
  ])
  .meta({ id: "ErrorCode" });

export const ValidationIssue = z
  .object({
    path: z.array(z.union([z.string(), z.number()])),
    code: z.string(),
    message: z.string(),
  })
  .meta({ id: "ValidationIssue" });

export const ErrorResponse = z
  .object({
    error: z.object({
      code: ErrorCode,
      message: z.string(),
      details: z.array(ValidationIssue).optional(),
    }),
  })
  .meta({ id: "Error" });

export const Health = z
  .object({ status: z.literal("ok") })
  .meta({ id: "Health" });

export const RegisterBody = z
  .strictObject({
    email: z.email().max(254),
    password: z.string().min(8).max(128),
    firstName: Name,
    lastName: Name,
  })
  .meta({ id: "RegisterBody" });

export const LoginBody = z
  .object({
    email: z.email().max(254),
    password: z.string().min(1).max(128),
  })
  .meta({ id: "LoginBody" });

export const LoginResponse = z
  .object({
    token: z.string().meta({
      description: "Send as `Authorization: Bearer <token>`.",
    }),
    user: User,
  })
  .meta({ id: "LoginResponse" });

export const UpdateUserBody = z
  .strictObject({
    firstName: Name.optional(),
    lastName: Name.optional(),
  })
  .refine((b) => b.firstName !== undefined || b.lastName !== undefined, {
    message: "Provide at least one of firstName or lastName",
  })
  .meta({ id: "UpdateUserBody" });

export const UserIdParams = z.object({
  id: z.uuid().meta({ description: "The user's id (must be your own)." }),
});

// ---------------------------------------------------------------------------
// Contracts
// ---------------------------------------------------------------------------

export type ResponseSpec = {
  description: string;
  // `undefined` means the response has no body (e.g. 204).
  schema?: z.ZodType;
};

export type Contract = {
  method: "get" | "post" | "patch" | "delete";
  // OpenAPI-style path, e.g. `/api/users/{id}`.
  path: string;
  operationId: string;
  summary: string;
  tags: string[];
  auth: boolean;
  params?: z.ZodObject;
  body?: z.ZodType;
  responses: Record<number, ResponseSpec>;
};

function defineContract<const C extends Contract>(contract: C): C {
  return contract;
}

const error = (description: string) => ({ description, schema: ErrorResponse });

const badRequest = error("The body is not valid JSON or fails validation.");
const unauthorized = error("Missing, malformed, unknown or expired token.");
const notFound = error(
  "The id is not your own. Same response whether it belongs to someone else, doesn't exist or isn't a UUID.",
);
const internal = error("Unexpected server error.");

export const healthCheck = defineContract({
  method: "get",
  path: "/healthz",
  operationId: "healthCheck",
  summary: "Liveness check",
  tags: ["Health"],
  auth: false,
  responses: {
    200: { description: "The server is up.", schema: Health },
    500: internal,
  },
});

export const register = defineContract({
  method: "post",
  path: "/api/auth/register",
  operationId: "register",
  summary: "Create an account",
  tags: ["Auth"],
  auth: false,
  body: RegisterBody,
  responses: {
    201: { description: "The created user. No token; log in next.", schema: User },
    400: badRequest,
    409: error("The email is already registered."),
    500: internal,
  },
});

export const login = defineContract({
  method: "post",
  path: "/api/auth/login",
  operationId: "login",
  summary: "Log in and get a bearer token",
  tags: ["Auth"],
  auth: false,
  body: LoginBody,
  responses: {
    200: { description: "A bearer token and the user.", schema: LoginResponse },
    400: badRequest,
    401: error("Unknown email or wrong password (indistinguishable)."),
    500: internal,
  },
});

export const me = defineContract({
  method: "get",
  path: "/api/auth/me",
  operationId: "getCurrentUser",
  summary: "Get the logged-in user",
  tags: ["Auth"],
  auth: true,
  responses: {
    200: { description: "The logged-in user.", schema: User },
    401: unauthorized,
    500: internal,
  },
});

export const getUser = defineContract({
  method: "get",
  path: "/api/users/{id}",
  operationId: "getUser",
  summary: "Read your own user",
  tags: ["Users"],
  auth: true,
  params: UserIdParams,
  responses: {
    200: { description: "The user.", schema: User },
    401: unauthorized,
    404: notFound,
    500: internal,
  },
});

export const updateUser = defineContract({
  method: "patch",
  path: "/api/users/{id}",
  operationId: "updateUser",
  summary: "Update your own name",
  tags: ["Users"],
  auth: true,
  params: UserIdParams,
  body: UpdateUserBody,
  responses: {
    200: { description: "The updated user.", schema: User },
    400: badRequest,
    401: unauthorized,
    404: notFound,
    500: internal,
  },
});

export const deleteUser = defineContract({
  method: "delete",
  path: "/api/users/{id}",
  operationId: "deleteUser",
  summary: "Delete your own account",
  tags: ["Users"],
  auth: true,
  params: UserIdParams,
  responses: {
    204: { description: "Deleted. All of your sessions are revoked." },
    401: unauthorized,
    404: notFound,
    500: internal,
  },
});

export const contracts = [
  healthCheck,
  register,
  login,
  me,
  getUser,
  updateUser,
  deleteUser,
] as const;
