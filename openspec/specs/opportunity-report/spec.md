# opportunity-report Specification

## Purpose
Ranking in code, the checks on the Editor's summaries, and the report that compares this run's top K with the last run's: New since last run, Still in top K, Dropped and Also open.
## Requirements
### Requirement: Ranking in code
Code SHALL score every open opportunity from config weights over role type, term match, location match, recency (first seen, posting date) and focus: whether the title names a role the search is for, by whole-word match against `ranking.focus_keywords` (software, ML, data, ...). Ties are broken by first-seen time, then company name. The score SHALL be deterministic for the same records and config. Work-authorization wording SHALL NOT affect it. The top K are the K highest-scoring open opportunities.

#### Scenario: Deterministic ranking
- **WHEN** ranking runs twice on unchanged records and config
- **THEN** both produce the same order

#### Scenario: Off-focus internship
- **WHEN** a "Product Design Intern" and a "Software Engineering Intern" match on role type, term, location and recency
- **THEN** the software internship ranks higher

### Requirement: Editor agent
The Editor agent SHALL write, for each opportunity whose summary the report shows (the first K new opportunities by rank, and the current top K), a summary of at most 3 sentences on what the role is and why it matches the configured criteria. Its tools SHALL be `get_opportunities` and `finish(summaries)`. It SHALL NOT change ranks, statuses, sources or records. A summary SHALL be accepted only when it cites the opportunity's id. If the Editor stage is skipped or runs out of budget, the report SHALL show the record's fields without a summary.

#### Scenario: Editor skipped
- **WHEN** the Editor stage is skipped because of a terminal model failure
- **THEN** the report still lists every opportunity with title, company, location, term and link, without summaries

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

### Requirement: Every listed opportunity cites its source
Each opportunity in the report SHALL show at least one source URL, and every quoted field SHALL come from the verified record. Summaries SHALL NOT add facts that are not in the record or posting text. This is checked by flagging summary sentences that contain numbers or dates absent from the record.

#### Scenario: Summary adds a salary
- **WHEN** the Editor's summary mentions "$45/hour", but the record has no compensation
- **THEN** the summary is rejected, and the report shows the fields without a summary for that opportunity

