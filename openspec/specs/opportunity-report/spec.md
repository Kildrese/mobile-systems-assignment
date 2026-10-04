# opportunity-report Specification

## Purpose
Ranking in code, the checks on the Editor's summaries, and the cumulative report with New since last run, Still open and Closed since last run.
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
The report SHALL start with the core header (topic, run, time, status, budget usage, plus per-stage outcomes), then three sections:
1. **New since last run**: opportunities whose `first_seen_run` is this run, by rank. The first K in full (fields, summary, quotes, link), any others in a compact list.
2. **Still open**: every open opportunity first seen in an earlier run, accumulated across all runs, in one table by rank, with the current top K marked, plus an "unverified" note for any whose source could not be checked.
3. **Closed since last run**: opportunities whose `closed_run` is this run, with the closing evidence.

An opportunity SHALL appear in exactly one section. When postings listed in this run are still waiting for the Curator because its budget ran out, the report SHALL say how many, above the sections.

#### Scenario: Second day
- **WHEN** run 1 found 6 opportunities, and run 2 finds 2 new ones, sees 5 of the earlier 6 still open, and 1 closed
- **THEN** run 2's report lists 2 under New, 5 under Still open, 1 under Closed, and none twice

#### Scenario: Curation not finished
- **WHEN** 21 postings listed in this run are still pending at the end of the run
- **THEN** the report says 21 postings are waiting for review and that the next run starts with them

#### Scenario: Still-open entries accumulate
- **WHEN** an opportunity first seen in run 1 stays open through run 5
- **THEN** it appears under Still open in the reports of runs 2 to 5, and never under New after run 1

### Requirement: Every listed opportunity cites its source
Each opportunity in the report SHALL show at least one source URL, and every quoted field SHALL come from the verified record. Summaries SHALL NOT add facts that are not in the record or posting text. This is checked by flagging summary sentences that contain numbers or dates absent from the record.

#### Scenario: Summary adds a salary
- **WHEN** the Editor's summary mentions "$45/hour", but the record has no compensation
- **THEN** the summary is rejected, and the report shows the fields without a summary for that opportunity

