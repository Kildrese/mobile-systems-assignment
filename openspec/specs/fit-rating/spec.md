# fit-rating Specification

## Purpose
A fit rating of each internship against the candidate's profile: the profile, the Assess stage and its agent, the checks code runs on each rating, how ratings are stored and reused, and how fit appears in the report.

## Requirements
### Requirement: Profile
`options.profile` SHALL hold a short, plain-language description of the candidate and the internship they want. It is trusted config: it goes into the assessor's system prompt, never into a tool result. Code SHALL identify the profile by a hash of its stripped text.

#### Scenario: Profile edited
- **WHEN** a word in the profile changes
- **THEN** its hash changes

### Requirement: Assess stage
With an `assessor` agent profile and a non-empty `options.profile`, the pipeline SHALL run an Assess stage after Liveness and before Rank. The stage SHALL ask the assessor to rate every open opportunity that has no rating for the current profile, newest first, in batches of 8. Each batch SHALL be one fresh conversation whose task holds, for each opportunity, its id, company, title, the record's fields and the first 1,500 characters of its posting text, as untrusted data. The assessor SHALL have no tools besides `finish(ratings)`. The stage SHALL stop when no opportunity is left to rate or the assessor's budget runs out. Without an `assessor` profile or a profile text, the stage SHALL be skipped and the report SHALL not mention fit.

#### Scenario: New opportunities rated
- **WHEN** Curate saved 3 new opportunities and the profile is unchanged
- **THEN** Assess rates those 3, in one batch, and no other

#### Scenario: Budget runs out
- **WHEN** 30 opportunities need a rating and the assessor's budget covers 2 batches
- **THEN** the 16 newest are rated, the stage is `partial`, and the next run starts with the remaining 14

#### Scenario: No assessor
- **WHEN** the policy has no `assessor` profile
- **THEN** the run has no Assess stage, and the ranking and report are as without fit

### Requirement: Ratings are checked by code
Each rating SHALL be `{opportunity_id, fit, reason}`, with `fit` an integer from 0 to 3: 0 does not fit the profile, 1 weak, 2 good, 3 strong. The assessor's `finish` SHALL store a rating only when the opportunity id was in this batch, `fit` is from 0 to 3, and the reason is at most 200 characters and passes the Editor's summary check (sentence count, and no number or month that is not in the record). Rejected ratings SHALL go back to the model with their reasons, and it MAY correct them in the same conversation. An opportunity still without a valid rating when the batch ends SHALL stay unrated.

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
Each opportunity SHALL have at most one stored rating, with the profile hash it was made under. An opportunity needs a rating when it has none, or its rating's hash differs from the current profile's. While the profile is unchanged, an opportunity SHALL NOT be rated again, including after it closes and reopens. After a profile change, an old rating SHALL stay in use until it is replaced.

#### Scenario: Same fit every day
- **WHEN** an opportunity was rated 3 in run 1 and nothing in config changes
- **THEN** runs 2 to 5 make no model call for it and rank it with fit 3

#### Scenario: Profile changed
- **WHEN** the profile text changes between run 4 and run 5
- **THEN** run 5's Assess re-rates opportunities, newest first, and those not yet re-rated keep their old rating

### Requirement: Fit in the report
When the run has a profile, each full entry in the report SHALL show "**Fit:** n/3" and the reason, and the Still in top K and Also open tables SHALL have a Fit column with n/3, or "-" when the opportunity is not rated.

#### Scenario: Rated entry
- **WHEN** a new opportunity in the top K is rated 2 with reason "Backend role with real ownership, close to the profile's experience."
- **THEN** its full entry shows "**Fit:** 2/3, Backend role with real ownership, close to the profile's experience."

