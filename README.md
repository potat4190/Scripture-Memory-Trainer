# Scripture Memory Trainer

Type a verse from memory, in any of four scripts, and find out exactly where you
went wrong — then let a Leitner scheduler decide when you see it again.

**Live: <https://scripture-memory-trainer-lemon.vercel.app>** — no sign-in, no
account.

> The first load after a quiet spell takes a few seconds: a free Vercel Python
> function has to wake and Supabase's connection pooler has to open. That is
> cold start, not a hang.

Frontier Commons Fellowship FA26 — Build Lane, Option B.

---

## What it does

Eight verses in English, Chinese, Arabic and Hindi — 32 cards. You get the
reference; you type the verse. The checker compares your answer to the card
position by position and tells you which word was wrong, which ones you never
reached, and how many you typed past the end. Grade yourself Again / Hard /
Good / Easy and the card moves through six Leitner boxes on a
`0 → 1 → 3 → 7 → 21 → 60` day ladder.

Three things make it more than a flashcard app:

**Comparison is Unicode-aware, per language.** Capitalisation, punctuation and
repeated whitespace never count. Arabic diacritics are optional and alef forms
are normalised; the Hindi nukta is optional. Chinese is compared per character,
and traditional is deliberately **not** folded into simplified — if the card is
simplified, traditional input is wrong, because that is the rule.

**The interface is genuinely multi-script.** `lang` and `dir` are set per
element from the card, not once on the page, so a right-to-left Arabic card and
a left-to-right Hindi card can sit in the same list without breaking. Every
inline edge in the stylesheet is a logical property — `margin-inline`,
`text-align: start` — because half these verses run the other way. A test fails
the build on `margin-left`.

**The clock travels.** Every date in the app comes from an offset the app
persists, so you can press +30d and watch the schedule respond without waiting
a month or touching the code. That single feature is what makes a spaced
repetition system demonstrable at all.

---

## How it is built

```
web/index.html          One static file. Alpine.js and Dexie from CDN, no build
   |                    step. Mirrors the database into IndexedDB so an offline
   |                    load still has a deck to read.
   |  fetch, same origin — no CORS, one thing to deploy
   v
api.py                  Eight endpoints. Routing only.
   |
service.py              The rules: what a review does, how a restore merges.
   |
   +-- clock, scheduler, normalizer, checker, queue, models
   |     The pure layer. No framework, no driver, no I/O.
   |
tables.py / database.py SQLModel tables, engine, per-request session.
   v
Supabase Postgres       Alembic owns the schema. SQLite locally, same code.
```

| Tool | Why |
|---|---|
| **FastAPI + SQLModel** | One type definition serves the table, the validation and the OpenAPI docs. `/docs` is a working interface, not a byproduct. |
| **`regex`, not `re`** | Only it supports `\p{P}`, the Unicode punctuation property. That makes "strip punctuation in every script" one line instead of a hand-maintained character list. |
| **Alembic** | The schema has a history and can move between SQLite and Postgres unchanged. `render_as_batch` so migrations run on both. |
| **uv** | Locked, reproducible installs; Vercel reads `pyproject.toml` and `uv.lock` directly. |
| **Alpine + Dexie from CDN** | The frontend is one file a reviewer can read top to bottom. No bundler, no `node_modules`, nothing to build. |
| **pytest + Hypothesis** | Examples prove the supplied cases; properties prove the shapes those cases imply. |
| **ruff + mypy strict** | Enforced in CI on every push. |

### The method that mattered most

**The logic was built and proven before any framework existed.** `clock`,
`scheduler`, `normalizer`, `checker`, `queue` and `models` import nothing but
the standard library and `regex` — no database, no web framework, no I/O. That
is what let the scheduler be verified against all 8 workbook traces and the
checker against all 21 answer cases while there was still nothing to hide
behind. It is enforced rather than hoped for: a test imports each module in a
**subprocess** and fails if SQLAlchemy or FastAPI has crept in.

**The acceptance data was extracted, never retyped.** `seed/cards.json` and both
fixture files are generated from the challenge workbook by
`tools/extract_fixtures.py`, and re-running it must be a no-op. Card and input
strings keep their exact codepoints and spacing — including one Arabic case
deliberately not in Unicode NFC form, and one English case whose leading and
trailing spaces are the entire point of the test. An earlier extraction from a
Markdown rendering of the workbook silently lost that padding, because Markdown
tables cannot carry cell-edge whitespace. Reading the `.xlsx` recovered it, and
a test now fails if it is ever dropped again.

**421 tests, 99% coverage** on the modules that matter. The scheduler traces are
asserted step by step, not just on their end state, by parsing the workbook's own
prose. The answer-case expectations are parsed from the workbook's verdict
sentences rather than transcribed, so the numbers cannot drift from the source.
Three properties come straight from the brief: normalisation is idempotent, it
never increases the word count, and the box always lands in 0–5.

---

## Running locally

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
uv sync
uv run alembic upgrade head                  # create the tables (SQLite by default)
uv run python -m scripture_memory_trainer    # load the 32 cards; safe to re-run
uv run uvicorn scripture_memory_trainer.api:app --reload
```

Then <http://127.0.0.1:8000> for the app, <http://127.0.0.1:8000/docs> for the
API. `DATABASE_URL` overrides the database; unset, it uses a local SQLite file.

```bash
uv run pytest              # 421 passed, 3 xfailed (the documented workbook errors)
uv run ruff check . && uv run mypy
```

### Time travel in ten seconds

Study a card, grade it **Easy**, then press **+7d** in the header. The app date
moves, the real date does not, and the card you scheduled comes back due.

> Use +7d or +30d rather than +1d. A card graded Easy from box 0 is scheduled
> three days out, which sorts it *last* — behind 31 cards still due today, and
> outside the daily cap of 20. It is due, just not on the first page.

---

## Decisions

The full argument for each is in [docs/DECISIONS.md](docs/DECISIONS.md).

- **The workbook wins over intuition.** Where a rule-correct implementation
  disagrees with a stated expected value, the implementation stands and the
  disagreement is documented. Three cases; see below.
- **The pure logic layer is inviolable.** Persistence lives in `tables.py`, not
  `models.py`, specifically so importing the queue cannot drag SQLAlchemy into
  the logic.
- **One source of time.** Nothing outside `clock.py` calls `date.today()`. The
  one deliberate exception is sync bookkeeping, which uses real UTC — otherwise
  a user who travelled 60 days forward would win every merge.
- **One `DATABASE_URL`.** SQLite locally, Postgres in production, identical
  code. A bare `postgresql://` is rewritten to psycopg 3 so the string copied
  from a dashboard just works.
- **Same origin.** The API serves the frontend, so there is no CORS, no
  credential plumbing and one thing to deploy.
- **Restores merge, never replace.** Import is last-write-wins on `updated_at`,
  strictly newer only, so restoring an old backup cannot delete newer work and
  re-importing the same file is a no-op.
- **Export works without an account, always.** That is the promise that your
  data is never held hostage.
- **Surplus input is its own fact.** Typing past the end of the verse is
  reported separately and never inflates or deflates the match counts, which are
  always computed from the card's length.
- **The queue sorts references as plain strings** — alphabetical, not canonical
  book order, so Isaiah < John < Leviticus. The rules say string; a test stops
  anyone "helpfully" fixing it.

---

## Known discrepancies with the workbook

Three cases where a rule-correct implementation disagrees with the workbook's
stated expectation. `B_Rules` and the supplied text are authoritative, so the
checker is **not** tuned to reproduce them. All three are marked
`xfail(strict=True)`, which means that if someone later "fixes" the checker to
match, the suite fails rather than going quietly green.

| Case | Workbook expects | This checker computes |
|---|---|---|
| Matthew 28:19 (en) — curly apostrophe, `Father's` wrong | 1 word wrong at position **16**, total **22** | position **15**, total **24** |
| Matthew 28:19 (en) — empty string | 0 of **22** words matched | 0 of **24** words matched |
| John 3:16 (zh) — traditional against a simplified card | **Incorrect** | **Partial** — 23 of 30 characters matched, 7 differ |

The first two are consistent with the expected values having been computed
against a 22-word text while `B_Cards` supplies 24. The third follows from the
rules as written: script conversion is not performed and every differing
character counts, but these two verses share 23 of 30 characters, so the result
is Partial rather than a zero-match Incorrect.

Separately, `B_Check_Answers` holds **21** data rows though its own preamble
says 22 — confirmed by reading the `.xlsx` directly, so there is no 22nd case to
pass or fail. Running the test suite regenerates
[reports/check-report.md](reports/check-report.md) with the current list, and a
test fails if the set of deviating cases ever changes.

---

## What is not built, and why

**There are no user accounts.** The app is a single shared deck: anyone with the
URL can grade cards and move the clock, and everyone sees the same state. Fine
for a demo, wrong for real use.

Adding accounts is more than an afternoon, and the reason is structural rather
than fiddly. `CardState`'s primary key *is* `card_id`, so two accounts studying
John 3:16 collide; `AppState` is a single pinned row, so one visitor pressing
+30d moves everyone's date. Both need re-keying, and Alembic's autogenerate
handles added columns well and primary-key changes badly. There is also a
decision hiding in it that the plan never mentioned: if every endpoint demands a
token, the public demo stops working, so anonymous sessions or a signed-out
local mode has to come first.

**Cross-device sync is closer than it looks.** The merge rule is already written
and tested — last-write-wins on `updated_at`, tombstone-aware, idempotent, with
21 tests covering it. Once rows have owners and clients authenticate, sync
largely falls out, because every device talks to the same Postgres.

**True offline-first is the genuinely large piece and is not attempted.** Today
Dexie is a *read* mirror: offline you can still see your deck, and the app says
so in a banner, but it will not accept a grade it might lose. Making the client
a writer means a local write queue, client-generated ids and reconciliation on
reconnect. That was a scoping decision, not an oversight — the honest version is
a read-only offline mode that never lies about what it saved.

The full migration plan, including the RLS policies, is written up in
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) §5.4.

---

## Shortcomings and hacks

An honest list of what I would flag in review.

**The clock is global.** It lives in one row, so time travel is shared by every
visitor at once. It should be per user, and will have to be as soon as accounts
exist.

**Two things are reimplemented in the browser.** The Leitner intervals (so a
grade button can show its date before you press it) and the unit split (so a
mismatch at position 15 can be highlighted at position 15). Both are duplicated
logic. They are pinned by tests that *parse `web/index.html` with a regex* and
compare the JavaScript literals to the Python — which catches drift, but is
itself the hackiest thing in the repo.

**The client-side split skips the language folding** and relies on an invariant:
stripping harakat or a nukta never changes how many units there are. That holds
for all 32 cards and is asserted for each of them, but it is an assumption about
the data, not a proof about the rules.

**`app.py` puts `src/` on `sys.path`.** A src-layout package is importable only
when the project itself is installed, and a deployment that installs
dependencies but not the project would fail with an error that looks like a
missing third-party package. The three-line workaround is deliberate and
commented, but it is a workaround.

**The production schema was applied as raw SQL, not by running Alembic against
it.** The SQL was generated by `alembic upgrade head --sql` and the version
table was stamped to match, so the result is byte-identical to the migration and
future migrations run normally — but the usual path would have been to point
Alembic at the production URL and let it do the work.

**`hard` on boxes 3 and 5 is unverified by fixture.** No supplied trace exercises
them. They follow the same floored-60% rule as the boxes that are covered, and
property tests bound the result, but no workbook trace confirms 4 days and 36
days specifically.

**The CDN failure check is a timer.** If Alpine does not load, `x-cloak` never
lifts and the page renders blank — a worse failure than a broken layout, because
nothing looks wrong. There is now a four-second check that reveals an
explanation and points at `/docs`, but a timeout is a crude substitute for a
proper load-error event.

**The API is unauthenticated and unthrottled**, `GET /api/cards` is unpaginated,
and `/api/health` returns a redacted database error message to anyone who asks.
All are acceptable at 32 cards and one user; none would survive contact with the
public.

**Row-level security is enabled with no policies.** That closes the Supabase
Data API completely rather than selectively — correct while there is nothing to
scope by, but a blunt instrument standing in for real policies.

---

## Time spent

About **6 hours**, spread over 3 days.

Roughly half of that went into the logic and its tests — the normalizer and the
scheduler are where correctness is judged, and both were finished before any
framework existed. The rest went to the API, the frontend, and deployment, with
deployment taking longer than expected: the failures arrived one at a time
(entrypoint, then driver, then network, then an empty database), each hidden
behind a generic 500 until the health endpoint was taught to report the cause.

---

## Text sources

All four translations are public domain, supplied complete in `B_Cards` —
nothing is fetched at runtime.

| Lang | Translation | Status |
|---|---|---|
| en | King James Version (1769) | Public domain |
| zh | Chinese Union Version (1919), simplified script | Public domain |
| ar | Smith & Van Dyck (1865), fully vocalized | Public domain (CC0) |
| hi | Hindi Old Version | Public domain |

---

## Repository map

```
src/scripture_memory_trainer/
  clock.py         injectable Clock: real date + a persisted day offset
  scheduler.py     Leitner box arithmetic
  normalizer.py    Unicode-aware folding for comparison
  checker.py       positional answer checking -> Verdict
  queue.py         due filter, three-key sort, cap of 20
  models.py        the Card dataclass the pure logic speaks
  tables.py        SQLModel tables + the columns sync will need
  database.py      engine, session, DATABASE_URL handling
  seed.py          idempotent import of seed/cards.json
  service.py       the rules the API applies
  schemas.py       request/response models — what /docs renders
  api.py           eight endpoints; also serves the frontend
web/index.html     the entire frontend
app.py             deployment entrypoint
seed/cards.json    32 verses, extracted from the workbook
tests/             421 tests, including a Playwright smoke test in tests/smoke/
docs/DECISIONS.md  every interpretation, with the argument for it
docs/DEPLOYMENT.md the deployment runbook and the plan for accounts and sync
docs/FLOWCHART.md  diagrams, lifecycle down to the check pipeline
docs/TOOLING.md    why each dependency was chosen
tools/             regenerates the fixtures from the workbook
```
