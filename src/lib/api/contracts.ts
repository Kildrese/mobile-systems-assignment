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

// Same rules as Better Auth's username plugin (see `@/lib/auth`).
const Username = z
  .string()
  .trim()
  .min(3)
  .max(30)
  .regex(/^[a-zA-Z0-9_.]+$/, "Use only letters, digits, underscores and periods")
  .toLowerCase()
  .meta({ description: "3-30 letters, digits, `_` or `.`. Case-insensitive; stored lowercased." });

export const User = z
  .object({
    id: z.uuid(),
    email: z.email(),
    username: z.string(),
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
    "USERNAME_TAKEN",
    "INVALID_PASSWORD",
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
    username: Username,
    password: z.string().min(8).max(128),
    firstName: Name,
    lastName: Name,
  })
  .meta({ id: "RegisterBody" });

export const LoginBody = z
  .object({
    identifier: z.string().trim().min(1).max(254).meta({
      description: "Your email or your username.",
    }),
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
    username: Username.optional(),
    firstName: Name.optional(),
    lastName: Name.optional(),
  })
  .refine((b) => Object.values(b).some((v) => v !== undefined), {
    message: "Provide at least one of username, firstName or lastName",
  })
  .meta({ id: "UpdateUserBody" });

export const ChangePasswordBody = z
  .strictObject({
    currentPassword: z.string().min(1).max(128),
    newPassword: z.string().min(8).max(128),
  })
  .meta({ id: "ChangePasswordBody" });

export const ChangePasswordResponse = z
  .object({
    token: z.string().meta({
      description: "The new bearer token. Every previous token is revoked.",
    }),
  })
  .meta({ id: "ChangePasswordResponse" });

export const ChangeEmailBody = z
  .strictObject({
    newEmail: z.email().max(254),
    currentPassword: z.string().min(1).max(128),
  })
  .meta({ id: "ChangeEmailBody" });

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
// 403, not 401: clients treat 401 as "token dead, sign out", and a typo in
// the current password shouldn't sign the user out.
const forbidden = error("The current password is wrong.");
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
    409: error("The email (EMAIL_TAKEN) or username (USERNAME_TAKEN) is already registered."),
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
    401: error("Unknown email or username, or wrong password (indistinguishable)."),
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

export const logout = defineContract({
  method: "post",
  path: "/api/auth/logout",
  operationId: "logout",
  summary: "Log out (revoke the current token)",
  tags: ["Auth"],
  auth: true,
  responses: {
    204: { description: "The token is revoked. Your other sessions stay valid." },
    401: unauthorized,
    500: internal,
  },
});

export const changePassword = defineContract({
  method: "post",
  path: "/api/auth/change-password",
  operationId: "changePassword",
  summary: "Change your password",
  tags: ["Auth"],
  auth: true,
  body: ChangePasswordBody,
  responses: {
    200: {
      description: "Every session is revoked, including this one. Use the returned token from now on.",
      schema: ChangePasswordResponse,
    },
    400: badRequest,
    401: unauthorized,
    403: forbidden,
    500: internal,
  },
});

export const changeEmail = defineContract({
  method: "post",
  path: "/api/auth/change-email",
  operationId: "changeEmail",
  summary: "Change your email",
  tags: ["Auth"],
  auth: true,
  body: ChangeEmailBody,
  responses: {
    200: {
      description: "The updated user. Takes effect immediately, without verification; your token keeps working.",
      schema: User,
    },
    400: badRequest,
    401: unauthorized,
    403: forbidden,
    409: error("The email is already registered to another user."),
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
  summary: "Update your own username or name",
  tags: ["Users"],
  auth: true,
  params: UserIdParams,
  body: UpdateUserBody,
  responses: {
    200: { description: "The updated user.", schema: User },
    400: badRequest,
    401: unauthorized,
    404: notFound,
    409: error("The username is already taken by another user."),
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
  logout,
  changePassword,
  changeEmail,
  getUser,
  updateUser,
  deleteUser,
] as const;
