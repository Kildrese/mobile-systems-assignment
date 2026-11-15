# Design

Ported from `../trademark` (commits `7b07fd7` and `58bd0b7`). The grilling answers behind these choices are D1–D7 in `decisions.md`.

## The loop

1. **Grilling** (AskUserQuestion, up to 4 questions a round). Read the specs and code the feature touches first, so you only ask what the repo can't answer.
2. **Worktree:** `git worktree add .claude/worktrees/<name> -b feat/<name> origin/master`, then `openspec new change <name>` there. The answers go into `decisions.md`.
3. **spec-writer** writes the artifacts. Then **reviewer** checks the proposal against the specs.
4. **implementer**s, one per task group. A blocked group stops alone. The orchestrator decides `expensive` entries and starts a fresh implementer. `mine` entries wait for the second grilling.
5. **checker** (exists) runs CI's commands for what changed.
6. **reviewer** and, when the diff touches auth, prompts, fetching, secrets or paid calls, **security-reviewer** (exists).
7. **Second grilling** on the open `mine` entries. It shows the options with their tradeoffs but not which one was built. After the user picks, it says what was built and the rework cost if they picked something else.
8. Fresh implementers apply the answers, then checker and reviewer again.
9. **Draft PR**, then the user runs `/ship <n>`.

Small fixes skip steps 1–3 but still get `openspec/changes/fix-<topic>/decisions.md`.

## What changes from trademark

| trademark | here | why |
| --- | --- | --- |
| `db-agent` + `db_apply.py` + `no-db-apply.sh` + `db-destructive.sh` | dropped | One shared Postgres with no backup there. Here the local database is disposable, CI runs `alembic upgrade head` + `alembic check`, and Neon production migrations are ordered against the deploy by `/ship`. `settings.json` already makes `db-migrate-neon.sh` and the Neon SQL tools ask (D3). |
| `scripts/check.sh` | `checker` agent | It already exists and reads CI's commands. |
| `DESIGN.md` writable by the orchestrator | not here | There is no DESIGN.md. Decisions that last go into specs or `docs/` through the spec-writer. |
| `mine` = "could change an eval number" | the list in `CLAUDE.md#Decisions` | This repo has no eval. What it has instead: ranking, prompts, paid-call exposure, the public repo and production (D2). |
| Sonnet only off the ranker, search and eval | Sonnet only off `backend/tracker`, auth, migrations and paid-call paths | Same rule, this repo's risky areas. |
| Stop hook runs the fast checks | unchanged | The existing Stop hook already runs ruff/tsc; tests stay with `checker` (D5). |

The agent prompts keep trademark's wording otherwise, including "a blocked tool means stop" (trademark D3), reports of at most 15 lines, and fresh subagents instead of resumed ones.

## Hook

`orchestrator-writes.sh` is trademark's version after `58bd0b7` (the `agent_id` pass, fails closed), with only the `decisions.md` pattern allowed. ponytail: Bash redirects and `sed -i` get past it; the prompt forbids them, and the reviewer reads the diff. The self-check is a shell script like `test-guard-private.sh`, not trademark's Python, so it needs no venv.

## Risks

- **Frontmatter hooks may also apply to subagents.** That's why subagents pass on `agent_id`. A subagent payload without `agent_id` would be blocked. That fails safe, and the implementer reports the block.
- **Two flows at once** share the local Postgres. trademark allows two flows and one db-agent. Here, tests use their own `_test` database, so two flows are safe as long as they don't both add migrations: two Alembic heads. The orchestrator checks this before running a pair.
