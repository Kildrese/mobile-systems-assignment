## MODIFIED Requirements

### Requirement: Schema is defined in TypeScript with Drizzle
The database schema SHALL be defined in a Drizzle schema file in the codebase, which is the single source of truth for table definitions and TypeScript types.

#### Scenario: Auth tables defined
- **WHEN** a developer opens the schema file
- **THEN** it defines the `user`, `account`, `session` and `verification` tables with UUID primary keys, and does not define a `notes` table

### Requirement: SQL migrations are generated and committed
The project SHALL generate SQL migration files from the schema using drizzle-kit via an npm script, and the generated files SHALL be committed to the repository. Migrations that have already been committed SHALL NOT be edited or deleted.

#### Scenario: Generate a migration
- **WHEN** a developer changes the schema and runs `npm run db:generate`
- **THEN** a new SQL migration file is created in the migrations folder reflecting the change

#### Scenario: Migration history present
- **WHEN** a developer clones the repository
- **THEN** the migrations folder contains the original migration creating `notes`, followed by a migration that creates the auth tables and drops `notes`

### Requirement: Migrations can be applied to the local database
The project SHALL provide an npm script that applies all pending migrations to the database specified by `DATABASE_URL`.

#### Scenario: Apply migrations to a fresh database
- **WHEN** the database is empty and a developer runs `npm run db:migrate`
- **THEN** the `user`, `account`, `session` and `verification` tables exist afterwards and the `notes` table does not

#### Scenario: Upgrade an existing database
- **WHEN** a database that already has the `notes` migration applied runs `npm run db:migrate`
- **THEN** the auth tables are created and the `notes` table is dropped

#### Scenario: Re-running is a no-op
- **WHEN** all migrations are already applied and `npm run db:migrate` runs again
- **THEN** it completes successfully without changing the schema

### Requirement: Database can be inspected with Drizzle Studio
The project SHALL provide an npm script to open Drizzle Studio against the local database.

#### Scenario: Open studio
- **WHEN** a developer runs `npm run db:studio` while the database is running
- **THEN** Drizzle Studio starts and shows the `user`, `account`, `session` and `verification` tables
