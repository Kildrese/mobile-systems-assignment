## 1. Contracts and config

- [x] 1.1 Add `INVALID_PASSWORD` to `ErrorCode` and add `ChangePasswordBody`, `ChangeEmailBody` and `ChangePasswordResponse` (strict, with `.meta({ id })`) to `src/lib/api/contracts.ts`
- [x] 1.2 Add the `logout`, `changePassword` and `changeEmail` contracts (auth, body, and every status from the specs: `204`/`401`/`500`; `200`/`400`/`401`/`403`/`500`; `200`/`400`/`401`/`403`/`409`/`500`) and append them to the `contracts` array
- [x] 1.3 Set `session: { freshAge: 0 }` in `src/lib/auth.ts`, with a comment explaining why (D5)

## 2. Account service

- [x] 2.1 Spike: check that `getAuth().api.signOut` with an `authorization: Bearer` header deletes that session row, and that `changePassword` with `revokeOtherSessions: true` returns a new token and throws `APIError` code `INVALID_PASSWORD` for a wrong password. If not, switch to the fallback in D7 and update `design.md`
- [x] 2.2 Create `src/lib/services/account.ts` (`server-only`) with `registerUser`, `signIn`, `signOut`, `updateName`, `changeEmail`, `changePassword` and `deleteAccount`, each returning `{ ok: true, … } | { ok: false, code }`. Move the existing logic out of the register, login and users routes unchanged
- [x] 2.3 Implement `changeEmail` as described in D6: verify the password against the credential account via `$context.password.verify`, return a no-op for the same email, update the email lowercased, and map a Postgres `23505` error to `EMAIL_TAKEN`
- [x] 2.4 Make `signIn` and `changePassword` also return the session's `expiresAt`, which the cookie needs

## 3. API routes

- [x] 3.1 Refactor `src/app/api/auth/register`, `login` and `src/app/api/users/[id]` to call the service. Responses must not change
- [x] 3.2 Add `src/app/api/auth/logout/route.ts`, `change-password/route.ts` and `change-email/route.ts` using `handle(contract)` and the service
- [x] 3.3 Run `npm run openapi:generate` and commit the updated `openapi/openapi.json`
- [x] 3.4 Extend `scripts/api-smoke.sh` with the new `user-auth` scenarios: logout (`204`, then `401`; other session survives), change-password (new token, all old tokens `401`, wrong password `403`, short password `400`), change-email (lowercased, `403` before `409`, `409` for a taken email, token still works), and the new `api-docs` paths

## 4. Web session and route protection

- [x] 4.1 Create `src/lib/session.ts` (`server-only`) with `setSessionCookie(token, expiresAt)`, `clearSessionCookie()`, `getCurrentSession()` (React `cache`, cookie turned into a bearer `getSession`, `null` on failure) and `requireSession()` (redirects to `/login?next=` using `x-pathname`)
- [x] 4.2 Add `safeNext(value)`, which accepts only same-site relative paths (not `//`, `/\`, `/login` or `/register`) and falls back to `/`
- [x] 4.3 Create `src/proxy.ts`. It sets the `x-pathname` request header, redirects cookie-less requests for protected pages to `/login?next=…`, and uses a matcher that excludes `api`, `_next/*`, `favicon.ico`, `healthz`, `docs` and files with an extension

## 5. UI components

- [x] 5.1 Run `npx shadcn@latest add login-03 signup-03 card input label field separator dropdown-menu avatar alert-dialog alert sonner`, review the diff, and delete or move any demo `page.tsx` files it creates under `src/app/`
- [x] 5.2 Move the block forms to `src/components/auth/`. Remove the social buttons, the "Or continue with" separator, the forgot-password link and the terms footer, and replace the placeholder brand with the app name

## 6. Auth pages

- [x] 6.1 Create `src/app/(auth)/layout.tsx` with the `login-03` full-screen muted wrapper
- [x] 6.2 Add Server Actions `signInAction` and `registerAction` (in `src/app/(auth)/actions.ts`). They validate with `LoginBody` and `RegisterBody` (plus `confirmPassword` for register), call the service, set the cookie and redirect to `safeNext(next)`, and otherwise return field errors and form errors. The email is sent back; passwords never are
- [x] 6.3 Create `(auth)/login/page.tsx` and `(auth)/register/page.tsx`. Each does a real `getCurrentSession()` and redirects to `safeNext(next)` when signed in, and otherwise renders its form with `useActionState`, a pending state, and a link to the other page that keeps `next`

## 7. App pages

- [x] 7.1 Create `src/app/(app)/layout.tsx`: `requireSession()`, a header with the app name linking to `/`, a user menu (initials avatar, name, email, Account link, Sign out) and `<Toaster />`
- [x] 7.2 Add `signOutAction`. It revokes the session through the service (ignoring "already gone"), clears the cookie and redirects to `/login`
- [x] 7.3 Move the home page to `src/app/(app)/page.tsx` (greeting with the first name, links to `/account` and `/docs`), call `requireSession()`, and delete `src/app/page.tsx` and `page.module.css`
- [x] 7.4 Add account Server Actions (`src/app/(app)/account/actions.ts`): `updateNameAction`, `changeEmailAction`, `changePasswordAction` (which replaces the cookie with the new token) and `deleteAccountAction` (which clears the cookie and redirects to `/login`). Each calls `requireSession()`, validates with the contract schemas and calls `revalidatePath("/", "layout")`
- [x] 7.5 Create `src/app/(app)/account/page.tsx` with Profile, Email, Password and Danger-zone cards. Each is a client form using `useActionState`, with field errors ("Incorrect password", "Email already registered"), success toasts, cleared password fields after submit, and an `AlertDialog` to confirm deletion

## 8. Verification

- [x] 8.1 `npm run typecheck`, `npm run lint`, `npm run build` and `npm run openapi:check` all pass
- [x] 8.2 Run `scripts/api-smoke.sh` against the dev server and confirm it passes
- [x] 8.3 Go through every `web-auth-ui` scenario by hand in the browser: signed-out redirects with `next`, external `next` ignored, stale cookie with no loop, cookie attributes and that `document.cookie` doesn't show it, register, login errors, edit name, change email, change password (another session gets `401`), sign out, delete account, and `/docs` still public
- [x] 8.4 Update `README.md` with the web UI routes and the email-verification limitation
