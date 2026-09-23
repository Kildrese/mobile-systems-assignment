# db-migrations Specification

## Purpose

Drizzle schema definitions, generated migrations, and a command to apply them to the local database.

## Requirements

### Requirement: Schema is defined in TypeScript with Drizzle
The database schema SHALL be defined in a Drizzle schema file in the codebase, which is the single source of truth for table definitions and TypeScript types.

#### Scenario: Notes table defined
- **WHEN** a developer opens the schema file
- **THEN** it defines a `notes` table with `id` (serial primary key), `content` (text, not null), and `created_at` (timestamp, default now, not null)

### Requirement: SQL migrations are generated and committed
The project SHALL generate SQL migration files from the schema using drizzle-kit via an npm script, and the generated files SHALL be committed to the repository.

#### Scenario: Generate a migration
- **WHEN** a developer changes the schema and runs `npm run db:generate`
- **THEN** a new SQL migration file is created in the migrations folder reflecting the change

#### Scenario: Initial migration present
- **WHEN** a developer clones the repository
- **THEN** a migration creating the `notes` table already exists in the migrations folder

### Requirement: Migrations can be applied to the local database
The project SHALL provide an npm script that applies all pending migrations to the database specified by `DATABASE_URL`.

#### Scenario: Apply migrations to a fresh database
- **WHEN** the database is empty and a developer runs `npm run db:migrate`
- **THEN** the `notes` table exists afterwards

#### Scenario: Re-running is a no-op
- **WHEN** all migrations are already applied and `npm run db:migrate` runs again
- **THEN** it completes successfully without changing the schema

### Requirement: Database can be inspected with Drizzle Studio
The project SHALL provide an npm script to open Drizzle Studio against the local database.

#### Scenario: Open studio
- **WHEN** a developer runs `npm run db:studio` while the database is running
- **THEN** Drizzle Studio starts and shows the `notes` table
