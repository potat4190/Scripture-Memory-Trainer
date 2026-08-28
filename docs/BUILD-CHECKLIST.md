# Build Checklist — Scripture Memory Trainer

Sequenced so that the hardest, most graded work happens first and everything after it is scaffolding. Check items off in order; each phase ends at a point where you could stop and still have something defensible.

---

## Phase 0 — Setup and spec extraction

- [x] `uv init` and create the project skeleton
- [x] `uv add fastapi pydantic sqlmodel alembic regex "psycopg[binary]" python-dotenv`
- [x] `uv add --dev pytest pytest-cov hypothesis ruff mypy "uvicorn[standard]" pre-commit`
- [x] `git init`, push to GitHub, make the repo **public** (free Actions minutes)
- [x] Add `.gitignore`, `ruff` config in `pyproject.toml`, `.pre-commit-config.yaml`
- [x] **Extract `B_Cards` to `seed/cards.json`** — 32 rows, fields: `card_id`, `reference`, `language`, `direction`, `text`
- [x] **Extract `B_Check_Schedule` to `tests/fixtures/check_schedule.json`** — 8 traces, fields: `grades[]`, `expected_box`, `expected_due`
- [x] **Extract `B_Check_Answers` to `tests/fixtures/check_answers.json`** — 22 cases, fields: `reference`, `lang`, `input`, `expected_verdict`
- [x] Copy input strings from the source cells verbatim; do **not** retype them. Retyping destroys the exact codepoints the cases test.
- [x] Create `docs/DECISIONS.md` with an empty decision log

**Exit criterion:** the fixtures exist and load. You have not written a line of logic yet, and that is correct.

---

## Phase 1 — Pure logic, zero I/O

Nothing in this phase touches a database, a network, or a framework. Every function is a pure function of its arguments. This is what makes it testable and what makes the fixtures meaningful.

### `src/clock.py`

- [x] `Clock` class holding `offset_days: int`
- [x] `Clock.today() -> date` returns `date.today() + timedelta(days=offset_days)`
- [x] **Grep the whole repo for `date.today()` and `datetime.now()`.** Every call outside `clock.py` is a bug.

### `src/scheduler.py`

- [x] `INTERVALS = {0:0, 1:1, 2:3, 3:7, 4:21, 5:60}`
- [x] `apply_grade(box, grade) -> (new_box, interval_days)`
- [x] `again` → box 0, interval 0
- [x] `hard` → box unchanged, `max(1, INTERVALS[box] * 60 // 100)` — floor, then floor at 1
- [x] `good` → `min(5, box + 1)`, interval of the **new** box
- [x] `easy` → `min(5, box + 2)`, interval of the **new** box
- [x] `next_due(review_date, interval) -> date`

### `src/normalizer.py`

- [x] `import regex as re` — **not** stdlib `re`
- [x] NFC-normalize input first
- [x] Curly quotes → straight: U+2018 U+2019 U+201C U+201D
- [x] Full-width → ASCII: U+FF0C → `,`, U+FF1B → `;`
- [x] Arabic only: strip U+064B–U+0652, U+0640, U+0670
- [x] Arabic only: U+0671 → U+0627, U+0649 → U+064A
- [x] Hindi only: strip U+093C nukta
- [x] Chinese: **no** simplified/traditional conversion — assert this in a test so nobody "fixes" it later
- [x] Strip all punctuation with `re.sub(r"\p{P}+", "", s)`
- [x] Collapse whitespace runs, trim ends
- [x] `.casefold()`, not `.lower()`

### `src/checker.py`

- [x] `check(card_text, user_input, lang) -> Verdict`
- [x] `Verdict` dataclass: `status`, `matched`, `total`, `mismatch_positions[]`, `missing_from`, `unit` (`words` or `chars`)
- [x] Word split for `en`, `ar`, `hi`; character split for `zh`
- [x] Positional comparison, 1-based positions in the output
- [x] Missing tail: report count and first absent position
- [x] Surplus input beyond card length: decide the behaviour, log it in `DECISIONS.md`
- [x] `matched == 0` → Incorrect; exact match → Correct; otherwise Partial

### `src/queue.py`

- [x] `build_queue(cards, today, lang_filter) -> list[Card]`
- [x] Filter `due_date <= today`
- [x] Sort key: `(due_date, box, reference)` — plain **string** sort on reference, not canonical book order
- [x] Cap at 20
- [x] Return the pre-cap total so the UI can show "20 of 47 due"

**Exit criterion:** five modules, no imports of FastAPI or any DB driver.

---

## Phase 2 — Prove the logic

- [x] `test_scheduler.py` parametrized over all 8 traces in `check_schedule.json`
- [x] `test_normalizer.py` parametrized over all 22 cases in `check_answers.json`
- [x] `test_queue.py`: cap of 20, all three sort keys, the alphabetical-not-canonical ordering
- [x] `test_clock.py`: offset arithmetic, and that advancing the clock changes the queue
- [x] Hypothesis: `normalize(normalize(x)) == normalize(x)` for all inputs, all languages
- [x] Hypothesis: normalization never increases word count
- [x] Hypothesis: box always lands in 0–5 for any grade sequence
- [x] Make the suite emit a machine-readable list of failing CHECK cases (`pytest --tb=no -q` plus a small reporter)
- [x] Paste that list into `DECISIONS.md`

### Expect two failures on Matthew 28:19

Both were confirmed by direct computation against the text in `B_Cards`:

| Case | Workbook expects | Correct value from B_Cards |
|---|---|---|
| Curly apostrophe, `Father's` | 1 word wrong at position **16** | position **15** |
| Empty string | 0 of **22** words matched | 0 of **24** words matched |

Every other spot-checked case matches exactly. Do **not** tune your checker to reproduce 22/16 — that would break the cases that currently pass. Document it and move on.

**Exit criterion:** all fixtures pass except the two above, and you can name every failure.

---

## Phase 3 — Backend

- [x] SQLModel tables: `Card`, `CardState` (box, due_date, updated_at), `ReviewLog`, `AppState` (clock offset) — in `tables.py`, not `models.py`; see DECISIONS D13
- [x] Every table gets `updated_at: datetime` and `deleted: bool` for sync
- [x] `alembic init`, generate and apply the first migration
- [x] Seed loader that imports `seed/cards.json` idempotently
- [x] `GET /api/cards` — list with filters
- [x] `GET /api/queue` — today's queue plus the pre-cap total
- [x] `POST /api/review` — body `{card_id, grade, answer_text?}`, returns verdict plus new box and due date
- [x] `POST /api/check` — verdict only, no state change (useful for the UI and for demos)
- [x] `GET/POST /api/clock` — read and set the offset
- [x] `GET /api/export` — full JSON dump
- [x] `POST /api/import` — restore from JSON
- [x] Confirm the auto-generated docs render at `/docs`

**Where this stands:** complete. Eight endpoints (the seven above plus
`GET /api/health`), 46 endpoint tests, and the full flow verified against a
running server — seed, queue, check, review, travel 60 days, export, restore.
Two bugs were found and fixed on the way: seeded cards had a null `due_date` so
the queue was empty forever (D18), and a restore into an empty database dropped
the clock offset (D17).

**Exit criterion:** the full flow works through `/docs` with no frontend at all.

---

## Phase 4 — Frontend

- [x] `index.html` with Alpine.js and Dexie from CDN
- [x] Google Fonts: Noto Sans, Noto Naskh Arabic, Noto Sans Devanagari, Noto Sans SC
- [x] Dexie schema mirroring the backend tables
- [x] Home: due counts per box, current app date, streak
- [x] **Clock control in the header** — +1 / +7 / +30 days, jump to date, reset
- [x] Review card: prompt, typed input, submit
- [x] `dir` and `lang` set **per element** from `card.direction` and `card.language`
- [x] CSS logical properties throughout — `margin-inline-start`, `text-align: start`, never `left`/`right`
- [x] Verdict display: green / amber / red, mismatch positions highlighted inline
- [x] Grade buttons showing the resulting next-due date on each
- [x] Cards graded `again` re-enter today's queue
- [x] Session summary screen
- [x] Export and import buttons, reachable without an account
- [x] Test with browser zoom at 200% and on a phone-width viewport

### Multi-script visual QA

- [x] Arabic renders right-to-left with harakat stacked correctly, not as tofu boxes
- [x] Hindi conjuncts render as ligatures, not decomposed
- [x] Chinese renders at a readable size — CJK needs more line-height than Latin
- [x] The typed input for an RTL card has the cursor on the right
- [x] Mixed-direction card list does not visually break

**Where this stands:** complete. One static file, no build step, served by the
API itself at `/`. Verified in a real browser at 1280px, 640px at 200% zoom and
375px: no horizontal scroll anywhere, every control at least 44x44, contrast at
or above 4.5:1 in both light and dark themes, and all four scripts rendering
correctly — Arabic right-to-left with harakat stacked, Devanagari conjuncts
ligated, Chinese split per character. `tests/test_web_contract.py` pins the
parts of the page a backend change could break.

**Exit criterion:** you can complete a full study session in all four languages without touching `/docs`.

---

## Phase 5 — Local-first sync

- [ ] Supabase project, Postgres schema matching `models.py`
- [ ] Row-level security so users only see their own rows
- [ ] Supabase auth: email sign-in
- [ ] Push: rows where `updated_at > last_sync_at`
- [ ] Pull: same predicate, merged with last-write-wins
- [ ] Tombstones honoured on both sides
- [ ] **Test the failure paths explicitly:** sign out mid-session, kill the network, use an expired token. In every case local data must survive intact and the app must keep working.
- [ ] "Sync unavailable — studying offline" banner
- [ ] Confirm export works while signed out

**Exit criterion:** you can turn off the network, study for ten minutes, reconnect, and lose nothing.

---

## Phase 6 — Ship

- [ ] `.github/workflows/ci.yml` — ruff, mypy, pytest on every push
- [ ] `.github/workflows/keepalive.yml` — cron every 3 days, trivial Supabase query
- [ ] Connect the repo to Vercel, set env vars (Supabase URL and anon key)
- [ ] Verify the production deploy and the auto-generated `/docs`
- [ ] One Playwright smoke test: load → advance clock 3 days → queue changes
- [ ] Custom `vercel.json` `excludeFiles` to keep `tests/` and `seed/` out of the function bundle

### README — this is graded

- [ ] What it is, and the live URL
- [ ] How to run locally in three commands
- [ ] **Which CHECK cases you fail, and why** — the two Matthew 28:19 cases, with your computed counts shown
- [ ] Every rule interpretation you made where B_Rules was ambiguous, lifted from `DECISIONS.md`
- [ ] How to demonstrate time travel — the single most impressive thing to show a reviewer in ten seconds
- [ ] Architecture in one paragraph plus the diagrams from `FLOWCHART.md`
- [ ] Text sources and public-domain status, per B_Rules

**Exit criterion:** a stranger can open the URL, study a card in Arabic, advance the clock 60 days, and see the schedule respond — without reading anything first.

---

## Ordering rationale

Phases 1 and 2 are the whole challenge. The normalizer and the scheduler are where correctness is judged, and both are pure functions with a supplied test suite — so build and prove them before any framework exists to hide behind. Everything from Phase 3 onward is plumbing around logic you have already shown to be right.

If you run short on time, a submission with Phases 0–3 complete plus a `/docs`-only interface is far stronger than a polished UI wrapped around a scheduler that fails trace #7.
