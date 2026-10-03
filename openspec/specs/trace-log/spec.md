# trace-log Specification

## Purpose
The append-only JSONL trace per run: one event per model attempt, tool call and run end, flushed as written, with long fields truncated and API keys redacted.
## Requirements
### Requirement: One JSONL trace per run
Each run SHALL write a trace file at `traces/<run_id>.jsonl`, one JSON object per line, appended as events happen, so a crashed or interrupted run still leaves a trace up to that point.

#### Scenario: Interrupted run
- **WHEN** a run is killed with Ctrl-C after three steps
- **THEN** the trace file contains the events of those three steps

### Requirement: Event fields
Every model call and tool call attempt SHALL produce an event with: timestamp, run id, step number, kind (`model` or `tool`), tool name (or model name), arguments, status (`ok`, `error`, `retry`, `blocked`, `budget`, `cached`), latency in milliseconds, and, where applicable, prompt, completion and total tokens, search credits, HTTP status, failure class and attempt number. The run SHALL end with a summary event holding totals and the outcome.

#### Scenario: Model call event
- **WHEN** the loop makes a model call that succeeds
- **THEN** the trace has an event with kind `model`, status `ok`, latency, and prompt, completion and total tokens from the provider's usage data

#### Scenario: Retry visible
- **WHEN** a model call gets a per-minute 429 and then succeeds
- **THEN** the trace has an event with status `retry`, HTTP status `429` and failure class `transient`, followed by an `ok` event for the same step

#### Scenario: Summary event
- **WHEN** a run ends for any reason
- **THEN** the last event has kind `summary`, with the outcome, stop reason, totals for steps, fetches, searches, tokens and credits, and wall time

### Requirement: Traces hold no secrets and bounded content
Trace events SHALL NOT contain API keys or authorization headers. Long argument and result fields SHALL be truncated to a fixed size, with the original length recorded.

#### Scenario: Key never logged
- **WHEN** a run's trace is searched for the value of `GROQ_API_KEY` or `TAVILY_API_KEY`
- **THEN** there is no match

