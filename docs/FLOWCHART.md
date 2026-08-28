# Scripture Memory Trainer — Project Flowchart

Nine diagrams, from project lifecycle down to the character-level answer-checking pipeline. All Mermaid — they render natively on GitHub.

---

## 1. Project lifecycle — planning to production

```mermaid
flowchart TD
    subgraph PLAN["PHASE 0 — Planning"]
        P1["Read B_Rules end to end<br/>RULES is authoritative over intuition"]
        P2["Extract B_Cards to seed/cards.json<br/>32 cards, 8 refs x 4 languages"]
        P3["Extract B_Check_Schedule to<br/>tests/fixtures/check_schedule.json<br/>8 grade traces"]
        P4["Extract B_Check_Answers to<br/>tests/fixtures/check_answers.json<br/>22 verdict cases"]
        P5["Write docs/DECISIONS.md<br/>log every rule interpretation"]
        P6["Sketch UI in Excalidraw<br/>review card, queue, clock control"]
    end

    subgraph CORE["PHASE 1 — Pure logic, no I/O"]
        C1["scheduler.py<br/>apply_grade box grade"]
        C2["normalizer.py<br/>normalize text lang"]
        C3["checker.py<br/>compare card input lang"]
        C4["clock.py<br/>injectable Clock service"]
        C5["queue.py<br/>build daily queue, cap 20"]
    end

    subgraph TEST["PHASE 2 — Prove it"]
        T1["pytest parametrized<br/>over both fixture files"]
        T2["Hypothesis property tests<br/>idempotence, invariants"]
        T3["Record every failing CHECK case"]
    end

    subgraph API["PHASE 3 — Backend"]
        A1["SQLModel schema + Alembic migration"]
        A2["FastAPI routes"]
        A3["Seed loader for cards.json"]
    end

    subgraph UI["PHASE 4 — Frontend"]
        U1["Static HTML + Alpine.js"]
        U2["Dexie IndexedDB local store"]
        U3["RTL and multi-script rendering"]
        U4["Clock control in header"]
    end

    subgraph SYNC["PHASE 5 — Local-first sync"]
        S1["Supabase auth"]
        S2["Push/pull on updated_at"]
        S3["JSON export/import, always free"]
    end

    subgraph SHIP["PHASE 6 — Deploy"]
        D1["GitHub Actions: ruff + pytest"]
        D2["Vercel auto-deploy on green main"]
        D3["Supabase keepalive cron"]
        D4["README with failing-case list"]
    end

    PLAN --> CORE --> TEST
    TEST -->|"all fixtures pass"| API
    TEST -->|"failures found"| CORE
    API --> UI --> SYNC --> SHIP

    style PLAN fill:#e8f0fe,stroke:#4285f4
    style CORE fill:#fce8e6,stroke:#ea4335
    style TEST fill:#fef7e0,stroke:#fbbc04
    style API fill:#e6f4ea,stroke:#34a853
    style UI fill:#f3e8fd,stroke:#a142f4
    style SYNC fill:#e0f7fa,stroke:#00acc1
    style SHIP fill:#eceff1,stroke:#546e7a
```

---

## 2. System architecture

```mermaid
flowchart TB
    subgraph BROWSER["Browser — the source of truth"]
        HTML["index.html<br/>Alpine.js components"]
        DEXIE[("IndexedDB via Dexie<br/>cards, reviews, state")]
        EXPORT["JSON export / import<br/>always available, never paywalled"]
        HTML <--> DEXIE
        DEXIE --> EXPORT
    end

    subgraph VERCEL["Vercel — free Hobby tier"]
        STATIC["Static assets<br/>HTML, CSS, JS, fonts"]
        subgraph FASTAPI["FastAPI on Python runtime"]
            ROUTES["Routes<br/>/api/cards /api/queue<br/>/api/review /api/clock"]
            SCHED["scheduler.py<br/>Leitner box arithmetic"]
            NORM["normalizer.py<br/>regex \\p{P} + unicodedata"]
            CHECK["checker.py<br/>positional comparison"]
            CLOCK["clock.py<br/>offset-aware today"]
            ROUTES --> SCHED
            ROUTES --> NORM --> CHECK
            ROUTES --> CLOCK
        end
    end

    subgraph SUPA["Supabase — free tier"]
        AUTH["Auth<br/>50k MAU"]
        PG[("Postgres 500 MB<br/>cards, reviews, users")]
    end

    subgraph GH["GitHub"]
        REPO["Repository"]
        ACTIONS["Actions<br/>ruff + pytest + keepalive"]
    end

    HTML -->|"fetch, verdict + schedule"| ROUTES
    HTML -->|"static load"| STATIC
    DEXIE <-->|"push/pull on updated_at<br/>NEVER destructive"| PG
    HTML <--> AUTH
    ROUTES <--> PG
    REPO --> ACTIONS -->|"deploy on green"| VERCEL
    ACTIONS -->|"cron every 3 days<br/>prevent 1-week pause"| PG

    style BROWSER fill:#f3e8fd,stroke:#a142f4
    style VERCEL fill:#e6f4ea,stroke:#34a853
    style SUPA fill:#e0f7fa,stroke:#00acc1
    style GH fill:#eceff1,stroke:#546e7a
```

---

## 3. User journey

```mermaid
flowchart TD
    START(["Open app"]) --> LOAD["Load local DB from IndexedDB"]
    LOAD --> SEEDED{"Cards seeded?"}
    SEEDED -->|No| SEED["Import 32 cards from seed<br/>all start box 0, due immediately"]
    SEEDED -->|Yes| AUTHQ
    SEED --> AUTHQ{"Signed in?"}

    AUTHQ -->|Yes| SYNCTRY["Attempt sync"]
    AUTHQ -->|No| HOME
    SYNCTRY --> SYNCOK{"Reachable?"}
    SYNCOK -->|Yes| MERGE["Merge remote into local<br/>last-write-wins on updated_at"]
    SYNCOK -->|No| BANNER["Show banner:<br/>sync unavailable, studying offline<br/>LOCAL DATA UNTOUCHED"]
    MERGE --> HOME
    BANNER --> HOME

    HOME["Home screen<br/>due count per box, streak,<br/>current app date"]

    HOME --> ACT{"What next?"}
    ACT -->|Study| QUEUE["Build today's queue"]
    ACT -->|"Time travel"| CLOCKUI["Clock control<br/>advance N days"]
    ACT -->|Browse| BROWSE["Card list<br/>filter by language, box, due date"]
    ACT -->|Backup| BACKUP["Export all data to JSON"]
    ACT -->|Settings| SET["Language filter, direction, font size"]

    CLOCKUI --> QUEUE
    QUEUE --> EMPTY{"Queue empty?"}
    EMPTY -->|Yes| DONE["Nothing due<br/>show next due date<br/>offer clock advance"]
    EMPTY -->|No| SESSION["REVIEW SESSION<br/>see diagram 4"]
    SESSION --> SUMMARY["Session summary<br/>graded counts, next due dates"]
    SUMMARY --> HOME
    DONE --> HOME
    BROWSE --> HOME
    BACKUP --> HOME
    SET --> HOME

    style BANNER fill:#fef7e0,stroke:#fbbc04,stroke-width:3px
    style SESSION fill:#fce8e6,stroke:#ea4335
    style CLOCKUI fill:#e8f0fe,stroke:#4285f4
```

---

## 4. Review session loop

```mermaid
flowchart TD
    ENTER(["Enter session with queue"]) --> POP["Take next card from queue"]
    POP --> RENDER["Render prompt<br/>reference + language label<br/>set dir from card.direction"]

    RENDER --> MODE{"Review mode"}
    MODE -->|"Typed recall"| TYPE["Show empty input<br/>dir and lang match card<br/>Noto font for script"]
    MODE -->|"Self-graded"| REVEAL["Show 'Reveal' button"]

    TYPE --> SUBMIT["User submits answer"]
    SUBMIT --> PIPELINE["ANSWER-CHECKING PIPELINE<br/>see diagram 5"]
    PIPELINE --> VERDICT{"Verdict"}

    VERDICT -->|Correct| SHOWC["Green result<br/>full verse displayed"]
    VERDICT -->|Partial| SHOWP["Amber result<br/>N of M units matched<br/>highlight each mismatch position<br/>show missing tail from position K"]
    VERDICT -->|Incorrect| SHOWI["Red result<br/>0 matched<br/>full verse displayed"]

    SHOWC --> GRADEUI
    SHOWP --> GRADEUI
    SHOWI --> GRADEUI
    REVEAL --> SHOWFULL["Display full verse"] --> GRADEUI

    GRADEUI["Grade buttons<br/>again / hard / good / easy<br/>each shows its resulting next-due date"]
    GRADEUI --> GRADE["User picks grade"]

    GRADE --> APPLY["SCHEDULER<br/>see diagram 6"]
    APPLY --> PERSIST["Write to IndexedDB:<br/>new box, new due date,<br/>review log row, updated_at = now"]
    PERSIST --> QUEUECHK{"Grade was 'again'<br/>and box reset to 0?"}

    QUEUECHK -->|Yes| REQUEUE["Due same day —<br/>push back onto today's queue"]
    QUEUECHK -->|No| NEXT
    REQUEUE --> NEXT{"Queue empty?"}
    NEXT -->|No| POP
    NEXT -->|Yes| END(["Session summary"])

    style PIPELINE fill:#fce8e6,stroke:#ea4335,stroke-width:3px
    style APPLY fill:#e6f4ea,stroke:#34a853,stroke-width:3px
    style SHOWP fill:#fef7e0,stroke:#fbbc04
```

---

## 5. Answer-checking pipeline — the hard part

```mermaid
flowchart TD
    IN(["card.text, user.input, card.language"]) --> NFC["Unicode NFC normalize both strings<br/>Arabic and Devanagari may arrive decomposed"]

    NFC --> QUOTE["Normalize quotes<br/>U+2018 U+2019 to apostrophe<br/>U+201C U+201D to quote"]
    QUOTE --> FW["Normalize full-width forms<br/>U+FF0C to comma<br/>U+FF1B to semicolon"]

    FW --> LANGSW{"card.language"}

    LANGSW -->|ar| AR1["Strip harakat — optional diacritics<br/>U+064B through U+0652<br/>plus U+0640 tatweel, U+0670 dagger alef"]
    AR1 --> AR2["Normalize alef forms<br/>U+0671 alef wasla to U+0627 plain alef"]
    AR2 --> AR3["Normalize yeh forms<br/>U+0649 alef maqsura to U+064A yeh"]
    AR3 --> PUNCT

    LANGSW -->|hi| HI1["Strip nukta U+093C — optional"]
    HI1 --> PUNCT

    LANGSW -->|zh| ZH1["NO script conversion<br/>traditional does NOT equal simplified<br/>this is a rule, not an oversight"]
    ZH1 --> PUNCT

    LANGSW -->|en| PUNCT

    PUNCT["Strip ALL Unicode punctuation<br/>regex \\p{P} plus — every script at once<br/>ASCII, U+060C Arabic comma,<br/>U+0964 danda, U+0965 double danda,<br/>U+FF0C full-width, CJK U+3002"]

    PUNCT --> WS["Collapse whitespace runs to one space<br/>then trim both ends"]
    WS --> CASE["casefold — Unicode case folding<br/>not .lower"]

    CASE --> EQ{"normalized card<br/>==<br/>normalized input?"}
    EQ -->|Yes| CORRECT(["CORRECT"])
    EQ -->|No| SPLITSW{"Is language Chinese?"}

    SPLITSW -->|"zh — no word boundaries"| SPLITCH["Split into characters<br/>remove all spaces first"]
    SPLITSW -->|"en, ar, hi"| SPLITWD["Split on whitespace into words"]

    SPLITCH --> COMPARE
    SPLITWD --> COMPARE

    COMPARE["Positional comparison<br/>zip card units with input units<br/>walk index by index"]

    COMPARE --> COUNT["Collect:<br/>matched count<br/>1-based position of each mismatch<br/>total card units"]
    COUNT --> TAIL{"len input < len card?"}

    TAIL -->|Yes| MISSING["Missing tail:<br/>units present in card, absent from input<br/>report count and first absent position"]
    TAIL -->|No| EXTRA{"len input > len card?"}
    EXTRA -->|Yes| SURPLUS["Report surplus units beyond card length"]
    EXTRA -->|No| BUILD

    MISSING --> BUILD
    SURPLUS --> BUILD

    BUILD["Build verdict object"] --> ZERO{"matched == 0?"}
    ZERO -->|Yes| INCORRECT(["INCORRECT<br/>0 of M units matched"])
    ZERO -->|No| PARTIAL(["PARTIAL<br/>N of M matched<br/>positions: list<br/>missing from position K"])

    style PUNCT fill:#fce8e6,stroke:#ea4335,stroke-width:3px
    style ZH1 fill:#fef7e0,stroke:#fbbc04,stroke-width:3px
    style CORRECT fill:#e6f4ea,stroke:#34a853
    style PARTIAL fill:#fef7e0,stroke:#fbbc04
    style INCORRECT fill:#fce8e6,stroke:#ea4335
```

---

## 6. Leitner scheduler decision tree

```mermaid
flowchart TD
    IN(["current box, grade, review date"]) --> G{"grade"}

    G -->|again| AG["new box = 0"]
    AG --> AGI["interval = INTERVALS[0] = 0 days"]
    AGI --> AGD["due = review date + 0<br/>SAME DAY — card returns to today's queue"]

    G -->|hard| HD["new box = current box<br/>UNCHANGED"]
    HD --> HDI["raw = INTERVALS[current box] x 60 / 100<br/>INTEGER FLOOR, not rounding"]
    HDI --> HDM["interval = max 1, raw<br/>minimum 1 day"]
    HDM --> HDD["due = review date + interval"]

    G -->|good| GD["new box = min 5, current + 1"]
    GD --> GDI["interval = INTERVALS[new box]"]
    GDI --> GDD["due = review date + interval"]

    G -->|easy| ES["new box = min 5, current + 2"]
    ES --> ESI["interval = INTERVALS[new box]"]
    ESI --> ESD["due = review date + interval"]

    AGD --> OUT
    HDD --> OUT
    GDD --> OUT
    ESD --> OUT
    OUT(["persist new box + due date<br/>append review log row"])

    style HDI fill:#fce8e6,stroke:#ea4335,stroke-width:3px
    style HDM fill:#fce8e6,stroke:#ea4335,stroke-width:3px
    style HD fill:#fef7e0,stroke:#fbbc04,stroke-width:2px
```

### Interval table and the three traps

| Box | Interval | `hard` result (60%, floored, min 1) |
|---|---|---|
| 0 | 0 days | 0 × 0.6 = 0 → floor 0 → **min 1 day**, box stays 0 |
| 1 | 1 day | 0.6 → floor 0 → **min 1 day** |
| 2 | 3 days | 1.8 → **1 day** |
| 3 | 7 days | 4.2 → **4 days** |
| 4 | 21 days | 12.6 → **12 days**, not 13 |
| 5 | 60 days | 36.0 → **36 days** (maximum box) |

1. **`hard` reads the interval of the box the card is already in** — not a new box, and not the base interval of box 0.
2. **Floor, never round.** Box 4 hard is 12 days. Rounding gives 13 and fails trace #7.
3. **`hard` on box 0 still advances by 1 day** thanks to the minimum, while leaving the box at 0. That is trace #8: three `hard` grades walk 09-01 → 09-02 → 09-03 → 09-04, box never leaves 0.

---

## 7. Daily queue construction

```mermaid
flowchart TD
    START(["Build queue for current app date"]) --> TODAY["today = Clock.today<br/>real date + user offset days"]
    TODAY --> FETCH["SELECT cards WHERE due_date <= today"]
    FETCH --> FILTER{"Language filter active?"}
    FILTER -->|Yes| LANGF["Keep only selected languages"]
    FILTER -->|No| SORT
    LANGF --> SORT

    SORT["SORT — three keys, in this order"]
    SORT --> K1["1. Most overdue first<br/>ascending due_date<br/>oldest due date wins"]
    K1 --> K2["2. Then lowest box first<br/>ascending box number"]
    K2 --> K3["3. Then reference A to Z<br/>STRING sort on the reference text<br/>NOT canonical Bible book order"]

    K3 --> CAP["Apply daily cap: take first 20"]
    CAP --> OVER{"More than 20 were due?"}
    OVER -->|Yes| NOTE["Surface the overflow count<br/>'20 of 47 due today'<br/>transparency, not silence"]
    OVER -->|No| EMIT
    NOTE --> EMIT
    EMIT(["Queue of at most 20 cards"])

    style K3 fill:#fef7e0,stroke:#fbbc04,stroke-width:3px
    style CAP fill:#e8f0fe,stroke:#4285f4,stroke-width:2px
    style NOTE fill:#e6f4ea,stroke:#34a853
```

**The trap in key 3:** "reference A-Z" is a plain string sort. `Isaiah 40:31` sorts before `John 3:16` before `Leviticus 19:34` before `Matthew 28:19` before `Philippians 4:13` before `Proverbs 3:5` before `Psalm 23:1` before `Romans 8:28`. That is alphabetical, not the order those books appear in scripture. Do not "helpfully" sort canonically.

**A second trap:** cards graded `again` become due the same day, so they re-enter today's queue. Decide and document whether a re-queued card counts a second time against the cap of 20. B_Rules does not say; log your reading in `DECISIONS.md`.

---

## 8. Time travel — the clock

```mermaid
flowchart LR
    subgraph FORBIDDEN["Never do this"]
        BAD["date.today called directly<br/>anywhere in the codebase"]
    end

    subgraph SERVICE["clock.py — single source of time"]
        OFFSET[("offset_days<br/>persisted in local DB")]
        FN["Clock.today returns<br/>real_today + offset_days"]
        OFFSET --> FN
    end

    subgraph CONSUMERS["Every consumer goes through it"]
        Q["queue.py — what is due"]
        S["scheduler.py — review date"]
        L["review log timestamps"]
        UI["Header date display"]
    end

    subgraph CONTROL["UI clock control — a graded requirement"]
        PLUS["+1 day / +7 days / +30 days"]
        SET["Jump to specific date"]
        RESET["Reset to real today"]
    end

    CONTROL -->|"writes"| OFFSET
    FN --> Q
    FN --> S
    FN --> L
    FN --> UI
    BAD -.->|"breaks time travel<br/>fails the requirement"| X(["Requirement not met"])

    style FORBIDDEN fill:#fce8e6,stroke:#ea4335,stroke-width:3px
    style SERVICE fill:#e6f4ea,stroke:#34a853,stroke-width:3px
    style CONTROL fill:#e8f0fe,stroke:#4285f4
```

B_Rules: *"The interface must let a reviewer advance the current date by an arbitrary number of days without editing code or system settings."* An offset stored in the DB and read through one `Clock` satisfies this, keeps tests deterministic, and means a judge can demonstrate 60-day intervals in five seconds.

---

## 9. Local-first sync and data safety

```mermaid
flowchart TD
    ACTION["User action — grade a card, edit, import"] --> LOCAL["Write to IndexedDB immediately<br/>set updated_at = now UTC"]
    LOCAL --> ACK["UI updates — action is already durable"]

    ACK --> ONLINE{"Signed in and online?"}
    ONLINE -->|No| QUEUEUP["Mark dirty, defer<br/>NO error shown, NO data touched"]
    ONLINE -->|Yes| PUSH["PUSH rows where updated_at > last_sync_at"]

    PUSH --> PUSHOK{"Push succeeded?"}
    PUSHOK -->|No| DEGRADE
    PUSHOK -->|Yes| PULL["PULL rows where updated_at > last_sync_at"]

    PULL --> PULLOK{"Pull succeeded?"}
    PULLOK -->|No| DEGRADE
    PULLOK -->|Yes| MERGE["MERGE into local<br/>per row: keep the higher updated_at<br/>tombstones honour deleted flag"]

    MERGE --> STAMP["last_sync_at = now"]
    STAMP --> IDLE(["Idle"])

    DEGRADE["Show banner:<br/>sync unavailable, studying offline"]
    DEGRADE --> RULE["HARD RULE<br/>never clear, wipe, or overwrite<br/>local data on auth or sync failure"]
    RULE --> IDLE
    QUEUEUP --> IDLE

    IDLE --> BACKUP{"User exports?"}
    BACKUP -->|Yes| JSON["Write full JSON to a file<br/>free, offline, no account needed"]
    JSON --> IDLE

    style RULE fill:#fce8e6,stroke:#ea4335,stroke-width:4px
    style LOCAL fill:#e6f4ea,stroke:#34a853,stroke-width:3px
    style JSON fill:#e8f0fe,stroke:#4285f4,stroke-width:2px
```

This is the direct answer to the failure mode catalogued in `leitnerboxappanalysis.md`: every data-loss report there traces to an app trusting the server over the device. Local is the source of truth; the server is a replica.

---

## 10. CI/CD pipeline

```mermaid
flowchart LR
    DEV["Local dev<br/>uv run uvicorn --reload"] --> PC["pre-commit<br/>ruff format + ruff check"]
    PC --> PUSH["git push"]
    PUSH --> GHA{"GitHub Actions"}

    GHA --> LINT["ruff check ."]
    GHA --> TYPES["mypy src/"]
    GHA --> UNIT["pytest — CHECK fixtures<br/>8 schedule traces<br/>22 answer cases"]
    GHA --> PROP["Hypothesis property tests"]

    LINT --> GATE
    TYPES --> GATE
    UNIT --> GATE
    PROP --> GATE

    GATE{"All green?"}
    GATE -->|No| FAIL["Block merge<br/>report which CHECK cases failed"]
    GATE -->|Yes| BRANCH{"Which branch?"}

    BRANCH -->|"pull request"| PREVIEW["Vercel preview deployment<br/>unique URL per PR"]
    BRANCH -->|main| PROD["Vercel production deployment"]

    PROD --> SMOKE["Playwright smoke test<br/>load, advance clock, verify queue"]
    SMOKE --> LIVE(["Live at your-app.vercel.app"])

    CRON["Scheduled Action<br/>every 3 days"] -->|"trivial query"| KEEP["Supabase stays active<br/>defeats the 1-week pause"]

    style GATE fill:#fef7e0,stroke:#fbbc04
    style LIVE fill:#e6f4ea,stroke:#34a853,stroke-width:3px
    style CRON fill:#e0f7fa,stroke:#00acc1
```
