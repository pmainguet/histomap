"""Audit all truthy Wikidata civilization instances against canonical Histomap records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
import pandas as pd
from SPARQLWrapper import JSON, SPARQLWrapper

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://query.wikidata.org/sparql"
REPORT_PATH = ROOT / "reports" / "civilization_audit.jsonl"
SUMMARY_PATH = ROOT / "reports" / "civilization_audit_summary.md"
POLITIES_DIR = ROOT / "polities"
PARQUET_PATH = ROOT / "sources" / "wikidata.parquet"
USER_AGENT = "histomap/0.1 (https://github.com/pmainguet/histomap)"

QUERY = """
SELECT DISTINCT ?item ?itemLabel ?directType ?directTypeLabel WHERE {
  ?item wdt:P31 ?directType .
  ?directType wdt:P279* wd:Q8432 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
ORDER BY ?item
"""


def fetch() -> list[dict]:
    client = SPARQLWrapper(ENDPOINT, agent=USER_AGENT)
    client.setQuery(QUERY)
    client.setReturnFormat(JSON)
    bindings = client.query().convert()["results"]["bindings"]
    return [
        {
            "qid": row["item"]["value"].rsplit("/", 1)[-1],
            "label": row.get("itemLabel", {}).get("value"),
            "direct_type_qid": row["directType"]["value"].rsplit("/", 1)[-1],
            "direct_type_label": row.get("directTypeLabel", {}).get("value"),
        }
        for row in bindings
    ]


def audit(
    rows: list[dict],
    *,
    polities_dir: Path = POLITIES_DIR,
    parquet_path: Path = PARQUET_PATH,
    report_path: Path = REPORT_PATH,
    summary_path: Path = SUMMARY_PATH,
) -> dict[str, int]:
    canonical = {}
    for path in polities_dir.glob("*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        qid = (document.get("external_ids") or {}).get("wikidata")
        if qid:
            canonical[qid] = document
    extracted: dict[str, dict] = {}
    if parquet_path.exists():
        frame = pd.read_parquet(parquet_path)
        extracted = {
            str(record["qid"]): record for record in frame.to_dict(orient="records")
        }

    by_qid: dict[str, dict] = {}
    for row in rows:
        item = by_qid.setdefault(
            row["qid"],
            {"qid": row["qid"], "label": row["label"], "direct_types": []},
        )
        item["direct_types"].append(
            {"qid": row["direct_type_qid"], "label": row["direct_type_label"]}
        )
    counts: dict[str, int] = {}
    output = []
    for qid, item in sorted(by_qid.items()):
        document = canonical.get(qid)
        candidate = extracted.get(qid)
        inception = candidate.get("inception") if candidate else None
        has_inception = candidate is not None and pd.notna(inception)
        if candidate is None:
            status = "missing_extraction"
        elif document is None and not has_inception:
            status = "dateless_review"
        elif document is None:
            status = "awaiting_import"
        elif document.get("entity_type") == "civilization":
            status = "canonical_civilization"
        else:
            status = "canonical_wrong_type"
        counts[status] = counts.get(status, 0) + 1
        item.update(
            {
                "status": status,
                "histomap_id": document.get("id") if document else None,
                "current_entity_type": document.get("entity_type") if document else None,
                "eligibility": document.get("eligibility") if document else None,
                "in_extraction": candidate is not None,
                "has_inception": has_inception,
                "wikidata_url": f"https://www.wikidata.org/wiki/{qid}",
            }
        )
        output.append(item)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in output),
        encoding="utf-8",
    )
    summary_path.write_text(
        "# Civilization completeness audit\n\n"
        + f"- Wikidata civilization instances: {len(output):,}\n"
        + "\n".join(
            f"- {name.replace('_', ' ').title()}: {count:,}"
            for name, count in sorted(counts.items())
        )
        + "\n\nDateless civilizations remain in the extraction dataset and require a reviewed "
        "start date before canonical import. Missing-extraction records indicate taxonomy "
        "coverage drift and should trigger a fresh Wikidata extraction.\n",
        encoding="utf-8",
    )
    return {"total": len(output), **counts}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Use saved SPARQL result rows instead of querying")
    args = parser.parse_args()
    rows = json.loads(args.input.read_text(encoding="utf-8")) if args.input else fetch()
    print(audit(rows))


if __name__ == "__main__":
    main()
