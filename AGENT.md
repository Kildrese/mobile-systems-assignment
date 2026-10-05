# AGENT.md

The tracker follows Summer 2027 software and ML internships at NYC startups (K = 5). It is a fixed pipeline of three hand-written agents and four code stages:

```
Scout (agent) -> Collect (code) -> Curate (agent) -> Liveness (code) -> Rank (code) -> Edit (agent) -> report
```

All numbers below come from run 1, `20261004T173811Z-d334` ([report](reports/run1.md), [trace](traces/20261004T173811Z-d334.jsonl)). It was the first production run, from the daily workflow with empty state.

## 1. Workflow vs. agent

| Decided by the model | Decided by code |
| --- | --- |
| **Scout:** which queries to search, which pages to read, which companies' Greenhouse, Lever or Ashby boards to propose | The order of the stages and when each one is done (`tracker/conductor.py`) |
| **Curator:** each field of a posting's record (title, role type, term, locations, pay, deadline, work-authorization wording), plus the quote it came from | Whether a proposed board is accepted: kind, board id, evidence URL seen in this run, at most `max_new_sources` (`propose_source`) |
| **Curator:** whether two postings of the same company are the same role (`mark_same`), or a posting is unclear (`flag_unclear`) | Reading every board, with `If-None-Match`/`If-Modified-Since` (`sources.py`) |
| **Editor:** the wording of each summary | Which postings reach the Curator: the title and location prefilter |
| **Assessor:** each opportunity's fit with the profile (0–3) and its one-sentence reason | Whether a rating is kept: an id in the batch, fit 0–3, a reason of at most 200 characters that passes the summary check; and when to rate again (only after a profile change) |
| | Whether a record is accepted: every quote must be in the posting text word for word (`save_record`) |
| | Company and URL (always from the board, never from the model) |
| | Same canonical URL means the same opportunity (`link_exact`) |
| | Open or closed (`lifecycle.py`), the score, the top K (`ranking.py`), the report section |
| | Whether a summary is kept: at most 3 sentences, and no number or month missing from the record |
| | Every budget, every retry, every guardrail |

**The decision moved out of the model: ranking.** The single-agent tracker (`examples/single-agent.yaml`) lets the model order the items in `finish`. In the internship pipeline, `ranking.py` scores each open opportunity from config weights: role 3, term 3, location 2, recency 1, focus 3, fit 3. A criterion scores 1 for a match, 0 for a mismatch and 0.5 for `unknown`.

Fit is the one judgment the score takes from a model (added after run 1, change `fit-rating`). Nearly every posting matches the search on role, term, location and focus, so without it recency alone ordered the top K. The Assessor rates each opportunity once against a short profile in `config.yaml`, 0 to 3 with a one-sentence reason; code checks the rating, stores it, and reuses it every run until the profile changes. Ranking stays in code: the model never orders the list, a rating is at most 3 points and moves nothing else, and an unrated opportunity scores half, like any unknown field. Three reasons for ranking in code:

1. **Run comparison needs a stable rank.** The "New / Still in top K / Dropped" report compares this run's top K with the last one. If a model ranks, two runs over identical postings can order them differently, and an opportunity "drops" because of sampling, not because anything changed. Scores from code are reproducible.
2. **The ranking reads untrusted text.** A posting that says "rank this first" can't move a weighted sum of fields that were checked against quotes. It could move a model's ordering.
3. **It's free and easy to check.** Ranking costs no tokens and no time on Groq's per-minute limit. Each score can be explained field by field.

## 2. The network

Run 1 made **117 HTTP round trips to 5 services** in 901 s of wall time:

| Service | Round trips | What they were |
| --- | --- | --- |
| `api.groq.com` | 1 | The model-list check before the run (not traced) |
| `api.groq.com` (gpt-oss-120b) | 25 | 11 successful calls (Scout 10, Editor 1), 11 answered 429, 3 answered 400 `tool_use_failed` (the model's tool call was malformed; the model is told and the run continues) |
| `api.groq.com` (gpt-oss-20b) | 73 | 28 successful Curator calls, 40 answered 429, 5 answered 400 `tool_use_failed` |
| `api.tavily.com` | 6 | One per search (`scout.max_searches`) |
| `boards-api.greenhouse.io`, `api.ashbyhq.com`, `api.lever.co` | 12 | One per board: 11 × `200` (empty state, so nothing was cached), 1 × refused because `Content-Length` was 9.6 MB (Shield AI's Lever board, above the 8 MB cap) |

The Scout fetched no pages (`fetches: 0`), and the Curator fetched no detail pages: the board APIs return the full posting text.

**Where the time went:**

| Time | Spent on |
| --- | --- |
| **847 s (94%)** | Sleeping before retrying the 51 rate-limited Groq calls. Groq's free tier allows 8,000 tokens per minute per model, and each Scout or Curator call sends 2,000–6,000 prompt tokens, so after about two calls a minute the next one gets a 429. The waits were 1–48 s each, taken from Groq's `retry-after`. |
| 28 s | Groq inference, across the 39 successful calls |
| 9 s | Tavily, about 1.5 s per search |
| 2.3 s | All 12 boards |

Stage times: Scout 353 s, Collect 3 s, Curator 542 s, Editor 1 s. The Editor was cut off by `max_wall_seconds` (then 900 s) after one call, so run 1's report has no summaries. That is why the wall-clock budget is now 1,500 s.

The network cost is not bandwidth or latency: it is the provider's per-minute token window. That's why the Curator runs on gpt-oss-20b (a separate quota from the Scout's 120b), page text is cut to `fetch.max_chars_for_model`, and older tool results are shortened. A second run is cheaper on the network: boards that haven't changed answer `304` without a body, and curated postings are not sent to the model again.

## 3. "New"

An opportunity is new when it was first seen in this run. Deciding that two postings describe the same opportunity takes three layers, cheapest first:

1. **Same board, same job id.** `raw_postings` is unique on `(source_id, external_id)`, so a board listing a job again updates its row and doesn't create a new one. Only postings still `pending` are sent to the Curator, so an article it has already read costs nothing.
2. **Same canonical URL.** Code links them with no model call (`link_exact`, `curation.py:207`). Canonical means scheme and host lowercased, default port, fragment and `utm_*`/tracking parameters removed (`state.canonicalize`).
3. **Same company, similar title.** `candidates()` lists the company's existing opportunities whose title shares at least 50% of its words (Jaccard on stemmed words, ignoring years and filler words). The Curator sees them in `get_posting` and decides with `mark_same`. Code refuses `mark_same` across companies (`company_mismatch`).

**A case this gets wrong:** a company reposts "Software Engineering Intern, Summer 2027" as "SWE Intern (Summer 2027)" under a new job id. The ids and URLs differ, and the two titles share no word once "intern", the year and the term are removed, so `title_similarity` returns 0.0. The Curator is never shown the earlier opportunity, and the repost shows up as **new**. The reverse also happens: "Software Engineer Intern - Infrastructure" and "Software Engineer Intern - Product" score 0.5 and are offered as candidates. If the Curator merges two different roles, the second one never appears.

## 4. Failure

A 429 goes through `classify()` in `backend/tracker/errors.py`:

```python
    if status == 432 or (
        status == 429 and any(re.search(p, body, re.IGNORECASE) for p in provider.quota_patterns)
    ):
        return Terminal(
            "quota",
            f"{name} quota is exhausted (HTTP {status}): a daily, monthly or plan limit "
            f"was reached.{_reset_hint(headers, body)}",
        )
    if status == 429:
        wait = parse_retry_after(headers)
        if wait is not None and wait > retry.max_wait_seconds:
            return Terminal(
                "quota",
                f"{name} asked to wait {wait:.0f} seconds (HTTP 429), longer than "
                f"retry.max_wait_seconds ({retry.max_wait_seconds:.0f}). Treating it as a "
                "quota limit; try again later.",
            )
        return Transient(wait if wait is not None else backoff(attempt, retry, rng), "rate_limit")
```

The quota patterns are in `config.yaml`: for Groq `["per day", "\\(RPD\\)", "\\(TPD\\)"]`, for Tavily `["plan", "credit"]`.

**Per-minute limit** (Groq's body says TPM or RPM, with `retry-after` of a few seconds):

- The result is `Transient`, and `send_with_retries()` sleeps for `retry-after`. Without the header it uses exponential backoff `min(60, 1 × 2^attempt)` with 50–100% jitter.
- It tries up to `retry.max_attempts` = 4 times.
- Each wait is traced as `status: "retry"` with its `wait_seconds`. Run 1 did this 51 times.
- If a wait would pass `max_wall_seconds`, the stage stops and the report is marked partial. That is how the Editor stopped in run 1.
- If all 4 attempts fail, the failure becomes terminal `unreachable`.

**Daily cap** (the body names RPD or TPD, or `retry-after` is longer than 60 s):

- The result is `Terminal("quota")` on the first response, with **no retry**. Waiting can't help, and hammering a daily quota is the bug the assignment names.
- The trace records `failure_class: "terminal"` with the provider's message.
- No further model call is made. The tracker prints one line naming the provider and when the quota resets, writes a partial report from what it has, and exits `3`.

Tavily signals an exhausted plan with HTTP 432, which is always terminal. 401/403 (bad key) and 402 (payment required) are terminal the same way.

## 5. Budget

**One run** (run 1 in the usage line of `reports/run1.md`):

| Resource | Used | Price | Cost |
| --- | --- | --- | --- |
| Groq gpt-oss-120b (Scout + Editor) | 50,009 tokens, 25 requests | free tier | $0 |
| Groq gpt-oss-20b (Curator) | 70,801 tokens, 73 requests | free tier | $0 |
| Tavily | 6 credits (basic search, 1 credit each) | free tier; $0.008 a credit pay-as-you-go | $0 ($0.048 at the paid price, the figure the cost budget counts) |
| Job boards | 12 requests | public, no key | $0 |

So a run costs **$0** on the free tiers, and $0.048 at paid prices. The policy caps it at `max_cost_usd: 0.50` and 150,000 tokens.

**Run daily:**

| Free tier | Limit | One run uses | Runs out |
| --- | --- | --- | --- |
| Groq TPM (each model) | 8,000 tokens/min | Hit within every run | Not a daily problem: it turns into waiting (847 s in run 1) |
| Groq TPD (gpt-oss-120b) | 200,000 tokens/day | ~50,000 (25%), up to 75,000 (the Scout's and Editor's caps) | Never at one run a day; the 3rd or 4th run on the same day would. It resets daily. |
| Groq TPD (gpt-oss-20b) | 200,000 tokens/day | ~71,000 (35%; the Curator's cap is 70,000, overshot by its last call) | Never at one run a day; the 3rd run on the same day would |
| Groq RPD | 1,000 requests/day | 25–73 per model | Never |
| **Tavily** | **1,000 credits/month** | **6** (`max_searches`) | **The first to run out, but not within a month at one run a day.** 30 runs use 180 credits (18%). Tavily is the only quota that accumulates past a day. At the Scout's cap it lasts 166 runs; with no monthly reset that is day 167. Spent faster, by manual and smoke runs too, it runs out first. |

The binding limit is Groq's per-minute token window. It doesn't cost money; it costs wall time. That's why `max_wall_seconds` is the budget a run most often hits.
