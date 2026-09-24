# web-app Specification

## Purpose

Next.js + TypeScript application run locally with npm, able to query the database.
## Requirements
### Requirement: Next.js TypeScript application runs locally with npm
The project SHALL contain a Next.js application written in TypeScript (App Router) that runs on the host machine via npm, without a container.

#### Scenario: Start dev server
- **WHEN** a developer runs `npm run dev` with dependencies installed
- **THEN** the app is served at `http://localhost:3000`

#### Scenario: Type check passes
- **WHEN** a developer runs `npx tsc --noEmit`
- **THEN** it completes without type errors

### Requirement: Application connects to the database via DATABASE_URL
The application SHALL create its database connection from the `DATABASE_URL` environment variable using Drizzle ORM, and SHALL reuse a single client across hot reloads in development.

#### Scenario: Missing DATABASE_URL
- **WHEN** the app attempts to access the database and `DATABASE_URL` is not set
- **THEN** it fails with an error message stating that `DATABASE_URL` is missing
