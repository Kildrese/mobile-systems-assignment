# Spec Delta

## ADDED Requirements

### Requirement: Profile
`options.profile` SHALL hold a plain-language description of what the user wants from an internship, up to 1,500 characters. It is trusted config: it goes into the assessor's system prompt, never into a tool result. Policy validation SHALL fail when the profile is longer than 1,500 characters. Code SHALL identify the profile by a hash of its text, with whitespace collapsed.

#### Scenario: Profile too long
- **WHEN** `options.profile` has 2,000 characters
- **THEN** validation fails before any network call, naming `options.profile`

#### Scenario: Whitespace-only edit
- **WHEN** the profile is re-indented without changing its words
- **THEN** its hash is unchanged, and no rating is redone

### Requirement: Assess stage
With an `assessor` agent profile and a non-empty `options.profile`, the pipeline SHALL run an Assess stage after Liveness and before Rank. The stage SHALL ask the assessor to rate every open opportunity that has no rating for the current profile, in batches of at most `options.assess_batch` (default 8). Opportunities SHALL be taken in order of their rank in the last run, then unranked ones by first-seen time, so the most visible are rated first. Each batch SHALL be one fresh conversation whose task holds, for each opportunity, its id, company, title, the record's fields and the first 1,500 characters of its posting text, as untrusted data. The stage SHALL stop when no opportunity is left to rate or the assessor's budget runs out. Without an `assessor` profile or a profile text, the stage SHALL be skipped and the report SHALL not mention fit.

#### Scenario: New opportunities rated
- **WHEN** Curate saved 3 new opportunities and the profile is unchanged
- **THEN** Assess rates those 3, in one batch, and no other

#### Scenario: Budget runs out
- **WHEN** 30 opportunities need a rating and the assessor's budget covers 2 batches of 8
- **THEN** the 16 most visible are rated, the stage is `partial`, and the next run starts with the remaining 14

#### Scenario: No assessor
- **WHEN** the policy has no `assessor` profile
- **THEN** the run has no Assess stage, and the ranking and report are as without fit

### Requirement: Assessor privileges
The assessor SHALL have no tools besides `finish(ratings)`: no search, no fetch, no source proposal, no record changes. Each rating SHALL be `{opportunity_id, fit, reason}`, with `fit` an integer from 0 to 3: 0 does not fit the profile, 1 weak, 2 good, 3 strong.

#### Scenario: Committed profile
- **WHEN** the committed `config.yaml` is loaded
- **THEN** the assessor profile lists no tools

### Requirement: Ratings are checked by code
The assessor's `finish` SHALL store a rating only when:
- the opportunity id was in this batch;
- `fit` is an integer from 0 to 3;
- the reason is one sentence of at most 200 characters, with no URL, and no number or month that is not in the record (the same check as the Editor's summaries).

Rejected ratings SHALL go back to the model with their reasons, and it MAY correct them in the same conversation. An opportunity still without a valid rating when the batch ends SHALL stay unrated.

#### Scenario: Out-of-range fit
- **WHEN** the assessor sends `fit: 5`
- **THEN** that rating is rejected as `invalid_fit`, and the others in the call are stored

#### Scenario: Invented number in the reason
- **WHEN** the reason says "pays $60/hour" and the record has no pay
- **THEN** the rating is rejected, naming `60`

#### Scenario: Id outside the batch
- **WHEN** the assessor rates an opportunity that was not in its task
- **THEN** that rating is rejected as `not_requested`

### Requirement: Ratings are kept and reused
A stored rating SHALL record the opportunity, the fit, the reason, the profile hash and the run that rated it. While the profile hash is unchanged, an opportunity SHALL NOT be rated again, including after it closes and reopens. When the profile hash changes, ratings for the old hash SHALL stay in use until each opportunity is rated again under the new one.

#### Scenario: Same fit every day
- **WHEN** an opportunity was rated 3 in run 1 and nothing in config changes
- **THEN** runs 2 to 5 make no model call for it and rank it with fit 3

#### Scenario: Profile changed
- **WHEN** the profile text changes between run 4 and run 5
- **THEN** run 5's Assess re-rates opportunities, most visible first, and those not yet re-rated keep their old rating

### Requirement: Fit in the report
When the run has a profile, each full entry in the report SHALL show "**Fit:** n/3" and the reason, and the Still in top K and Also open tables SHALL have a Fit column with n/3, or "-" when the opportunity is not rated. The report header SHALL say how many open opportunities are still waiting for a rating, when any are.

#### Scenario: Rated entry
- **WHEN** a new opportunity in the top K is rated 2 with reason "Backend role on a small data team, close to the profile's interests."
- **THEN** its full entry shows "**Fit:** 2/3, Backend role on a small data team, close to the profile's interests."

#### Scenario: Waiting for a rating
- **WHEN** 14 open opportunities are unrated at the end of the run
- **THEN** the report says 14 opportunities are waiting for a fit rating, and that they rank as half a fit until then
