# frontend/

Vite + React 19 + React Router, Tailwind v4, shadcn/ui, TanStack Query. Deployed as the `mobile-systems-assignment` Vercel project.

- `src/api/` is generated from `../openapi/openapi.json` (`npm run api:generate`). Never edit it. Call the backend through its TanStack Query helpers (`@/api/@tanstack/react-query.gen`), not `fetch`.
- `src/lib/api.ts` configures the client once (base URL, bearer token, what a 401 means). Don't configure it elsewhere.
- UI primitives come from `src/components/ui/` (shadcn). Add new ones with `npx shadcn@latest add <name>`, then adapt; don't hand-write a primitive shadcn ships.
- Feature components live in `src/components/<area>/`; routes, guards and layouts in `src/routes/`.
- Tests are Vitest, next to the code (`*.test.ts`). Pure logic in `src/lib/` gets a test; components don't need one.
- Done means `npm run api:check && npm run typecheck && npm test && npm run lint && npm run build` pass.
