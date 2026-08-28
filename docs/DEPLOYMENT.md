# Deployment runbook — Phases 5 and 6

Everything up to Phase 4 runs with no account anywhere: `uv sync`,
`alembic upgrade head`, a SQLite file, `uvicorn`. Phases 5 and 6 are the point
where that stops being true. This document is the full sequence for both, with
the decisions called out before they bite.

**Nothing in this file has been done yet.** It is written so you can do it in
order, and so the parts that need a decision from you are visible before you
start paying for anything.

---

## Before you start: three things that will surprise you

**1. Your production database cannot be SQLite.** Vercel's filesystem is
read-only apart from `/tmp`, and `/tmp` is per-invocation. A SQLite file there
would appear empty on the next request. Postgres is not optional once you
deploy — it is the reason Phase 5 comes before Phase 6.

**2. The schema has no owner column yet.** `Card`, `CardState`, `ReviewLog` and
`AppState` carry `updated_at` and `deleted`, which is what sync needs, but there
is no `user_id`. Row-level security has nothing to filter on until you add one.
That migration is step 5.4 below and it is the largest single piece of work left
in the project — plan for it rather than discovering it.

**3. Free Supabase projects pause after 7 days with no activity.** A paused
project fails every query, so a reviewer opening your link three weeks from now
sees an error. The keepalive workflow in Phase 6 exists for exactly this, and it
is worth setting up the same day you create the project.

---

## Phase 5 — Supabase

### 5.1 Create the project (5 minutes, needs an account)

1. Sign up at <https://supabase.com> — GitHub sign-in is fine.
2. **New project.** Name it `scripture-memory-trainer`.
3. **Database password:** generate one and put it in your password manager
   immediately. Supabase shows it once. You will need it in 5.2.
4. **Region:** pick the one nearest whoever will be marking this. Every query
   from Vercel crosses that distance.
5. Wait for provisioning (~2 minutes).

### 5.2 Get the connection string

1. Project → **Connect** (top bar) → **Connection string** → **Session pooler**.
2. Copy the URI. It looks like:

   ```
   postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-eu-west-2.pooler.supabase.com:5432/postgres
   ```

3. **Use the session pooler, not the direct connection.** The direct host is
   IPv6-only on the free tier; GitHub Actions runners and Vercel functions are
   IPv4, and a direct URL fails there with a network error that looks like a
   credentials problem.
4. Rewrite the scheme for SQLAlchemy — `postgresql://` becomes
   `postgresql+psycopg://`, because this project uses psycopg 3:

   ```
   postgresql+psycopg://postgres.abcdefgh:YOUR-PASSWORD@aws-0-eu-west-2.pooler.supabase.com:5432/postgres
   ```

5. Put it in `.env` at the repo root (which is already gitignored):

   ```
   DATABASE_URL=postgresql+psycopg://postgres.abc...:PASSWORD@...pooler.supabase.com:5432/postgres
   ```

### 5.3 Point the existing app at Postgres — no code changes

This is the check that the `DATABASE_URL` design (D14) actually paid off:

```bash
uv run alembic upgrade head          # creates all four tables in Supabase
uv run python -m scripture_memory_trainer   # seeds the 32 cards
uv run uvicorn scripture_memory_trainer.api:app --reload
```

Open <http://127.0.0.1:8000> and study a card. If that works, the whole
backend is running on Postgres and only the auth and sync layers are left.

**Verify in Supabase:** Table Editor should show `card` (32 rows), `cardstate`
(32), `reviewlog` and `appstate`. If `alembic upgrade head` reports
"Target database is not up to date", you are still pointed at SQLite — check
that `.env` is being read.

### 5.4 Add ownership to the schema (the real work)

Row-level security filters rows by user. Right now there is no user on a row.

1. **Add the column** to each of the four tables in `tables.py`:

   ```python
   user_id: uuid.UUID | None = Field(default=None, index=True)
   ```

   Nullable, because every row that exists today has no owner. A `NOT NULL`
   column here means writing a data migration for rows you do not yet need to
   keep.

2. **Generate and review the migration:**

   ```bash
   uv run alembic revision --autogenerate -m "Add user_id for row-level security"
   ```

   Read the generated file before applying it. Autogenerate is good but not
   trustworthy — it has been known to drop and recreate indexes.

3. **Decide what a shared card means.** The 32 seed verses are the same for
   everyone. Two workable answers:
   - **Cards are global, state is per user.** `card.user_id` stays null and its
     RLS policy allows any authenticated read; `cardstate`, `reviewlog` and
     `appstate` are per user. Less duplication, and a corrected verse reaches
     everyone.
   - **Everything is per user**, seeded per account on first sign-in. Simpler
     policies, 32 duplicate rows per user.

   The first is better and is what the policies below assume. Record whichever
   you choose in `DECISIONS.md`.

4. **Enable RLS and write the policies.** Supabase → SQL Editor:

   ```sql
   alter table card      enable row level security;
   alter table cardstate enable row level security;
   alter table reviewlog enable row level security;
   alter table appstate  enable row level security;

   -- Cards are shared reference data: any signed-in user may read them.
   create policy "cards are readable by authenticated users"
     on card for select to authenticated using (true);

   -- Everything else is private to its owner, for every verb.
   create policy "own card state" on cardstate for all to authenticated
     using (auth.uid() = user_id) with check (auth.uid() = user_id);
   create policy "own review log" on reviewlog for all to authenticated
     using (auth.uid() = user_id) with check (auth.uid() = user_id);
   create policy "own app state"  on appstate  for all to authenticated
     using (auth.uid() = user_id) with check (auth.uid() = user_id);
   ```

5. **Verify the policies actually bite.** Create two accounts, study different
   cards on each, and confirm neither can see the other's boxes. A policy that
   is enabled but never tested is a policy you are guessing about. Note that
   the `postgres` connection string used by the backend **bypasses RLS** — RLS
   protects the anon-key path the browser uses, not the service path.

### 5.5 Supabase Auth, email sign-in

1. Supabase → **Authentication** → **Providers** → Email. Enable it.
2. For a demo, turn **Confirm email** off — otherwise every reviewer who tries
   your link waits for a message that may land in spam. Turn it back on if this
   ever holds real user data.
3. Copy **Project URL** and the **anon/publishable key** from Project Settings →
   API. The anon key is designed to be public; it is safe in `index.html`. The
   **service_role key is not** — it bypasses RLS. Never put it in the frontend,
   in a commit, or in a Vercel environment variable that the browser can read.
4. In `web/index.html`, add the Supabase client next to Alpine and Dexie:

   ```html
   <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
   ```

   and a sign-in panel that calls `signInWithOtp` or
   `signInWithPassword`. Keep it out of the study flow: the app already works
   signed out, and it must keep working that way (the export button is the
   promise that your data is never held hostage).

### 5.6 Push and pull

The merge rule already exists — `service.import_payload()` is last-write-wins on
`updated_at`, honours tombstones, and is idempotent (D17). Sync is that rule
pointed at two directions:

- **Push:** rows where `updated_at > last_sync_at`, sent to Supabase.
- **Pull:** rows where `updated_at > last_sync_at`, merged locally with the same
  comparison.
- Store `last_sync_at` in Dexie, not in the synced tables — it is a property of
  this device, not of the account.
- `updated_at` is real UTC and never the travellable app clock (D15), so a user
  who has jumped 60 days forward does not win every merge.

### 5.7 Test the failure paths explicitly

The checklist calls these out because they are the ones that get skipped:

- [ ] Sign out mid-session — the current card and the local mirror survive.
- [ ] Kill the network mid-session — the "studying offline" banner appears and
      the queue still builds from Dexie.
- [ ] Expired token — the app degrades to offline rather than erroring blank.
- [ ] Sign in on a second device — boxes and due dates arrive intact.
- [ ] Study the same card offline on two devices, then reconnect — the later
      `updated_at` wins and nothing is lost.
- [ ] Export while signed out — must work. No account, no lock-in.

---

## Phase 6 — CI and deploy

### 6.1 Push the work that exists

Seven commits are sitting on your machine unpushed:

```bash
git push origin main
```

Everything below assumes that has happened.

### 6.2 GitHub Actions

`.github/workflows/ci.yml` — ruff, mypy and pytest on every push. The suite
needs no database (every test builds its own SQLite in a temp directory), so CI
needs no secrets.

`.github/workflows/keepalive.yml` — cron every 3 days, one trivial query, so
the free Supabase project never idles into a pause. It needs `DATABASE_URL` as a
**GitHub Actions secret** (Settings → Secrets and variables → Actions). Note
that GitHub disables scheduled workflows in repos with no activity for 60 days;
a paused keepalive is worth a calendar reminder before submission.

I can write both files whenever you say — they need no account, only the push.

### 6.3 Vercel

1. <https://vercel.com> → **Add New** → **Project** → import the GitHub repo.
2. **Framework preset:** Other. Vercel does not detect FastAPI.
3. **Environment variables** (Settings → Environment Variables), for Production
   *and* Preview:
   - `DATABASE_URL` — the session-pooler URI from 5.2.
   - `SUPABASE_URL` and `SUPABASE_ANON_KEY` if the frontend reads them from a
     config endpoint rather than a hardcoded literal.
4. **`vercel.json`** is required — this is a Python ASGI app, not a Next.js
   site. It also needs `excludeFiles` to keep `tests/` and `seed/` out of the
   function bundle, per the checklist.
5. **Migrations do not run on Vercel.** The build step has no database access
   and serverless functions must not run migrations on cold start — concurrent
   invocations would race. Run `alembic upgrade head` from your machine against
   the production `DATABASE_URL`, or add a manual GitHub Actions job that does
   it. Same for the seed.
6. **Cold starts:** a free Vercel Python function that has not been hit in a
   while takes a few seconds to wake, and Supabase's pooler adds its own
   connection setup. The first page load after a quiet period is slow. This is
   worth one sentence in the README so a reviewer does not read it as a bug.

### 6.4 The smoke test

One Playwright test — load, advance the clock 3 days, confirm the queue
changes — run against the deployed URL. That single test covers the frontend,
the API, the database and the clock in one pass, which is why it is the one
worth having.

### 6.5 Pre-submission checks

- [ ] Open the production URL in a private window. It must work signed out.
- [ ] Study one Arabic card end to end. Fonts load, direction is right to left.
- [ ] Advance the clock 60 days and watch the queue change. This is the ten-second
      demo and it must not need a sign-in.
- [ ] `/docs` renders on production.
- [ ] Export downloads a file; import restores it.
- [ ] Load it on a phone.
- [ ] Confirm no key, password or connection string appears in
      `git log -p | grep -i` for your Supabase host.

### Rollback

Vercel keeps every deployment. Promoting the previous one from the dashboard is
instant and needs no rebuild. A schema migration is the part that does not roll
back automatically: take a Supabase backup before applying one to production
(Database → Backups), and prefer additive migrations — a nullable column added
is safe to leave in place while you revert the code that reads it.
