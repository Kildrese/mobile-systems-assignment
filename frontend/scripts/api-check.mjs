// Fails when the committed client in src/api differs from what the current
// ../openapi/openapi.json generates. Regenerate with `npm run api:generate`.
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const out = mkdtempSync(path.join(tmpdir(), "api-check-"));
try {
  execFileSync("npx", ["openapi-ts"], {
    stdio: ["ignore", "ignore", "inherit"],
    env: { ...process.env, API_OUTPUT: out },
  });
  try {
    execFileSync("diff", ["-r", "src/api", out], { stdio: "inherit" });
  } catch {
    console.error(
      "\nsrc/api is out of date with ../openapi/openapi.json. Run `npm run api:generate` and commit the result.",
    );
    process.exit(1);
  }
  console.log("src/api is up to date.");
} finally {
  rmSync(out, { recursive: true, force: true });
}
