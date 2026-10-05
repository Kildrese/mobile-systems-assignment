# Spec Delta

## MODIFIED Requirements

### Requirement: Cumulative report layout
The report SHALL start with the core header (topic, run, time, status, budget usage, plus per-stage outcomes). It SHALL then compare this run's top K with the last run's: the newest earlier finished run that has ranks. The sections SHALL appear in this order:
1. **New since last run**: open opportunities whose `first_seen_run` is this run, by rank. The first K in full (fields, summary, quotes, link), any others in a compact list. Those in the top K are marked.
2. **Still in top K**: the rest of this run's top K, by rank, each with its rank in the last run. One that was not in the last run's top K is marked "entered the top K".
3. **Dropped**: each opportunity that was in the last run's top K and is not in this one, with its reason. The reason is `closed`, with the closing evidence, or `outranked`, with its current rank. The section also lists any other opportunity whose `closed_run` is this run, with reason `closed`.
4. **Also open**: every other open opportunity first seen in an earlier run, accumulated across all runs, in one table by rank, plus an "unverified" note for any whose source could not be checked.

An opportunity SHALL appear in at most one section, taking the first that applies in the order above. On a first run (no earlier finished run with ranks), Still in top K and Dropped SHALL be empty and say that there is no earlier run to compare with. When postings listed in this run are still waiting for the Curator because its budget ran out, the report SHALL say how many, above the sections.

#### Scenario: Second day
- **WHEN** run 1's top 5 is A, B, C, D, E, and in run 2 a new opportunity F ranks 2nd, C closes, and E ranks 7th
- **THEN** run 2's report lists F under New since last run (marked top K), A, B and D plus the next-ranked earlier opportunity under Still in top K, C (closed, with evidence) and E (outranked, now 7th) under Dropped, and every other open earlier opportunity under Also open, none twice

#### Scenario: First run
- **WHEN** the state holds no earlier finished run with ranks
- **THEN** every open opportunity is under New since last run, and Still in top K and Dropped each say there is no earlier run to compare with

#### Scenario: Entered the top K
- **WHEN** an opportunity first seen in run 1 ranked 8th, and ranks 3rd in run 2
- **THEN** run 2 lists it under Still in top K at rank 3, marked "entered the top K"

#### Scenario: Last run failed before ranking
- **WHEN** run 2 stopped on a terminal failure before Rank, and run 3 finishes
- **THEN** run 3 compares its top K with run 1's

#### Scenario: Curation not finished
- **WHEN** 21 postings listed in this run are still pending at the end of the run
- **THEN** the report says 21 postings are waiting for review and that the next run starts with them

#### Scenario: Open entries accumulate
- **WHEN** an opportunity first seen in run 1 stays open but outside the top K through run 5
- **THEN** it appears under Also open in the reports of runs 2 to 5, and never under New after run 1
