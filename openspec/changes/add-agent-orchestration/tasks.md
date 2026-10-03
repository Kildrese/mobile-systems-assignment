# Tasks

## 1. Refactor without behavior change

- [ ] 1.1 Extract `AgentLoop` from `Runner._loop`, `_dispatch` and `_finish_call` into `backend/tracker/agents.py`, with `AgentProfile.from_policy` as the default profile (design D1). Verify the full existing `tests_tracker` suite passes unchanged
- [ ] 1.2 Replace `ARG_MODELS`/`TOOL_SCHEMAS` with the tool registry and a pluggable finish handler (design D4). Verify the core tool, CLI and config tests pass unchanged, and a new test registers a toy tool and calls it through the CLI

## 2. Profiles and budgets

- [ ] 2.1 Add `AgentProfile`, `Policy.agents`, `use_case`, model inheritance and all validators (design D2), and update `openspec/specs/tracker-config` behavior per the delta. Verify with unit tests: inherited model fields, a top-level `tools` key still rejected, an unregistered tool in a profile, a bad agent name, `fetch_hosts` outside the run allowlist, an over-allocated limit sum (message names the limit and total), a missing provider
- [ ] 2.2 Add the parent `Budget` with level-qualified reasons (design D3). Verify with unit tests: agent limit hit first, global limit hit first, both levels charged, wall time and cost only global
- [ ] 2.3 Load secrets for every provider used by an enabled profile. Verify a missing key for any profile's provider is reported before any network call

## 3. Privileges

- [ ] 3.1 Offer each agent only its profile's tools. Verify an agent without `search_web` gets `unknown_tool`, the call counts as a step, and no request is made
- [ ] 3.2 Add the per-agent `fetch_hosts` check ahead of the core guardrails (design D5). Verify with respx tests: an off-list host gives `host_not_allowed` with no request, and an on-list host still goes through the address checks

## 4. Conductor and trace

- [ ] 4.1 Add `Trace.bind` and the per-stage summary (design D7). Verify with unit tests: events carry `stage` and `agent`, redaction still applies, the summary lists stages
- [ ] 4.2 Implement `Stage`, `StageContext`, `StageOutcome`, chat clients per model, and `conductor.run` with the skip and outcome rules (design D6, D8). Verify with toy stages and a scripted fake model: all complete exits 0; an agent limit gives a partial stage and later stages still run; a terminal provider error skips later stages for that provider while code stages run and the exit is 2; a failed required code stage exits 3; a disabled stage is `skipped`; a later agent's first prompt contains nothing from an earlier agent
- [ ] 4.3 Route `python -m tracker run` to the conductor when `agents` and a known `use_case` are set, with unknown names rejected. Verify with subprocess tests for both policy shapes and an unknown `use_case`

## 5. Docs and CI

- [ ] 5.1 Add a "Multiple agents" section to `docs/tracker.md` (profiles, budget split, privileges, stages, outcomes, trace fields) with a toy two-agent example config. Verify the example config validates in a test
- [ ] 5.2 Run ruff and the full `tests_tracker` suite. Verify both pass locally and in CI
