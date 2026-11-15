## Why

Assignment 2 ("Agentic Orchestration") asks for an `ORCHESTRATION.md` that explains how two agents talk over a network. The verifier from `add-claim-verifier` is that second agent, and all of that change's tasks are checked. Its delta specs still sit in the change folder, so `openspec/specs/` does not yet describe the verifier. The brief asks for Render. We run on Vercel and Neon, and the document has to say why and what that costs.

## What Changes

> Rebuilt on master after #38 on 2026-11-15: #38 already archived `add-claim-verifier` and the other shipped changes, so this change no longer archives anything (see D16). What remains is `ORCHESTRATION.md`.

- **Archive `add-claim-verifier` by hand** (decisions D1, D5). The OpenSpec CLI is not installed, so its six delta specs are merged into `openspec/specs/` the way the openspec-archive-change skill does it. `claim-verification` becomes a new spec. The change folder moves to `openspec/changes/archive/2026-11-15-add-claim-verifier/`.
- **No other change is archived** (D4 is open; the build does B). The five changes with unchecked production tasks stay where they are.
- **Write `ORCHESTRATION.md` at the repo root, hosting parts only** (D2, D3):
  - "Why Vercel and Neon instead of Render", honest about cold starts.
  - Q2 "The network": cold start and timeouts only, with numbers checked against the code.
  - Q3 "Duplicates": both cases, quoting `services/verifier`, plus what a restarted instance changes.
  - Q1 contract, Q4 injection and Q5 "was it worth it" as headings with "TODO".
- Numbers nobody has measured are marked placeholders, each with the `curl` command that measures it.

## Capabilities

### New Capabilities
None. This change adds no requirements. The archive step creates `openspec/specs/claim-verification/spec.md` from the already reviewed `add-claim-verifier` change.

### Modified Capabilities
None of its own. The archive step applies `add-claim-verifier`'s deltas to `internship-pipeline`, `internship-report-view`, `opportunity-report`, `report-publishing` and `trace-log`.

## Impact

- **Files:** `ORCHESTRATION.md` (new), `openspec/specs/` (one new spec, five updated), `openspec/changes/add-claim-verifier/` moved to the archive.
- **No code, tests, migrations, dependencies or deploys.** No paid API call is added.
- **Out of scope:** the rest of `ORCHESTRATION.md` (Q1, Q4, Q5), real latency numbers (no run with the verifier exists yet), and archiving the five changes in D4.
