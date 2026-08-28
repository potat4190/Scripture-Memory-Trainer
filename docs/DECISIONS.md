# Decision Log — Scripture Memory Trainer

Every place where `B_Rules` (or the supplied data) could be read more than one way,
and the reading this build committed to. Per the challenge brief, `B_Rules` is
authoritative over intuition; this file records where intuition was set aside and
where the data itself forced a call.

Format: one entry per decision. `Status` is `Decided`, `Open`, or `Superseded`.

**Source of truth:** the challenge workbook, `Frontier Commons Fellowship FA26 —
Build Lane Challenge Data.xlsx`. It is **not tracked in this repo** — keep your
own copy in `docs/`. `seed/cards.json` and both `tests/fixtures/*.json` are
generated from it by `tools/extract_fixtures.py`, and those generated files *are*
tracked, so the repo stands on its own. Re-running the script against the
workbook must leave them unchanged.

---

## D1 — `B_Check_Answers` has 21 rows, not 22

- **Status:** Decided (data constraint, not a choice) — **confirmed against the workbook**
- **Context:** The checklist and the `B_Check_Answers` preamble both say 22 cases.
  The sheet itself holds **21** data rows (rows 6–26 under the header at row 5).
  This was first seen in a Markdown export and has since been re-confirmed by
  reading the `.xlsx` directly, so it is a property of the workbook, not an
  artifact of the export.
- **Decision:** Extract the 21 rows that exist into
  `tests/fixtures/check_answers.json` and treat 21 as the real count. There is no
  22nd case to represent.
- **Consequence:** Any "X of 22" phrasing from the checklist maps to 21 here.
  README states this. `tests/test_fixtures.py` pins the count at 21.

## D2 — `B_Cards` stored verbatim; Unicode normalization happens at compare time

- **Status:** Decided — **confirmed against the workbook**
- **Context:** The Arabic verses in `B_Cards` are **not** in any Unicode normal
  form — combining marks appear in source order, not canonical (`NFC`) order. An
  earlier hand-made `seed/cards.json` had silently `NFC`-normalized them.
  Re-extracting from the `.xlsx` reproduces the current `seed/cards.json`
  byte-for-byte, so all 32 cards now match their source cells exactly.
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

## D4 — Leviticus 19:34 outer-whitespace case: padding recovered from the workbook

- **Status:** **Superseded** — the earlier reading was wrong, and is now fixed
- **Original context:** Case 8 (Leviticus 19:34, en — "Trailing and leading
  whitespace") carries leading and trailing spaces. Markdown tables cannot
  represent cell-edge whitespace, so the Markdown export this fixture was first
  built from had dropped it. At the time that looked unrecoverable, and the
  fixture stored the trimmed string.
- **Correction:** The `.xlsx` preserves the padding — the cell holds three
  leading and three trailing spaces (190 characters, versus the 184 the export
  gave). `tools/extract_fixtures.py` now reads the workbook, so the fixture
  carries the real string.
- **Decision:** Extract from the `.xlsx`, never from a Markdown rendering of it.
  `tests/test_fixtures.py::test_outer_whitespace_case_keeps_its_padding` fails if
  the padding is ever lost again.
- **Note:** The verdict was **Correct** either way, since trimming a trimmed
  string is a no-op — so this never masked a checker bug. But the case existed
  specifically to exercise trimming, and with the padding gone it was not
  testing anything.

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
- **Phase 2 addendum:** covering it turned up a real bug. `save_state` writes
  `"due_date": null` for a card that was never scheduled, and `load_state` passed
  that straight to `date.fromisoformat`, which raises `TypeError` — so a state
  file containing any unscheduled card could not be reloaded. Fixed: such a card
  keeps its box and is treated as due now.
  `tests/test_storage.py::test_a_saved_card_with_no_due_date_loads_as_due_now`
  pins it.

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

## D11 — Phase 2 pins the three known deviations with strict `xfail`

- **Status:** Decided
- **Context:** D5 (×2) and D10 record three CHECK cases where the computed
  verdict disagrees with `B_Check_Answers`. A plain "expected failure" that
  someone later "fixes" would go green silently — which is precisely the
  outcome the checklist warns against.
- **Decision:** `tests/test_normalizer.py` marks them
  `pytest.mark.xfail(..., strict=True)`, and splits status from counts so each
  deviation is pinned where it actually occurs:
  - cases **6** and **7** — counts only; their *status* assertions pass normally
  - case **10** — status only; it states no numbers to check
  With `strict=True`, tuning the checker to reproduce the workbook's 22/16 turns
  these into failures instead of quiet passes.
- **Also:** expected values are **parsed from the workbook's own verdict prose**
  (`"7 of 10 words matched; 3 missing from position 8"`), not retyped into the
  tests. Same reasoning as extracting the fixtures rather than hand-writing
  them: one source of truth. `test_the_prose_parser_actually_extracts_numbers`
  guards the parser, so a regex that silently stopped matching cannot make the
  numeric assertions vacuous.

## D12 — "Exact match" is decided on units, not on the normalized string

- **Status:** Decided — **bug found and fixed in Phase 2**
- **Context:** `checker.check()` short-circuits to `Correct` when the answer
  matches the card. It originally tested that with `norm_card == norm_input`,
  comparing the two **normalized strings**, while every other number in the
  `Verdict` was computed from the **split unit lists**.
- **The bug:** those two views agree for `en` / `ar` / `hi`, because `str.split()`
  already discards the whitespace `normalize` has collapsed. They disagree for
  `zh`, where the unit is the character and `_split` drops spaces outright. So a
  Chinese verse recited perfectly but typed with spaces between the characters
  came back **Partial — 30 of 30 characters matched**, with no mismatch
  positions, nothing missing and nothing surplus: a verdict the UI cannot
  explain. All 8 Chinese cards were affected.
- **Decision:** decide exactness on `card_units == input_units`, the same list
  everything else is derived from. For the word languages this is provably
  equivalent; for `zh` it makes spacing a non-unit, which is what "character
  split" means and what the checklist's `exact match → Correct` requires.
- **Why the suite missed it:** the "a Partial must report something actionable"
  assertion existed, but only ran over the 21 CHECK cases, none of which vary
  `zh` spacing. It is now also a Hypothesis property. A second property,
  `test_spacing_is_not_a_unit_for_character_languages`, builds the answer *from*
  the card — drawing card and answer independently never produces a
  spacing-only variant, so the generic property alone would not have found this.
- **Consequence:** none of the 21 CHECK cases change.
  `reports/check-report.json` is byte-identical before and after, and the three
  known deviations (D5 ×2, D10) are untouched.

---

## Phase 2 — failing CHECK cases

Generated by the test suite, not by hand. Running `pytest` writes
`reports/check-report.json` (machine-readable) and `reports/check-report.md`;
the table below is that file's contents. The test
`test_check_report_is_written` fails if the set of deviating case ids ever
changes, so this list cannot silently drift out of date.

**18 of 21 CHECK cases agree with the workbook. Failing case ids: 6, 7, 10.**

| Case | Reference | Lang | Change | Workbook expects | Computed | Deviation |
|---|---|---|---|---|---|---|
| 6 | Matthew 28:19 | en | Curly apostrophe and quotes | Partial. Curly apostrophe normalises to straight, but Father’s is still 1 word wrong at position 16. | partial — 23 of 24 words matched, wrong at [15] | wrong position: workbook 16, computed [15] |
| 7 | Matthew 28:19 | en | Empty string | Incorrect. 0 of 22 words matched. | incorrect — 0 of 24 words matched, 24 missing from 1 | total: workbook 22, computed 24 |
| 10 | John 3:16 | zh | Traditional characters instead of simplified | Incorrect. Script conversion is not performed. Every differing character counts. | partial — 23 of 30 chars matched, wrong at [2, 7, 10, 13, 14, 16, 25] | status: workbook says incorrect, computed partial |

All three are the deviations already argued in D5 and D10 — no new ones. The
schedule side has none: 8 of 8 traces match exactly, step by step, including
every intermediate box, interval and due date.

---

## Open

- **O1 — `again`-requeued card vs. the daily cap of 20.** `FLOWCHART.md` diagram
  7 flags this. `build_queue()` itself already behaves the simple way — it only
  knows `due_date <= today`, sorts, and caps at 20, so a same-day requeue is just
  another due card on the next build. What's still undecided is whether the
  *session driver* (not yet written) re-inserts an `again` card within the
  current session regardless of the cap. Decide when that driver exists.

---

## Consistency audit against the workbook — 2026-08-27

All four Option-B tabs (`B_Cards`, `B_Rules`, `B_Check_Schedule`,
`B_Check_Answers`) were read straight out of the `.xlsx` and compared against
this repo. Phase 2–6 items were out of scope.

| Check | Result |
|---|---|
| `B_Rules` vs. the implemented rules | consistent — intervals, grade effects, cap, sort order, normalization list, partial-credit split, and text sources all match |
| `B_Cards` (32 rows) vs. `seed/cards.json` | byte-identical, all 5 fields |
| `B_Check_Schedule` (8 traces) vs. `check_schedule.json` | identical |
| `B_Check_Answers` (21 rows) vs. `check_answers.json` | **1 difference — case 8 whitespace, fixed. See D4** |
| Scheduler vs. the 8 traces | 8/8 exact |
| Checker vs. the 21 cases | 18/21 exact; 3 known (D5 ×2, D10) |

Every numeric claim the workbook states in prose — "1 of 9 words wrong at
position 5", "7 of 10 words matched; 3 missing from position 8", "1 word wrong at
position 2" — was checked against the computed `Verdict`, not just the
correct/partial/incorrect label. All match except the three in D5 and D10.

At the status level alone (correct / partial / incorrect) the checker agrees on
20 of 21; only D10 disagrees on the label. D5's two cases carry the right label
and the wrong counts.
