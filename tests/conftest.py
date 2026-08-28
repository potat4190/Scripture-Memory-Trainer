"""Shared fixture loading, plus the CHECK-case deviation reporter.

The reporter is the Phase 2 checklist item "make the suite emit a
machine-readable list of failing CHECK cases". ``test_normalizer.py`` records
every case it runs into the session-scoped ``check_report`` collector; at the
end of the session the collector writes ``reports/check-report.json`` and
``reports/check-report.md``. The Markdown table is what gets pasted into
``docs/DECISIONS.md``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
SEED = ROOT / "seed"
REPORTS = ROOT / "reports"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_schedule_traces() -> list[dict[str, Any]]:
    """The 8 traces of ``B_Check_Schedule``."""
    traces: list[dict[str, Any]] = _load(FIXTURES / "check_schedule.json")
    return traces


def load_answer_cases() -> list[dict[str, Any]]:
    """The 21 cases of ``B_Check_Answers`` (see DECISIONS D1 on the count)."""
    cases: list[dict[str, Any]] = _load(FIXTURES / "check_answers.json")
    return cases


def load_seed_cards() -> dict[tuple[str, str], str]:
    """``(reference, language) -> text`` for the 32 rows of ``B_Cards``."""
    rows: list[dict[str, str]] = _load(SEED / "cards.json")
    return {(r["reference"], r["language"]): r["text"] for r in rows}


@dataclass
class CaseResult:
    """One CHECK case as the checker actually computed it."""

    id: int
    reference: str
    lang: str
    change: str
    expected_verdict: str
    status: str
    matched: int
    total: int
    unit: str
    mismatch_positions: list[int] = field(default_factory=list)
    missing_from: int | None = None
    missing_count: int = 0
    surplus_count: int = 0
    deviations: list[str] = field(default_factory=list)

    @property
    def agrees(self) -> bool:
        return not self.deviations


class CheckReport:
    """Collects every CHECK case result and writes the report at teardown."""

    def __init__(self) -> None:
        self.results: list[CaseResult] = []

    def record(self, result: CaseResult) -> None:
        self.results.append(result)

    def _payload(self) -> dict[str, Any]:
        failing = [r for r in self.results if not r.agrees]
        return {
            "total_cases": len(self.results),
            "agreeing": len(self.results) - len(failing),
            "failing": len(failing),
            "failing_case_ids": [r.id for r in failing],
            "cases": [asdict(r) for r in self.results],
        }

    def _markdown(self) -> str:
        failing = [r for r in self.results if not r.agrees]
        lines = [
            "| Case | Reference | Lang | Change | Workbook expects | Computed | Deviation |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in failing:
            expected = r.expected_verdict.replace("|", "\\|")
            computed = f"{r.status} — {r.matched} of {r.total} {r.unit} matched"
            if r.mismatch_positions:
                computed += f", wrong at {r.mismatch_positions}"
            if r.missing_count:
                computed += f", {r.missing_count} missing from {r.missing_from}"
            lines.append(
                f"| {r.id} | {r.reference} | {r.lang} | {r.change} | "
                f"{expected} | {computed} | {'; '.join(r.deviations)} |"
            )
        if not failing:
            lines.append("| — | — | — | — | — | — | no deviations |")
        summary = (
            f"{len(self.results) - len(failing)} of {len(self.results)} CHECK cases agree "
            f"with the workbook. Failing case ids: "
            f"{[r.id for r in failing] or 'none'}."
        )
        return f"# CHECK case deviations\n\n{summary}\n\n" + "\n".join(lines) + "\n"

    def write(self) -> None:
        if not self.results:
            return  # a filtered run (e.g. `-k queue`) must not truncate the report
        REPORTS.mkdir(exist_ok=True)
        self.results.sort(key=lambda r: r.id)
        (REPORTS / "check-report.json").write_text(
            json.dumps(self._payload(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (REPORTS / "check-report.md").write_text(self._markdown(), encoding="utf-8")


@pytest.fixture(scope="session")
def check_report() -> Iterator[CheckReport]:
    report = CheckReport()
    yield report
    report.write()
