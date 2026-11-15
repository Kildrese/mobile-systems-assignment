## MODIFIED Requirements

### Requirement: Ranking in code
Code SHALL score every open opportunity from config weights over role type, term match, location match, recency (first seen, posting date), focus and fit. Focus is whether the title names a role the search is for, by whole-word match against `ranking.focus_keywords` (software, ML, data, ...). Fit is the opportunity's stored fit rating divided by 3, weighted by `ranking.weights.fit` (default 3); an opportunity without a rating scores 0.5, like any unknown field. A field whose stored verdict is `unsupported` SHALL score as `unknown`. `unreachable` and `unverified` SHALL NOT change a score. Ties are broken by first-seen time, then company name. The score SHALL be deterministic for the same records, ratings, verdicts and config. Work-authorization wording SHALL NOT affect it. The top K are the K highest-scoring open opportunities.

#### Scenario: Deterministic ranking
- **WHEN** ranking runs twice on unchanged records, ratings, verdicts and config
- **THEN** both produce the same order

#### Scenario: Off-focus internship
- **WHEN** a "Product Design Intern" and a "Software Engineering Intern" match on role type, term, location and recency, and have the same fit
- **THEN** the software internship ranks higher

#### Scenario: Fit separates equal matches
- **WHEN** two software internships match on role type, term, location, focus and recency, and one is rated fit 3 and the other fit 1
- **THEN** the one rated 3 ranks higher

#### Scenario: Unrated opportunity
- **WHEN** an opportunity has no fit rating
- **THEN** its fit criterion scores half of `ranking.weights.fit`

#### Scenario: Unsupported term
- **WHEN** an opportunity's term "Summer 2027" is verified `unsupported`
- **THEN** its term criterion scores half of `ranking.weights.term`

#### Scenario: Unreachable page
- **WHEN** an opportunity's claims are all `unreachable`
- **THEN** its score is the same as without verification

## ADDED Requirements

### Requirement: Verdicts in the report
For each opportunity in the top K, the report SHALL list its claims with their label: `supported`, `unsupported`, `unreachable` or `unverified`. A supported claim SHALL show its evidence as a quote. When the Verify stage failed or was skipped, the report header SHALL say so and name the failed service.

#### Scenario: Supported claim
- **WHEN** the pay claim is supported with the evidence "$55/hour"
- **THEN** the report shows the claim, the label `supported` and the quoted evidence

#### Scenario: Verifier down
- **WHEN** the Verify stage failed
- **THEN** the header says the report is partial because `verifier` failed, and every claim shows `unverified`
