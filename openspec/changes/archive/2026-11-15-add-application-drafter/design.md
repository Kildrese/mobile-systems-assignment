## Context

Today Kilian tailors each CV by hand from a Word master, following rules that Cowork wrote down from his past applications (`private/applicant/`: `cv.docx`, `cv_structure.md`, `fact_bank.yaml` with 69 items, 52 approved, `rules.md`, `examples.md`, `form_answers.yaml`). The tracker already publishes each day's top K to Postgres. The verifier (`services/verifier`) set the pattern for a remote worker: its own Vercel project and token, the `agentkit` contract, idempotency, budgets, and model output checked by code.

What `cv_structure.md` establishes, and the design relies on:
- Formatting is direct run formatting on `Normal`. Bullets are `List Paragraph` (`Listenabsatz`) with one of six identical numbering ids. "Clone a sibling bullet and replace only its `w:t`" keeps the layout.
- The experience block is one 21-row table. Row r5 mixes the end of one ipt sub-project and the start of the next.
- A bullet of up to about 105 characters is one line and about 106–210 is two. The page has about 3 free lines, at about 12 pt each.
- LibreOffice renders this file differently from Word and once showed a false second page.

## Goals / Non-Goals

**Goals:** a tailored CV that is always one page, never claims anything outside the approved fact bank, and keeps the master's layout exactly; a cover letter when it's asked for, held to the same fact rules; drafts on the morning they're needed and on demand; personal files only behind the owner's login.

**Non-Goals:** CV layouts other than this master (the layout map is written for it); autofilling forms (`form_answers.yaml` waits for that change); a summary line (the rules forbid one); a model rendering or editing the `.docx`.

## Decisions

**1. The drafter is stateless and gets the profile in each request.** The caller (`app.draft_new` in the daily job, or the API for the button) reads the profile from Postgres and sends it with the posting URL. The drafter has no database, like the verifier. That keeps personal data in one place, and the drafter's only secret is `ANTHROPIC_API_KEY`. The `.docx` is about 20 KB, so the request (about 70 KB with the fact bank) is far under Vercel's 4.5 MB body limit. *Alternative:* the drafter reads Postgres itself. Rejected, because it would be a second service holding the database URL.

**2. The posting text: fetched by the drafter, read from state for the letter decision.** Postgres has no posting text, so the drafter fetches `posting_url` itself through `agentkit.fetch`, the same way the verifier does (including the Ashby JSON-LD fix). `app.draft_new` runs in the tracker job, next to the SQLite state, so it reads the posting text from there to decide whether the posting asks for a cover letter. The button lets the user choose instead.

**3. The layout map is code written for this master, in `agentkit/cv/layout.py`.** It lives in the shared package (with the fact-bank and `checks.yaml` parsers in `agentkit/cv/profile.py`) because the backend validates uploads with it and the drafter builds with it. It finds the four section headings by text, the experience table by the heading before it, each entry by the first bold run of its header row, the ipt sub-projects by their sub-heading text, and the skills lines by their bold labels. First it normalizes row r5 into one row per sub-project, so sub-projects become groups that can move: sub-heading, bullets, spacer. Bullets are made by `deepcopy` of a sibling bullet paragraph with its `w:t` replaced. Fixed parts (name, contact line, headers, Education, Languages, hyperlinks, `customXml`) are never touched. If the map doesn't recognize an uploaded file, the upload is rejected (applicant-profile).

**4. One page by line budget, not by rendering.** `lines(doc)` adds up, over the body's content paragraphs: 1 for each non-bullet paragraph and spacer, as it is in the master, and `ceil(len(text) / 105)` for bullets (1 up to 105 characters, 2 up to 210). The budget is `lines(master) + 1`, where the +1 is a safety margin inside the 3 free lines `cv_structure.md` measured. A test pins `lines(master)` to the value computed for the current `cv.docx` and checks that it's one page. When Kilian changes the master, the test points at the number to re-measure, never at a silent overflow. Over budget, `cut_order` from `checks.yaml` applies one step at a time:
1. shorten wrapping bullets to their shortest approved variant;
2. drop Interests;
3. drop Research, then Thesis;
4. reduce Footpower to its entry line;
5. drop the least relevant ipt sub-project's second bullet;
6. drop the third Advisory bullet.

It never touches the "never cut" ids. The per-entry bounds in `checks.yaml` limit the model's plan; each cut-order step is Kilian's explicit permission to go below them (Footpower to 0, a sub-project to 1, Advisory to 2), so the bounds' minimums are the plan's, not the cuts'. *Alternative:* LibreOffice with Caladea (the same metrics as Cambria) in a container. Rejected: the false-page history, the container, and a slower drafter, for no better answer on a layout this fixed.

**5. `checks.yaml` holds the rules code enforces; `rules.md` stays prose for the model.** The keys are:
- `banned_words` (the AI vocabulary and the Germanisms) and `scope_words` (led, owned, sole, architected, the only, spearheaded, ...);
- `client_names`, and `never_on_cv` (`exp.bumpee.8`, Adex, Gymnasium, King's College, ...);
- `never_cut`, `bullet_bounds` per entry (from `cv_structure.md`'s observed min/max) and `cut_order`;
- `role_types`: per type, the ipt sub-project order, the skills that lead, and whether PROJECTS moves under EDUCATION.

The SWE row doubles as the default. Writing `checks.yaml` from `rules.md` is the first task. Kilian edits these files, never code, to change a rule.

**6. The model plans; code decides.** One call to Claude Sonnet 5.5 (`claude-sonnet-5-5`) through the `anthropic` SDK, with the answer constrained to a JSON schema for the plan (`output_config.format`; Sonnet 5.5 rejects forced `tool_choice`, so structured outputs do the same job). Server-side refusal fallbacks (`fallbacks: "default"`) are on. The system prompt holds `rules.md`, the approved, allowed fact-bank items (id, entry, text, tags) and the role types. These sit in a cached prefix (prompt caching), because they're the same for every draft. The posting arrives as untrusted data. The checks follow the application-drafter spec. A rejected rewording falls back to its source, and an invalid id is dropped and refilled from the entry's next approved item by tag overlap, so the entry keeps its minimum count. The letter is a second call only when asked for, sent back once on a failed check. That's 1–3 calls per draft, so `max_steps: 3`.

**7. Rewording check.** Words are lowercased alphabetic and numeric tokens. "Keeps the source's facts" means every number, date and token starting with a capital in the source (Azure, Kafka, GPT-4, ~250) appears in the rewording, and the rewording has no number or capitalized name that the source lacks. The source's words must make up at least 60 % of the rewording's word set, and its length must stay within 115 % of the source's. Merging two items from the same entry ("may merge two bank bullets about the same entry" in `rules.md`) is allowed when the plan cites both ids, and the check then runs against their union.

**8. Storage and API.** `applicant_profiles(user_id PK, cv_docx bytea, fact_bank text, rules_md text, checks_yaml text, hashes jsonb, viewer_ids uuid[], uploaded_at)` and `application_drafts(user_id, opportunity_id, status, cv_docx bytea, letter_docx bytea, letter_text text, role_type, checks jsonb, model, profile_hash, request_id, created_at, PK (user_id, opportunity_id))`. `POST /api/drafts` calls the drafter synchronously, within the backend function's 300 s limit, with a drafter `time_budget_ms` of 120,000. It writes `pending` first, so a second click gets `409`. Downloads stream the `bytea` with `Content-Disposition`.

**9. Who can spend model tokens.** Only two paths reach the drafter: the backend, for users in `DRAFTING_USERS` (set to `kiliandresse` in the backend's Vercel env), and `app.draft_new` in the daily workflow, which only repository writers and the cron route can start. Both check the allowlist and a per-user cap of 20 drafts per UTC day before calling the drafter. The drafter itself needs `DRAFTER_TOKEN`, which fork pull requests never receive, and the Anthropic console's hard cap is the last limit. Registration stays open, and `nyugrader`'s password stays public. Neither can start a draft.

**10. Sharing is a list on the owner's profile, set from the command line.** It's `viewer_ids` on `applicant_profiles`, set with `python -m app.share_drafts kiliandresse nyugrader` against production, like the migration script. There's one share and no UI.

## Risks / Trade-offs

- **[The line budget drifts from Word's real layout]** → The budget keeps one line of margin inside the 3 measured free lines, the master's count is pinned by a test, and Kilian still exports the PDF from Word (his rule). A draft that Word puts on two pages is a bug in the layout model, fixed by adjusting one constant.
- **[The rewording check is too strict]** → Rejected rewordings fall back to approved text, so the cost is blander wording, not wrong facts. The thresholds are named constants, tuned against `examples.md`'s real past rewordings.
- **[Personal data in transit and at rest]** → TLS only, a per-service token, no file contents in logs or traces, Postgres rows readable by the owner only, and downloads for the owner and named viewers. Drafts shared with `nyugrader` are readable by anyone who has that public test password. That's accepted, and limited to drafts, never the master or the fact bank.
- **[Spend]** → The Anthropic console's hard cap, `max_tokens` per request, and prompt caching of the profile prefix.
- **[The posting changed or closed since the run]** → The drafter's fetch fails: the draft is `partial` with `posting_unreachable`, and "Draft again" works later.

## Migration Plan

1. Land the migration, the API and the drafter, with the drafter project connected to git.
2. Kilian uploads his profile on `/account`, and `python -m app.share_drafts kiliandresse nyugrader` runs once against production.
3. The next daily run drafts the new top-K offers.

Rollback: remove the workflow step, and the button answers `503` while `DRAFTER_URL` is unset.

## Open Questions

None.
