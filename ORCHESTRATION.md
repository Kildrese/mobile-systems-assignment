# Agentic Orchestration

Two agents talk over a network here. The orchestrator is the tracker's daily run (`backend/tracker`, on GitHub Actions). The worker is the claim verifier (`services/verifier`, its own Vercel project). The tracker sends one `POST /verify` per top-K opportunity whose record changed. The verifier fetches the posting itself and answers with a verdict per claim.

Numbers marked `<measure: ...>` have not been measured yet. No run with the verifier exists in `reports/` or `traces/` so far. Each placeholder comes with the command that measures it.

## Why Vercel and Neon instead of Render

The brief suggests Render's free tier. A free Render web service spins down after 15 minutes without traffic, and the next request waits about a minute while it starts again.

We use Vercel and Neon instead. The frontend and the backend already ran on Vercel, with Neon Postgres behind the backend, before this assignment. The verifier is one more Vercel project (`mobile-systems-verifier`, see `docs/deployment.md`). The drafter (`services/drafter`) is built the same way and will be a third one. It is not deployed yet. So there is one platform, one deploy flow (a push to `master` deploys, other branches get previews) and one place for env vars.

This does not remove cold starts. It makes them smaller.

- **Vercel Python functions still cold-start.** A new instance has to start Python and import FastAPI, pydantic and httpx before it can answer. That takes seconds, not a minute. There is no 15-minute rule, but an idle function is still shut down at some point.
- **Fluid Compute reuses instances, without a guarantee.** Two requests close together can land on the same warm instance. Nothing promises it.
- **Instances are not durable.** The verifier keeps its idempotency store in process memory (see Q3). A new instance starts with an empty store. That is the same problem as a Render restart.
- **Our traffic pattern hits a cold start every day.** The tracker runs once a day and sends at most 5 requests (`max_requests: 5` in `config.yaml`). After a day of no traffic, the first request will most likely start a new instance on either platform. The difference is how long it waits.
- **Neon does not affect the verifier.** The verifier has no database. Neon's free tier suspends compute after it has been idle and wakes it on the next connection. That delay hits the backend API and the tracker's publish step, not `/verify`.

The trade: a cold start of seconds and no 15-minute spin-down, instead of a cold start of about a minute. It is not zero cold start.

| What | Value | How to measure |
| --- | --- | --- |
| Verifier, first `/healthz` after 20 min idle | `<measure: first /healthz after 20 min idle>` | `curl -s -o /dev/null -w '%{time_total}\n' "$VERIFIER_URL/healthz"` |
| Verifier, `/healthz` right after that | `<measure: warm /healthz>` | `curl -s -o /dev/null -w '%{time_total}\n' "$VERIFIER_URL/healthz"` |
| Verifier, first `/healthz` after a day idle | `<measure: first /healthz after 24 h idle>` | `curl -s -o /dev/null -w '%{time_total}\n' "$VERIFIER_URL/healthz"` |

`/healthz` needs no token and spends nothing.

## Q1 The contract

TODO

## Q2 The network

This section covers cold starts and timeouts only.

### What a cold start costs here

The verifier's clock starts when its code receives the request (`services/verifier/verify.py:85-86`):

```python
    start = clock()
    deadline = start + req.time_budget_ms / 1000
```

A cold start happens before that line runs. So the time a cold start takes is not part of `time_budget_ms`, and the client has to wait for both. On a warm instance the cold-start part is close to zero.

| Call | Latency | How to measure |
| --- | --- | --- |
| Cold start of the verifier | `<measure: first /healthz after 20 min idle minus warm /healthz>` | the two `curl` lines in the table above |
| One `/verify`, first of the day | `<measure: /verify latency, cold>` | `curl -s -o /dev/null -w '%{time_total}\n' -X POST "$VERIFIER_URL/verify" -H "Authorization: Bearer $VERIFIER_TOKEN" -H 'Content-Type: application/json' -d @verify-body.json` |
| One `/verify`, right after | `<measure: /verify latency, warm>` | the same `curl`, with a new `request_id` in `verify-body.json` |

A `/verify` call costs one page fetch and one Groq call. Only someone with `VERIFIER_TOKEN` can make it: the tracker's GitHub Actions run, or the owner by hand with the line above.

Per-call latency from the first run with the verifier. This table is empty until that run exists:

| request | attempt | status | latency_ms (tracker side) |
| --- | --- | --- | --- |
| `<measure: from run 1 traces>` | | | |

Command to fill it: `jq -c 'select(.kind=="service") | [.request_id, .attempt, .status, .latency_ms]' traces/<run_id>.jsonl`

### How the timeouts were chosen

All values come from `config.yaml` `options.verifier` (lines 129-136) and are read by `VerifierSettings` (`backend/tracker/usecases/internships/verifying.py:49-60`):

```yaml
    time_budget_ms: 60000  # the verifier's clock, from when it receives the request
    cold_start_ms: 15000   # added to the client timeout: a cold start happens before the clock
    max_attempts: 4
```

- **Client timeout: 75 s.** It is `time_budget_ms` plus `cold_start_ms`, 60 s plus 15 s (`verifying.py:157`). The 60 s is the work: one fetch (up to 6 with redirects) and one or two model calls. The 15 s is for a cold start. A Vercel Python cold start takes seconds, so 15 s leaves room. If the cold start runs longer, the attempt times out, and the next attempt may find the instance warm.
- **Attempts: 4** (`max_attempts`). The same body and the same `request_id` are sent each time.
- **What is retried.** A timeout, a connection error, and `502`, `503` or `504` (`verifying.py:212`). A retry after `502` or `504` can repeat the verifier's paid Groq call, because the first copy may have made its model call before the gateway gave up. `401` stops the whole Verify stage. `400`, `409`, `500` and an invalid `200` are not retried.
- **Backoff.** Before attempt n+1 the client waits `min(2^n, 30)` seconds times a factor between 0.8 and 1.2, so ±20% jitter (`verifying.py:214-215`). With 4 attempts that is about 2 s, 4 s and 8 s. The 30 s cap is never reached at this setting.
- **`Retry-After` is honored.** The client reads the header (`agentkit.fetch.parse_retry_after`, `packages/agentkit/src/agentkit/fetch.py:26`) and waits the longer of the backoff and the header.

```python
            backoff = min(2**attempt, 30) * (0.8 + 0.4 * random.random())
            pause = max(backoff, wait or 0)
```

Worst case for one request, computed from these settings and not measured: 4 attempts of 75 s plus about 14 s of backoff, so a bit over 5 minutes. A `Retry-After` can make it longer. With 5 requests a run, a verifier that hangs every time could add about 26 minutes to the run, if nothing stopped it.

The wall-time check stops it. The GitHub Actions job has `timeout-minutes: 30` (`.github/workflows/tracker.yml:30`). The run has its own wall-time budget, `max_wall_seconds: 1500` (`config.yaml:47`), which ends earlier. Before each attempt, including each retry, the client checks the run's remaining wall time (`verifying.py:160`). If the wait before the attempt plus 75 s would pass it, the client sends nothing more and does not sleep. The rest of the claims stay `unverified`, the stage is partial, and the run names `verifier` as the failed service. So the run ends before the job's 30-minute limit, and Report and the publish step (`tracker.yml:74-75`) still run. The 75 s timeout applies to each phase of an attempt in httpx, not to the whole attempt, so a slow-streaming response can run longer. The 300 s between `max_wall_seconds` and the job limit absorbs that. The deadline is the run's own (`Budget.deadline`), passed in by the Verify stage (`wiring.py:820-821`). A request that was never sent is not counted or charged.

A verifier that refuses connections fails much faster. Then the run goes on: the claims show `unverified`, and the report is marked partial and names `verifier`.

## Q3 Duplicates

The tracker can send the same request twice. The usual cause is a timeout: the first attempt was still running when the client gave up, and the retry carries the same `request_id` and the same bytes.

The duplicate handling is shared by the verifier and the drafter, so it lives in `packages/agentkit/src/agentkit/service.py`. The verifier uses it with one store per process (`services/verifier/main.py:23`):

```python
store = Store()
```

Each request is keyed by its `request_id` and the SHA-256 of its body. `Store.claim` decides what happens (`service.py:54-65`):

```python
    def claim(self, request_id: str, digest: str) -> tuple[str, dict | None]:
        """`new` (caller does the work), `done` (stored answer), `running` or `conflict`."""
        with self._lock:
            if request_id not in self._items:
                self._items[request_id] = (digest, None)
                while len(self._items) > self._max:
                    self._items.popitem(last=False)
                return "new", None
            stored_digest, response = self._items[request_id]
            if stored_digest != digest:
                return "conflict", None
            return ("done", response) if response is not None else ("running", None)
```

### The first copy has finished

The stored `200` response is sent back as it is. There is no new fetch and no model call (`service.py:123-125`):

```python
    state, stored = store.claim(str(req.request_id), body_hash(raw))
    if state == "done":
        return reply(200, stored)
```

Only a `200` is stored (`service.py:164-165`). A `503` from a rate-limited provider or a `500` removes the entry, so a retry can do the work again. The test `test_same_request_twice_costs_nothing` (`services/verifier/tests/test_verifier.py:339`) checks that two identical requests make one fetch and one model call.

### The first copy is still running

The duplicate gets `503` with `Retry-After: 5`, and the work does not start a second time (`service.py:25` and `service.py:130-135`):

```python
RUNNING_RETRY_AFTER = 5
```

```python
    if state == "running":
        return reply(
            503,
            _error("in_progress", "this request_id is still being processed", True),
            {"Retry-After": str(RUNNING_RETRY_AFTER)},
        )
```

The client treats `503` as retryable and waits at least 5 s before the next attempt. If the first copy has finished by then, the next attempt gets the stored answer. The test `test_duplicate_while_running_is_503` (`test_verifier.py:364`) holds the first copy inside its model call, sends the second, and checks for `503`, `Retry-After: 5` and a single model call.

A reused `request_id` with a different body gets `409` and is not retried.

### If the platform restarted the verifier in between

The store is in process memory. The class says so (`service.py:43-44`):

```python
    In process memory only: a new instance starts empty, and a retry that lands there
    does the work again.
```

On Vercel that does not take a crash. A retry can land on a different instance, or the old one can have been shut down. Either way the new instance has an empty store. It sees the `request_id` for the first time and verifies again.

- **Cost:** one more page fetch and one more Groq call for that request.
- **The result is still counted once.** The tracker keeps the first valid `200` it gets for a `request_id` and stops retrying (`verifying.py:192-203`). It stores those verdicts and charges that response's `usage` once (`verifying.py:302-303`). A request that never gets a valid answer is charged its full share instead (`verifying.py:295-297`).
- **What the run's budget misses.** If the first copy kept running on the old instance after the client timed out, its fetch and model call were spent but never reported. The tracker only sees the `usage` of the answer it got.

A shared store such as Redis would close this gap. We left it out on purpose (non-goal in the `add-claim-verifier` design). At 5 requests a day the cost of a repeat is one fetch and one small model call.

## Q4 Injection

TODO

## Q5 Was it worth it

TODO
