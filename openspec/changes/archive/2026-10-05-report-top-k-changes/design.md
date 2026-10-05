# Design

## Context

`report.sections(store, run_id)` is the one place that sorts opportunities into sections. Both the Markdown report and `app.publish_report` use it. It reads `ranks(run_id)` for the current rank and top-K mark, and each opportunity's `status`, `first_seen_run` and `closed_run`. Ranks are kept for every run (`ranks` is keyed by `(run_id, opportunity_id)`), so the previous run's top K is already in state.

## Goals / Non-Goals

**Goals:**
- The report reads New since last run, Still in top K, Dropped, in that order, as the assignment asks.
- "Dropped" means leaving the top K, which includes being outranked while still open.
- Nothing listed today disappears from the report.

**Non-Goals:**
- Changing how ranks or the top K are computed.
- A history across more than two runs. That belongs to `show-run-history`.

## Decisions

### D1. "Last run" is the previous finished run that has ranks
The comparison is with the newest earlier run in `runs` that has an end time and rows in `ranks`. A run that failed before Rank (for example a terminal failure in the Scout) has no ranks and is skipped, so a failed day does not empty the next day's Still in top K. If no such run exists, it is a first run.

*Alternative:* the immediately previous run, whatever its outcome. After a failed run, every top-K opportunity would show as entering the top K again, which is noise.

### D2. Section rules, applied in order
For each opportunity, take the first rule that matches:

1. Open and `first_seen_run` is this run → **New since last run**. A new opportunity in the top K is marked top K, as now.
2. In this run's top K → **Still in top K**, with `previous_rank`. One with no previous top-K mark is "entered the top K".
3. In the last run's top K and not in this one → **Dropped**. The reason is `closed` if its status is closed (with the evidence), otherwise `outranked` (with its new rank).
4. Closed with `closed_run` this run → **Dropped**, reason `closed`.
5. Open → **Also open**.

Everything else (closed in an earlier run) is not listed, as now. These rules put each opportunity in at most one section.

*Alternative:* keep closed opportunities that were never in the top K in their own Closed section. That makes five sections. The assignment's Dropped already covers "no longer reported", so closed opportunities go there with their reason.

### D3. An opportunity reopened into the top K
An opportunity that reopens keeps its first-seen run (opportunity-lifecycle), so it is not new. If it ranks in the top K it goes under Still in top K, marked "entered the top K". That describes what happened from the reader's side.

### D4. Published rows carry the section and why
`internship_offers.section` takes `new`, `top_k`, `dropped` or `open`. It gets two new nullable columns:

- `previous_rank`: the rank in the last run, if it had one.
- `drop_reason`: `closed` or `outranked`, for dropped rows only.

`status_evidence` still carries the closing evidence. The migration updates old `closed` rows to `dropped` with `drop_reason = 'closed'`, so the `/latest` endpoint never returns a section the page doesn't know. Old `open` rows stay `open`, because their top-K mark was never split out. Every run published after this change uses the new values.

## Risks / Trade-offs

- **Old published runs read slightly differently.** Their former Still open rows appear under Also open, including the ones that were top K. Only the latest run is shown, and the next daily run replaces it, so this lasts one day at most.
- **Outranked items churn.** If two opportunities have close scores, one can move in and out of the top K from day to day. That is a fair report of a deterministic ranking, and Dropped shows the new rank, so the reader can see the drop was by a little.
