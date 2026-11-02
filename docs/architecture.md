# Architecture and security

## Two origins

The frontend (<http://localhost:5173>) and the backend (<http://localhost:8000>) are **separate origins**, as they are in production. Every call from the browser is a cross-origin request. `openapi/openapi.json` is the contract between them: the backend writes it, and the frontend generates its typed client from it.

- **CORS:** the backend answers only origins listed in `CORS_ORIGINS`. It allows `GET`, `POST`, `PATCH` and `DELETE` with the `Authorization` and `Content-Type` headers, never sends `Access-Control-Allow-Credentials` (no cookies are involved), and adds the headers to error responses too, so the browser can read a `401`. Other origins get no CORS headers.
- **Bearer token in `localStorage`:** after login the frontend stores the token under `token` and sends it as `Authorization: Bearer <token>` to protected endpoints only. A `401` from any call removes the token and shows `/login?next=<current page>`. Route protection in the browser only decides what to show; the backend checks the token on every request.
- **Content-Security-Policy:** production builds carry a CSP `<meta>` tag that allows scripts only from the app's own origin (no inline scripts, no `eval`) and network requests only to itself and `VITE_API_URL`. Inline styles are allowed, because Radix's dialogs and menus insert computed `<style>` elements. `frontend/vercel.json` adds `frame-ancestors 'none'`. The dev server doesn't enforce the policy, because hot reload needs inline scripts. Lint forbids `dangerouslySetInnerHTML`.

A token in `localStorage` can be read by any script running on the page, so XSS is the main risk to it. React's escaping, the ban on `dangerouslySetInnerHTML` and the strict `script-src` are the defence, and a stolen token can be revoked on the server by logging out or changing the password. A cookie set by the backend would be a cross-site cookie (`SameSite=None`), which browsers increasingly block.

## Worker services

The verifier ([`services/verifier/`](../services/verifier/)) is the first agent that runs as its own service. It is a separate Vercel project with its own environment: `VERIFIER_TOKEN` and `GROQ_API_KEY`, and no database URL. The tracker reaches it only through `POST /verify`, so a bug in it, or a page that fools its model, can't reach any state.

- **Shared code, not shared state.** [`packages/agentkit/`](../packages/agentkit/) holds what both sides need: the wire contract (`contract.py`, validated in both directions), the fetch guardrails (`fetch.py`, `guard.py`), the quote and evidence normalizer (`text.py`), the untrusted-data wrapper and the cross-service log line (`wire_log.py`). Neither service imports the other.
- **One token per worker.** `/verify` needs `Authorization: Bearer $VERIFIER_TOKEN`, compared in constant time, and checked before the body is parsed, so an unauthenticated caller learns nothing about the schema. A future worker gets its own token, so one that leaks unlocks only that worker.
- **Idempotent by `request_id`.** The same id with the same body (SHA-256 of the sorted-key JSON) returns the stored response with no new fetch or model call; with another body it gets `409`; while the first copy runs, `503` with `Retry-After`. Stored responses live in the instance's memory: a new instance starts empty, and a retry that lands there does the work again.
- **Code decides the verdict.** The model proposes `supported` with an excerpt, or `unsupported`. Code keeps `supported` only when the excerpt is at most 300 characters and is found in the page the verifier fetched itself, after decoding HTML entities, NFKC, mapping curly quotes, primes, dashes and the no-break space to ASCII, collapsing whitespace and lowercasing. Only code says `unreachable`.

## Security decisions

1. **Passwords are hashed with argon2id** ([pwdlib](https://github.com/frankie567/pwdlib), argon2-cffi's defaults: 64 MiB, 3 iterations, 4 lanes, above OWASP's minimums), with a random salt per hash. Hashes live only in `user_passwords`, never on `users`. A login for an unknown user still verifies the password against a dummy hash, so response times don't reveal which accounts exist.
2. **Password hashes are never returned.** Every route declares a Pydantic `response_model`, and the `User` model is an allow-list (`id`, `username`, `firstName`, `lastName`, `createdAt`, `updatedAt`): even when a route returns a database row, nothing else is serialized. Unexpected errors return a generic `500` and are logged without the request body.
3. **Session tokens are random and stored hashed.** A token is 32 random bytes (`secrets.token_urlsafe`); the database keeps only its SHA-256, so a leaked database can't be used to log in. A token expires after `SESSION_TTL_DAYS` (7) days without use; using it extends the expiry, at most once a day. Logout deletes that session; a password change deletes all of the user's sessions and issues one new token; deleting the account cascades to its password and sessions.
4. **A missing, bad or expired token returns `401`.** Only a well-formed `Authorization: Bearer <token>` header is accepted; cookies are ignored. Unknown, expired and revoked tokens, and the token of a deleted user, all get the same `401 UNAUTHORIZED`.
5. **You can't touch another user's account; we return `404`, not `403`.** `/api/users/:id` compares `:id` with the caller's own id before looking anything up. Another user's id, an id that doesn't exist and a value that isn't a UUID all get the same `404 NOT_FOUND`. A `403` would confirm that the id belongs to a real account.
6. **A wrong current password returns `403`, not `401`.** On change-password, `403 INVALID_PASSWORD` keeps clients from mistaking a typo for an expired token and signing the user out.

Not implemented yet: login rate limiting. Expired sessions are deleted when their user logs in again.
