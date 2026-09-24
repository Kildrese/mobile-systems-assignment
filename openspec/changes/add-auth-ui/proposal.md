## Why

The app has a complete auth API but no user interface: the only page is a placeholder that links to `/docs`. People need to sign up, sign in, sign out and manage their account (name, email, password, deletion) from the browser, and anyone who isn't signed in should land on a login page instead of seeing app pages. The API also lacks sign-out, change-password and change-email, so a mobile client can't do those things either.

## What Changes

- **Browser session via an httpOnly cookie.** Login and register forms run as Server Actions that call the same service code as the API and store the session token in an httpOnly, `SameSite=Lax` cookie (`Secure` in production). The JSON API is unchanged in this respect: it stays bearer-only and keeps ignoring cookies.
- **Redirecting signed-out visitors**, in two layers:
  - `src/proxy.ts` (Next 16's replacement for `middleware.ts`) does an optimistic check. If an app page is requested without a session cookie, it redirects to `/login?next=<path>`.
  - The layout for app pages verifies the session for real and redirects to `/login` if it is missing, expired or revoked.
  - The login and register pages send an already signed-in user to `/`.
  - `next` is only followed when it is a same-site relative path.
- **Pages** (shadcn/ui):
  - `/login`: full-page login based on the shadcn `login-03` block (muted background, centred card).
  - `/register`: the matching `signup-03` block. After registering, the user is signed in straight away.
  - `/`: the signed-in home page, which replaces the static placeholder.
  - `/account`, with four cards:
    - **Profile**: first and last name.
    - **Email**: new email plus current password.
    - **Password**: current password plus new password twice.
    - **Danger zone**: delete the account after a confirm dialog.
  - A header with a user menu (name, email, Account, Sign out) on every signed-in page.
- **New JSON API endpoints**, with Zod contracts and in the OpenAPI document:

  | Method | Path                        | Auth | Purpose                                                          |
  |--------|-----------------------------|------|------------------------------------------------------------------|
  | POST   | `/api/auth/logout`          | yes  | revoke the current token (`204`)                                 |
  | POST   | `/api/auth/change-password` | yes  | needs the current password; revokes every session, returns a new token |
  | POST   | `/api/auth/change-email`    | yes  | needs the current password; changes the email immediately        |

- **New error code `INVALID_PASSWORD`** (`403`), returned when the current password is wrong on change-password or change-email. It is deliberately not `401`, so clients don't mistake it for an invalid token and sign the user out.
- **Shared account services.** Register, login, logout, update name, change email, change password and delete account move into one server-only module. Route handlers and Server Actions both call it, so the web and API rules can't drift apart. The existing routes are refactored to use it, with no change in behaviour.
- Email changes are **not** verified by email: no mail is sent anywhere in the app yet. This is noted as a known limitation.

## Capabilities

### New Capabilities
- `web-auth-ui`: the browser UI and web session. This covers the cookie session, redirecting signed-out visitors (proxy plus server-side check, safe `next` handling), the `/login`, `/register`, `/` and `/account` pages, sign-out, and the user menu.

### Modified Capabilities
- `user-auth`: adds the logout, change-password and change-email requirements and the `INVALID_PASSWORD` error code.
- `api-docs`: the "All endpoints documented" scenario and the list of protected endpoints now include the three new endpoints.
- `web-app`: the "Placeholder home page" requirement (static, no database) is replaced. `/` is now a signed-in page, and `/docs` stays public.

## Impact

- **Code:**
  - new `src/proxy.ts`
  - new `src/lib/session.ts` (cookie helpers, `getCurrentSession()`, `requireSession()`)
  - new `src/lib/services/account.ts`
  - Server Actions for the auth and account forms
  - route groups `src/app/(auth)/` and `src/app/(app)/`
  - three new route handlers
  - new contracts in `src/lib/api/contracts.ts`
  - the existing auth and user routes refactored to use the services
  - `src/app/page.tsx` and `page.module.css` removed in favour of `(app)/page.tsx`
- **Better Auth config:** `session.freshAge: 0`, because Better Auth's own freshness check would block changing the password once a session is a day old. We ask for the current password instead.
- **UI dependencies:** shadcn blocks `login-03` and `signup-03`, plus the `card`, `input`, `label`, `field`, `dropdown-menu`, `avatar`, `alert-dialog`, `alert` and `sonner` components, added through the shadcn CLI. This brings in their Radix and `sonner` dependencies. There's no form library; forms use React 19 `useActionState`.
- **API clients:**
  - Additive only; existing endpoints and responses don't change.
  - After changing the password, the old token stops working, and clients must store the token returned in the response.
- **OpenAPI:** `openapi/openapi.json` is regenerated.
- **Smoke test:** `scripts/api-smoke.sh` gains checks for the new endpoints.
