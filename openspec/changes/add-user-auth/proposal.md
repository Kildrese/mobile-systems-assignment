## Why

The app has no concept of users yet. Every future feature needs to know who is calling, so we need accounts, login, and a way to authenticate API requests. The API is JSON-only and protected routes take `Authorization: Bearer <token>`, so authentication must work with a bearer token rather than relying only on browser cookies. The API should also be self-documenting with an OpenAPI spec, so it can be explored and tested without reading source.

## What Changes

- Add **Better Auth** as the authentication library, backed by the existing Postgres database through its Drizzle adapter.
- Add Better Auth's core tables to the Drizzle schema, with one committed migration:
  - `user`: the application's user record. It uses a **UUID primary key** and has `email`, `name`, `firstName`, `lastName` and timestamps. `name` is derived as `firstName + " " + lastName`.
  - `account`: login credentials per provider. The email/password **hash lives here**, not on `user`.
  - `session`: active sessions and tokens.
  - `verification`: email-verification and reset tokens, required by Better Auth.
- Enable email/password sign-up and the Better Auth **bearer plugin**, so login returns a token that clients send as `Authorization: Bearer <token>`.
- Add these HTTP endpoints:

  | Method | Path                 | Auth | Purpose                           |
  |--------|----------------------|------|-----------------------------------|
  | GET    | `/healthz`           | no   | returns `{ "status": "ok" }`      |
  | POST   | `/api/auth/register` | no   | create an account                 |
  | POST   | `/api/auth/login`    | no   | returns a token                   |
  | GET    | `/api/auth/me`       | yes  | the logged-in user                |
  | GET    | `/api/users/:id`     | yes  | read a user                       |
  | PATCH  | `/api/users/:id`     | yes  | update a user                     |
  | DELETE | `/api/users/:id`     | yes  | delete a user                     |

- `/register`, `/login` and `/me` are thin wrappers around Better Auth's server API (`auth.api.*`), so the public contract stays stable no matter how Better Auth names its own routes.
- All endpoints take JSON and return JSON, including errors. A malformed body or invalid fields return `400`.
- **Zod schemas are the single source of truth for the API contract (code-first).** Each endpoint's request body, path params and responses (per status code) are defined once in Zod and used for three things:
  - runtime validation of input, which produces the `400`s
  - shaping output, so responses are parsed through the response schema and unknown fields such as the hash are stripped
  - generating an **OpenAPI 3.1 document** with `zod-openapi`, served at `GET /api/openapi.json`
- An interactive API reference built with Scalar is served at `GET /docs`, rendered from that document.
- New npm scripts:
  - `npm run openapi:generate` writes the same document to a committed `openapi/openapi.json`, without starting the server or database, so API changes show up as diffs.
  - `npm run openapi:check` fails if the committed file is out of date with the schemas.
- Client generation is out of scope. There is no client yet, and one can be generated from `/api/openapi.json` later.
- The API enforces three rules on every endpoint:
  1. **Never return a password hash.** Not from any endpoint, not in an error, not in development. User responses are built from an explicit allow-list of fields, never by spreading a DB row.
  2. **No token, bad token or expired token returns `401`.** Never `200` or `500`. This is enforced in one shared helper that every protected route uses.
  3. **You cannot touch another user's account.** `GET`, `PATCH` and `DELETE /api/users/:id` succeed only when `:id` is the caller's own id. Otherwise they return **`404`**, the same response as for an id that doesn't exist. That way the API doesn't reveal which user ids exist. It is used consistently across all three methods and documented in the write-up.
- There are no admin roles in this change. Deleting a user cascades to that user's accounts and sessions, so its tokens stop working immediately.
- **BREAKING** Remove the `notes` demo, which only existed to prove the database round trip worked:
  - drop the `notes` table in a new migration (the committed `0000` migration stays, since migration history is append-only)
  - delete `src/app/actions.ts`
  - replace the home page (`src/app/page.tsx` and `page.module.css`) with a minimal placeholder
  - remove the `Note`/`NewNote` types and the README section about the demo

## Capabilities

### New Capabilities
- `health-check`: an unauthenticated liveness endpoint at `/healthz`.
- `user-auth`: account registration, login that returns a bearer token, resolving the current user from a token, and the `user`/`account`/`session`/`verification` data model.
- `user-management`: authenticated read, update and delete of users by id, restricted to the caller's own account (`404` otherwise).
- `api-docs`: an OpenAPI 3.1 document generated from the Zod schemas at `/api/openapi.json`, plus an interactive reference at `/docs`, and the `openapi:generate`/`openapi:check` scripts that keep a committed `openapi/openapi.json` in sync. Every endpoint in this change, including its bearer auth and error responses, must appear in it.

### Modified Capabilities
- `web-app`: remove the "Demo page reads and writes data end to end" requirement. The home page no longer lists or adds notes.
- `db-migrations`: scenarios that name the `notes` table (schema defined, initial migration, apply to a fresh DB, Studio shows it) now refer to the auth tables (`user`, `account`, `session`, `verification`).
- `dev-scripts`: the "Fresh clone" scenario no longer expects the app to show "the notes page", only that it is reachable.

## Impact

- **Dependencies:**
  - adds `better-auth`, which has password hashing built in, so no separate hashing library is needed
  - adds `zod` (v4) and `zod-openapi` for validation and spec generation
  - adds `@scalar/nextjs-api-reference` for the `/docs` page
  - adds `tsx` as a dev dependency to run the TypeScript generation script, which imports the schemas through the `@/` path alias
- **Configuration:** new env vars `BETTER_AUTH_SECRET` and `BETTER_AUTH_URL`, added to `.env.example`.
- **Code:**
  - new `src/lib/auth.ts` for the Better Auth instance
  - new auth tables in `src/db/schema.ts`
  - new route handlers under `src/app/healthz/` and `src/app/api/`
  - a shared helper that resolves the session from the request headers
  - Zod contracts for every endpoint, in `src/lib/api/contracts.ts`
  - the OpenAPI document builder, in `src/lib/api/openapi.ts`
  - route handlers for `/api/openapi.json` and `/docs`
  - new `scripts/generate-openapi.ts`, which writes the committed `openapi/openapi.json`
- **Database:** one new Drizzle migration in `drizzle/` that creates the auth tables and drops `notes`. Any local notes data is lost; it was only demo data.
- **Removed code:** `src/app/actions.ts`, the notes UI in `src/app/page.tsx` and `page.module.css`, the notes types in `src/db/schema.ts`, and the demo paragraph in `README.md`.
- **Clients:** authenticated endpoints need the `Authorization: Bearer <token>` header and return `401` without a valid token.
- **Provider choice:** Better Auth is a self-hosted library, not a managed service. Users, hashes and sessions live in our own Postgres, and every route and authorization check is written by us. That fits the assignment's recommendation to understand the security side rather than hand it to Clerk or Auth0.
- **Write-up:** the assignment write-up needs to say that we chose `404` for other users' ids, and why.
