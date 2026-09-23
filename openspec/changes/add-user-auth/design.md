## Context

The repo is a Next.js 16 App Router app (TypeScript, npm, running on the host) with Postgres in Docker and Drizzle ORM. `getDb()` in `src/db/index.ts` lazily creates one `postgres-js` client and reuses it across hot reloads. The only table is the `notes` demo, which this change removes.

This change adds the assignment's user/auth API. The API is JSON only, protected routes take `Authorization: Bearer <token>`, and there are three hard rules:
1. Never return a password hash.
2. A missing, bad or expired token returns `401`.
3. No access to another user's account (we return `404`).

It also adds an OpenAPI spec generated from code.

Next.js 16 specifics that affect the design (from `node_modules/next/dist/docs/`):
- In route handlers, `ctx.params` is a **Promise** and is typed with the global `RouteContext<'/path/[id]'>` helper.
- Route handlers are not cached by default.
- `middleware` has been renamed to `proxy`. We don't use either one.

## Goals / Non-Goals

**Goals:**
- The seven endpoints from the proposal, each with a Zod contract that drives validation, response shaping and the OpenAPI document.
- Each of the three rules is enforced in **one shared place**, so a new route can't silently skip it.
- An OpenAPI 3.1 document that can be produced without a running server or database.
- Removal of the notes demo.

**Non-Goals:**
- Changing email or password through the API, email verification, and password reset. The `verification` table exists only because Better Auth requires it.
- OAuth or social login.
- Admin roles, and listing or searching users.
- Rate limiting and brute-force protection on login.
- Browser cookie sessions and CSRF handling. The API is bearer-only.
- Generating a client from the spec.
- An automated test framework. Verification is a scripted curl pass (see Risks).

## Decisions

### D1. Better Auth as a library, called only through `auth.api.*` (no catch-all handler)

`src/lib/auth.ts` exports `getAuth()`, which lazily builds a `betterAuth({...})` instance:
- `database: drizzleAdapter(getDb(), { provider: "pg", schema })`
- `emailAndPassword: { enabled: true, autoSignIn: false, minPasswordLength: 8 }`
- `user.additionalFields: { firstName, lastName }`, both `string`, required and `input: true`
- `advanced.database.generateId: "uuid"`
- `plugins: [bearer()]`
- `secret` and `baseURL` from `BETTER_AUTH_SECRET` and `BETTER_AUTH_URL`

**We do not mount Better Auth's `[...all]` route handler.** Our route handlers call `auth.api.signUpEmail`, `auth.api.signInEmail` and `auth.api.getSession` directly.
- *Why:* the assignment defines the public API exactly. Mounting the catch-all would also expose `/api/auth/sign-up/email`, `/api/auth/sign-in/email`, `/api/auth/get-session` and others. Those are extra surface that bypasses our Zod contracts and response shaping, so rule 1 would no longer be enforced in one place.
- *Why lazy:* like `getDb()`, building the instance at import time would require `DATABASE_URL` during `next build` and in the OpenAPI script.
- *Alternative considered:* mount the catch-all and add rewrites for our paths. It was rejected because it creates two ways into the same logic and more ways to leak data.
- *Alternative considered:* write auth by hand (bcrypt/argon2 plus our own session table). It was rejected because Better Auth gives us vetted hashing and session handling. We still write every route and every authorization check ourselves.

### D2. Data model: Better Auth's four tables, with UUIDs and snake_case columns

The tables are added to `src/db/schema.ts` by hand. The shape comes from `npx @better-auth/cli generate` as a reference, adjusted as follows:
- `user`
  - `id uuid pk default gen_random_uuid()`
  - `email text unique not null`, `email_verified boolean`
  - `name text not null`, `first_name text not null`, `last_name text not null`
  - `image text`
  - `created_at`, `updated_at`
- `account`
  - `id uuid pk`, `account_id`, `provider_id`
  - `user_id uuid → user.id on delete cascade`
  - `password text`, which holds the **hash**
  - token and expiry columns for future OAuth, and timestamps
- `session`
  - `id uuid pk`, `token text unique`, `expires_at`
  - `user_id uuid → user.id on delete cascade`
  - `ip_address`, `user_agent`, timestamps
- `verification`: `id uuid pk`, `identifier`, `value`, `expires_at`, timestamps

`name` is kept because Better Auth requires it. It is always set to `` `${firstName} ${lastName}` `` at registration and on PATCH. It is not part of the public API contract.

- *Why a DB default and `generateId: "uuid"`:* Better Auth sends the id itself, and the default covers rows inserted any other way, such as seeds or Studio.
- *Why cascade:* `DELETE /api/users/:id` removes one row, and that user's credentials and sessions disappear with it, so their tokens stop working immediately.

### D3. The notes table is dropped in the same new migration

`notes` is removed from the schema, and `npm run db:generate` produces one migration that creates the four auth tables and drops `notes`. `0000_*.sql` stays unchanged, because migrations are append-only and existing local databases have already applied it.

drizzle-kit may ask interactively whether `user` (or another new table) is a rename of `notes`. The answer is **"create table"**.

Also removed: `src/app/actions.ts`, the notes UI, the `Note`/`NewNote` types, and the notes `metadata` in `layout.tsx` (title "Notes", which becomes something neutral). `page.tsx` becomes a small static page that links to `/docs`, and `page.module.css` is reduced to match.

### D4. Contracts module: pure Zod, no runtime imports

`src/lib/api/contracts.ts` (the proposal's `schemas.ts`) declares one contract object per endpoint:

```ts
{ method, path, auth: boolean, summary, params?, body?, responses: { 200: UserResponse, 401: ErrorResponse, ... } }
```

Shared schemas, registered with `.meta({ id })` so they become OpenAPI components:
- `User`: exactly `{ id, email, firstName, lastName, createdAt, updatedAt }`
- `RegisterBody`: `{ email, password, firstName, lastName }`
- `LoginBody`: `{ email, password }`
- `LoginResponse`: `{ token, user }`
- `UpdateUserBody`: `{ firstName?, lastName? }`, which must contain at least one key and is `.strict()`
- `Error`: `{ error: { code, message, details? } }`
- `Health`: `{ status: "ok" }`

This module and `src/lib/api/openapi.ts` import **only** `zod` and `zod-openapi`. They never import `@/db`, `@/lib/auth` or `next/*`. That is what lets `scripts/generate-openapi.ts` run with just `tsx`, with no env vars or database.

- *Alternative considered:* co-locate schemas in each `route.ts`. It was rejected because the generator would then have to import route files, and they pull in the database and Better Auth.

### D5. One `handle()` wrapper enforces the rules

`src/lib/api/handler.ts` exports `handle(contract, fn)`, which returns a Next route handler. Route files look like:

```ts
export const PATCH = handle(updateUser)(async ({ session, params, body }) => { ... return { status: 200, body: user } })
```

`handle` is curried. With a single `handle(contract, fn)` call, TypeScript infers the contract type and checks `fn`'s return in the same pass. The returned `status` literals then widen to `number` and no longer match the contract's status union. Currying fixes the contract type first, so each `{ status, body }` pair is type-checked against that status's schema.

`handle` does the following, in order:
1. **Auth (rule 2).** When `contract.auth` is set, it reads `Authorization`. If the header is missing or not of the form `Bearer <non-empty>`, it returns `401`. Otherwise it calls `auth.api.getSession({ headers })` with a `Headers` object that contains **only** the `authorization` header, so cookies are ignored and the API is bearer-only.
   - A `null` result (unknown, expired or revoked token) returns `401`.
   - A Better Auth `APIError` also returns `401`.
   - Only non-auth failures (for example, the database is unreachable) fall through to `500`.
2. **Params.** It awaits `ctx.params` and validates them against `contract.params`. For `:id`, a value that isn't a UUID returns **`404`**, not `400`: it can't be the caller's id, and this avoids a Postgres cast error turning into a `500`.
3. **Body.** It checks the JSON content type, then `await req.json()`. A parse failure returns `400`. It validates with `contract.body.safeParse`, and a failure returns `400` with `details` taken from the Zod issues. Issue messages never echo input values, so a password can't end up in an error.
4. **Handler.** It calls `fn`.
5. **Output shaping (rule 1).** It runs `contract.responses[status].parse(body)`. Zod objects strip unknown keys by default, so even if a handler passes a raw DB row or Better Auth's user object, only the fields in the allow-list are sent. A missing schema for a returned status is a programming error and returns `500`.
6. **Errors.** Any thrown error becomes `500 { error: { code: "INTERNAL", message: "Internal server error" } }`. The error is logged on the server with `console.error(err)`, never the request body. Error messages and stacks are never sent to the client, not even in development.

Every non-2xx response uses the same `Error` shape.

- *Why a wrapper rather than per-route checks:* the rules are "never" and "always" rules, and one enforcement point is the only way that is true by construction.

### D6. Endpoint behavior

| Endpoint | Behavior | Statuses |
|---|---|---|
| `GET /healthz` | Returns `{ status: "ok" }`. It doesn't touch the database; it is a liveness probe. File: `src/app/healthz/route.ts`. | 200 |
| `POST /api/auth/register` | Calls `auth.api.signUpEmail({ body: { email, password, name, firstName, lastName } })` and returns the created user. It does **not** return a token, because `autoSignIn` is off and login is the only way to get one. A duplicate email returns `409`. | 201, 400, 409 |
| `POST /api/auth/login` | Calls `auth.api.signInEmail({ body })` and returns `{ token, user }`. Wrong email and wrong password both return the same `401 INVALID_CREDENTIALS`, with no hint about which part was wrong. | 200, 400, 401 |
| `GET /api/auth/me` | Returns `session.user`, shaped to `User`. | 200, 401 |
| `GET /api/users/:id` | If `id !== session.user.id`, returns `404`. Otherwise selects the user and returns it. | 200, 401, 404 |
| `PATCH /api/users/:id` | Same ownership check (`404`). Updates `firstName` and/or `lastName` and recomputes `name` with Drizzle. Returns the updated user. | 200, 400, 401, 404 |
| `DELETE /api/users/:id` | Same ownership check (`404`). Deletes the `user` row with Drizzle, and cascade removes its accounts and sessions. | 204, 401, 404 |

- The ownership check comes **before** any DB lookup, so "someone else's id" and "id that doesn't exist" produce identical responses with no timing or content difference to probe.
- `/api/users/*` uses Drizzle directly rather than `auth.api.updateUser` or `deleteUser`. Those Better Auth endpoints act on the *session's* user, carry extra config (`deleteUser` needs enabling plus verification), and would hide the explicit ownership check that rule 3 asks us to show.
- Login token (verified against `better-auth@1.7.5`): `signInEmail` returns the raw session token in its result body (`{ token, user, ... }`). The bearer plugin accepts that raw token in `Authorization: Bearer` and signs it with the secret before the lookup. The signed form in the `set-auth-token` header works too, but we don't need `returnHeaders`. Unknown, truncated or garbage tokens make `getSession` return `null`; it doesn't throw.
- Duplicate email (verified against `better-auth@1.7.5`): with `autoSignIn: false`, `signUpEmail` does **not** throw for an existing email. As anti-enumeration it returns a fake success with a synthetic user, and no row is written. Because the spec requires `409 EMAIL_TAKEN`, the register route first looks up the lowercased email with Drizzle and returns `409` if it exists. If a concurrent sign-up wins the race, the unique constraint makes `signUpEmail` throw an `APIError`. The route then re-checks the email and maps that case to `409` too. (Returning `409` deliberately reveals that an email is registered. The assignment asks for it, and it's the usual trade-off for a sign-up form.)

### D7. OpenAPI generation

`src/lib/api/openapi.ts` exports `buildOpenApiDocument()`. It uses `createDocument` from `zod-openapi` to map every contract to `paths`, and it declares a `bearerAuth` HTTP security scheme (`scheme: bearer`), applied to each contract with `auth: true`. The document is served and generated in three places:
- **`GET /api/openapi.json`** (`src/app/api/openapi.json/route.ts`) returns `Response.json(buildOpenApiDocument())`. The document is deterministic, so it can be static (`dynamic = "force-static"`).
- **`GET /docs`** (`src/app/docs/route.ts`) is `ApiReference({ url: "/api/openapi.json" })` from `@scalar/nextjs-api-reference`.
- **`npm run openapi:generate`** runs `tsx scripts/generate-openapi.ts`. It writes `openapi/openapi.json` as pretty-printed JSON with a trailing newline, so diffs are stable. `npm run openapi:check` runs the same script with `--check`: it compares against the file on disk and exits non-zero with a message if they differ.

`tsx` resolves the `@/` alias from `tsconfig.json`, so the contracts can use the same imports as the app.

- *Alternative considered:* `@asteasolutions/zod-to-openapi`. It was rejected in favor of `zod-openapi`, which works natively with Zod v4's `.meta()` and needs no registry or `extendZodWithOpenApi` patching.

### D8. Configuration

`.env.example` gains:
- `BETTER_AUTH_SECRET`: a clearly marked, local-only placeholder, at least 32 chars. `start.sh` copies `.env.example`, so a fresh clone still works with no extra steps.
- `BETTER_AUTH_URL=http://localhost:3000`

`getAuth()` throws a clear error if `BETTER_AUTH_SECRET` is missing, the same way `getDb()` does for `DATABASE_URL`.

### D9. Write-up of the 403-vs-404 choice

A "Security decisions" section is added to `README.md`. It states:
- we return `404` for other users' ids, and why (the API doesn't reveal which ids exist, and the response is identical to a nonexistent id)
- how each of the three rules is enforced (D5)

## Risks / Trade-offs

- **[Better Auth API drift]** Option names such as `generateId: "uuid"`, how the bearer token is returned, and `additionalFields` typing have changed between minor versions. → Pin `better-auth` to an exact minor, and verify D6's token handling against the installed version before building the routes on top.
- **[Session lookup errors turning into 500s]** If a malformed token makes Better Auth throw something other than `APIError`, rule 2 is violated. → Cover it in the curl pass: send a garbage token, a truncated token, `Bearer` with nothing after it, and `Basic xyz`. Adjust the error classification in `handle()` if any of them returns 500.
- **[Hash leaks through a new code path]** Someone could add a route that returns `Response.json(row)` directly, bypassing `handle()`. → Every `/api/*` route uses `handle()`, and the tasks include a grep check for `Response.json` under `src/app/api` outside `openapi.json`. The `User` schema is an allow-list, and the hash isn't even on the `user` table.
- **[Brute-force login]** Calling `auth.api.*` directly bypasses Better Auth's HTTP-level rate limiter. → Accepted for this assignment and listed as a non-goal. Can be added later with a small in-memory limiter in `handle()`.
- **[Interactive drizzle-kit prompt]** The rename-or-create prompt in D3 can't be scripted. → Documented in D3 and in the task step. Answer "create".
- **[`openapi/openapi.json` goes stale]** → `openapi:check` exists. Wiring it into `npm run typecheck` is an easy follow-up, but it isn't done here, to keep typecheck fast.
- **[No automated tests]** → A `scripts/api-smoke.sh` curl script exercises each endpoint and each rule, including another user's id, an expired or garbage token, and a grep of every response for `password` and `$argon`/`scrypt` markers. It is run manually against `scripts/start.sh`.

## Migration Plan

1. Install the dependencies. Add the env vars to `.env.example`, and to your existing `.env` by hand.
2. Update the schema, then run `npm run db:generate` (answer "create") and `npm run db:migrate`. `notes` is dropped and its demo data is lost, which is intended.
3. Rollback: revert the commit and reset the local DB with `scripts/db-down.sh` and a volume reset, then `db:migrate`. There is no production data.

## Open Questions

- Should `PATCH /api/users/:id` also allow changing `email` or `password`? This design says no (see Non-Goals). Adding either one needs re-verification or current-password checks.
- Session lifetime: Better Auth's default is 7 days, with a rolling refresh. That's fine for now; state it in the README.
