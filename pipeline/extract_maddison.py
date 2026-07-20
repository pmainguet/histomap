"""Normalize the Maddison Project Database workbook to long-format Parquet."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "sources" / "mpd2023_web.xlsx"
DEFAULT_OUTPUT = ROOT / "sources" / "maddison.parquet"
REPORT_PATH = ROOT / "reports" / "maddison_extraction_summary.md"

COLUMN_ALIASES = {
    "country_code": {"countrycode", "country_code", "code"},
    "country": {"country", "countryname", "country_name"},
    "year": {"year"},
    "population_thousands": {"pop", "population", "population_thousands"},
    "gdp_per_capita": {"gdppc", "gdp_per_capita", "gdp per capita"},
}


def _key(value: object) -> str:
    return str(value).strip().lower().replace("\n", " ")


def _column_mapping(columns: list[object]) -> dict[object, str]:
    mapping = {}
    for column in columns:
        normalized = _key(column)
        for output_name, aliases in COLUMN_ALIASES.items():
            if normalized in aliases:
                mapping[column] = output_name
                break
    return mapping


def detect_table(path: Path) -> tuple[str, int]:
    workbook = pd.read_excel(path, sheet_name=None, header=None, nrows=20)
    for sheet_name, preview in workbook.items():
        for row_number, row in preview.iterrows():
            mapped = set(_column_mapping(row.tolist()).values())
            if {"country", "year", "population_thousands", "gdp_per_capita"} <= mapped:
                return sheet_name, int(row_number)
    raise ValueError("no sheet contains country, year, population, and GDP-per-capita columns")


def normalize(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = frame.rename(columns=_column_mapping(frame.columns.tolist()))
    required = {"country", "year", "population_thousands", "gdp_per_capita"}
    missing = required - set(renamed.columns)
    if missing:
        raise ValueError(f"missing Maddison columns: {', '.join(sorted(missing))}")
    if "country_code" not in renamed:
        renamed["country_code"] = pd.NA
    output = renamed[
        ["country_code", "country", "year", "population_thousands", "gdp_per_capita"]
    ].copy()
    for column in ("year", "population_thousands", "gdp_per_capita"):
        output[column] = pd.to_numeric(output[column], errors="coerce")
    output = output.dropna(subset=["country", "year"])
    output = output.dropna(subset=["population_thousands", "gdp_per_capita"], how="all")
    output["year"] = output["year"].astype(int)
    output["population"] = (output["population_thousands"] * 1000).round().astype("Int64")
    output["country"] = output["country"].astype(str).str.strip()
    output["country_code"] = output["country_code"].astype("string").str.strip()
    return output[
        ["country_code", "country", "year", "population", "gdp_per_capita"]
    ].sort_values(["country_code", "country", "year"], na_position="last", ignore_index=True)


def run(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT) -> pd.DataFrame:
    if not input_path.exists():
        raise FileNotFoundError(
            f"Maddison workbook not found at {input_path}. Download mpd2023_web.xlsx from "
            "https://www.rug.nl/ggdc/historicaldevelopment/maddison/releases/"
            "maddison-project-database-2023"
        )
    sheet_name, header_row = detect_table(input_path)
    normalized = normalize(pd.read_excel(input_path, sheet_name=sheet_name, header=header_row))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_parquet(output_path, index=False)
    lines = [
        "# Maddison extraction",
        "",
        f"- Input: `{input_path.name}`",
        f"- Sheet: `{sheet_name}` (header row {header_row + 1})",
        f"- Countries: {normalized['country'].nunique():,}",
        f"- Years: {normalized['year'].min()}–{normalized['year'].max()}",
        f"- Rows: {len(normalized):,}",
        f"- Population observations: {normalized['population'].notna().sum():,}",
        f"- GDP-per-capita observations: {normalized['gdp_per_capita'].notna().sum():,}",
        "",
        "The MPD `pop` field is stored in thousands; `population` is emitted as persons.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run(args.input, args.output)
    print(f"Maddison: wrote {len(result):,} observations to {args.output}")


if __name__ == "__main__":
    main()
