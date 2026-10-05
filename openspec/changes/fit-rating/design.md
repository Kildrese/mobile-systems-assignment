# Design

## Context

`ranking.score()` sums five criteria from `RankingSettings`: role 3, term 3, location 2, recency 1, focus 3. Each scores 1 for a match, 0 for a mismatch and 0.5 for `unknown`. In practice nearly every curated opportunity matches on role, term, location and focus, so recency alone orders the top K.

The pipeline already has the pieces this change needs:
- The Editor (`editing.py`) is an agent whose only tool is `finish`. Its handler checks every item, stores the good ones and returns the rejected ones to the model. `summary_problem()` rejects numbers and months that are not in the record.
- The Curator runs one fresh conversation per unit of work, with that work in its task as untrusted data.
- `store.py` versions its tables in `MIGRATIONS`.

## Goals / Non-Goals

**Goals:**
- The top K reflects what the user wants, not only what matches the search.
- The rank stays stable from run to run, so Still in top K and Dropped stay meaningful.
- Every score can still be explained field by field, now including a one-sentence fit reason.

**Non-Goals:**
- Letting a model order the list, or re-score every opportunity every run.
- Learning from the user's clicks or applications. That would need feedback in the app, which can be a later change.
- More than one profile or user. The tracker serves one person's search.

## Decisions

### D1. A separate Assess stage, not part of the Curator
The Curator extracts facts and has every field checked against a quote. Fit is a judgment and cannot be quoted. Mixing the two would blur what "verified record" means. A separate stage also rates the opportunities that existed before this change, and re-rates them after a profile change, which the Curator never sees again.

It runs after Liveness, so closed opportunities are not rated, and before Rank, so today's ratings count today.

*Alternative:* rate inside `save_record`. That saves one call per new opportunity, but leaves the existing backlog unrated forever and makes the Curator's prompt longer for every posting.

### D2. Batches, one fresh conversation each, `finish` as the only tool
Each batch of up to 8 opportunities goes into the task, wrapped by `untrusted.wrap()`. The assessor answers with one `finish(ratings)` call. This follows the Editor's pattern: one model call per batch usually suffices, and a rejected rating can be fixed in the same conversation. The posting text is cut to 1,500 characters per opportunity, so a batch stays near 4,000 prompt tokens, under Groq's per-minute limit.

Order: by rank in the last run, then by first seen. After a profile change, or on the first run after deploy, the visible opportunities are rated first.

### D3. Ratings are keyed by profile hash and never re-asked
A new table in the state file (`MIGRATIONS[2]`):

```sql
CREATE TABLE fit_ratings (
    opportunity_id INTEGER NOT NULL REFERENCES opportunities(id),
    profile_hash TEXT NOT NULL,
    fit INTEGER NOT NULL CHECK (fit BETWEEN 0 AND 3),
    reason TEXT NOT NULL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (opportunity_id, profile_hash)
);
```

`profile_hash` is the SHA-256 of the profile with whitespace collapsed. "Needs a rating" means there is no row for the current hash. Ranking uses the current hash's row, else the newest row for any hash, else unknown (0.5). So editing the profile never makes the ranking jump to "everything unknown": old ratings stay until they are replaced.

Reopened opportunities keep their rating, since the opportunity id is stable (opportunity-lifecycle).

### D4. Fit weight 6, unrated is 0.5
`Weights` gains `fit: float = 6`, and the criterion is `fit / 3`. With 6, a fit-3 opportunity seen a month ago (recency 0) beats a fit-2 one seen today: 6 against 4 + 1. Fit dominates, but focus, term and location still exclude an off-target role (each worth 2–3). The weight is in `ranking.weights`, so it can be tuned without code.

An unrated opportunity scores 3, between fit 1 (2) and fit 2 (4): it is neither buried nor promoted, the same rule as other unknown fields.

### D5. Checks on a rating
- The id is in this batch (`not_requested` otherwise).
- `fit` is an integer from 0 to 3 (`invalid_fit`).
- The reason is one sentence of at most 200 characters, with no URL, and `summary_problem()` finds no invented number or month.

The reason is shown to the user, so it gets the same "nothing that isn't in the record" check as summaries.

### D6. The profile lives in `options.profile`
It is use-case config next to `ranking`, validated by `wiring.validate()`, and goes into the assessor's system prompt through a `{profile}` placeholder. If the profile is missing or empty, the Assess stage is not built. Without an `assessor` agent profile, the stage is not built either. Existing configs and test policies keep working unchanged.

### D7. Budgets
The `assessor` profile in `config.yaml` uses the main model (`openai/gpt-oss-120b`) with `max_steps: 6` and `max_tokens: 25000`, which covers 4–5 batches. The run's `limits.max_tokens` rises from 150,000 to 175,000 so the agents' limits still fit inside it, which policy validation checks. Steps already fit: 12 + 35 + 6 + 6 = 59 ≤ 60. Groq's free tier prices tokens at 0, so cost is unchanged, but daily token quotas and wall time are not free. See Risks.

### D8. Publishing and the page
`internship_offers` gains `fit_score` (integer, nullable) and `fit_reason` (text, nullable). `publish_report.offers()` reads the rating that ranking used. The API exposes `fitScore` and `fitReason`, and the card shows "Fit n/3" with the reason. Old rows stay null.

## Risks / Trade-offs

- **A posting can talk itself up.** The assessor reads untrusted posting text, and a posting saying "this is a perfect fit" might get a 3. The damage is bounded: fit is at most 6 points, the same as a real strong fit, and it can't change any other criterion, the status or the record. The trace flags suspected injection as it does for other agents. This trade is accepted: judging fit means reading the posting.
- **A rating can be wrong and stays wrong.** Stability means a bad rating is never revisited unless the profile changes. A small profile edit re-rates everything, which is the escape hatch. A command to re-rate one opportunity can come later if needed.
- **First run after deploy.** Every open opportunity is unrated. At 8 per batch and 4–5 batches a run, about 40 are rated per run; a larger backlog takes a few days. Until then, unrated ones rank as half a fit.
- **Wall time.** Each batch is one or two calls; on the free tier a per-minute wait can add a minute. `max_wall_seconds` (1,500) stays as is. If runs start hitting it, lower `assess_batch` or the assessor's steps.
- **The profile is personal.** It sits in `config.yaml`, which is committed. It should describe interests, not private details.
