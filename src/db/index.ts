import { drizzle, type PostgresJsDatabase } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

type Database = PostgresJsDatabase<typeof schema>;

// One client per process, kept on globalThis so it also survives hot reloads
// in development. Without the cache every call would open a new connection
// pool and quickly exhaust Postgres's connection limit.
const globalForDb = globalThis as unknown as { db?: Database };

function createDb(): Database {
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error(
      "DATABASE_URL is missing. Copy .env.example to .env and set DATABASE_URL.",
    );
  }
  return drizzle(postgres(url), { schema });
}

export function getDb(): Database {
  globalForDb.db ??= createDb();
  return globalForDb.db;
}
