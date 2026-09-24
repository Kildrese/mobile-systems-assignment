# web-auth-ui Specification

## Purpose
The browser UI for accounts: a cookie-based web session, login and registration pages, route protection with a safe post-login redirect, the signed-in home page and header, and an account page to edit the profile, change email or password, and delete the account. It reuses the API's validation and account rules.

## Requirements
### Requirement: Web session cookie
The web UI SHALL keep the signed-in session in a cookie named `session` holding the session token. The cookie SHALL be `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` when `NODE_ENV` is `production`, and SHALL expire when the session expires. The token SHALL NOT be exposed to client-side JavaScript or rendered into the page. The cookie SHALL be set only by server code (Server Actions) after a successful sign-in, registration or password change, and cleared on sign-out and account deletion. The JSON API SHALL continue to ignore this cookie (see `user-auth`).

#### Scenario: Cookie attributes after sign-in
- **WHEN** a user signs in through `/login`
- **THEN** the response sets a `session` cookie with `HttpOnly`, `SameSite=Lax` and `Path=/`, and `document.cookie` in the browser does not contain it

#### Scenario: API ignores the web cookie
- **WHEN** a browser signed in to the web UI calls `GET /api/auth/me` without an `Authorization` header
- **THEN** the response is `401`

### Requirement: Signed-out visitors are sent to the login page
Every page except `/login`, `/register` and `/docs` SHALL require a signed-in session. API routes, `/healthz`, `/api/openapi.json` and static assets SHALL NOT be affected. A request for a protected page without a `session` cookie SHALL be redirected by the proxy to `/login?next=<original path and query>` before the page renders. A protected page SHALL also verify the session on the server, and SHALL redirect to `/login?next=<path>` when the cookie is present but its session is unknown, expired or revoked, or its user was deleted. No protected content SHALL be rendered for a signed-out visitor.

#### Scenario: No cookie
- **WHEN** a signed-out visitor opens `/account`
- **THEN** they are redirected to `/login?next=%2Faccount` and no account data is sent

#### Scenario: Stale cookie
- **WHEN** a browser has a `session` cookie whose session was revoked (e.g. by logging out through the API) and opens `/`
- **THEN** it is redirected to `/login?next=%2F`

#### Scenario: Public routes stay public
- **WHEN** a signed-out visitor requests `/docs`, `/healthz` or `/api/openapi.json`
- **THEN** each responds normally without a redirect

#### Scenario: API routes are not redirected
- **WHEN** a client without a token calls `GET /api/auth/me`
- **THEN** the response is the API's `401` JSON, not a redirect

### Requirement: Safe post-login redirect
After a successful sign-in or registration the user SHALL be sent to the `next` query parameter when it is a same-site relative path (starts with a single `/`, not `//` or `/\`, and is not `/login` or `/register`), and to `/` otherwise.

#### Scenario: Return to the requested page
- **WHEN** a user is redirected from `/account` to `/login?next=%2Faccount` and signs in
- **THEN** they land on `/account`

#### Scenario: External next is ignored
- **WHEN** a user signs in from `/login?next=https%3A%2F%2Fevil.example` or `/login?next=%2F%2Fevil.example`
- **THEN** they land on `/`

### Requirement: Signed-in users skip the auth pages
When a user with a valid session opens `/login` or `/register`, the page SHALL redirect to the safe `next` target (or `/`) instead of showing the form. A stale cookie SHALL NOT cause a redirect loop: with an invalid session, the forms are shown.

#### Scenario: Already signed in
- **WHEN** a signed-in user opens `/login`
- **THEN** they are redirected to `/`

#### Scenario: Stale cookie on the login page
- **WHEN** a browser with a revoked session cookie opens `/login`
- **THEN** the login form is shown

### Requirement: Login page
`/login` SHALL be a full-page layout based on the shadcn `login-03` block: a muted full-screen background with the app name and a centred card holding an "Email or username" field and a password field, a submit button, and a link to `/register` that keeps the `next` parameter. It SHALL NOT show social-login buttons or a "forgot password" link, since neither exists. Wrong credentials SHALL show one generic "Invalid email, username or password" message without revealing whether the account exists, and SHALL keep the entered email or username. The submit button SHALL be disabled while the request is pending.

#### Scenario: Successful sign-in
- **WHEN** a registered user enters correct credentials on `/login`
- **THEN** the session cookie is set and they are redirected (see "Safe post-login redirect")

#### Scenario: Wrong credentials
- **WHEN** a user enters an unknown email or username, or a wrong password
- **THEN** the page shows "Invalid email, username or password", keeps the email-or-username field filled, and sets no cookie

#### Scenario: Invalid input
- **WHEN** a user submits an empty password or an empty email-or-username field
- **THEN** the field shows a validation message and no sign-in is attempted

### Requirement: Registration page
`/register` SHALL use the matching shadcn `signup-03` layout with first name, last name (optional), username, email, password and confirm-password fields and a link to `/login` that keeps the `next` parameter. It SHALL apply the same validation as `POST /api/auth/register` and SHALL also require the two passwords to match. On success the user SHALL be signed in immediately (session cookie set) and redirected as in "Safe post-login redirect". A taken email SHALL show an error on the email field, and a taken username an error on the username field.

#### Scenario: Successful registration
- **WHEN** a visitor fills in valid details on `/register`
- **THEN** the account is created, the session cookie is set, and they land on `/`

#### Scenario: Passwords don't match
- **WHEN** the password and confirm-password fields differ
- **THEN** the form shows an error and no account is created

#### Scenario: Email taken
- **WHEN** a visitor registers with an email that already exists (any letter case)
- **THEN** the email field shows that the email is already registered and no cookie is set

#### Scenario: Username taken
- **WHEN** a visitor registers with a new email but a username that already exists (any letter case)
- **THEN** the username field shows that the username is already taken and no cookie is set

#### Scenario: Sign in with the username afterwards
- **WHEN** a user registered with username `ada_l` signs out and enters `ada_l` and the password on `/login`
- **THEN** they are signed in

### Requirement: Signed-in home page
`/` SHALL be a signed-in page that greets the user by first name and links to `/account` and to the API reference at `/docs`.

#### Scenario: Home greets the user
- **WHEN** a signed-in user named Ada opens `/`
- **THEN** the page shows a greeting containing "Ada" and links to `/account` and `/docs`

### Requirement: App header and sign-out
Every signed-in page SHALL show a header with the app name (linking to `/`) and a user menu showing the user's name, `@username` and email, a link to `/account`, and a "Sign out" item. Signing out SHALL revoke the session on the server, clear the cookie, and redirect to `/login`.

#### Scenario: Sign out
- **WHEN** a signed-in user chooses "Sign out"
- **THEN** they land on `/login`, the old session token returns `401` on `GET /api/auth/me`, and opening `/account` afterwards redirects to `/login`

### Requirement: Edit profile
`/account` SHALL have a Profile card with username, first-name and last-name fields prefilled with the current values. Saving SHALL apply the same rules as `PATCH /api/users/:id`, show a success confirmation, and update the name and username shown in the header. A taken username SHALL show an error on the username field.

#### Scenario: Update name
- **WHEN** a user changes the first name to "Grace" and saves
- **THEN** a success message is shown and the header's user menu shows "Grace"

#### Scenario: Update username
- **WHEN** a user changes the username to "Grace_H" and saves
- **THEN** a success message is shown, the field shows `grace_h`, and the user can sign in with `grace_h`

#### Scenario: Username taken
- **WHEN** a user enters another user's username and saves
- **THEN** the username field shows that the username is already taken and nothing is changed

#### Scenario: Empty name
- **WHEN** a user clears the last-name field and saves
- **THEN** the field shows a validation error and nothing is changed

### Requirement: Change email in the UI
`/account` SHALL have an Email card showing the current email, with fields for the new email and the current password. It SHALL apply the same rules as `POST /api/auth/change-email`. A wrong password SHALL show an error on the password field, and a taken email SHALL show an error on the email field. On success the new email SHALL be shown, the password field SHALL be cleared, and the user SHALL stay signed in.

#### Scenario: Change email
- **WHEN** a user enters an unused email and the correct password
- **THEN** a success message is shown, the card shows the new email, and the user is still signed in

#### Scenario: Wrong password
- **WHEN** a user enters the wrong current password
- **THEN** the password field shows "Incorrect password" and the email is unchanged

### Requirement: Change password in the UI
`/account` SHALL have a Password card with current-password, new-password and confirm-new-password fields, and SHALL state that other devices will be signed out. It SHALL apply the same rules as `POST /api/auth/change-password`, and SHALL require the two new passwords to match. On success the browser SHALL stay signed in, with its cookie replaced by the new session token, and all fields SHALL be cleared.

#### Scenario: Change password
- **WHEN** a user enters the correct current password and matching valid new passwords
- **THEN** a success message is shown, the user is still signed in on this browser, and tokens from other sessions return `401`

#### Scenario: Wrong current password
- **WHEN** a user enters the wrong current password
- **THEN** the current-password field shows "Incorrect password" and nothing changes

### Requirement: Delete account in the UI
`/account` SHALL have a Danger zone card with a "Delete account" button that opens a confirmation dialog explaining that deletion is permanent. Confirming SHALL delete the account through the same rules as `DELETE /api/users/:id`, clear the cookie and redirect to `/login`. Cancelling SHALL change nothing.

#### Scenario: Confirm deletion
- **WHEN** a user confirms account deletion
- **THEN** they land on `/login`, and signing in with the old credentials fails with "Invalid email, username or password"

#### Scenario: Cancel deletion
- **WHEN** a user opens the dialog and cancels
- **THEN** the dialog closes and the account still exists
