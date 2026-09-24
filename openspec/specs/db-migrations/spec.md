# db-migrations Specification

## Purpose

SQLAlchemy model definitions, Alembic migrations, and the commands to generate and apply them.
## Requirements
### Requirement: Schema is defined with SQLAlchemy models
The database schema SHALL be defined as SQLAlchemy 2 declarative models in `backend/app/models.py`, which are the single source of truth for table definitions and the ORM types.

#### Scenario: Tables defined
- **WHEN** a developer opens the models module
- **THEN** it defines the `users`, `user_passwords` and `sessions` tables with UUID primary keys (or `user_id` for `user_passwords`)

### Requirement: Alembic migrations are generated and committed
The project SHALL manage schema changes with Alembic in `backend/alembic/`, and migration files SHALL be committed. `uv run alembic revision --autogenerate -m "<message>"` SHALL create a new migration from model changes. Migrations that have already been committed and applied to production SHALL NOT be edited or deleted. The first migration SHALL drop the previous Better Auth and Drizzle tables (`user`, `account`, `session`, `verification`, `notes`, and the `drizzle` schema) if they exist, then create the new tables.

#### Scenario: Generate a migration
- **WHEN** a developer changes a model and runs the autogenerate command in `backend/`
- **THEN** a new migration file reflecting the change is created in `backend/alembic/versions/`

#### Scenario: Old tables are dropped
- **WHEN** the migrations run against a database that has the old Better Auth tables
- **THEN** afterwards only `users`, `user_passwords`, `sessions` and `alembic_version` exist in the `public` schema

### Requirement: Migrations can be applied
`uv run alembic upgrade head` in `backend/` SHALL apply all pending migrations to the database in `DATABASE_URL`, and SHALL be a no-op when everything is applied.

#### Scenario: Apply migrations to a fresh database
- **WHEN** the database is empty and a developer runs the upgrade command
- **THEN** the `users`, `user_passwords` and `sessions` tables exist afterwards

#### Scenario: Re-running is a no-op
- **WHEN** all migrations are applied and the upgrade command runs again
- **THEN** it completes successfully without changing the schema

