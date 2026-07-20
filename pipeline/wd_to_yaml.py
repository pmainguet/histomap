"""Convert the extracted Wikidata Parquet into canonical draft YAML files.

Existing YAML files are preserved by default: generated drafts should never
silently overwrite hand-curated data. Use ``--overwrite`` for a deliberate
regeneration.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "sources" / "wikidata.parquet"
DEFAULT_OUTPUT = ROOT / "polities"
DEFAULT_TYPE_REPORT = ROOT / "reports" / "wikidata_type_decisions.jsonl"
YEAR_RE = re.compile(r"^([+-]?\d{1,6})")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def present(value: object) -> bool:
    """Return whether a DataFrame value contains useful scalar data."""
    if value is None:
        return False
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return True
    return isinstance(missing, bool) and not missing


def parse_year(value: object) -> int | None:
    """Parse a Wikidata timestamp (including astronomical BCE years)."""
    if not present(value):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) else int(value)
    match = YEAR_RE.match(str(value).strip())
    return int(match.group(1)) if match else None


def slugify(label: str) -> str:
    normalized = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    slug = NON_ALNUM_RE.sub("_", normalized.lower()).strip("_")
    if not slug:
        return "polity"
    if not slug[0].isalpha():
        slug = f"polity_{slug}"
    return slug


def aliases(value: object) -> list[str]:
    if not present(value):
        return []
    return list(dict.fromkeys(part.strip() for part in str(value).split("|") if part.strip()))


def allocate_ids(rows: Iterable[dict]) -> list[tuple[dict, str]]:
    """Allocate stable slugs, suffixing every collision with its QID."""
    rows = list(rows)
    bases = [slugify(str(row.get("label_en") or row["qid"])) for row in rows]
    counts = {base: bases.count(base) for base in set(bases)}
    allocated: list[tuple[dict, str]] = []
    used: set[str] = set()
    for row, base in zip(rows, bases, strict=True):
        polity_id = base
        if counts[base] > 1 or polity_id in used:
            polity_id = f"{base}_{str(row['qid']).lower()}"
        used.add(polity_id)
        allocated.append((row, polity_id))
    return allocated


def to_document(row: dict, polity_id: str) -> dict:
    qid = str(row["qid"])
    start = parse_year(row.get("inception"))
    if start is None:
        raise ValueError(f"{qid} has no parseable inception year")
    end = parse_year(row.get("dissolution"))
    if end is not None and end <= start:
        end = None

    names: dict[str, str] = {}
    if present(row.get("label_fr")):
        names["fr"] = str(row["label_fr"])
    alias_values = aliases(row.get("aliases_en"))
    if alias_values:
        names["aliases_en"] = " | ".join(alias_values)

    external_ids = {"wikidata": qid}
    if present(row.get("wikipedia_en")):
        external_ids["wikipedia_en"] = str(row["wikipedia_en"])

    return {
        "id": polity_id,
        "canonical_name": str(row.get("label_en") or qid),
        "names": names,
        "external_ids": external_ids,
        "parent": None,
        "successors": [],
        "region": None,
        "culture_group": None,
        "start": start,
        "end": end,
        "start_confidence": "low",
        "end_confidence": "low",
        "weight_by_era": {start: 5},
        "weight_imputed": True,
        "eligibility": "review",
        "icon": None,
        "text": {"short_child_en": "", "short_adult_en": "", "long_en": ""},
        "notes": "Automatically generated from Wikidata; requires review.",
        "sources": ["wikidata"],
    }


def convert(
    input_path: Path,
    output_dir: Path,
    overwrite: bool = False,
    type_report: Path | None = None,
) -> tuple[int, int, int]:
    frame = pd.read_parquet(input_path).sort_values("qid", kind="stable")
    required = {"qid", "label_en", "inception"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"input is missing columns: {', '.join(sorted(missing))}")

    output_dir.mkdir(parents=True, exist_ok=True)
    decisions: dict[str, str] = {}
    if type_report is not None and type_report.exists():
        for line in type_report.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            decisions[row["qid"]] = row["decision"]
    existing_qids: dict[str, str | None] = {}
    for path in output_dir.glob("*.yaml"):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            existing_qids[path.stem] = (document.get("external_ids") or {}).get("wikidata")
        except (OSError, yaml.YAMLError):
            # Validation reports malformed canonical files; the importer only needs
            # to avoid overwriting a path it cannot confidently identify.
            existing_qids[path.stem] = None

    written = preserved = rejected = 0
    for row, polity_id in allocate_ids(frame.to_dict(orient="records")):
        qid = str(row["qid"])
        if decisions.get(qid) == "excluded":
            rejected += 1
            continue
        occupied_by = existing_qids.get(polity_id)
        if polity_id in existing_qids and occupied_by != qid:
            polity_id = f"{polity_id}_{qid.lower()}"
        destination = output_dir / f"{polity_id}.yaml"
        if destination.exists() and not overwrite:
            preserved += 1
            continue
        try:
            document = to_document(row, polity_id)
        except ValueError:
            rejected += 1
            continue
        document["eligibility"] = decisions.get(qid, "review")
        destination.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        existing_qids[polity_id] = qid
        written += 1
    return written, preserved, rejected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--type-report",
        type=Path,
        default=DEFAULT_TYPE_REPORT,
        help="Eligibility report; excluded QIDs are not imported.",
    )
    args = parser.parse_args()
    if not args.input.exists():
        parser.error(f"input does not exist: {args.input}; run extract_wikidata.py first")
    written, preserved, rejected = convert(
        args.input, args.output_dir, args.overwrite, args.type_report
    )
    print(
        f"Wrote {written} draft YAML files; preserved {preserved} existing files; "
        f"rejected {rejected} rows with invalid inception dates."
    )


if __name__ == "__main__":
    main()
