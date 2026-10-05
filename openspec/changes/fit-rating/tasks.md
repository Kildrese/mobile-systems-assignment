# Tasks

## 1. Profile and storage (fit-rating)

- [ ] 1.1 Add `profile` to the internship options, plus `profile_hash()` over the stripped text. Test that changing a word changes the hash
- [ ] 1.2 Add `MIGRATIONS[2]` with the `fit_ratings` table (design D3), and `OpportunityStore.put_fit()` (upsert), `fits()` and `needs_fit(profile_hash)` (open, no row or another hash, newest first). Test that an old-hash rating is still returned until replaced, and that a reopened opportunity keeps its rating

## 2. Assess stage (fit-rating, internship-pipeline)

- [ ] 2.1 Write `usecases/internships/assessing.py`: the batch task (untrusted, posting text cut to 1,500 characters), `RatingsArgs`, and `finish_ratings()` with the checks in design D5 (reuse `summary_problem()`). Write a table test: valid, `invalid_fit`, `not_requested`, over 200 characters, an invented number
- [ ] 2.2 Add `AssessStage` to `wiring.py` between Liveness and Rank, built only with an `assessor` profile and a profile text; the `{profile}` placeholder in its instructions; `partial` when the budget stops it with opportunities left. Tests: "New opportunities rated", "Budget runs out", "No assessor"
- [ ] 2.3 Add the `assessor` profile and the `options.profile` from design D6 to `config.yaml`, and raise `limits.max_tokens` to 175,000. Extend the committed-configs test: the assessor has no tools, and the limits fit
- [ ] 2.4 Pipeline test with a scripted model: two runs, the second makes no assessor call for already-rated opportunities ("Same fit every day"), and the stage list includes `assess`

## 3. Ranking and report (opportunity-report, fit-rating)

- [ ] 3.1 Add `Weights.fit = 3` and the fit criterion in `ranking.score()` (unrated scores 0.5). Tests: "Fit separates equal matches", "Unrated opportunity", and that the existing scores are unchanged when nothing is rated
- [ ] 3.2 Show fit in `report.py`: "**Fit:** n/3, reason" in full entries, a Fit column in the Still in top K and Also open tables. Nothing about fit when the run has no profile. Test: "Rated entry"

## 4. Publishing and page (report-publishing, internship-report-view)

- [ ] 4.1 Alembic migration adding `fit_score` and `fit_reason` to `internship_offers`; update `models.py`, `schemas.py` (`fitScore`, `fitReason`) and `publish_report.offers()`. Test "Fit published"
- [ ] 4.2 Regenerate `openapi/openapi.json` and the frontend client
- [ ] 4.3 Show "Fit n/3" and the reason on the card in `components/internships/report.tsx`

## 5. Docs and rollout

- [ ] 5.1 Update `docs/tracker.md` (stages, ranking, config), the flow in `docs/agent-loop.md`, and the ranking section of `AGENT.md`
- [ ] 5.2 Before merging, apply the migration to production with `./scripts/db-migrate-neon.sh`, since the daily publish writes the new columns
