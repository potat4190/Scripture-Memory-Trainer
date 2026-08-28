# Scripture Memory Trainer

A spaced-repetition trainer for memorizing scripture in four languages — English,
Chinese, Arabic, and Hindi — with a Leitner-box scheduler, a Unicode-aware
answer checker, and a time-travel clock so a reviewer can advance the date by any
number of days without touching code.

Frontier Commons Fellowship FA26 — Build Lane, Option B.

---

## Status

**Phase 1 complete — the pure logic exists and has been checked against every
fixture.** No database, network, or framework is involved yet; that is the point
of the phase. See [docs/BUILD-CHECKLIST.md](docs/BUILD-CHECKLIST.md) for the plan.

| Phase | What | State |
|---|---|---|
| 0 | Setup, dependency pinning, extract the workbook tabs to fixtures | **done** |
| 1 | Pure logic — `clock`, `scheduler`, `normalizer`, `checker`, `queue` | **done** |
| 2 | Lock the logic in with parametrized pytest + Hypothesis | next |
| 3 | FastAPI backend + SQLModel + Alembic | not started |
| 4 | Static HTML / Alpine.js frontend, multi-script rendering | not started |
| 5 | Local-first sync (Supabase, last-write-wins, offline-safe) | not started |
| 6 | CI, deploy to Vercel, Playwright smoke test | not started |

Checked against the challenge workbook: **8/8** schedule traces, **18/21** answer
cases. The three exceptions are workbook errors, not checker bugs — see below.
Phase 2 turns this into a committed, parametrized test suite.

---

## What is in the repo now

```
src/scripture_memory_trainer/
  clock.py         injectable Clock: real date + a persisted day offset
  scheduler.py     Leitner box arithmetic — apply_grade, next_due
  normalizer.py    Unicode-aware text folding for comparison (uses `regex`, not `re`)
  checker.py       positional answer checking -> Verdict
  queue.py         daily review queue: due filter, 3-key sort, cap of 20
  models.py        the one shared data type (Card) for Phase 1
  storage.py       local JSON persistence — a deliberate I/O exception (see DECISIONS D9)
seed/cards.json                     32 verses — 8 references x 4 languages (from B_Cards)
tests/fixtures/check_schedule.json   8 grade-sequence traces (from B_Check_Schedule)
tests/fixtures/check_answers.json    21 answer-checking cases (from B_Check_Answers)
tests/test_fixtures.py               proves the fixtures load and are well-formed
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
uv run pytest                 # currently: the fixture-integrity checks
```

The logic is importable now (`from scripture_memory_trainer import check,
apply_grade, normalize, build_queue, Clock`), but there is no web app or CLI yet —
that arrives in Phase 3.

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

## Planned architecture

Browser is the source of truth (IndexedDB via Dexie); a FastAPI backend on
Vercel serves the pure logic and static assets; Supabase Postgres provides
optional cross-device sync with last-write-wins merge and a hard rule that a
failed sync or sign-out never touches local data. JSON export/import works with
no account, always. Full diagrams in [docs/FLOWCHART.md](docs/FLOWCHART.md);
dependency rationale in [docs/TOOLING.md](docs/TOOLING.md).

The one non-negotiable design constraint: no module outside `clock.py` ever calls
`date.today()`. All "what day is it" goes through an injectable `Clock` that adds
a persisted offset, so a reviewer can jump the date forward from the UI and every
due-date calculation follows.

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
