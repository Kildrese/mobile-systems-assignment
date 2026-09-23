// Writes the OpenAPI document built from the Zod contracts to
// openapi/openapi.json. With --check, compares instead and fails on drift.
// Needs no server, database or env vars.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { buildOpenApiDocument } from "@/lib/api/openapi";

const outFile = resolve(__dirname, "..", "openapi", "openapi.json");
const expected = `${JSON.stringify(buildOpenApiDocument(), null, 2)}\n`;

if (process.argv.includes("--check")) {
  let actual: string | null = null;
  try {
    actual = readFileSync(outFile, "utf8");
  } catch {
    // Missing file counts as out of date.
  }
  if (actual !== expected) {
    console.error("openapi/openapi.json is out of date, run `npm run openapi:generate`.");
    process.exit(1);
  }
  console.log("openapi/openapi.json is up to date.");
} else {
  mkdirSync(dirname(outFile), { recursive: true });
  writeFileSync(outFile, expected);
  console.log("Wrote openapi/openapi.json.");
}
