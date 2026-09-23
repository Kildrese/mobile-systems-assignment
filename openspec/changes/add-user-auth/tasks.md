## 1. Dependencies and configuration

- [x] 1.1 Install `better-auth` (exact version pin), `zod` (v4), `zod-openapi` and `@scalar/nextjs-api-reference` as dependencies, and `tsx` as a dev dependency
- [x] 1.2 Add `BETTER_AUTH_SECRET` (a clearly marked local-only placeholder, at least 32 chars) and `BETTER_AUTH_URL=http://localhost:3000` to `.env.example`, and add them to the local `.env` by hand

## 2. Remove the notes demo

- [x] 2.1 Delete `src/app/actions.ts`
- [x] 2.2 Replace `src/app/page.tsx` with a static placeholder page (no DB access) that links to `/docs`, and trim `page.module.css` to match
- [x] 2.3 Update the `metadata` in `src/app/layout.tsx` so it no longer says "Notes" or "notes demo"
- [x] 2.4 Remove the `notes` table and the `Note`/`NewNote` types from `src/db/schema.ts`
- [x] 2.5 Remove the notes demo paragraph from `README.md`

## 3. Auth data model and migration

- [x] 3.1 Generate Better Auth's reference schema with `npx @better-auth/cli generate` and use it to hand-write `user`, `account`, `session` and `verification` in `src/db/schema.ts`: UUID PKs with `defaultRandom()`, snake_case columns, `first_name`/`last_name` on `user`, unique `user.email` and `session.token`, and `ON DELETE CASCADE` on `account.user_id` and `session.user_id`. Don't commit any CLI output files
- [x] 3.2 Run `npm run db:generate` (answer "create table" if drizzle-kit asks whether a table was renamed from `notes`) and confirm the new SQL creates the four tables and drops `notes`, while `0000_*.sql` stays unchanged
- [x] 3.3 Run `npm run db:migrate` against an existing DB and against a fresh one (reset the volume), and check in Drizzle Studio that the four tables exist and `notes` doesn't

## 4. Better Auth instance

- [x] 4.1 Create `src/lib/auth.ts` with a lazy `getAuth()`: Drizzle adapter (`provider: "pg"`, the schema), email/password with `autoSignIn: false` and `minPasswordLength: 8`, `user.additionalFields` `firstName`/`lastName`, `advanced.database.generateId: "uuid"`, the `bearer()` plugin, and `secret`/`baseURL` from the env. It throws a clear error when `BETTER_AUTH_SECRET` is missing
- [x] 4.2 Spike against the installed version: sign up and sign in with `auth.api.*`, then confirm how the login token is returned (in the result body, or in the `set-auth-token` header with `returnHeaders: true`) and that `getSession` accepts it as `Authorization: Bearer`. If the design's assumptions don't hold, update D6 in `design.md`

## 5. API contracts and OpenAPI builder

- [x] 5.1 Create `src/lib/api/contracts.ts`, importing only `zod` and `zod-openapi`, with these shared schemas (`.meta({ id })`): `User`, `Error`, `Health`, `RegisterBody` (strict), `LoginBody`, `LoginResponse`, `UpdateUserBody` (strict, at least one key) and a UUID `UserIdParams`
- [x] 5.2 Add one contract per endpoint (the seven from the proposal) with method, path, `auth`, summary, params/body, and a response schema for every status code listed in design D6
- [x] 5.3 Create `src/lib/api/openapi.ts` with `buildOpenApiDocument()`, which uses `createDocument` to produce OpenAPI 3.1 from the contracts, with a `bearerAuth` security scheme applied to `auth: true` contracts

## 6. Request handler wrapper

- [x] 6.1 Create `src/lib/api/handler.ts` with `handle(contract, fn)`: bearer-only session resolution. Build a `Headers` object with only `authorization`. A missing or malformed header, a `null` session, or an `APIError` returns `401 UNAUTHORIZED`
- [x] 6.2 In `handle`, await `ctx.params` and validate them. An invalid `:id` UUID returns `404 NOT_FOUND`
- [x] 6.3 In `handle`, parse and validate the JSON body. Invalid JSON or schema failures return `400 VALIDATION_ERROR` with `details` from the Zod issues, which must not contain input values
- [x] 6.4 In `handle`, parse the handler's return value through `contract.responses[status]` (which strips unknown keys). Support empty-body `204`. A status without a schema is treated as a `500`
- [x] 6.5 In `handle`, catch everything else and return a generic `500 INTERNAL` response. Log the error on the server, but never the request body

## 7. Endpoints

- [x] 7.1 `src/app/healthz/route.ts`: `GET` returns `{ status: "ok" }`, with no DB access
- [x] 7.2 `src/app/api/auth/register/route.ts`: `POST` calls `signUpEmail` with `name = firstName + " " + lastName` and returns `201` with the user. A duplicate email maps to `409 EMAIL_TAKEN`
- [x] 7.3 `src/app/api/auth/login/route.ts`: `POST` calls `signInEmail` and returns `{ token, user }`. Any credential failure maps to an identical `401 INVALID_CREDENTIALS`, and no `Set-Cookie` header is forwarded
- [x] 7.4 `src/app/api/auth/me/route.ts`: `GET` returns the session user
- [x] 7.5 `src/app/api/users/[id]/route.ts`: `GET`, `PATCH` and `DELETE`, each checking `id === session.user.id` before any DB access (`404` otherwise). `PATCH` updates `firstName`/`lastName`, recomputes `name` and bumps `updatedAt` via Drizzle. `DELETE` removes the user row and returns `204`

## 8. API docs and generation scripts

- [x] 8.1 `src/app/api/openapi.json/route.ts`: `GET` returns `buildOpenApiDocument()` (`dynamic = "force-static"`)
- [x] 8.2 `src/app/docs/route.ts`: Scalar `ApiReference({ url: "/api/openapi.json" })`
- [x] 8.3 `scripts/generate-openapi.ts`: writes `openapi/openapi.json` (2-space JSON and a trailing newline). With `--check`, it compares against the file on disk and exits non-zero with "out of date, run `npm run openapi:generate`"
- [x] 8.4 Add `openapi:generate` and `openapi:check` npm scripts, generate the spec, and commit `openapi/openapi.json`
- [x] 8.5 With the DB stopped and no `.env`, run `npm run openapi:generate` twice and confirm it succeeds and the output is byte-identical

## 9. Documentation

- [x] 9.1 Add a "Security decisions" section to `README.md`: why `404` rather than `403` for other users' ids, how each of the three rules is enforced (`handle()`, response allow-list, bearer-only), and the session lifetime (Better Auth default of 7 days)
- [x] 9.2 Document the new env vars, the `/docs` and `/api/openapi.json` URLs, and the `openapi:*` scripts in `README.md`

## 10. Verification

- [x] 10.1 Write `scripts/api-smoke.sh`, a curl-based script that exercises every scenario in the `health-check`, `user-auth` and `user-management` specs. It registers two users, logs both in, checks cross-user access returns `404`, tries missing/garbage/malformed/`Basic` tokens, an expired token (set `expires_at` in the past via `psql`) and a cookie-only request, deletes a user and then checks the token and login, and scans every response body for `password`, `passwordHash`, `hash` and the stored hash value. It exits non-zero on the first failure
- [x] 10.2 Run `scripts/start.sh` on a fresh DB, then run `scripts/api-smoke.sh` until it passes
- [x] 10.3 Confirm that every `route.ts` under `src/app/api/` (except `openapi.json`) exports only `handle(...)`-wrapped handlers. Use grep for direct `Response.json`/`NextResponse` usage
- [x] 10.4 Run `npm run lint`, `npm run typecheck`, `npm run build` and `npm run openapi:check`, all of which must pass
- [ ] 10.5 Open `/docs`, log in via the "Try it" panel using a token, and call `/api/auth/me` successfully
- [x] 10.6 Run `openspec validate add-user-auth --strict`
