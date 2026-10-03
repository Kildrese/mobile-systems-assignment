# Spec Delta

## Purpose

Defines the tracker's tools (`search_web`, `fetch_article`, `finish`): their inputs, outputs and errors, and how to run each one directly from the command line without a model.

## ADDED Requirements

### Requirement: search_web
`search_web(query)` SHALL query the configured search provider and return a list of results. Each result SHALL have title, URL and snippet. The number of results SHALL be capped by policy. Each call SHALL count one search against `max_searches`, and the trace SHALL record the provider's credits used. An empty or overlong query (over 400 characters) SHALL be rejected without a network call.

#### Scenario: Normal search
- **WHEN** `search_web("founding engineer NYC startup")` is called with a valid key
- **THEN** it returns up to the configured number of results, each with title, URL and snippet

#### Scenario: Empty query
- **WHEN** `search_web("")` is called
- **THEN** it returns a validation error and makes no request

### Requirement: fetch_article
`fetch_article(url)` SHALL apply the fetch guardrails, download the page, extract readable text and title, store them in state, and return title, canonical URL, extracted text truncated to the policy's character limit, and whether the result came from cache. A URL already in state SHALL be served from state without a network request and SHALL NOT count against `max_fetches`.

#### Scenario: Fresh article
- **WHEN** `fetch_article` is called with an allowed URL not yet in state
- **THEN** the page is downloaded, its text is stored, and the result has `cached: false`

#### Scenario: Known article
- **WHEN** `fetch_article` is called with a URL whose canonical form is already in state
- **THEN** no request is made, and the stored text is returned with `cached: true`

### Requirement: finish
`finish(report)` SHALL accept a structured report: a ranked list of at most K items, each with title, summary and source URLs, plus an optional overall note. It SHALL validate the structure, render it as Markdown and write the report file. Calling `finish` SHALL end the loop.

#### Scenario: Too many items
- **WHEN** `finish` is called with K+2 items
- **THEN** only the top K by rank are kept, and the trace records the truncation

### Requirement: Tools run without the model
Each tool SHALL be callable from the command line as `python -m tracker.tools <tool> <args>` (from `backend/`): `search_web <query>`, `fetch_article <url>`, `finish <report.json>`. The CLI SHALL print the tool's result as JSON to stdout. It SHALL exit `0` on success and non-zero on a validation, guardrail or provider error, with the error printed as JSON.

#### Scenario: Direct fetch
- **WHEN** a user runs `uv run python -m tracker.tools fetch_article https://example.com/`
- **THEN** the extracted article JSON is printed and the command exits `0`

#### Scenario: Direct fetch of a blocked URL
- **WHEN** a user runs `uv run python -m tracker.tools fetch_article http://127.0.0.1:8000/`
- **THEN** a JSON error with reason `blocked_address` is printed, no connection is made, and the command exits non-zero

### Requirement: Tool errors are results, not crashes
Inside a run, a tool's validation, guardrail or non-terminal provider error SHALL be returned to the model as an error tool result with a machine-readable reason, so the model can choose another action. Only terminal provider failures SHALL end the run.

#### Scenario: Guardrail rejection during a run
- **WHEN** the model calls `fetch_article` with a URL whose host is not allowed
- **THEN** the model receives an error result with reason `host_not_allowed`, and the run continues
