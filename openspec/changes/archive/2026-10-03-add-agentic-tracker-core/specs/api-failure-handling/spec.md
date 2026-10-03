# Spec Delta

## Purpose

Classifies every failure from the model provider and the search provider as transient or terminal, so transient ones are retried with capped backoff and terminal ones (bad key, exhausted daily or monthly quota, payment required) stop the run at once with a clear message.

## ADDED Requirements

### Requirement: Failure classification
Every failed call to the model provider or search provider SHALL be classified as **transient** or **terminal**, and the class SHALL be recorded in the trace.
- Transient: connect and read timeouts, connection errors, HTTP 408, per-minute rate limits (429 not tied to a daily or monthly quota), 500, 502, 503 and 504.
- Terminal: 400 for an invalid request, 401, 403, 402, quota-exhausted responses (Groq daily request or token limits, Tavily plan or credit limits such as 432), and any other 4xx.

#### Scenario: Bad key
- **WHEN** the model provider returns 401
- **THEN** the call is not retried, and the run stops with a message saying the API key for that provider was rejected

#### Scenario: Server error
- **WHEN** the search provider returns 503
- **THEN** the call is treated as transient and retried

### Requirement: Per-minute versus daily 429
A 429 SHALL be classified from the response body and headers. When the response names a daily or monthly limit (for example "tokens per day (TPD)" or "requests per day (RPD)"), or asks for a wait longer than the configured maximum retry wait, it SHALL be terminal. Otherwise it SHALL be transient. A daily or monthly quota SHALL never be retried.

#### Scenario: Per-minute limit
- **WHEN** Groq returns 429 naming "tokens per minute (TPM)" with `retry-after: 7`
- **THEN** the client waits about 7 seconds and retries the same request

#### Scenario: Daily cap
- **WHEN** Groq returns 429 naming "requests per day (RPD)"
- **THEN** the client does not retry, and the run stops with a message saying the daily quota is exhausted and when it resets if the provider says

### Requirement: Capped retries with backoff
Transient failures SHALL be retried with exponential backoff and jitter, honoring `retry-after` when present, up to a configured maximum number of attempts and a maximum single wait. Each retry SHALL count against the wall-clock budget. When attempts run out, the failure SHALL be treated as terminal for the run.

#### Scenario: Network cut
- **WHEN** every request fails with a connection error
- **THEN** the client retries up to the configured attempt cap, then the run stops with a message saying the provider is unreachable and writes a partial report

#### Scenario: Recovery
- **WHEN** the first attempt times out and the second succeeds
- **THEN** the run continues normally, and the trace shows one `retry` entry followed by an `ok` entry

### Requirement: Clean terminal stop
A terminal failure SHALL end the run without a stack trace. The process SHALL print one message naming the provider, the failure class and the likely fix, write a partial report when any evidence exists, record the failure in the trace, and exit with status `3`.

#### Scenario: Payment required
- **WHEN** the model provider returns 402
- **THEN** the process prints a message saying that provider requires payment or credit, writes the trace, and exits `3`
