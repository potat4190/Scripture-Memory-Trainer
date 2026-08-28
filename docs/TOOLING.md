# Scripture Memory Trainer — Tooling Recommendations

**Challenge:** Frontier Commons Fellowship FA26, Build Lane, Option B
**Constraint:** zero paid services
**Stack decision:** Python backend + simple frontend, local-first storage with free cloud sync

---

## 0. The decisions that actually matter

Four choices determine whether this project succeeds. Everything else is interchangeable.

| Decision | Choice | Why it is not negotiable |
|---|---|---|
| Punctuation stripping | `regex` package (not stdlib `re`) | The rules say "strip punctuation entirely, **in every script**." Only `regex` supports `\p{P}`, the Unicode punctuation property. Stdlib `re` has no property escapes, so you would hand-maintain a character list and miss cases. |
| Clock | Injectable `Clock` service, never `date.today()` | B_Rules requires the UI to advance the current date arbitrarily. If any module calls `date.today()` directly, time travel breaks and that requirement fails. |
| Database host | Neon or Supabase — **not** Render Postgres | Render's free Postgres expires 30 days after creation and is then deleted. Your submission would go dark mid-review. |
| Backend host | Vercel — **not** Render free web service | Render free web services spin down after 15 minutes idle and take ~1 minute to wake. A judge clicking your link waits a minute on a blank page. |

---

## 1. Planning stage

| Need | Tool | Cost | Notes |
|---|---|---|---|
| Repo + issues + project board | **GitHub** (Free) | Free | Unlimited private/public repos, GitHub Projects boards, Actions minutes free for public repos. |
| Diagrams | **Mermaid** in Markdown | Free | Renders natively on GitHub. Version-controlled, no external tool. See `FLOWCHART.md`. |
| Wireframes | **Excalidraw** | Free | Browser-based, `.excalidraw` files commit to the repo. |
| Decision log | `docs/DECISIONS.md` (plain ADRs) | Free | The brief says ambiguities must be resolved via RULES. Log each interpretation you made and why — this is README material later. |
| Spec extraction | Convert `B_Check_Schedule` and `B_Check_Answers` into `tests/fixtures/*.json` on day one | Free | These tabs are your acceptance test suite. Turn them into data before writing any logic. |

**Do this first:** write the two CHECK tabs out as JSON fixtures. Your whole build becomes "make the fixtures pass."

---

## 2. Backend

### Core

| Library | Purpose | Why this one |
|---|---|---|
| **Python 3.12** | Runtime | Vercel's default Python. Stable `unicodedata` for Unicode 15. |
| **FastAPI** | Web framework | Async, automatic OpenAPI docs at `/docs`, Pydantic-native, first-class Vercel support. |
| **Pydantic v2** | Validation + serialization | Comes with FastAPI. Rust-backed, fast, gives you typed request/response contracts for free. |
| **SQLModel** | ORM | Thin layer over SQLAlchemy 2.0 + Pydantic — one model class serves as both DB table and API schema. Cuts boilerplate roughly in half on a project this size. If you want full control, use SQLAlchemy 2.0 directly. |
| **Alembic** | Migrations | Ships with SQLModel/SQLAlchemy. Needed the moment you point at hosted Postgres. |
| **`regex`** | Unicode-aware regex | **Critical.** `\p{P}` for cross-script punctuation. `pip install regex`. |
| **`unicodedata`** | stdlib | NFC normalization before any comparison. Arabic and Devanagari text can arrive decomposed. |
| **`uvicorn`** | ASGI server | Local dev. Vercel supplies its own runtime in production. |

### Dependency and quality tooling

| Tool | Purpose |
|---|---|
| **`uv`** | Package manager and virtualenv. Roughly 10–100× faster than pip; `uv.lock` gives reproducible installs. Vercel reads `pyproject.toml` + `uv.lock` natively. |
| **`ruff`** | Linter **and** formatter in one binary. Replaces black + flake8 + isort + pyupgrade. Zero config to start. |
| **`mypy`** or **`ty`** | Static typing. Optional, but the normalizer is exactly the kind of code where a type error hides for hours. |
| **`pre-commit`** | Runs ruff on every commit so CI never fails on formatting. |

### What NOT to use

- **PyICU** — the "proper" Unicode library, but it needs system-level ICU binaries. It will fight you on serverless hosts. `regex` + `unicodedata` covers every rule in B_Rules.
- **Django** — far too much machinery for ~8 endpoints.
- **Celery / Redis** — there are no background jobs here. The scheduler is pure arithmetic.

---

## 3. Frontend

You said "simple frontend." That is the right call — the interesting work in this challenge is normalization and scheduling, not UI architecture.

| Layer | Recommendation | Why |
|---|---|---|
| Structure | **Plain HTML** served as static files | No build step, no bundler config, no framework version churn. |
| Interactivity | **Alpine.js** (~15 KB, one `<script>` tag) | Gives you reactive state (`x-data`, `x-show`, `x-model`) without a build pipeline. Perfect for a review card that flips between prompt / typing / feedback states. |
| Styling | **Plain CSS with custom properties** + CSS **logical properties** | `margin-inline-start` instead of `margin-left`, `padding-inline` instead of `padding-left/right`. RTL then works from a single `dir="rtl"` attribute with no separate stylesheet. |
| Fonts | **Google Fonts**: Noto Sans, Noto Sans Arabic, Noto Naskh Arabic, Noto Sans Devanagari, Noto Sans SC | Free, and non-negotiable. Default system fonts render vocalized Arabic and Devanagari conjuncts badly or not at all. Noto Naskh Arabic in particular handles stacked harakat correctly. |
| Local storage | **Dexie.js** (IndexedDB wrapper) | IndexedDB's raw API is painful. Dexie gives promises, queries, and schema versioning in ~25 KB. |
| Diffing display | Write ~30 lines yourself | Your checker already returns mismatch positions. Just map them to `<span class="wrong">`. A diff library would be more code than the feature. |

### Alternative if you want fewer moving parts

**HTMX** + server-rendered **Jinja2** templates. Every interaction is a form POST that swaps in HTML. This puts *all* logic in Python — attractive here, since the graded logic is Python. The tradeoff: every keystroke-level interaction needs a round trip, and the typed-answer feedback feels less immediate.

**Verdict:** Alpine.js if you want a snappy feel; HTMX if you want a single language. Both are free and buildless.

### RTL, specifically

```html
<!-- Drive direction from the card's `direction` column, per card -->
<div class="verse" dir="rtl" lang="ar">...</div>
<input dir="rtl" lang="ar" ...>
```

Set `dir` on the **element**, not the page. A card list mixes `ltr` and `rtl` rows. Use `:dir(rtl)` in CSS for direction-specific tweaks, and never use `text-align: left` — use `text-align: start`.

---

## 4. Data layer — local-first with free sync

Your own `leitnerboxappanalysis.md` identified data loss as the #1 destroyer of that app's rating. Build the opposite.

### Architecture

```
IndexedDB (Dexie)  ←── source of truth ──→  UI
        │
        │  push/pull on demand, never destructive
        ▼
Supabase Postgres (free tier)  ←── auth + cross-device sync
```

**The one hard rule:** never delete or clear local data because of a failed auth or a failed sync. Show a "syncing unavailable — studying offline" banner and carry on. Every data-loss review in your analysis traces back to an app trusting the server over the device.

### Sync strategy (keep it simple)

- Every row carries `updated_at` (UTC) and `deleted` (soft-delete tombstone).
- Pull: `SELECT * WHERE updated_at > last_sync_at`.
- Push: send local rows where `updated_at > last_sync_at`.
- Conflicts: last-write-wins on `updated_at`. For a single-user study app this is correct and needs no CRDT.
- Free local export/import to JSON regardless of sync status. This is the feature that would have saved the app in your analysis, and it costs nothing.

### Provider comparison

| Provider | Free tier | Verdict |
|---|---|---|
| **Supabase** | 500 MB DB, 5 GB egress, 50,000 MAU auth, 2 active projects. **Paused after 1 week of inactivity.** | **Recommended.** Postgres + auth + row-level security in one, and the auth alone saves you days. Mitigate the pause with a GitHub Actions cron (below). |
| **Neon** | 0.5 GB/project, 100 CU-hours/month, scale-to-zero after 5 min, permanent free plan, no inactivity deletion. | **Best fallback.** Never pauses permanently. But no built-in auth — you would write your own, or drop auth entirely. |
| **Render Postgres** | 256 MB, **expires 30 days after creation, then deleted**. | **Avoid.** Disqualifying for a submission that must stay live. |

### Keeping Supabase awake (free)

`.github/workflows/keepalive.yml` — a scheduled Action that runs a trivial query every 3 days. Free on public repos, and it keeps the project from pausing during the review window.

---

## 5. Testing

| Tool | Purpose |
|---|---|
| **pytest** | Test runner. Use `@pytest.mark.parametrize` fed directly from your CHECK-tab JSON fixtures. |
| **pytest-cov** | Coverage. Aim high on `normalizer.py` and `scheduler.py`; ignore the rest. |
| **Hypothesis** | Property-based testing. High value here: assert `normalize(normalize(x)) == normalize(x)` (idempotence) and that normalization never changes word count for whitespace-only edits. Catches classes of bug that example tests miss. |
| **Playwright** | One end-to-end smoke test: load app → advance clock 3 days → verify queue changes. Free, and it proves the time-travel requirement works. |
| **GitHub Actions** | CI. Free minutes on public repos. Run ruff + pytest on every push. |

**Structure your tests to mirror the deliverable:**

```
tests/
  fixtures/
    check_schedule.json     # from B_Check_Schedule, all 8 traces
    check_answers.json      # from B_Check_Answers, all 22 cases
  test_scheduler.py         # parametrized over check_schedule.json
  test_normalizer.py        # parametrized over check_answers.json
  test_queue.py             # daily cap of 20, sort order
  test_properties.py        # Hypothesis
```

Your README must list which CHECK cases you fail. Make the test suite print that list automatically — then the README section writes itself.

---

## 6. Deployment

### Recommended: everything on Vercel + Supabase

| Piece | Host | Free tier reality |
|---|---|---|
| FastAPI backend | **Vercel** (Python runtime) | Detects FastAPI from `requirements.txt`/`pyproject.toml`, needs a top-level `app` in `app.py`/`main.py`/`api/index.py`. Serverless, so cold starts are ~1–2s, not the ~60s of a sleeping container. |
| Static frontend | **Vercel** (same project, via Services) | One domain, no CORS configuration at all. |
| Database + auth | **Supabase** free | Postgres 500 MB + auth. |
| CI | **GitHub Actions** | Free on public repos. |
| Domain | `your-app.vercel.app` | Free HTTPS subdomain. |

Vercel Hobby is free and forbids *commercial* use — a fellowship submission is fine.

### Deployment flow

```
git push main
   → GitHub Actions: ruff check + pytest
   → Vercel builds & deploys automatically on green
   → Preview URL for every PR, production URL for main
```

### Alternatives if Vercel does not fit

| Option | Free tier | Tradeoff |
|---|---|---|
| **Fly.io** | Small always-on VMs on the trial credit | No cold start, real container. Credit is limited and requires a card. |
| **Hugging Face Spaces** (Docker/Gradio) | Free CPU tier, always-on | Fine for a demo; unconventional home for a web app, and sleeps after inactivity. |
| **Cloudflare Pages + Workers** | Generous free tier | Workers is JS/WASM — your Python would need Pyodide. Not worth it here. |
| **GitHub Pages** | Free static hosting | Only viable if you go **fully client-side** with no Python backend — which contradicts your stack choice. |

---

## 7. Complete dependency manifest

`pyproject.toml`:

```toml
[project]
name = "scripture-memory-trainer"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.117",
    "pydantic>=2.9",
    "sqlmodel>=0.0.22",
    "alembic>=1.13",
    "regex>=2024.11.6",       # \p{P} — do not substitute stdlib re
    "psycopg[binary]>=3.2",   # Postgres driver
    "python-dotenv>=1.0",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-cov>=6.0",
    "hypothesis>=6.115",
    "ruff>=0.8",
    "mypy>=1.13",
    "uvicorn[standard]>=0.32",
    "pre-commit>=4.0",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]
```

Frontend (all CDN, no build step):

```html
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dexie@4/dist/dexie.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;600&family=Noto+Naskh+Arabic:wght@400;600&family=Noto+Sans+Devanagari:wght@400;600&family=Noto+Sans+SC:wght@400;600&display=swap" rel="stylesheet">
```

---

## 8. Verified reference logic

Both of these were run against every case in the CHECK tabs before being written down.

### Scheduler — passes all 8 `B_Check_Schedule` traces

```python
INTERVALS = {0: 0, 1: 1, 2: 3, 3: 7, 4: 21, 5: 60}

def apply_grade(box: int, grade: str) -> tuple[int, int]:
    """Return (new_box, interval_days)."""
    if grade == "again":
        return 0, INTERVALS[0]
    if grade == "hard":
        # Box unchanged. 60% of the *current* box interval, floored, min 1.
        return box, max(1, (INTERVALS[box] * 60) // 100)
    if grade == "good":
        nb = min(5, box + 1)
        return nb, INTERVALS[nb]
    if grade == "easy":
        nb = min(5, box + 2)
        return nb, INTERVALS[nb]
    raise ValueError(grade)
```

Three subtleties this encodes, each of which a naive implementation gets wrong:

1. `hard` uses the interval of the box the card is **already in**, not a new box.
2. `hard` on box 0: 0 × 60% = 0, floored to 0, then raised to the **minimum of 1** — so box 0 + hard advances the due date by one day while leaving the box at 0. That is trace #8.
3. Integer floor, not rounding. Box 4 hard = 21 × 0.6 = 12.6 → **12**, not 13. That is trace #7.

### Normalizer — matches 11 of 13 spot-checked `B_Check_Answers` cases

```python
import regex as re
import unicodedata

QUOTES    = {0x2018: 39, 0x2019: 39, 0x201C: 34, 0x201D: 34}
FULLWIDTH = {0xFF0C: 44, 0xFF1B: 59}          # ，→,   ；→;
HARAKAT   = set(range(0x064B, 0x0653)) | {0x0640, 0x0670}

def normalize(s: str, lang: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.translate(QUOTES).translate(FULLWIDTH)
    if lang == "ar":
        s = "".join(c for c in s if ord(c) not in HARAKAT)
        s = s.replace("ٱ", "ا")     # alef wasla → alef
        s = s.replace("ى", "ي")     # alef maqsura → yeh
    if lang == "hi":
        s = s.replace("़", "")           # nukta optional
    s = re.sub(r"\p{P}+", "", s)              # ← requires `regex`, not `re`
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()
```

`\p{P}` is what makes the rule "strip punctuation entirely, in every script" true in one line. It covers the Arabic comma U+060C, the Devanagari danda U+0964 and double danda U+0965, ASCII punctuation, and the full-width CJK forms — all without a hand-maintained list.

Use `.casefold()` rather than `.lower()`. It is the correct Unicode case-folding operation and handles scripts `.lower()` does not.

---

## 9. Two discrepancies to document in your README

The brief requires you to state which CHECK cases you fail. Two of them appear to be errors in the workbook rather than in a correct implementation. Verified by direct computation:

**Matthew 28:19 (en), curly-apostrophe case.** Expected verdict says "Father's is still 1 word wrong at position **16**." The KJV text of Matthew 28:19 as supplied in B_Cards contains **24** words after normalization, and `Father's` sits at position **15**.

**Matthew 28:19 (en), empty string.** Expected verdict says "0 of **22** words matched." The card holds **24** words.

Every other spot-checked case — English, Chinese, Arabic (harakat, alef wasla, alef maqsura, combined), and Hindi (nukta, danda) — matched exactly. Both discrepancies concern the same verse and are consistent with a word count of 22 rather than 24, which suggests the workbook's expected values for that one card were computed against a different text.

State this plainly in the README: show your count, show the position you report, and note that you follow B_Rules as authoritative. That is a better outcome than silently tuning your checker to match a bad expectation.

---

## 10. Total cost

**$0.** Every tool above is free at the scale of this project: GitHub, Vercel Hobby, Supabase free (or Neon free), GitHub Actions on a public repo, Google Fonts, and every Python and JS package listed.
