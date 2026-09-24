# web-auth-ui Specification

## Purpose
The browser UI for accounts: a cookie-based web session, login and registration pages, route protection with a safe post-login redirect, the signed-in home page and header, and an account page to edit the profile, change email or password, and delete the account. It reuses the API's validation and account rules.
## Requirements
### Requirement: Signed-out visitors are sent to the login page
Every page of the frontend except `/login` and `/register` SHALL require a signed-in user.
- **No stored token:** opening a protected page SHALL show `/login?next=<original path and query>` without calling the API.
- **Stored token:** the page SHALL first load the current user with `GET /api/auth/me`. It SHALL show a loading state until that succeeds, and SHALL go to `/login?next=<path>` if it answers `401`.

No protected content SHALL be rendered for a signed-out visitor. All authorization SHALL be enforced by the backend; the client-side check only decides what to show.

#### Scenario: No token
- **WHEN** a visitor without a stored token opens `/account`
- **THEN** they see `/login?next=%2Faccount` and no request to a protected endpoint is made

#### Scenario: Stale token
- **WHEN** a browser has a stored token whose session was revoked (e.g. by logging out through the API) and opens `/`
- **THEN** `GET /api/auth/me` returns `401`, the token is removed, and the browser shows `/login?next=%2F`

### Requirement: Safe post-login redirect
After a successful sign-in or registration the user SHALL be sent to the `next` query parameter when it is a same-site relative path (starts with a single `/`, not `//` or `/\`, and is not `/login` or `/register`), and to `/` otherwise.

#### Scenario: Return to the requested page
- **WHEN** a user is redirected from `/account` to `/login?next=%2Faccount` and signs in
- **THEN** they land on `/account`

#### Scenario: External next is ignored
- **WHEN** a user signs in from `/login?next=https%3A%2F%2Fevil.example` or `/login?next=%2F%2Fevil.example`
- **THEN** they land on `/`

### Requirement: Signed-in users skip the auth pages
When a user whose stored token is accepted by `GET /api/auth/me` opens `/login` or `/register`, the app SHALL navigate to the safe `next` target (or `/`) instead of showing the form. A stale token SHALL NOT cause a redirect loop: when the token is rejected, it is removed and the form is shown.

#### Scenario: Already signed in
- **WHEN** a signed-in user opens `/login`
- **THEN** they are taken to `/`

#### Scenario: Stale token on the login page
- **WHEN** a browser with a revoked stored token opens `/login`
- **THEN** the login form is shown and the token is removed

### Requirement: Login page
`/login` SHALL be a full-page layout based on the shadcn `login-03` block: a muted full-screen background with the app name and a centred card holding an "Email or username" field and a password field, a submit button, and a link to `/register` that keeps the `next` parameter. It SHALL NOT show social-login buttons or a "forgot password" link, since neither exists. Signing in SHALL call `POST /api/auth/login` and store the returned token (see `frontend-app`). Wrong credentials SHALL show one generic "Invalid email, username or password" message without revealing whether the account exists, and SHALL keep the entered email or username. The submit button SHALL be disabled while the request is pending.

#### Scenario: Successful sign-in
- **WHEN** a registered user enters correct credentials on `/login`
- **THEN** the token is stored and they are sent on (see "Safe post-login redirect")

#### Scenario: Wrong credentials
- **WHEN** a user enters an unknown email or username, or a wrong password
- **THEN** the page shows "Invalid email, username or password", keeps the email-or-username field filled, and stores no token

#### Scenario: Invalid input
- **WHEN** a user submits an empty password or an empty email-or-username field
- **THEN** the field shows a validation message and no sign-in request is sent

### Requirement: Registration page
`/register` SHALL use the matching shadcn `signup-03` layout with first name, last name (optional), username, email, password and confirm-password fields, and a link to `/login` that keeps the `next` parameter. It SHALL require the two passwords to match before sending anything. It SHALL show the API's validation errors on the matching fields.

On success (`POST /api/auth/register`) the app SHALL sign the user in immediately with `POST /api/auth/login`, store the token, and send them on as in "Safe post-login redirect". A taken email SHALL show an error on the email field, and a taken username an error on the username field.

#### Scenario: Successful registration
- **WHEN** a visitor fills in valid details on `/register`
- **THEN** the account is created, a token is stored, and they land on `/`

#### Scenario: Passwords don't match
- **WHEN** the password and confirm-password fields differ
- **THEN** the form shows an error and no request is sent

#### Scenario: Email taken
- **WHEN** a visitor registers with an email that already exists (any letter case)
- **THEN** the email field shows that the email is already registered and no token is stored

#### Scenario: Username taken
- **WHEN** a visitor registers with a new email but a username that already exists (any letter case)
- **THEN** the username field shows that the username is already taken and no token is stored

#### Scenario: Sign in with the username afterwards
- **WHEN** a user registered with username `ada_l` signs out and enters `ada_l` and the password on `/login`
- **THEN** they are signed in

### Requirement: Signed-in home page
`/` SHALL be a signed-in page that greets the user by first name and shows their `@username` and, if they have one, their email. It SHALL link to `/account` and to the backend's API reference at `<VITE_API_URL>/docs`.

#### Scenario: Home greets the user
- **WHEN** a signed-in user named Ada opens `/`
- **THEN** the page shows a greeting containing "Ada", their `@username`, and links to `/account` and the API reference

### Requirement: App header and sign-out
Every signed-in page SHALL show a header with the app name (linking to `/`) and a user menu showing:
- the user's name, `@username` and email (if any)
- a link to `/account`
- a "Sign out" item

Signing out SHALL call `POST /api/auth/logout` with the token, remove the token even if that call fails, and navigate to `/login`.

#### Scenario: Sign out
- **WHEN** a signed-in user chooses "Sign out"
- **THEN** they land on `/login`, the token is gone from `localStorage`, the old token returns `401` on `GET /api/auth/me`, and opening `/account` afterwards shows the login page

### Requirement: Edit profile
`/account` SHALL have a Profile card with username, first-name and last-name fields prefilled with the current values. Saving SHALL call `PATCH /api/users/:id` for the signed-in user, show a success confirmation, and update the name and username shown in the header. A taken username SHALL show an error on the username field.

#### Scenario: Update name
- **WHEN** a user changes the first name to "Grace" and saves
- **THEN** a success message is shown and the header's user menu shows "Grace"

#### Scenario: Update username
- **WHEN** a user changes the username to "Grace_H" and saves
- **THEN** a success message is shown, the field shows `grace_h`, and the user can sign in with `grace_h`

#### Scenario: Username taken
- **WHEN** a user enters another user's username and saves
- **THEN** the username field shows that the username is already taken and nothing is changed

#### Scenario: Empty first name
- **WHEN** a user clears the first-name field and saves
- **THEN** the field shows a validation error and nothing is changed

### Requirement: Change email in the UI
`/account` SHALL have an Email card showing the current email (or saying that no email has been added), with fields for the new email and the current password. Submitting SHALL call `POST /api/auth/change-email`. A wrong password SHALL show an error on the password field, and a taken email SHALL show an error on the email field. On success the new email SHALL be shown, the password field SHALL be cleared, and the user SHALL stay signed in.

#### Scenario: Change email
- **WHEN** a user enters an unused email and the correct password
- **THEN** a success message is shown, the card shows the new email, and the user is still signed in

#### Scenario: Wrong password
- **WHEN** a user enters the wrong current password
- **THEN** the password field shows "Incorrect password" and the email is unchanged

### Requirement: Change password in the UI
`/account` SHALL have a Password card with current-password, new-password and confirm-new-password fields, and SHALL state that other devices will be signed out. Submitting SHALL call `POST /api/auth/change-password` and require the two new passwords to match. On success the browser SHALL stay signed in, with the stored token replaced by the returned one, and all fields SHALL be cleared.

#### Scenario: Change password
- **WHEN** a user enters the correct current password and matching valid new passwords
- **THEN** a success message is shown, the user is still signed in on this browser with a new stored token, and tokens from other sessions return `401`

#### Scenario: Wrong current password
- **WHEN** a user enters the wrong current password
- **THEN** the current-password field shows "Incorrect password" and nothing changes

### Requirement: Delete account in the UI
`/account` SHALL have a Danger zone card with a "Delete account" button that opens a confirmation dialog explaining that deletion is permanent. Confirming SHALL call `DELETE /api/users/:id` for the signed-in user, remove the token, and navigate to `/login`. Cancelling SHALL change nothing.

#### Scenario: Confirm deletion
- **WHEN** a user confirms account deletion
- **THEN** they land on `/login`, and signing in with the old credentials fails with "Invalid email, username or password"

#### Scenario: Cancel deletion
- **WHEN** a user opens the dialog and cancels
- **THEN** the dialog closes and the account still exists

