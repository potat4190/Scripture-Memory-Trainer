# Decision Log — Scripture Memory Trainer

Every place where `B_Rules` (or the supplied data) could be read more than one way,
and the reading this build committed to. Per the challenge brief, `B_Rules` is
authoritative over intuition; this file records where intuition was set aside and
where the data itself forced a call.

Format: one entry per decision. `Status` is `Decided`, `Open`, or `Superseded`.

**Source of truth:** the challenge workbook, `Frontier Commons Fellowship FA26 —
Build Lane Challenge Data.xlsx`. It is **not tracked in this repo** — keep your
own copy in `docs/`. `seed/cards.json` and both `tests/fixtures/*.json` are
generated from it by `tools/extract_fixtures.py`, and those generated files *are*
tracked, so the repo stands on its own. Re-running the script against the
workbook must leave them unchanged.

---

## D1 — `B_Check_Answers` has 21 rows, not 22

- **Status:** Decided (data constraint, not a choice) — **confirmed against the workbook**
- **Context:** The checklist and the `B_Check_Answers` preamble both say 22 cases.
  The sheet itself holds **21** data rows (rows 6–26 under the header at row 5).
  This was first seen in a Markdown export and has since been re-confirmed by
  reading the `.xlsx` directly, so it is a property of the workbook, not an
  artifact of the export.
- **Decision:** Extract the 21 rows that exist into
  `tests/fixtures/check_answers.json` and treat 21 as the real count. There is no
  22nd case to represent.
- **Consequence:** Any "X of 22" phrasing from the checklist maps to 21 here.
  README states this. `tests/test_fixtures.py` pins the count at 21.

## D2 — `B_Cards` stored verbatim; Unicode normalization happens at compare time

- **Status:** Decided — **confirmed against the workbook**
- **Context:** The Arabic verses in `B_Cards` are **not** in any Unicode normal
  form — combining marks appear in source order, not canonical (`NFC`) order. An
  earlier hand-made `seed/cards.json` had silently `NFC`-normalized them.
  Re-extracting from the `.xlsx` reproduces the current `seed/cards.json`
  byte-for-byte, so all 32 cards now match their source cells exactly.
- **Decision:** `seed/cards.json` now holds the card text **exactly** as it
  appears in the workbook cell — no normalization applied at extraction. The
  normalizer (Phase 1) applies `NFC` to both card and input as its first step,
  so runtime comparison is unaffected.
- **Rationale:** One source of truth, no invisible transforms between the
  workbook and the seed file. Matches the checklist's "copy verbatim, do not
  retype" instruction for the CHECK inputs; applied to the cards too.

## D3 — `check_answers` case 14 kept in decomposed form on purpose

- **Status:** Decided
- **Context:** Case 14 (John 3:16, ar — "Alef wasla written as plain alef") is
  the one input string in the fixture that is not `NFC`. That is the point of the
  case: the exact codepoints are what it tests.
- **Decision:** Preserve it byte-for-byte from the source. Do not "clean" the
  fixture.

## D4 — Leviticus 19:34 outer-whitespace case: padding recovered from the workbook

- **Status:** **Superseded** — the earlier reading was wrong, and is now fixed
- **Original context:** Case 8 (Leviticus 19:34, en — "Trailing and leading
  whitespace") carries leading and trailing spaces. Markdown tables cannot
  represent cell-edge whitespace, so the Markdown export this fixture was first
  built from had dropped it. At the time that looked unrecoverable, and the
  fixture stored the trimmed string.
- **Correction:** The `.xlsx` preserves the padding — the cell holds three
  leading and three trailing spaces (190 characters, versus the 184 the export
  gave). `tools/extract_fixtures.py` now reads the workbook, so the fixture
  carries the real string.
- **Decision:** Extract from the `.xlsx`, never from a Markdown rendering of it.
  `tests/test_fixtures.py::test_outer_whitespace_case_keeps_its_padding` fails if
  the padding is ever lost again.
- **Note:** The verdict was **Correct** either way, since trimming a trimmed
  string is a no-op — so this never masked a checker bug. But the case existed
  specifically to exercise trimming, and with the padding gone it was not
  testing anything.

## D5 — Matthew 28:19 (en): two expected verdicts disagree with `B_Cards`

- **Status:** Decided — documented, not worked around
- **Context:** Confirmed by direct computation against the KJV text in `B_Cards`:

  | Case | Workbook expects | Value computed from `B_Cards` |
  |---|---|---|
  | Curly apostrophe, `Father's` | 1 word wrong at position **16** | position **15** |
  | Empty string | 0 of **22** words matched | 0 of **24** words matched |

  Both are consistent with the workbook's expected values having been computed
  against a 22-word text, while `B_Cards` supplies 24 words.
- **Decision:** Follow `B_Rules` and the `B_Cards` text as authoritative. Report
  our computed counts. Do **not** tune the checker to reproduce 22/16 — the
  checklist explicitly warns that doing so breaks the cases that currently pass.
  These two are expected failures; README lists them with the computed numbers.

## D6 — Surplus input beyond the card length

- **Status:** Decided
- **Context:** The checklist leaves "surplus input beyond card length" as an
  explicit open decision. If the user types more units than the card has, those
  extra units have nothing on the card to compare against.
- **Decision:** `checker.check()` reports surplus as its own two facts —
  `surplus_count` and `surplus_from` (1-based) — and it does **not** feed into
  `matched`, `total`, `mismatch_positions`, or `status`. Those four are always
  computed from the **card's** length. Surplus with at least one earlier match is
  `partial`; the verse still isn't an exact match, so it is never `correct`.

## D7 — `Verdict` carries three fields beyond the checklist's minimum

- **Status:** Decided
- **Context:** The checklist names `status, matched, total, mismatch_positions[],
  missing_from, unit`. `B_Rules` ("report the count **and** the first absent
  position") and the surplus decision above need slightly more.
- **Decision:** Add `missing_count` (the count `missing_from` alone doesn't
  give), plus `surplus_count` / `surplus_from` (see D6). Additive only; the
  checklist's six fields keep their exact meaning.

## D8 — One `Card` type in Phase 1, not `Card` + `CardState`

- **Status:** Decided (revisit in Phase 3)
- **Context:** Phase 3 calls for separate `Card` and `CardState` SQLModel tables,
  with state split out for sync bookkeeping (`updated_at`, `deleted`).
- **Decision:** With no database in Phase 1, `models.Card` is a single dataclass
  carrying `box` and `due_date` directly. `queue.build_queue()` needs exactly
  those two plus `reference` / `language`. When Phase 3 adds the DB, this splits
  into the two tables the checklist describes.

## D9 — `storage.py` was a deliberate exception to Phase 1's "zero I/O"

- **Status:** **Superseded by Phase 3** — the module has been removed
- **Original decision:** `src/scripture_memory_trainer/storage.py` did plain
  JSON file I/O (no framework, no DB driver — so the Phase 1 *exit criterion*
  still held), kept strictly separate from the five pure files. It existed to
  back a future terminal driver and to prototype the Phase 3 seed loader and
  export. Nothing in the pure modules imported it.
- **Phase 2 addendum (kept for the record):** covering it turned up a real bug.
  `save_state` wrote `"due_date": null` for a card that was never scheduled, and
  `load_state` passed that straight to `date.fromisoformat`, which raises
  `TypeError`. The same class of bug then appeared for real in the Phase 3 seed
  loader — see D18.
- **Why it is gone:** Phase 3 shipped the thing it was standing in for.
  `seed.py` is the real seed loader, `GET /api/export` and `POST /api/import`
  are the real dump and restore, and `database.py` owns persistence. Keeping a
  second, parallel state format would mean two ways to save that could disagree.
  Removed along with `tests/test_storage.py`.

## D10 — zh traditional-vs-simplified is a **third** expected failure

- **Status:** Decided — documented, not worked around
- **Context:** `B_Check_Answers` case 10 (John 3:16, zh — traditional input
  against a simplified card) expects **Incorrect**. Running the checker gives
  **Partial — 23 of 30 characters matched**, 7 differing
  (爱/愛, 将/將, 独/獨, 赐/賜, 给/給, 们/們, 灭/滅).
- **Decision:** This is rules-correct and stays. `B_Rules` says script conversion
  must **not** be performed and "every differing character counts"; the checklist
  says `matched == 0 → Incorrect, otherwise Partial`. These two verses happen to
  share 23 of 30 characters, so the rules produce Partial, not a zero-match
  Incorrect. Per the checklist's own instruction not to tune the checker to
  reproduce workbook artifacts, this is documented — a third known failure
  alongside the two in D5. README must list all three.

---

## D11 — Phase 2 pins the three known deviations with strict `xfail`

- **Status:** Decided
- **Context:** D5 (×2) and D10 record three CHECK cases where the computed
  verdict disagrees with `B_Check_Answers`. A plain "expected failure" that
  someone later "fixes" would go green silently — which is precisely the
  outcome the checklist warns against.
- **Decision:** `tests/test_normalizer.py` marks them
  `pytest.mark.xfail(..., strict=True)`, and splits status from counts so each
  deviation is pinned where it actually occurs:
  - cases **6** and **7** — counts only; their *status* assertions pass normally
  - case **10** — status only; it states no numbers to check
  With `strict=True`, tuning the checker to reproduce the workbook's 22/16 turns
  these into failures instead of quiet passes.
- **Also:** expected values are **parsed from the workbook's own verdict prose**
  (`"7 of 10 words matched; 3 missing from position 8"`), not retyped into the
  tests. Same reasoning as extracting the fixtures rather than hand-writing
  them: one source of truth. `test_the_prose_parser_actually_extracts_numbers`
  guards the parser, so a regex that silently stopped matching cannot make the
  numeric assertions vacuous.

## D12 — "Exact match" is decided on units, not on the normalized string

- **Status:** Decided — **bug found and fixed in Phase 2**
- **Context:** `checker.check()` short-circuits to `Correct` when the answer
  matches the card. It originally tested that with `norm_card == norm_input`,
  comparing the two **normalized strings**, while every other number in the
  `Verdict` was computed from the **split unit lists**.
- **The bug:** those two views agree for `en` / `ar` / `hi`, because `str.split()`
  already discards the whitespace `normalize` has collapsed. They disagree for
  `zh`, where the unit is the character and `_split` drops spaces outright. So a
  Chinese verse recited perfectly but typed with spaces between the characters
  came back **Partial — 30 of 30 characters matched**, with no mismatch
  positions, nothing missing and nothing surplus: a verdict the UI cannot
  explain. All 8 Chinese cards were affected.
- **Decision:** decide exactness on `card_units == input_units`, the same list
  everything else is derived from. For the word languages this is provably
  equivalent; for `zh` it makes spacing a non-unit, which is what "character
  split" means and what the checklist's `exact match → Correct` requires.
- **Why the suite missed it:** the "a Partial must report something actionable"
  assertion existed, but only ran over the 21 CHECK cases, none of which vary
  `zh` spacing. It is now also a Hypothesis property. A second property,
  `test_spacing_is_not_a_unit_for_character_languages`, builds the answer *from*
  the card — drawing card and answer independently never produces a
  spacing-only variant, so the generic property alone would not have found this.
- **Consequence:** none of the 21 CHECK cases change.
  `reports/check-report.json` is byte-identical before and after, and the three
  known deviations (D5 ×2, D10) are untouched.

---

## Phase 2 — failing CHECK cases

Generated by the test suite, not by hand. Running `pytest` writes
`reports/check-report.json` (machine-readable) and `reports/check-report.md`;
the table below is that file's contents. The test
`test_check_report_is_written` fails if the set of deviating case ids ever
changes, so this list cannot silently drift out of date.

**18 of 21 CHECK cases agree with the workbook. Failing case ids: 6, 7, 10.**

| Case | Reference | Lang | Change | Workbook expects | Computed | Deviation |
|---|---|---|---|---|---|---|
| 6 | Matthew 28:19 | en | Curly apostrophe and quotes | Partial. Curly apostrophe normalises to straight, but Father’s is still 1 word wrong at position 16. | partial — 23 of 24 words matched, wrong at [15] | wrong position: workbook 16, computed [15] |
| 7 | Matthew 28:19 | en | Empty string | Incorrect. 0 of 22 words matched. | incorrect — 0 of 24 words matched, 24 missing from 1 | total: workbook 22, computed 24 |
| 10 | John 3:16 | zh | Traditional characters instead of simplified | Incorrect. Script conversion is not performed. Every differing character counts. | partial — 23 of 30 chars matched, wrong at [2, 7, 10, 13, 14, 16, 25] | status: workbook says incorrect, computed partial |

All three are the deviations already argued in D5 and D10 — no new ones. The
schedule side has none: 8 of 8 traces match exactly, step by step, including
every intermediate box, interval and due date.

---

# Phase 3 — Backend

## D13 — SQLModel tables live in `tables.py`, not `models.py`

- **Status:** Decided — supersedes the shape D8 anticipated
- **Context:** The Phase 3 checklist says "`models.py` — SQLModel tables". But
  `models.py` already holds the pure `Card` dataclass, and `queue.py` — one of
  the five Phase 1 modules whose exit criterion is *"no imports of FastAPI or
  any DB driver"* — imports it. Following the checklist literally would pull
  SQLAlchemy into the pure logic through that import and quietly break Phase 1.
- **Decision:** the four SQLModel tables go in `tables.py`. `models.Card` stays
  a plain dataclass and remains the type the pure logic speaks; the API layer
  converts between the two. The checklist's *intent* — real tables with real
  sync columns — is met; only the filename differs, and for a reason.
- **Enforcement:** `tests/test_phase1_guards.py` now checks the purity of all
  six pure modules two ways — statically (parsing their imports) and by
  importing each in a **subprocess**, since by that point the rest of the suite
  has already loaded SQLModel into the test interpreter and an in-process check
  would pass vacuously. Reintroducing the import fails 7 tests.

## D14 — `DATABASE_URL`, defaulting to local SQLite

- **Status:** Decided
- **Context:** Phase 3 needs a database now; Phase 5 needs Supabase Postgres.
  `psycopg` is already a dependency.
- **Decision:** one `DATABASE_URL` environment variable, read in
  `database.py`, defaulting to a SQLite file in the repo root. Clone, `uv sync`,
  `alembic upgrade head` — no server, no configuration. Phase 5 repoints the
  same variable and nothing else changes, because every query goes through
  SQLModel. `alembic.ini`'s `sqlalchemy.url` is deliberately left **empty** and
  `alembic/env.py` reads the same function, so there is one source of truth and
  no credentials in a tracked file.
- **Consequence:** migrations must run on both backends, so
  `render_as_batch=True` is set — SQLite cannot `ALTER` a column in place.

## D15 — Sync timestamps use real time; only *scheduling* is travellable

- **Status:** Decided
- **Context:** Every table carries `updated_at` for last-write-wins sync. The
  app's whole premise is a clock the user can move by 60 days.
- **Decision:** `updated_at` comes from `clock.real_now()`, which returns real
  UTC and **ignores** the offset. If sync timestamps followed the app clock, a
  user who travelled forward would write rows that win every merge until the
  real date caught up — silent, and unrecoverable without hand-editing. What
  *is* travellable is `ReviewLog.reviewed_on`, the app date a review happened,
  so time travel stays visible in the history.
- **Note:** `real_now()` lives in `clock.py` so the checklist's "no
  `datetime.now()` outside `clock.py`" rule stays literally true — and
  `test_only_clock_reaches_for_the_real_time` now enforces that by parsing
  every module in `src/`, rather than relying on someone remembering to grep.
- **Follow-on bug this surfaced:** SQLite has no timezone type, so an aware
  datetime went in and a **naive** one came back — making `stored > real_now()`
  raise `TypeError`, which is exactly the comparison Phase 5's merge is built
  on. `tables.UTCDateTime` normalizes both directions so SQLite and Postgres
  behave identically. Pinned by
  `tests/test_tables.py::test_timestamps_round_trip_as_aware_utc`.

## D16 — Re-seeding never touches study state

- **Status:** Decided
- **Context:** The checklist asks for a seed loader that imports
  `seed/cards.json` "idempotently".
- **Decision:** card **content** is upserted, so a corrected verse reaches an
  existing install; `CardState` is only ever *created*, never overwritten, so a
  re-seed cannot knock a card the user has been studying back to box 0. A row
  whose content is byte-identical is left completely alone — bumping its
  `updated_at` would manufacture sync traffic for a no-op, since Phase 5 pushes
  rows where `updated_at > last_sync_at`.

---

## D17 — `POST /api/import` merges last-write-wins; it does not replace

- **Status:** Decided
- **Context:** "Restore from JSON" can mean two things: overwrite everything
  with the file, or merge the file into what is there. Overwriting is simpler
  and is what most export/import pairs do.
- **Decision:** merge, row by row, last-write-wins on `updated_at`. An incoming
  row applies only if it is **strictly newer** than the stored one; equal
  timestamps and missing timestamps lose.
- **Why:** restoring a Tuesday backup onto a device that has studied since must
  not delete Wednesday's work — that is data loss dressed as a feature. Strict
  `>` also makes import idempotent: re-importing the same file reports all rows
  skipped and changes nothing, so a nervous user can press the button twice.
  It is the same merge rule Phase 5's sync needs, written once.
- **Two corrections found while testing:**
  1. Restoring into an **empty** database silently dropped the clock offset.
     `get_app_state()` created the default `AppState` row on the way in, stamped
     it with `real_now()`, and that fresh timestamp then beat the incoming one.
     Fixed by reading the row with `session.get` and creating it *from* the
     payload when it is absent.
  2. A `card_state` or `review_log` whose `card` is in neither the payload nor
     the database violates the foreign key. SQLite does not enforce it by
     default and Postgres does, so this would have passed every local test and
     500ed in production. Orphans are now skipped and counted on both backends.
- **Also:** an export whose `version` is newer than this build understands is
  rejected rather than partially applied.

## D18 — A seeded card is due immediately, never null

- **Status:** Decided — **bug found and fixed**
- **Context:** `seed_cards` created each `CardState` with SQLModel's defaults,
  which left `due_date` null.
- **The bug:** `build_queue` filters on `due_date <= today`, and null satisfies
  nothing. A freshly seeded install therefore showed **an empty queue forever**
  — every card present, none reviewable. `GET /api/health` reported 32 cards and
  32 states, so nothing looked wrong.
- **Why the suite missed it:** the API test fixture seeded the cards and then
  set their due dates itself before handing the client over. It was testing a
  database no user would ever have. The fixture now seeds and does nothing else,
  and `test_a_freshly_seeded_install_is_reviewable_immediately` asserts the
  queue is non-empty straight after a seed.
- **Decision:** a new `CardState` is created at box 0, due on the **app** date
  (so a seed run while time-travelled behaves consistently). Re-seeding still
  never touches an existing state — D16 is unchanged.

---

# Phase 4 — Frontend

## D19 — Two things are duplicated in the browser, and both are pinned by tests

- **Status:** Decided
- **Context:** `web/index.html` is one static file with no build step, so it
  cannot import from `src/`. Two pieces of backend logic have to exist there
  as well:
  1. **The Leitner intervals.** A grade button has to say *"Good — tomorrow,
     Aug 29"* before it is pressed, which means computing the next due date
     client-side. Asking the server for four hypothetical futures on every card
     would be four round trips to render a button row.
  2. **The unit split.** The verdict reports mismatches as positions — "wrong at
     15" — and the page has to highlight the fifteenth *unit* of the verse. That
     means splitting the text the same way the server did.
- **Decision:** duplicate both, and make the duplication impossible to break
  silently. `tests/test_web_contract.py` parses `web/index.html` and fails if
  the JavaScript `INTERVALS`, `MAX_BOX` or cap disagree with `scheduler.py` and
  `queue.py`.
- **Why the split is safe to simplify:** the client strips punctuation and
  collapses whitespace but skips the language-specific folding (harakat, nukta,
  alef forms, case), because none of those rules change *how many* units there
  are — they only change what the units contain. That invariant is asserted for
  all 32 cards, both directly and by comparing the client and server splits card
  by card. Add a card that breaks it and the suite says so.

## D20 — The frontend is served by the API, from the same origin

- **Status:** Decided
- **Context:** A static page and an API can be deployed separately or together.
- **Decision:** FastAPI mounts `web/` at `/`, after every real route, so `/api/*`
  and `/docs` still match first (a test asserts the mount does not shadow them).
- **Why:** a separate static host would need CORS, credentials on every fetch,
  and a second deploy target. Same origin removes all three, and Phase 6 has one
  thing to ship instead of two.

## D21 — Offline is a read of the local mirror, not a write queue

- **Status:** Decided (revisit in Phase 5)
- **Context:** Phase 4 asks for Dexie mirroring the backend tables; Phase 5 is
  where sync actually lands.
- **Decision:** every load hydrates Dexie from `GET /api/export` — one request
  that returns exactly the four tables. When the network is up the server is the
  source of truth for the queue; when it is down the page rebuilds the queue
  from the mirror using the same rules and says so in a banner. Grades are not
  queued for later: the banner states plainly that they will not be saved until
  the connection is back, rather than accepting work it might lose.
- **Also:** a blocked CDN must not blank the page. Dexie backs only the mirror,
  so when it fails to load the app falls back to an in-memory stand-in with the
  same small surface and keeps working online.

---

## Open

- **O1 — `again`-requeued card vs. the daily cap of 20.** `FLOWCHART.md` diagram
  7 flags this. `build_queue()` itself already behaves the simple way — it only
  knows `due_date <= today`, sorts, and caps at 20, so a same-day requeue is just
  another due card on the next build. What's still undecided is whether the
  *session driver* (not yet written) re-inserts an `again` card within the
  current session regardless of the cap. Decide when that driver exists.

- **O2 — Per-user ownership, and whether the 32 verses are shared.** Phase 5
  needs every row to have an owner, which is more than an added column: today
  `CardState` is keyed on `card_id` alone and `AppState` is a single pinned row,
  so a second account collides on the first and shares the clock offset on the
  second. The intended answer is **shared verses** — `card.user_id` nullable,
  NULL meaning global reference data — which leaves `card`'s primary key alone
  and still allows user-authored verses later. It carries one trap: a new
  account has cards but no `CardState`, and `build_queue` treats a null due date
  as not due, so the queue would be empty. `service.to_domain()` should
  substitute the app date for missing state rather than the queue changing its
  rule. Written up in full in `docs/DEPLOYMENT.md` section 5.4. Decide by
  implementing it; move to a numbered decision then.

---

## Consistency audit against the workbook — 2026-08-27

All four Option-B tabs (`B_Cards`, `B_Rules`, `B_Check_Schedule`,
`B_Check_Answers`) were read straight out of the `.xlsx` and compared against
this repo. Phase 2–6 items were out of scope.

| Check | Result |
|---|---|
| `B_Rules` vs. the implemented rules | consistent — intervals, grade effects, cap, sort order, normalization list, partial-credit split, and text sources all match |
| `B_Cards` (32 rows) vs. `seed/cards.json` | byte-identical, all 5 fields |
| `B_Check_Schedule` (8 traces) vs. `check_schedule.json` | identical |
| `B_Check_Answers` (21 rows) vs. `check_answers.json` | **1 difference — case 8 whitespace, fixed. See D4** |
| Scheduler vs. the 8 traces | 8/8 exact |
| Checker vs. the 21 cases | 18/21 exact; 3 known (D5 ×2, D10) |

Every numeric claim the workbook states in prose — "1 of 9 words wrong at
position 5", "7 of 10 words matched; 3 missing from position 8", "1 word wrong at
position 2" — was checked against the computed `Verdict`, not just the
correct/partial/incorrect label. All match except the three in D5 and D10.

At the status level alone (correct / partial / incorrect) the checker agrees on
20 of 21; only D10 disagrees on the label. D5's two cases carry the right label
and the wrong counts.
