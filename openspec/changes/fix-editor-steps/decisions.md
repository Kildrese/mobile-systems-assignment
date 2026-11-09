# Decisions: fix-editor-steps

Evidence (read-only look at prod runs on 2026-11-09: Neon tracker_runs/tracker_articles plus Actions trace artifacts for the Nov 3, 5, 8 and 9 runs):
- Caps (config.yaml): run 70 steps / 1500 s wall; scout 12 steps / 6 searches; editor 6 steps.
- Groq answers 2–4 of each agent's calls per run with a 400, which the tracker logs as `model_output_rejected`. Every Scout finish step was rejected. The trace doesn't keep Groq's error text, so the cause is unknown.
- The Editor needs 2 good steps (get_opportunities, then finish). Nov 3 and Nov 9 used 6 of 6 with 4 rejected and never finished, and 0 summaries were published (5 on complete runs). After a rejection, the Editor calls get_opportunities again.
- The Scout used 12 of 12 steps every run: 4–7 wasted, including 3 boards it already knew re-proposed each run. No visible loss in what was published.
- Wall time: ~481–521 s of 1500 per run, with the Editor taking 67–131 s.

## D1 Raise the Editor's step cap
- class: mine
- source: grilling
- status: decided
- question: The Editor runs out of steps on Groq 400s, and those days publish no summaries. Raise its cap?
- options: A 8 / B 10 / C 12 / D leave 6
- decision: Kilian, 2026-11-09: B, 10. Stopgap until the 400s are understood (D2). Scout and run caps are unchanged.
- landed: not landed, blocked on D3 (config.yaml still says 6)

## D2 Keep Groq's 400 reason in the trace
- class: mine
- source: grilling
- status: decided
- question: The 400s are logged without the provider's error text, so we can't tell why the calls are rejected. Record it?
- options: A record the provider's error message on model_output_rejected trace events / B no
- decision: Kilian, 2026-11-09: A. Diagnostics only: it doesn't change what is ranked or reported, and it doesn't go into any prompt. The repo is public and traces are published from cron runs, so truncate the message (e.g. 500 chars) and make sure it can't carry API keys or headers. If the error body echoes model output or prompt text, record only Groq's error code and message fields. A later change uses the evidence to fix the root cause.
- landed: backend/tracker/llm.py `_provider_error` (trace field `provider_error: {code, message}`, key scrubbed before the 500-char cut, `failed_generation` and headers never read); backend/tests_tracker/test_clients.py::test_chat_rejection_traces_only_the_providers_code_and_message

## D3 Editor at 10 doesn't fit the run's step cap
- class: mine
- source: implementer, D1
- status: open
- question: The internship use case checks that the agents' step caps plus the verifier's (max_requests x max_steps) fit in limits.max_steps (wiring.validate). Today 12 + 35 + 6 + 6 + 5x2 = 69 of 70. With the Editor at 10 it is 73, so every run fails with "limits.max_steps: agents and verifier add up to 73, more than 70" before the first call. D1 said the run cap is unchanged. Which gives?
- options: A run cap 70 -> 74 (the run's real step use stays the same; the cap only reserves room) / B Editor 7, the most that fits under 70 / C take 4 steps from another cap, e.g. Assessor 6 -> 2 or Curator 35 -> 31 (changes what gets curated or rated) / D verifier max_requests 5 -> 3 (fewer top-K claims checked)
- built: none; config.yaml still has the Editor at 6
- decision:
- landed:
