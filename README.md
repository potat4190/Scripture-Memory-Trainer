# Scripture Memory Trainer

A spaced-repetition trainer for memorizing scripture in four languages — English,
Chinese, Arabic, and Hindi — with a Leitner-box scheduler, a Unicode-aware
answer checker, and a time-travel clock so a reviewer can advance the date by any
number of days without touching code.

Frontier Commons Fellowship FA26 — Build Lane, Option B.

---

## Status

**Phase 0 complete — project setup and spec extraction.** No application logic
exists yet, which is intentional: the acceptance data is turned into fixtures
first, then the pure logic is built and proven against it. See
[docs/BUILD-CHECKLIST.md](docs/BUILD-CHECKLIST.md) for the full plan.

| Phase | What | State |
|---|---|---|
| 0 | Setup, dependency pinning, extract the workbook tabs to fixtures | **done** |
| 1 | Pure logic — `clock`, `scheduler`, `normalizer`, `checker`, `queue` | not started |
| 2 | Prove the logic against the fixtures (pytest + Hypothesis) | not started |
| 3 | FastAPI backend + SQLModel + Alembic | not started |
| 4 | Static HTML / Alpine.js frontend, multi-script rendering | not started |
| 5 | Local-first sync (Supabase, last-write-wins, offline-safe) | not started |
| 6 | CI, deploy to Vercel, Playwright smoke test | not started |

---

## What is in the repo now

```
seed/cards.json                     32 verses — 8 references x 4 languages (from B_Cards)
tests/fixtures/check_schedule.json   8 grade-sequence traces (from B_Check_Schedule)
tests/fixtures/check_answers.json    21 answer-checking cases (from B_Check_Answers)
tests/test_fixtures.py               proves the fixtures load and are well-formed
docs/BUILD-CHECKLIST.md              the sequenced build plan
docs/DECISIONS.md                    every rule interpretation made so far
docs/FLOWCHART.md                    9 Mermaid diagrams, lifecycle down to the check pipeline
docs/TOOLING.md                      why each dependency was chosen; verified reference logic
src/scripture_memory_trainer/        package scaffold (no logic yet)
```

The three fixture files are the acceptance test suite. Everything from Phase 1
onward is "make the fixtures pass, and name every case you don't."

### The fixtures were extracted, not retyped

`seed/cards.json` and both `tests/fixtures/*.json` files were parsed
programmatically out of the supplied workbook export. Card and input strings are
stored with their **exact original codepoints** — including one Arabic case that
is deliberately not in Unicode NFC form, because that is precisely what the case
tests. Retyping any of this would destroy the cases. See
[docs/DECISIONS.md](docs/DECISIONS.md) D2–D4.

---

## Running locally

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
uv sync                       # create the venv, install everything from uv.lock
uv run pre-commit install     # ruff lint + format on every commit
uv run pytest                 # currently: the fixture-integrity checks
```

There is no web app or CLI to run yet — that arrives in Phase 3. When it does,
this section becomes the three commands that start it.

Lint and types:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

---

## Known discrepancies with the workbook

The brief requires stating which CHECK cases we fail and why. Two are already
known from direct computation against the `B_Cards` text; both concern
**Matthew 28:19 (en)** and both are consistent with the workbook's expected
values having been computed against a different, shorter text than the 24-word
KJV verse actually supplied in `B_Cards`.

| Case | Workbook expects | Computed from `B_Cards` |
|---|---|---|
| Curly apostrophe — `Father's` wrong | 1 word wrong at position **16** | position **15** |
| Empty string | 0 of **22** words matched | 0 of **24** words matched |

Per the brief, `B_Rules` and the supplied text are authoritative; the checker
will **not** be tuned to reproduce 22/16, as that would break the cases that
currently pass.

Separately, the supplied workbook export contains **21** `B_Check_Answers` rows,
though the tab's own header says 22. The 22nd case is not in the data we were
given. See [docs/DECISIONS.md](docs/DECISIONS.md) D1 and D5.

---

## Planned architecture

Browser is the source of truth (IndexedDB via Dexie); a FastAPI backend on
Vercel serves the pure logic and static assets; Supabase Postgres provides
optional cross-device sync with last-write-wins merge and a hard rule that a
failed sync or sign-out never touches local data. JSON export/import works with
no account, always. Full diagrams in [docs/FLOWCHART.md](docs/FLOWCHART.md);
dependency rationale in [docs/TOOLING.md](docs/TOOLING.md).

The one non-negotiable design constraint: no module ever calls `date.today()`
directly. All "what day is it" goes through an injectable `Clock` that adds a
persisted offset, so a reviewer can jump the date forward from the UI and every
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
