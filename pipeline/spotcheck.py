"""Run the Phase 2 editorial spot checks against canonical polity records."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
REPORT_PATH = ROOT / "reports" / "phase2_spotcheck.md"


@dataclass(frozen=True)
class ExpectedPolity:
    polity_id: str
    label: str
    earliest_start: int
    latest_start: int
    earliest_end: int
    latest_end: int
    continent: str


EXPECTED = (
    ExpectedPolity("akkadian_empire", "Akkad", -2400, -2250, -2200, -2000, "asia"),
    ExpectedPolity("achaemenid_empire", "Achaemenid", -570, -530, -350, -320, "asia"),
    ExpectedPolity("han_dynasty", "Han", -220, -190, 200, 230, "asia"),
    ExpectedPolity("sasanian_empire", "Sasanian", 210, 240, 630, 660, "asia"),
    ExpectedPolity("abbasid_caliphate", "Abbasid", 740, 760, 1240, 1260, "asia"),
    ExpectedPolity("song_dynasty", "Song", 950, 970, 1260, 1290, "asia"),
    ExpectedPolity("mongol_empire", "Mongol", 1190, 1220, 1250, 1400, "asia"),
    ExpectedPolity("ottoman_empire", "Ottoman", 1280, 1310, 1900, 1930, "asia"),
    ExpectedPolity("mughal_empire", "Mughal", 1510, 1540, 1840, 1870, "asia"),
    ExpectedPolity("qing_dynasty", "Qing", 1620, 1650, 1900, 1920, "asia"),
)


def assess(document: dict, expected: ExpectedPolity) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    if document.get("eligibility") != "accepted":
        failures.append("not accepted")
    if not expected.earliest_start <= document["start"] <= expected.latest_start:
        failures.append("start outside baseline")
    if document.get("end") is None or not expected.earliest_end <= document["end"] <= expected.latest_end:
        failures.append("end outside baseline")
    geography = document.get("geography") or {}
    if expected.continent not in geography.get("continents", []):
        failures.append(f"missing {expected.continent} geography")
    if not geography.get("present_countries"):
        warnings.append("no present country")
    if not (document.get("external_ids") or {}).get("seshat"):
        warnings.append("not linked to Seshat")
    return failures, warnings


def run() -> tuple[int, int]:
    rows = []
    passed = 0
    for expected in EXPECTED:
        path = POLITIES_DIR / f"{expected.polity_id}.yaml"
        if not path.exists():
            rows.append((expected.label, "FAIL", "canonical record missing"))
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        failures, warnings = assess(document, expected)
        status = "PASS" if not failures else "FAIL"
        passed += status == "PASS"
        details = "; ".join(failures + warnings) or "dates and geography pass"
        rows.append((expected.label, status, details))

    lines = [
        "# Phase 2 spot check",
        "",
        f"Core checks passed: **{passed}/{len(EXPECTED)}**.",
        "",
        "Warnings identify incomplete source or present-country coverage but do not fail the core check.",
        "",
        "| Polity | Core status | Findings |",
        "|---|---|---|",
    ]
    lines.extend(f"| {label} | {status} | {details} |" for label, status, details in rows)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return passed, len(EXPECTED)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="fail if any core spot check fails")
    args = parser.parse_args()
    passed, total = run()
    print(f"Phase 2 spot checks: {passed}/{total} core checks passed")
    if args.strict and passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
