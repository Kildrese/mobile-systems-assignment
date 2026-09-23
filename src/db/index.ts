import { drizzle, type PostgresJsDatabase } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

type Database = PostgresJsDatabase<typeof schema>;

// Reuse one client across hot reloads in development so we don't open a new
// connection pool every time a module is re-evaluated.
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
  const db = globalForDb.db ?? createDb();
  if (process.env.NODE_ENV !== "production") globalForDb.db = db;
  return db;
}
