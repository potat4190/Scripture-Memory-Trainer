# Scripture Memory Trainer

A spaced-repetition trainer for memorizing scripture in four languages — English,
Chinese, Arabic, and Hindi — with a Leitner-box scheduler, a Unicode-aware
answer checker, and a time-travel clock so a reviewer can advance the date by any
number of days without touching code.

**Live: <https://scripture-memory-trainer-lemon.vercel.app>** — no sign-in, no
account. Open it, study a verse in Arabic, then press **+30d** in the header and
watch the schedule respond.

Frontier Commons Fellowship FA26 — Build Lane, Option B.

> The first load after a quiet spell takes a few seconds: a free Vercel Python
> function has to wake and Supabase's pooler has to open a connection. That is
> cold start, not a hang.

---

## Status

**Phase 4 complete — there is an app.** The pure logic is pinned by every
fixture the workbook supplies, the whole flow runs over HTTP, and a single
static page drives it in four scripts and two writing directions. Sync and
deployment (Phases 5 and 6) both need third-party accounts and are documented
in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) rather than half-built. See
[docs/BUILD-CHECKLIST.md](docs/BUILD-CHECKLIST.md) for the plan.

| Phase | What | State |
|---|---|---|
| 0 | Setup, dependency pinning, extract the workbook tabs to fixtures | **done** |
| 1 | Pure logic — `clock`, `scheduler`, `normalizer`, `checker`, `queue` | **done** |
| 2 | Lock the logic in with parametrized pytest + Hypothesis | **done** |
| 3 | FastAPI backend + SQLModel + Alembic | **done** |
| 4 | Static HTML / Alpine.js frontend, multi-script rendering | **done** |
| 5 | Local-first sync (Supabase, last-write-wins, offline-safe) | **not started** — needs per-user ownership first; see [DEPLOYMENT.md](docs/DEPLOYMENT.md) 5.4 |
| 6 | CI, deploy to Vercel, Playwright smoke test | **done** — deployed, CI green, smoke test run against production |

Checked against the challenge workbook: **8/8** schedule traces (verified step by
step, not just on their end state) and **18/21** answer cases. The three
exceptions are workbook errors, not checker bugs — see below; they are marked
`xfail(strict=True)`, so "fixing" the checker to reproduce them turns them into
failures rather than quiet passes.

`uv run pytest` — **407 passed, 3 xfailed**, and it writes
`reports/check-report.json` / `.md`, the machine-readable list of which CHECK
cases deviate and by how much.

---

## What is in the repo now

```
src/scripture_memory_trainer/
  clock.py         injectable Clock: real date + a persisted day offset
  scheduler.py     Leitner box arithmetic — apply_grade, next_due
  normalizer.py    Unicode-aware text folding for comparison (uses `regex`, not `re`)
  checker.py       positional answer checking -> Verdict
  queue.py         daily review queue: due filter, 3-key sort, cap of 20
  models.py        the Card dataclass the pure logic speaks
  tables.py        SQLModel tables: Card, CardState, ReviewLog, AppState (+ sync columns)
  database.py      engine and per-request session; DATABASE_URL, SQLite by default
  seed.py          idempotent import of seed/cards.json
  service.py       what the API does to the database — the rules, minus the routing
  schemas.py       request/response models; these are what /docs renders
  api.py           eight endpoints, and it serves the frontend from the same origin
web/index.html     the whole frontend: one file, no build step
app.py             deployment entrypoint; Vercel loads `app` from here
vercel.json        excludeFiles, keeping tests/ and docs/ out of the function bundle
.github/workflows/ ci.yml (ruff, mypy, pytest) and keepalive.yml (Supabase anti-pause)
seed/cards.json                     32 verses — 8 references x 4 languages (from B_Cards)
tests/fixtures/check_schedule.json   8 grade-sequence traces (from B_Check_Schedule)
tests/fixtures/check_answers.json    21 answer-checking cases (from B_Check_Answers)
tests/test_fixtures.py               proves the fixtures load and are well-formed
tests/test_scheduler.py              all 8 traces, step by step, plus the grade rules
tests/test_normalizer.py             all 21 CHECK cases + every normalization rule
tests/test_queue.py                  due filter, 3-key sort, cap of 20, language filter
tests/test_clock.py                  offset arithmetic, and that the clock moves the queue
tests/test_properties.py             Hypothesis: idempotence, word count, box bounds
tests/test_phase1_guards.py          the invariants nobody may "helpfully" fix
tests/test_tables.py                 schema shape, sync columns, seed idempotency
tests/test_api.py                    every endpoint, plus the whole flow end to end
tests/test_web_contract.py           what the page duplicates from the backend, pinned
tests/test_service.py                the merge rules, including last-write-wins overwrites
tests/smoke/test_deployment.py       one Playwright test against a deployed URL
tests/test_database.py               engine construction and session lifetime
tests/conftest.py                    fixture loading + the CHECK-case deviation reporter
reports/check-report.{json,md}       generated by the suite: which CHECK cases deviate
alembic/                             migration environment and versions
docs/BUILD-CHECKLIST.md              the sequenced build plan
docs/DECISIONS.md                    every rule interpretation made so far
docs/FLOWCHART.md                    9 Mermaid diagrams, lifecycle down to the check pipeline
docs/TOOLING.md                      why each dependency was chosen; verified reference logic
tools/extract_fixtures.py            regenerates the three data files from the workbook
```

### The logic

- **`clock.py`** — the only place in the codebase allowed to call `date.today()`.
  Everything else asks a `Clock`, which returns `date.today() + offset_days`. That
  is what makes time travel a one-liner and tests deterministic.
- **`scheduler.py`** — `INTERVALS = {0:0, 1:1, 2:3, 3:7, 4:21, 5:60}`. `hard` keeps
  the box and advances by `INTERVALS[box] * 60 // 100` (floored, minimum 1) — so
  box 4 `hard` is 12 days, not 13, and box 0 `hard` still moves a day.
- **`normalizer.py`** — NFC, then curly→straight quotes, full-width→ASCII, then
  per-language rules (Arabic harakat/alef/yeh, Hindi nukta; **no** Chinese
  simplified↔traditional conversion), then `\p{P}` punctuation strip, whitespace
  collapse, and `casefold()`.
- **`checker.py`** — splits into words (`en`, `ar`, `hi`) or characters (`zh`),
  compares position by position, and returns a `Verdict` with 1-based mismatch
  positions, the missing tail (count + first absent position), and surplus input
  reported separately (DECISIONS D6).
- **`queue.py`** — filters to `due_date <= today`, sorts by
  `(due_date, box, reference)` with **string** ordering on the reference (not
  canonical book order), caps at 20, and returns the pre-cap total for a
  "20 of 47 due" line.

### The fixtures were extracted, not retyped

`seed/cards.json` and both `tests/fixtures/*.json` files are generated straight
from the challenge workbook by [tools/extract_fixtures.py](tools/extract_fixtures.py).
The workbook itself is not tracked here; drop your copy into `docs/` and run:

```bash
uv run --with openpyxl python tools/extract_fixtures.py   # must be a no-op
```

Card and input strings keep their **exact original codepoints and spacing** —
including one Arabic case deliberately not in Unicode NFC form, and one English
case whose leading and trailing spaces are the whole point of the test. Both
would be destroyed by retyping, and the second was in fact lost by an earlier
extraction from a Markdown rendering of the workbook, since Markdown tables
cannot carry cell-edge whitespace. Reading the `.xlsx` recovered it
([docs/DECISIONS.md](docs/DECISIONS.md) D4); `tests/test_fixtures.py` now fails if
it is ever dropped again. See D1–D4.

---

## Running locally

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
uv sync                       # create the venv, install everything from uv.lock
uv run pre-commit install     # ruff lint + format on every commit
uv run pytest                 # 407 passed, 3 xfailed (the documented workbook errors)
uv run pytest --tb=no -q      # + writes reports/check-report.{json,md}
```

Bring up the database and the API:

```bash
uv run alembic upgrade head          # create the tables (SQLite by default)
uv run python -m scripture_memory_trainer   # load the 32 cards; safe to re-run
uv run uvicorn scripture_memory_trainer.api:app --reload
```

Then open <http://127.0.0.1:8000> for the app, or
<http://127.0.0.1:8000/docs> for the API. (Or skip all of it and use the
[live deployment](https://scripture-memory-trainer-lemon.vercel.app).) `DATABASE_URL` overrides the database;
unset, it uses a local SQLite file. See `.env.example`.

### Time travel in ten seconds

On the [live app](https://scripture-memory-trainer-lemon.vercel.app): study a
card, grade it **Easy**, then press **+7d** in the header. The app date moves,
the real date does not, and the card you just scheduled comes back due.

> A card graded `easy` from box 0 is scheduled 3 days out, which sorts it
> *last* — behind 31 cards still due today, and outside the daily cap of 20. It
> is due, just not on the first page. Travel **+7d** or **+30d** and the effect
> is unmistakable.

The same thing from `/docs`, with no frontend at all:

1. `GET /api/queue` — 20 of 32 due today.
2. `POST /api/review` with `{"card_id": "...", "grade": "easy"}` — the card
   jumps to box 2 and is scheduled three days out.
3. `GET /api/queue` — it is gone from today's list.
4. `POST /api/clock` with `{"advance_days": 3}` — the app date moves; the real
   date does not.
5. `GET /api/queue` — it is back, and the schedule responded rather than the
   calendar.

The pure logic is importable directly (`from scripture_memory_trainer import
check, apply_grade, normalize, build_queue, Clock`) and stays free of any
framework or driver import — a test enforces that.

Lint and types:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy            # strict
```

---

## Known discrepancies with the workbook

The brief requires stating which CHECK cases we fail and why. All three below are
cases where a rule-correct implementation disagrees with the workbook's stated
expectation; per the brief, `B_Rules` and the supplied text are authoritative, so
the checker is **not** tuned to reproduce them.

| Case | Workbook expects | This checker computes |
|---|---|---|
| Matthew 28:19 (en) — curly apostrophe, `Father's` wrong | 1 word wrong at position **16**, total **22** | position **15**, total **24** |
| Matthew 28:19 (en) — empty string | 0 of **22** words matched | 0 of **24** words matched |
| John 3:16 (zh) — traditional against simplified card | **Incorrect** | **Partial** — 23 of 30 characters matched, 7 differ |

The two Matthew cases are consistent with the workbook's expected values having
been computed against a different, shorter text than the 24-word KJV verse in
`B_Cards`. The Chinese case follows the workbook's own rules — "no script
conversion", "every differing character counts", and "`matched == 0` → Incorrect,
otherwise Partial" — which land on Partial because the two scripts happen to share
23 of 30 characters. Details in [docs/DECISIONS.md](docs/DECISIONS.md) D5 and D10.

Note that at the *status* level (correct / partial / incorrect) the checker
agrees with 20 of 21 cases — only the Chinese one disagrees on the label. The two
Matthew cases return the right label and different counts.

Separately, `B_Check_Answers` holds **21** data rows though its own preamble says
22. Confirmed by reading the workbook directly, so there is no 22nd case to pass
or fail ([docs/DECISIONS.md](docs/DECISIONS.md) D1).

---

## Architecture

One FastAPI application, deployed as a single Vercel function, serving both the
API and the frontend from the same origin. Postgres on Supabase holds the data.
The whole frontend is one static file with no build step.

```
web/index.html          Alpine + Dexie from CDN. Mirrors the four tables into
   |                    IndexedDB so an offline load still has a deck to study.
   |  fetch, same origin — no CORS, one thing to deploy
   v
api.py                  eight endpoints, routing only
   |
service.py              the rules: what a review does, how a merge resolves
   |
   +-- clock, scheduler, normalizer, checker, queue, models
   |       the pure layer. No framework, no driver, no I/O. A subprocess test
   |       fails the build if any of them grows an import.
   |
tables.py / database.py SQLModel tables, engine, per-request session
   |
   v
Supabase Postgres       DATABASE_URL; alembic owns the schema
```

**The pure layer is the point.** `clock`, `scheduler`, `normalizer`, `checker`,
`queue` and `models` import nothing but the standard library and `regex`. That
is what let the scheduler be proven against all 8 workbook traces and the
checker against all 21 answer cases before any database existed, and it is
enforced rather than hoped for: `tests/test_phase1_guards.py` imports each of
them in a **subprocess** and fails if SQLAlchemy or FastAPI comes along.

**One rule about time.** No module outside `clock.py` calls `date.today()`.
Every "what day is it" goes through a `Clock` carrying a persisted offset, which
is why time travel works everywhere at once instead of only in the UI. Sync
timestamps are the deliberate exception — `clock.real_now()` is real UTC, so a
user who has travelled 60 days forward does not win every merge
([DECISIONS](docs/DECISIONS.md) D15).

**Where the data lives.** Online, the server is authoritative and Dexie is a
mirror hydrated from `GET /api/export`. Offline, the page rebuilds the queue
from that mirror and says so in a banner; it does not queue grades it might
lose. Export and import work signed out, always — that is the promise that your
data is never held hostage ([DECISIONS](docs/DECISIONS.md) D21).

Full diagrams in [docs/FLOWCHART.md](docs/FLOWCHART.md); dependency rationale in
[docs/TOOLING.md](docs/TOOLING.md); the deployment runbook, including everything
Phase 5 still needs, in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## Rule interpretations

Where `B_Rules` or the supplied data admitted more than one reading, this is the
reading taken. Each links to the full argument in
[docs/DECISIONS.md](docs/DECISIONS.md).

| # | Ambiguity | Decision |
|---|---|---|
| D6 | Input longer than the card | Surplus is reported as its own two facts (`surplus_count`, `surplus_from`) and never feeds `matched`, `total` or `status`, which are always computed from the **card's** length. Surplus with at least one match is Partial — never Correct. |
| D8, D13 | Where the review state lives | `Card` and `CardState` are separate tables, because content is seeded once and state changes every review. The tables live in `tables.py`, not `models.py`, so importing them cannot drag SQLAlchemy into the pure logic. |
| D10 | Traditional Chinese against a simplified card | No script conversion, per `B_Rules`. The two verses happen to share 23 of 30 characters, so the rules give **Partial**, not the workbook's Incorrect. Documented, not tuned away. |
| D12 | What "exact match" compares | The split **unit lists**, not the normalized strings. They agree for word languages; for `zh` they disagree, and comparing strings made a perfectly recited verse typed with spaces come back "Partial — 30 of 30 matched". |
| D15 | Which clock stamps `updated_at` | Real UTC, never the travellable clock. Otherwise a time-travelled device wins every sync merge until the real date catches up. |
| D17 | What "restore from JSON" means | Merge, last-write-wins on `updated_at`, strictly newer only. Restoring an old backup cannot delete newer work, and re-importing the same file is a no-op. |
| D18 | When a seeded card is first due | Immediately — box 0, due on the **app** date. A null due date satisfies nothing in `build_queue`, so the deck would be present and permanently invisible. |
| D19 | Logic the browser has to duplicate | The intervals and the unit split, both pinned by tests that parse `web/index.html` and fail when they drift from `scheduler.py` and `queue.py`. |
| — | Queue sort order | `(due_date, box, reference)` with `reference` as a plain **string** sort — alphabetical, not canonical book order, so Isaiah < John < Leviticus. `B_Rules` says string; a test stops anyone "fixing" it. |
| — | `hard` interval | 60% of the interval of the box the card is **already in**, floored, minimum 1 day. Box 4 gives 12 days, not 13, and `hard` on box 0 still moves the due date by a day while leaving the box at 0. |
| D1 | "22 CHECK cases" | The sheet holds **21** data rows. Confirmed against the `.xlsx`, not an export. |

---

## Text sources

All four translations are public domain, supplied complete in `B_Cards` — nothing
is fetched at runtime.

| Lang | Translation | Status |
|---|---|---|
| en | King James Version (1769) | Public domain |
| zh | Chinese Union Version (1919), simplified script | Public domain |
| ar | Smith & Van Dyck (1865), fully vocalized | Public domain (CC0) |
| hi | Hindi Old Version | Public domain |
