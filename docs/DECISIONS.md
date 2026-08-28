# Decision Log — Scripture Memory Trainer

Every place where `B_Rules` (or the supplied data) could be read more than one way,
and the reading this build committed to. Per the challenge brief, `B_Rules` is
authoritative over intuition; this file records where intuition was set aside and
where the data itself forced a call.

Format: one entry per decision. `Status` is `Decided`, `Open`, or `Superseded`.

---

## D1 — `B_Check_Answers` has 21 rows, not 22

- **Status:** Decided (data constraint, not a choice)
- **Context:** The checklist and the workbook's own `B_Check_Answers` header say
  22 cases. The supplied source — `frontiercommonsfa26buildlanedata.md`, a
  Markdown export of the Google Sheets workbook — contains **21** rows in that
  table.
- **Decision:** Extract the 21 rows that exist into
  `tests/fixtures/check_answers.json` and treat 21 as the real count. The 22nd
  case is not in the data we were given, so it cannot be represented.
- **Consequence:** Any "X of 22" phrasing from the checklist maps to 21 here.
  README must state this.

## D2 — `B_Cards` stored verbatim; Unicode normalization happens at compare time

- **Status:** Decided
- **Context:** The Arabic verses in the source are **not** in any Unicode normal
  form — combining marks appear in source order, not canonical
  (`NFC`) order. An earlier hand-made `seed/cards.json` had silently
  `NFC`-normalized them.
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

## D4 — Leviticus 19:34 outer-whitespace case: whitespace lost in the export

- **Status:** Decided (data constraint)
- **Context:** Case 8 (Leviticus 19:34, en — "Trailing and leading whitespace")
  is meant to carry leading and trailing spaces. Markdown tables cannot represent
  cell-edge whitespace, so the export collapsed it; the supplied source shows the
  verse with only normal single-space cell padding.
- **Decision:** Store the string as the source gives it (no synthetic whitespace
  re-added — that would be retyping the very thing the case tests). The expected
  verdict is **Correct** ("outer whitespace is trimmed"); a correct checker
  returns Correct whether or not the padding survived, so the case still
  exercises the right verdict.

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

## D9 — `storage.py` is a deliberate exception to Phase 1's "zero I/O"

- **Status:** Decided
- **Context:** Phase 1 is meant to be five pure modules that touch no disk,
  network, or framework.
- **Decision:** `src/scripture_memory_trainer/storage.py` does plain JSON file
  I/O (no framework, no DB driver — so the Phase 1 *exit criterion* still holds)
  and is kept strictly separate from the five pure files. It exists to back a
  future terminal driver and to prototype the Phase 3 seed loader / export.
  Nothing in the pure modules imports it.

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

## Open

- **O1 — `again`-requeued card vs. the daily cap of 20.** `FLOWCHART.md` diagram
  7 flags this. `build_queue()` itself already behaves the simple way — it only
  knows `due_date <= today`, sorts, and caps at 20, so a same-day requeue is just
  another due card on the next build. What's still undecided is whether the
  *session driver* (not yet written) re-inserts an `again` card within the
  current session regardless of the cap. Decide when that driver exists.
