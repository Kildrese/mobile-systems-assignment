import { defineConfig } from "@hey-api/openapi-ts";

// Generates the typed API client from the backend's committed OpenAPI
// document. `npm run api:check` regenerates into a temp dir and diffs.
export default defineConfig({
  input: "../openapi/openapi.json",
  output: { path: process.env.API_OUTPUT ?? "src/api" },
  plugins: ["@hey-api/client-fetch", "@hey-api/typescript", "@hey-api/sdk", "@tanstack/react-query"],
});
