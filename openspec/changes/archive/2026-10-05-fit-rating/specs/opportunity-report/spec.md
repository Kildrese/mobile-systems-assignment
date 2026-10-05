# Spec Delta

## MODIFIED Requirements

### Requirement: Ranking in code
Code SHALL score every open opportunity from config weights over role type, term match, location match, recency (first seen, posting date), focus and fit. Focus is whether the title names a role the search is for, by whole-word match against `ranking.focus_keywords` (software, ML, data, ...). Fit is the opportunity's stored fit rating divided by 3, weighted by `ranking.weights.fit` (default 3); an opportunity without a rating scores 0.5, like any unknown field. Ties are broken by first-seen time, then company name. The score SHALL be deterministic for the same records, ratings and config. Work-authorization wording SHALL NOT affect it. The top K are the K highest-scoring open opportunities.

#### Scenario: Deterministic ranking
- **WHEN** ranking runs twice on unchanged records, ratings and config
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
