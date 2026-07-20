"""Normalize the public Seshat Equinox workbook into Parquet tables."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "sources" / "seshat_equinox_2022.xlsx"
POLITIES_OUT = ROOT / "sources" / "seshat_polities.parquet"
TIMESERIES_OUT = ROOT / "sources" / "seshat_timeseries.parquet"
REPORT_OUT = ROOT / "reports" / "seshat_extraction_summary.md"


@dataclass(frozen=True)
class ParsedDate:
    year: int
    confidence: str
    raw: str


def _century_bounds(century: int, era: str) -> tuple[int, int]:
    if era == "BCE":
        return -100 * century + 1, -100 * (century - 1)
    return 100 * (century - 1), 100 * century - 1


def parse_historical_date(value: object, boundary: str = "start") -> ParsedDate:
    """Parse numeric years and common Seshat-style historical date phrases."""
    if boundary not in {"start", "end"}:
        raise ValueError("boundary must be 'start' or 'end'")
    if isinstance(value, int):
        return ParsedDate(value, "high", str(value))
    if isinstance(value, float) and not pd.isna(value):
        return ParsedDate(int(value), "high", str(value))
    if value is None or pd.isna(value):
        raise ValueError("date is missing")

    raw = str(value).strip()
    text = raw.upper()
    text = re.sub(r"\bB\.?C\.?(?:E\.?)?\b", "BCE", text)
    text = re.sub(r"\b(?:A\.?D\.?|C\.?E\.?)\b", "CE", text)
    approximate = bool(re.search(r"\b(C\.?|CA\.?|CIRCA)\b", text))
    text = re.sub(r"\b(C\.?|CA\.?|CIRCA)\b", "", text).strip()
    era_match = re.search(r"\b(BCE|CE)\b", text)
    era = era_match.group(1) if era_match else "CE"

    century_match = re.search(r"(?:(EARLY|MID|MIDDLE|LATE)\s+)?(\d+)(?:ST|ND|RD|TH)\s+CENTURY", text)
    if century_match:
        qualifier = century_match.group(1)
        lower, upper = _century_bounds(int(century_match.group(2)), era)
        span = upper - lower + 1
        if qualifier == "EARLY":
            upper = lower + span // 3 - 1
        elif qualifier in {"MID", "MIDDLE"}:
            lower, upper = lower + span // 3, lower + (2 * span) // 3 - 1
        elif qualifier == "LATE":
            lower = lower + (2 * span) // 3
        return ParsedDate(lower if boundary == "start" else upper, "medium", raw)

    range_match = re.search(r"(\d{1,5})\s*(?:-|–|TO)\s*(\d{1,5})", text)
    if range_match:
        first, second = int(range_match.group(1)), int(range_match.group(2))
        years = [-first, -second] if era == "BCE" else [first, second]
        return ParsedDate(min(years) if boundary == "start" else max(years), "medium", raw)

    year_match = re.search(r"(?<!\d)(-?\d{1,5})(?!\d)", text)
    if not year_match:
        raise ValueError(f"unrecognized historical date: {raw!r}")
    year = int(year_match.group(1))
    if era == "BCE":
        year = -abs(year)
    return ParsedDate(year, "medium" if approximate else "high", raw)


def _required(frame: pd.DataFrame, columns: set[str], sheet: str) -> None:
    missing = columns - set(frame.columns)
    if missing:
        raise ValueError(f"{sheet} sheet is missing columns: {', '.join(sorted(missing))}")


def normalize_workbook(input_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    polity_source = pd.read_excel(input_path, sheet_name="Polities")
    aggregate = pd.read_excel(input_path, sheet_name="AggrSCWarAgriRelig")
    complexity = pd.read_excel(input_path, sheet_name="SPC_MilTech")
    _required(
        polity_source,
        {"NGA", "PolName", "PolID", "Start", "End", "World Region", "Complexity"},
        "Polities",
    )
    _required(aggregate, {"NGA", "PolID", "Time", "Pop", "Terr"}, "AggrSCWarAgriRelig")
    _required(complexity, {"NGA", "PolID", "Time", "SPC"}, "SPC_MilTech")

    polity_rows = []
    rejected = []
    for row in polity_source.to_dict(orient="records"):
        try:
            start = parse_historical_date(row["Start"], "start")
            end = parse_historical_date(row["End"], "end")
        except ValueError as exc:
            rejected.append((row.get("PolID"), str(exc)))
            continue
        polity_rows.append(
            {
                "seshat_id": str(row["PolID"]),
                "canonical_name": str(row["PolName"]),
                "nga": str(row["NGA"]),
                "world_region": str(row["World Region"]),
                "start_year": start.year,
                "end_year": end.year,
                "start_confidence": start.confidence,
                "end_confidence": end.confidence,
                "date_notes": "" if start.confidence == end.confidence == "high" else f"Start: {start.raw}; End: {end.raw}",
                "complexity_category": row.get("Complexity"),
                "language": row.get("Language"),
                "language_genus": row.get("Genus"),
                "language_family": row.get("Family"),
                "is_duplicate": str(row.get("Dupl", "n")).lower() == "y",
            }
        )
    polities = pd.DataFrame(polity_rows)

    aggregate = aggregate.rename(
        columns={"PolID": "seshat_id", "Time": "year", "Pop": "population_log10", "Terr": "area_km2_log10"}
    )
    complexity = complexity.rename(columns={"PolID": "seshat_id", "Time": "year", "SPC": "social_complexity_index"})
    timeseries = aggregate[["seshat_id", "year", "population_log10", "area_km2_log10"]].merge(
        complexity[["seshat_id", "year", "social_complexity_index"]],
        on=["seshat_id", "year"],
        how="outer",
    )
    timeseries = timeseries.merge(
        polities[["seshat_id", "canonical_name", "nga", "start_year", "end_year"]],
        on="seshat_id",
        how="inner",
    ).sort_values(["seshat_id", "year"])

    peaks = timeseries.groupby("seshat_id", as_index=False).agg(
        peak_population_log10=("population_log10", "max"),
        peak_area_km2_log10=("area_km2_log10", "max"),
        peak_social_complexity=("social_complexity_index", "max"),
    )
    polities = polities.merge(peaks, on="seshat_id", how="left").sort_values("seshat_id")
    polities.attrs["rejected_dates"] = rejected
    return polities.reset_index(drop=True), timeseries.reset_index(drop=True)


def run(input_path: Path = DEFAULT_INPUT) -> tuple[int, int]:
    polities, timeseries = normalize_workbook(input_path)
    POLITIES_OUT.parent.mkdir(parents=True, exist_ok=True)
    polities.to_parquet(POLITIES_OUT, index=False)
    timeseries.to_parquet(TIMESERIES_OUT, index=False)
    rejected = polities.attrs.get("rejected_dates", [])
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(
        "# Seshat extraction\n\n"
        f"- Polities: {len(polities):,}\n"
        f"- Time-series rows: {len(timeseries):,}\n"
        f"- Duplicate-flagged polities retained: {int(polities['is_duplicate'].sum()):,}\n"
        f"- Rejected date rows: {len(rejected):,}\n"
        "- Population and territory values are preserved as the workbook's log10 measures.\n",
        encoding="utf-8",
    )
    return len(polities), len(timeseries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    if not args.input.exists():
        parser.error(f"input does not exist: {args.input}")
    polity_count, timeseries_count = run(args.input)
    print(f"Wrote {polity_count} polities and {timeseries_count} time-series rows")


if __name__ == "__main__":
    main()
