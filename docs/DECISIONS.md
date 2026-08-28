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

---

## Open — to be decided when Phase 1 logic is written

- **O1 — Surplus input beyond card length.** `checker.check()` must decide what
  to do when the user types more units than the card has. Candidate: report a
  surplus count separately; do not let it change `matched` / `total` / `status`,
  which are computed from the card's length only.
- **O2 — `again`-requeued card vs. the daily cap of 20.** `FLOWCHART.md` diagram
  7 flags this. Candidate: no special-casing — `build_queue()` only knows
  `due_date <= today`, sorts, and caps at 20; a same-day requeue is just another
  due card on the next build.
- **O3 — zh traditional-vs-simplified verdict.** `B_Check_Answers` case 10
  expects **Incorrect**, but "every differing character counts" with
  `matched == 0 → Incorrect, otherwise Partial` may land on **Partial** if the
  two scripts share most characters. Decide and record which rule wins.
