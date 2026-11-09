# Decisions: fix-archive-shipped-changes

Archive the OpenSpec changes whose code is merged and whose production steps are done.

## D1 Production steps confirmed done
- class: mine
- source: grilling
- status: decided
- question: Are the remaining production/manual tasks of add-claim-verifier, add-application-drafter, tracker-daily-trigger, complete-daily-runs and show-run-history done?
- options: A all done, archive them / B some pending
- decision: Kilian, 2026-11-09: A. Drafter tested and working; daily trigger working; the rest fine. Tick the remaining boxes and archive.
- landed: openspec/changes/archive/2026-11-09-{add-claim-verifier,add-application-drafter,tracker-daily-trigger,complete-daily-runs,show-run-history}; specs synced into openspec/specs/ (new: claim-verification, applicant-profile, application-drafter, application-drafts, tracker-dispatch)

## D2 Hold agentic-dev-cycle open
- class: cheap
- source: grilling
- status: resolved
- question: agentic-dev-cycle task 4.1 needs a first real orchestrator run on a feature; an archive-only fix doesn't exercise grilling → spec-writer → implementer. Archive it now?
- options: A keep it open until the first real feature run / B archive now
- decision: orchestrator, 2026-11-09: A. Not archived in this fix.
- landed: openspec/changes/agentic-dev-cycle left untouched

## D3 Commit services/drafter/.gitignore
- class: cheap
- source: grilling
- status: resolved
- question: The main checkout has an untracked services/drafter/.gitignore (`.vercel`, `.env*`), written by `vercel link`. Commit it?
- options: A commit it on this branch / B drop it
- decision: orchestrator, 2026-11-09: A. It keeps Vercel link state and env files out of the public repo.
- landed: services/drafter/.gitignore

## D4 Archive order
- class: cheap
- source: implementer
- status: resolved
- question: Archiving show-run-history after tracker-daily-trigger failed: its MODIFIED "The API cannot start the tracker" was renamed by tracker-daily-trigger. MODIFIED replaces whole requirements, so archiving out of merge order would also let older text overwrite newer. Which order?
- options: A archive in merge order / B log a conflict and skip show-run-history
- built: A
- decision: implementer, 2026-11-09: A. Reset and re-archived in merge order: complete-daily-runs (#18), show-run-history (#23), tracker-daily-trigger (#29), add-claim-verifier (#33), add-application-drafter (#34). All applied cleanly; `openspec validate --all` passes.
- landed: openspec/specs/ (sync), openspec/changes/archive/2026-11-09-*

## D5 Stale drafter delta reverted "Daily scheduled run"
- class: cheap
- source: reviewer
- status: resolved
- question: add-application-drafter's MODIFIED "Daily scheduled run" (report-publishing) was written against the pre-#29 text; archived last, it restored "scheduled GitHub Actions workflow at 09:00 UTC" and dropped tracker-daily-trigger's Vercel-cron / workflow_dispatch-only text, the job-timeout clause, and scenarios "GitHub's scheduler can't add a run", "Manual run while the daily run is in progress", "Run uses its full wall time". Code matches the cron version (.github/workflows/tracker.yml:17,30; backend/vercel.json:3). Fix how?
- options: A merge by hand: tracker-daily-trigger's text + the drafter's draft_new sentence, "nothing is published or drafted" wording and "Drafting fails" scenario / B re-archive
- decision: orchestrator, 2026-11-09: A. Also check every other requirement the drafter (#34) and verifier (#33) deltas MODIFIED for the same stale-base problem against the code.
- landed: openspec/specs/report-publishing/spec.md#Daily scheduled run (tracker-daily-trigger text + draft_new sentence, "published or drafted", "Drafting fails"; checked against .github/workflows/tracker.yml:16-17,30,77-79 and backend/vercel.json:3). Other MODIFIED requirements checked, none stale: verifier's Internship page (extends show-run-history), Publish the latest finished run (extends fit-rating), Fixed stage order (extends fit-rating), Ranking in code (extends fit-rating), Degraded runs still report (extends add-internship-tracker); the drafter modified only Daily scheduled run.

## D6 Purpose lines for the new specs
- class: cheap
- source: reviewer
- status: resolved
- question: The 5 new specs (claim-verification, applicant-profile, application-drafter, application-drafts, tracker-dispatch) keep "Purpose: TBD - created by archiving change ...". Fill them?
- options: A one-line purpose each, from the archived proposal / B leave TBD
- decision: orchestrator, 2026-11-09: A.
- landed: openspec/specs/{claim-verification,applicant-profile,application-drafter,application-drafts,tracker-dispatch}/spec.md, ## Purpose
