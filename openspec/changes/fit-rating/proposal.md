# Proposal

## Why

The ranking can't tell a strong internship from a weak one. Almost every Summer 2027 software internship in NYC scores full marks on role, term, focus and location, so recency decides the order. In practice the top K is "matches the search, seen most recently", not "best for me". Judging fit with a person's interests needs a model, but the reasons for ranking in code still hold (`AGENT.md`): the run comparison needs a stable rank, postings are untrusted text, and every score should be explainable.

## What Changes

- **A profile in config.** `options.profile` is a short, plain-language description of what the user wants: skills, interests, the kind of team and company. It is trusted config, like the topic.
- **A new agent stage, Assess**, between Liveness and Rank. An `assessor` agent rates each open opportunity's fit with the profile on a 0–3 scale, with a one-sentence reason. It reads the record and the start of the posting as untrusted data. Code checks each rating before storing it.
- **Ratings are stored once and reused.** A rating is kept with the opportunity and is never asked for again while the profile stays the same, so the same opportunity has the same fit every day. When the profile changes, ratings are redone over the following runs, the most relevant first.
- **Fit becomes a sixth ranking criterion**, weighted 6 by default, double the next largest weight. Code still computes the score. An opportunity that is not rated yet scores 0.5 of the weight, like any `unknown` field.
- **The report, the published rows and the `/internships` page show fit**: the rating and its reason.
- **Optional.** Without an `assessor` profile or `options.profile`, the stage is skipped and ranking works as now.

## Capabilities

### New Capabilities
- `fit-rating`: the profile, the Assess stage and its agent, the checks on ratings, how ratings are stored and reused, and how fit appears in the report.

### Modified Capabilities
- `opportunity-report`: "Ranking in code" gains the fit criterion.
- `internship-pipeline`: the stage order gains Assess, and the agent privileges gain the assessor.
- `report-publishing`: each published offer carries its fit rating and reason.
- `internship-report-view`: the page shows fit.

## Impact

- **Tracker code:** a new `usecases/internships/assessing.py` (task, checks, finish handler), `store.py` (a `fit_ratings` table, migration 3), `ranking.py` (the fit criterion), `wiring.py` (the stage and its tools), `report.py` (fit in entries and tables).
- **Config:** `config.yaml` gains the `assessor` profile and `options.profile`. The run's `max_tokens` rises so the agents' limits still fit inside it.
- **Backend:** an Alembic migration adding `fit_score` and `fit_reason` to `internship_offers`; `models.py`, `schemas.py`, `publish_report.py`; the regenerated OpenAPI document.
- **Frontend:** `components/internships/report.tsx` and the regenerated client.
- **Cost:** one short model call per batch of new or re-rated opportunities, on the Groq free tier. It costs no money, but uses daily tokens and some wall time.
- **Docs:** `docs/tracker.md`, `docs/agent-loop.md` (the flow) and `AGENT.md` (the ranking section).
