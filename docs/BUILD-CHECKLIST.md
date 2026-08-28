# Build Checklist — Scripture Memory Trainer

Sequenced so that the hardest, most graded work happens first and everything after it is scaffolding. Check items off in order; each phase ends at a point where you could stop and still have something defensible.

---

## Phase 0 — Setup and spec extraction

- [ ] `uv init` and create the project skeleton
- [ ] `uv add fastapi pydantic sqlmodel alembic regex "psycopg[binary]" python-dotenv`
- [ ] `uv add --dev pytest pytest-cov hypothesis ruff mypy "uvicorn[standard]" pre-commit`
- [ ] `git init`, push to GitHub, make the repo **public** (free Actions minutes)
- [ ] Add `.gitignore`, `ruff` config in `pyproject.toml`, `.pre-commit-config.yaml`
- [ ] **Extract `B_Cards` to `seed/cards.json`** — 32 rows, fields: `card_id`, `reference`, `language`, `direction`, `text`
- [ ] **Extract `B_Check_Schedule` to `tests/fixtures/check_schedule.json`** — 8 traces, fields: `grades[]`, `expected_box`, `expected_due`
- [ ] **Extract `B_Check_Answers` to `tests/fixtures/check_answers.json`** — 22 cases, fields: `reference`, `lang`, `input`, `expected_verdict`
- [ ] Copy input strings from the source cells verbatim; do **not** retype them. Retyping destroys the exact codepoints the cases test.
- [ ] Create `docs/DECISIONS.md` with an empty decision log

**Exit criterion:** the fixtures exist and load. You have not written a line of logic yet, and that is correct.

---

## Phase 1 — Pure logic, zero I/O

Nothing in this phase touches a database, a network, or a framework. Every function is a pure function of its arguments. This is what makes it testable and what makes the fixtures meaningful.

### `src/clock.py`

- [ ] `Clock` class holding `offset_days: int`
- [ ] `Clock.today() -> date` returns `date.today() + timedelta(days=offset_days)`
- [ ] **Grep the whole repo for `date.today()` and `datetime.now()`.** Every call outside `clock.py` is a bug.

### `src/scheduler.py`

- [ ] `INTERVALS = {0:0, 1:1, 2:3, 3:7, 4:21, 5:60}`
- [ ] `apply_grade(box, grade) -> (new_box, interval_days)`
- [ ] `again` → box 0, interval 0
- [ ] `hard` → box unchanged, `max(1, INTERVALS[box] * 60 // 100)` — floor, then floor at 1
- [ ] `good` → `min(5, box + 1)`, interval of the **new** box
- [ ] `easy` → `min(5, box + 2)`, interval of the **new** box
- [ ] `next_due(review_date, interval) -> date`

### `src/normalizer.py`

- [ ] `import regex as re` — **not** stdlib `re`
- [ ] NFC-normalize input first
- [ ] Curly quotes → straight: U+2018 U+2019 U+201C U+201D
- [ ] Full-width → ASCII: U+FF0C → `,`, U+FF1B → `;`
- [ ] Arabic only: strip U+064B–U+0652, U+0640, U+0670
- [ ] Arabic only: U+0671 → U+0627, U+0649 → U+064A
- [ ] Hindi only: strip U+093C nukta
- [ ] Chinese: **no** simplified/traditional conversion — assert this in a test so nobody "fixes" it later
- [ ] Strip all punctuation with `re.sub(r"\p{P}+", "", s)`
- [ ] Collapse whitespace runs, trim ends
- [ ] `.casefold()`, not `.lower()`

### `src/checker.py`

- [ ] `check(card_text, user_input, lang) -> Verdict`
- [ ] `Verdict` dataclass: `status`, `matched`, `total`, `mismatch_positions[]`, `missing_from`, `unit` (`words` or `chars`)
- [ ] Word split for `en`, `ar`, `hi`; character split for `zh`
- [ ] Positional comparison, 1-based positions in the output
- [ ] Missing tail: report count and first absent position
- [ ] Surplus input beyond card length: decide the behaviour, log it in `DECISIONS.md`
- [ ] `matched == 0` → Incorrect; exact match → Correct; otherwise Partial

### `src/queue.py`

- [ ] `build_queue(cards, today, lang_filter) -> list[Card]`
- [ ] Filter `due_date <= today`
- [ ] Sort key: `(due_date, box, reference)` — plain **string** sort on reference, not canonical book order
- [ ] Cap at 20
- [ ] Return the pre-cap total so the UI can show "20 of 47 due"

**Exit criterion:** five modules, no imports of FastAPI or any DB driver.

---

## Phase 2 — Prove the logic

- [ ] `test_scheduler.py` parametrized over all 8 traces in `check_schedule.json`
- [ ] `test_normalizer.py` parametrized over all 22 cases in `check_answers.json`
- [ ] `test_queue.py`: cap of 20, all three sort keys, the alphabetical-not-canonical ordering
- [ ] `test_clock.py`: offset arithmetic, and that advancing the clock changes the queue
- [ ] Hypothesis: `normalize(normalize(x)) == normalize(x)` for all inputs, all languages
- [ ] Hypothesis: normalization never increases word count
- [ ] Hypothesis: box always lands in 0–5 for any grade sequence
- [ ] Make the suite emit a machine-readable list of failing CHECK cases (`pytest --tb=no -q` plus a small reporter)
- [ ] Paste that list into `DECISIONS.md`

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

- [ ] `models.py` — SQLModel tables: `Card`, `CardState` (box, due_date, updated_at), `ReviewLog`, `AppState` (clock offset)
- [ ] Every table gets `updated_at: datetime` and `deleted: bool` for sync
- [ ] `alembic init`, generate and apply the first migration
- [ ] Seed loader that imports `seed/cards.json` idempotently
- [ ] `GET /api/cards` — list with filters
- [ ] `GET /api/queue` — today's queue plus the pre-cap total
- [ ] `POST /api/review` — body `{card_id, grade, answer_text?}`, returns verdict plus new box and due date
- [ ] `POST /api/check` — verdict only, no state change (useful for the UI and for demos)
- [ ] `GET/POST /api/clock` — read and set the offset
- [ ] `GET /api/export` — full JSON dump
- [ ] `POST /api/import` — restore from JSON
- [ ] Confirm the auto-generated docs render at `/docs`

**Exit criterion:** the full flow works through `/docs` with no frontend at all.

---

## Phase 4 — Frontend

- [ ] `index.html` with Alpine.js and Dexie from CDN
- [ ] Google Fonts: Noto Sans, Noto Naskh Arabic, Noto Sans Devanagari, Noto Sans SC
- [ ] Dexie schema mirroring the backend tables
- [ ] Home: due counts per box, current app date, streak
- [ ] **Clock control in the header** — +1 / +7 / +30 days, jump to date, reset
- [ ] Review card: prompt, typed input, submit
- [ ] `dir` and `lang` set **per element** from `card.direction` and `card.language`
- [ ] CSS logical properties throughout — `margin-inline-start`, `text-align: start`, never `left`/`right`
- [ ] Verdict display: green / amber / red, mismatch positions highlighted inline
- [ ] Grade buttons showing the resulting next-due date on each
- [ ] Cards graded `again` re-enter today's queue
- [ ] Session summary screen
- [ ] Export and import buttons, reachable without an account
- [ ] Test with browser zoom at 200% and on a phone-width viewport

### Multi-script visual QA

- [ ] Arabic renders right-to-left with harakat stacked correctly, not as tofu boxes
- [ ] Hindi conjuncts render as ligatures, not decomposed
- [ ] Chinese renders at a readable size — CJK needs more line-height than Latin
- [ ] The typed input for an RTL card has the cursor on the right
- [ ] Mixed-direction card list does not visually break

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
