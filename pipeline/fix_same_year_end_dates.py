"""One-off remediation: recompute the real end year for live polities whose
end was silently nulled to "present" by the same-year start/end bug fixed in
pipeline/wd_to_yaml.py and schema.py's Polity validator (see
tests/test_wd_to_yaml.py's test_same_year_dissolution_is_kept_not_nulled).
Recovers the correct year from the cached raw Wikidata extraction
(sources/wikidata.parquet), which still has the original dissolution value
even for records whose imported YAML had it dropped.

Usage: python -m pipeline.fix_same_year_end_dates [--dry-run] [--root PATH]
"""
import argparse
from pathlib import Path

import pandas as pd
import yaml

from pipeline.wd_to_yaml import parse_year

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PARQUET = ROOT / "sources" / "wikidata.parquet"


def _load_dissolution_years(parquet_path: Path) -> dict[str, int]:
    """Maps qid -> dissolution year, for every Wikidata row whose
    inception/dissolution both parse to a year and dissolution >= inception
    (a genuinely reversed dissolution < inception stays excluded -- that's a
    real data problem, not a same-year precision artifact)."""
    df = pd.read_parquet(parquet_path)
    years: dict[str, int] = {}
    for _, row in df.iterrows():
        inception_year = parse_year(row.get("inception"))
        dissolution_year = parse_year(row.get("dissolution"))
        if inception_year is None or dissolution_year is None:
            continue
        if dissolution_year < inception_year:
            continue
        years[str(row["qid"])] = dissolution_year
    return years


def main(
    root: Path = ROOT, parquet_path: Path = DEFAULT_PARQUET, *, dry_run: bool = False
) -> dict[str, int]:
    """Run the one-off same-year end-date remediation. Returns a summary
    dict with a `fixed` count."""
    dissolution_years = _load_dissolution_years(parquet_path)
    summary = {"fixed": 0}
    for path in sorted((root / "polities").glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if document.get("end") is not None:
            continue
        if "dates" in (document.get("manual_overrides") or []):
            continue
        qid = (document.get("external_ids") or {}).get("wikidata")
        if not qid or qid not in dissolution_years:
            continue
        end_year = dissolution_years[qid]
        document["end"] = end_year
        document["end_confidence"] = "low"
        document["notes"] = (
            document.get("notes", "").rstrip()
            + f" End date corrected from null (\"present\") to {end_year} -- Wikidata"
            + " records a same-year (or single approximate) dissolution date that was"
            + " previously misread as invalid (found live, 1 September 2026)."
        ).strip()
        summary["fixed"] += 1
        if dry_run:
            continue
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    args = parser.parse_args()
    result = main(args.root, args.parquet, dry_run=args.dry_run)
    print(f"{'[dry run] ' if args.dry_run else ''}fixed {result['fixed']} records")
