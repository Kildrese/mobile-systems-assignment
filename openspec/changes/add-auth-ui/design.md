## Context

This is a Next.js 16 App Router app with Better Auth 1.7.5 used as a library. Our own route handlers call `getAuth().api.*`; Better Auth's catch-all handler is not mounted. The JSON API is **bearer-only**: `src/lib/api/handler.ts` resolves the session from `Authorization: Bearer` and ignores cookies, and login returns the token in the body without setting a cookie. `PATCH` and `DELETE /api/users/:id` already cover changing the name and deleting the account. There's no sign-out, change-password or change-email yet, and no UI apart from a placeholder `/` page and the Scalar `/docs` page. shadcn is set up (`radix-rhea` style, Tailwind v4, lucide), but only `button` is installed.

Next 16 specifics, from `node_modules/next/dist/docs/`:
- `middleware.ts` is now **`proxy.ts`** (`export function proxy(req)`, plus an optional `config.matcher`), and it runs on the Node.js runtime.
- The docs recommend the proxy only for optimistic, cookie-only checks, with the real check in a Data Access Layer close to the data.
- `cookies()` from `next/headers` is async, and can only set cookies in Server Actions and route handlers, not while a Server Component is rendering.

Better Auth behaviour checked in `node_modules/better-auth/dist/api/routes/`:
- `changePassword` runs behind `sensitiveSessionMiddleware`, which rejects sessions older than `session.freshAge` (default 1 day) with `SESSION_NOT_FRESH`. With `revokeOtherSessions: true` it deletes **all** of the user's sessions, creates a new one and returns `{ token }`.
- `changeEmail` needs `user.changeEmail.enabled` plus either verification email sending or `updateEmailWithoutVerification`. When the new email is already taken it deliberately returns `{ status: true }` without changing anything, to hide which emails exist.
- `signOut` reads the session token from the signed session cookie. The bearer plugin turns an `Authorization: Bearer` header into that cookie in a before-hook.

## Goals / Non-Goals

**Goals:**
- A browser UI for register, sign in, sign out, edit name, change email, change password and delete account, built with shadcn and full-page `login-03`/`signup-03` screens.
- Signed-out visitors can never see an app page. They're redirected to `/login` and come back to where they were after signing in.
- The API gains sign-out, change-password and change-email, so a mobile client can do everything the web UI can.
- The web and API paths share one implementation of every account rule.

**Non-Goals:**
- Email verification, password reset, "forgot password", and sending any email.
- OAuth or social login, 2FA, and "remember me".
- Listing or managing active sessions or devices.
- Rate limiting and brute-force protection (still out of scope, as in `add-user-auth`).
- Dark-mode toggle, i18n, and a design system beyond the shadcn defaults.
- Automated browser tests. The UI is checked by hand against the scenarios; the API is covered by `scripts/api-smoke.sh`.

## Decisions

### D1. Web session = our own httpOnly cookie holding the Better Auth session token

Server Actions sign in with `getAuth().api.signInEmail` (the same call the API uses) and write the returned token into a cookie named `session`:
- `httpOnly`, `sameSite: "lax"`, `path: "/"`
- `secure` in production
- `expires` equal to the session's `expiresAt`

To read the session, `src/lib/session.ts` turns the cookie into a bearer header and calls `getAuth().api.getSession({ headers: { authorization: "Bearer <token>" } })`. That is the same path `resolveSession` in `handler.ts` takes.

- *Why:*
  - The token never reaches client JavaScript, so XSS can't steal it.
  - Pages render on the server with the user already known, with no flash of signed-out content.
  - The proxy can see the cookie.
  - The JSON API is untouched and stays bearer-only, so it needs no CSRF protection.
- *Why not Better Auth's own cookie* (`better-auth.session_token`, set via `nextCookies()`/the catch-all): it would mean mounting the catch-all or using the `nextCookies` plugin. The catch-all brings back the extra surface that `add-user-auth` D1 rejected, and `nextCookies` couples cookie writing to Better Auth's internals. With our own cookie, one small module owns the web session.
- *Alternative considered:* token in `localStorage` calling `/api/*` from the client. It was rejected because of XSS exposure, because the proxy can't see it, and because every page would become a client component with a loading flash.
- *CSRF:* mutations happen only through Server Actions. Next checks their `Origin` against `Host` and they only accept POST, and the `SameSite=Lax` cookie adds a second layer. No route handler reads the cookie.

### D2. Two-layer route protection: `src/proxy.ts` (optimistic) plus `requireSession()` (authoritative)

- **Proxy.**
  - It matches everything except `api`, `_next/static`, `_next/image`, `favicon.ico`, `healthz`, `docs` and files with an extension.
  - When the path is not `/login` or `/register` and there's no `session` cookie, it redirects to `/login?next=<pathname+search>`.
  - It never touches the database. The Next docs warn against DB work in the proxy because it runs on every request, including prefetches.
- **`requireSession()`**, in `src/lib/session.ts`, imports `server-only` and is wrapped in React `cache()` so it runs once per request.
  - It reads the cookie and validates it with Better Auth.
  - When the session is invalid, it calls `redirect("/login?next=…")`. The current path comes from a request header the proxy sets (`x-pathname`), because Server Components can't see the URL.
  - `(app)/layout.tsx` calls it, and so does every Server Action that needs a user.
  - Layouts don't re-render on client navigation, so each `(app)` page also calls `requireSession()` itself (cached, so it's cheap). This follows the Next docs' warning not to rely on layouts alone for auth checks.
- **Redirecting away from the auth pages** (signed-in user opens `/login` or `/register`) is done by those pages on the server with a *real* session check, not by the proxy. If the proxy did it from cookie presence alone, a stale cookie would loop: the proxy sends `/login` to `/`, the layout finds the session invalid and sends it back to `/login`, and so on. Server Components can't clear the stale cookie. It stays until the next sign-in overwrites it, or until sign-out, which deletes it.
- *Alternative considered:* layout check only. It was rejected because the page would start rendering before the redirect, and the proxy is cheap.

### D3. Route groups

```
src/app/
  (auth)/layout.tsx          full-screen muted background (login-03 wrapper)
  (auth)/login/page.tsx
  (auth)/register/page.tsx
  (app)/layout.tsx           requireSession() + header with user menu + <Toaster/>
  (app)/page.tsx             home (replaces src/app/page.tsx and page.module.css)
  (app)/account/page.tsx
  docs/route.ts              unchanged, public
```

The blocks are installed with the shadcn CLI:
- `login-03` gives `components/login-form.tsx`, moved to `components/auth/login-form.tsx`.
- `signup-03` gives `signup-form.tsx`.

In both, the social buttons, the "Or continue with" separator, the "Forgot password" link and the terms footer are removed. The forms are client components that post to Server Actions.

### D4. Shared account service: `src/lib/services/account.ts`

This is a server-only module of plain functions that know nothing about HTTP or forms. Each returns a discriminated union such as `{ ok: true, … } | { ok: false, code: "EMAIL_TAKEN" | "INVALID_PASSWORD" | "INVALID_CREDENTIALS" }`:
- `registerUser`
- `signIn` → `{ token, expiresAt, user }`
- `signOut(token)`
- `updateName(userId, …)`
- `changeEmail(userId, { newEmail, currentPassword })`
- `changePassword(token, { currentPassword, newPassword })` → `{ token, expiresAt }`
- `deleteAccount(userId)`

- The route handlers become thin mappers, from `code` to HTTP status and from `ErrorCode` to body. The logic now inline in `register`, `login` and `users/[id]` moves here unchanged.
- Server Actions map the same codes to field errors.
- *Why:* the API contract and the UI have to follow the same rules. If they were written twice they would drift apart. This rules out, for example, the UI calling `fetch("/api/...")` against its own server, which would need the token in JS or a server-to-self round trip.
- Input validation stays in the Zod schemas in `contracts.ts`. Server Actions parse `FormData` with the **same** schemas (`RegisterBody`, `LoginBody`, `UpdateUserBody`, `ChangeEmailBody`, `ChangePasswordBody`) and add a UI-only `confirmPassword` refinement.

### D5. Change password through `auth.api.changePassword` with `revokeOtherSessions: true`, and `session.freshAge: 0`

- `changePassword` is called with `headers: { authorization: "Bearer <token>" }` and returns `{ token }`.
- The API responds `200 { token }`.
- The Server Action overwrites the cookie with the new token, so the browser stays signed in while every other session ends.
- Better Auth reports a wrong current password as an `APIError` with code `INVALID_PASSWORD`, which the service maps to our `INVALID_PASSWORD`.
- `freshAge: 0` turns off Better Auth's "session younger than a day" rule. Without it, anyone signed in for more than a day couldn't change their password (`SESSION_NOT_FRESH`). We already ask for the current password, which is a stronger check than session age. `freshAge` only affects Better Auth's sensitive endpoints, and `changePassword` is the only one we call.
- *Alternative considered:* hash and update the password ourselves through `(await auth.$context).password`/`internalAdapter`. It was rejected because Better Auth already does verify, hash, revoke and re-issue together, and doing it ourselves means using internal APIs.

### D6. Change email implemented by us, not with Better Auth's `changeEmail`

- The current password is checked with `(await getAuth().$context).password.verify({ hash, password })` against the user's credential `account.password`, read with Drizzle.
- Then `UPDATE user SET email = lower(newEmail), updated_at = now()`.
- A violation of the unique constraint on `email` (Postgres `23505`) becomes `EMAIL_TAKEN`. Checking the constraint rather than doing a lookup first avoids a race between the check and the write.
- *Why not Better Auth `changeEmail`:*
  - It returns success without doing anything when the email is taken, which clashes with our contract, where `register` already returns `409 EMAIL_TAKEN`, and would make the UI say "changed" when nothing changed.
  - It needs either a verification-email sender or `updateEmailWithoutVerification`, which only works while `emailVerified` is false.
  - It doesn't ask for a password.
- Order of checks: first the password (`403`), then same-email (a no-op `200`), then uniqueness (`409`). A caller with the wrong password therefore can't use this endpoint to find out whether an email exists.
- The session stays valid: Better Auth reads the user from the DB on `getSession`, and no cookie cache is configured.

### D7. Sign-out

- `signOut(token)` calls `getAuth().api.signOut({ headers: { authorization: "Bearer <token>" } })`, which deletes that one session row. The bearer plugin converts the header into the signed session cookie that `signOut` reads.
- If the spike (task 2.1) shows that doesn't delete the row, the fallback is `(await auth.$context).internalAdapter.deleteSession(token)`.
- The API responds `204`.
- The web action deletes the cookie and redirects to `/login` even if revoking fails because the session was already gone.

### D8. New contracts and error code

Added to `contracts.ts` and to the `contracts` array, so they show up in OpenAPI automatically:
- `ChangePasswordBody`: strict, `currentPassword` 1–128 characters, `newPassword` 8–128.
- `ChangeEmailBody`: strict, `newEmail` a valid email of at most 254 characters, `currentPassword` 1–128.
- `ChangePasswordResponse`: `{ token }`.
- The contracts `logout`, `changePassword` and `changeEmail`.
- `INVALID_PASSWORD` added to `ErrorCode`, with a shared `forbidden` response description.

`403` rather than `401` for a wrong current password: many clients, including the future mobile app, treat any `401` as "token dead, sign out". A typo in the current-password field shouldn't sign the user out.

### D9. Forms: React 19 `useActionState` and shadcn `Field`, no form library

- Each form is a small client component: `const [state, action, pending] = useActionState(serverAction, initial)`.
- `state` holds `{ fieldErrors, formError, values, success }`. `values` sends back the non-secret inputs, so a failed submit doesn't clear them. Password fields are never sent back.
- Success messages use `sonner` toasts. After a mutation, `revalidatePath("/", "layout")` refreshes the header name and email.
- Deleting the account uses a shadcn `AlertDialog` whose confirm button submits a form to the `deleteAccount` action.
- *Alternative considered:* shadcn `Form` with `react-hook-form` and `@hookform/resolvers`. It was rejected because it adds dependencies and duplicates validation on the client, and five small forms don't need it. Native `required`, `type="email"` and `minLength` attributes give quick feedback in the browser, and the server check is the one that counts.

### D10. shadcn components

Added with `npx shadcn@latest add login-03 signup-03 card input label field separator dropdown-menu avatar alert-dialog alert sonner`. The avatar shows the user's initials, since there are no images. After adding them, check that the generated code builds with React 19, Tailwind v4 and the `radix-rhea` style.

## Risks / Trade-offs

- **[Two ways to authenticate: cookie for web, bearer for API]** → Both go through `getSession` and the same service module, and the cookie is only read in `src/lib/session.ts`. `handler.ts` still ignores cookies, and a scenario in `web-auth-ui` confirms that.
- **[Stale cookie after a session is revoked elsewhere]** → Harmless. `requireSession()` redirects to `/login`, which does a real check and shows the form (no loop, see D2). The cookie is overwritten on the next sign-in.
- **[`freshAge: 0` weakens Better Auth's defaults]** → It only affects `changePassword`, which asks for the current password anyway. This is documented in `auth.ts`.
- **[No email verification on email change]** → Someone who has both the token and the password can move the account to another email. That's acceptable for this assignment and listed as a known limitation. Verification can be added once the app can send email.
- **[Login and change-password still have no brute-force protection]** → Same accepted risk as in `add-user-auth`.
- **[`x-pathname` header for `next`]** → If the header is missing (for example the proxy didn't run), `next` falls back to `/`. Only a UX loss.
- **[Adding shadcn blocks overwrites or adds files]** → Review the CLI's diff. The blocks' demo `page.tsx` files go under `src/app/login` and `src/app/signup`; move or delete them so they don't clash with the route groups.

## Migration Plan

- No database migration; the schema is unchanged.
- The API changes are additive.
- The home page at `/` becomes a signed-in page, so a signed-out visitor who opens `http://localhost:3000/` is now sent to `/login`. `/docs` stays public.
- Rollback: revert the commit.

## Open Questions

- None blocking. The details of `signOut` with a bearer header (D7) are confirmed by a spike during implementation, and a fallback is defined.
