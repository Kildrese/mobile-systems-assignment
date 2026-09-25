## Context

Login (`app/services/accounts.py:login`) looks up the user by lowercased username, runs one argon2id verify (a dummy one for unknown usernames) and answers `401 INVALID_CREDENTIALS` identically for every failure. Nothing counts failures. The backend runs on Vercel as a function with many possible instances, so any in-memory counter would be per instance and useless; Postgres (Neon) is the only shared state.

## Goals / Non-Goals

**Goals:**
- Make online password guessing against one account impractical, and slow down spraying one password across many accounts from one client.
- Keep the existing guarantee that responses never reveal whether a username exists.
- Stay friendly to a person who mistypes their password a couple of times.

**Non-Goals:**
- Rate limiting registration, change-password (already needs a valid token) or other endpoints.
- CAPTCHAs, account lockout requiring an admin, or notifying users of failed attempts.
- Defending against a large botnet guessing across many IPs and many usernames at once (the per-username backoff still bounds guesses per account).

## Decisions

### Two keys per attempt: username and client IP
Each login attempt checks, and on failure updates, two rows: `user:<sha256(lowercased username)>` and `ip:<sha256(client ip)>`. The attempt is refused if either is locked. The username key protects one account from many IPs; the IP key limits one client trying many usernames.

### Exponential backoff instead of a fixed window
After the n-th consecutive failure on a key, that key is locked until `now + min(2^(n-1) s, 900 s)`. A typo costs a one- or two-second wait; ten wrong guesses in a row take about 17 minutes; after that each guess costs 15 minutes, which bounds a single account to about 96 guesses a day.

The IP key gets a free allowance before backoff starts (see Open Questions), because many users can share one IP (NYU Wi-Fi, carrier NAT), and one person's typos must not lock out a whole campus.

### Unknown usernames are throttled like real ones
The username key is derived from the submitted string, not from a user row, so it exists for any username. Locked or not, unknown and existing usernames behave the same. This keeps the "indistinguishable" rule of the existing `Log in` requirement.

### Check before any work
A locked key answers `429` before the user lookup and before argon2, so a locked-out attacker costs us one small query instead of a 64 MiB hash. Body validation still runs first, so malformed bodies get `400` as today.

### Postgres table with atomic upserts
`login_throttles(key text primary key, failures int, locked_until timestamptz, last_failure_at timestamptz)`. A failure is one `INSERT … ON CONFLICT (key) DO UPDATE` that increments `failures` and sets `locked_until` in the same statement, so concurrent failures on different instances can't lose updates. When `last_failure_at` is older than an hour, the update starts again from `failures = 1`. A success deletes the username row. Rows untouched for a day are deleted opportunistically on each failure (a short indexed `DELETE`), so the table stays small without a scheduled job.

### Hash the keys
Users sometimes type a password into the username field. Storing SHA-256 digests instead of the raw strings means the table never holds typed secrets or raw IP addresses. The lookup only needs equality, so a hash is enough.

### Client IP
Locally, the IP is the socket peer (`request.client.host`). Behind Vercel, the peer is Vercel's proxy, and the real client is in `X-Forwarded-For`, which Vercel overwrites so clients can't spoof it. A new setting `TRUST_FORWARDED_FOR` (default `false`) takes the first `X-Forwarded-For` entry when `true`; production sets it to `true`. Trusting that header anywhere else would let any client choose its own IP key.

### Response
`429` with `{ "error": { "code": "RATE_LIMITED", "message": "Too many login attempts. Try again later." } }` and `Retry-After: <seconds>` (rounded up, at least 1). CORS adds `expose_headers=["Retry-After"]`, otherwise the browser hides the header from the frontend.

## Risks / Trade-offs

- **[An attacker locks a real user out by failing on purpose]** → Accepted: the lock is at most 15 minutes and lifts by itself; the user can still log in afterwards. This is the usual trade-off of per-account throttling.
- **[Shared IPs]** → The IP allowance (Open Questions) keeps normal typo rates on a campus network from locking everyone out.
- **[One extra write per failed login]** → Small compared to the argon2 verify it accompanies.
- **[Clock skew between instances]** → All times come from Postgres `now()`, not from the instances.

## Migration Plan

1. Add the model and generate the migration (additive: a new table only).
2. Production order: **migrate first, then deploy**, since the new code needs the table and the old code ignores it.
3. Rollback: deploy the previous version; the table can stay or be dropped by the downgrade.

## Open Questions

- **IP allowance:** proposed default is 20 failures per IP (within the one-hour decay) before the IP key starts backing off. Should it be different?
- **Settings:** proposed `LOGIN_BACKOFF_MAX_SECONDS=900` and `LOGIN_IP_FREE_FAILURES=20` as backend settings with those defaults, so tests and production can tune them. Or hard-code them?
