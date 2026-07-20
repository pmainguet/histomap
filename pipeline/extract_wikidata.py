"""Pipeline step 4: Wikidata SPARQL extraction.

For each polity-adjacent Wikidata class, runs a paginated SPARQL query that
collapses per-entity multivalues with SAMPLE / MIN / MAX / GROUP_CONCAT, caches
the raw JSON per class under sources/wikidata_raw/, and writes a merged +
deduped Parquet at sources/wikidata.parquet.

Smoke usage:
    python pipeline/extract_wikidata.py --class Q48349   # empire only

Full run:
    python pipeline/extract_wikidata.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError

import pandas as pd
from SPARQLWrapper import JSON, SPARQLWrapper

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "sources" / "wikidata_raw"
PARQUET_OUT = ROOT / "sources" / "wikidata.parquet"

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "histomap/0.1 (https://github.com/pmainguet/histomap) python-SPARQLWrapper"
PAGE_SIZE = 2000
SLEEP_BETWEEN_PAGES = 1.0

# Polity-adjacent Wikidata classes. Labels are for logging/cache filenames only.
# Q3024240 is historical country (and covers the former-country role in the plan);
# Q8432 is civilization. These definitions were verified against Wikidata in July 2026.
CLASSES = {
    "Q48349": "empire",
    "Q417175": "kingdom",
    "Q8432": "civilization",
    "Q7275": "state",
    "Q3024240": "historical_country",
}

QUERY_TEMPLATE = """
SELECT ?item
       (SAMPLE(?label_en_v)   AS ?label_en)
       (SAMPLE(?label_fr_v)   AS ?label_fr)
       (MIN(?inception_v)     AS ?inception)
       (MAX(?dissolution_v)   AS ?dissolution)
       (SAMPLE(?area_v)       AS ?area)
       (SAMPLE(?population_v) AS ?population)
       (SAMPLE(?country_v)    AS ?country)
       (SAMPLE(?coords_v)     AS ?coords)
       (SAMPLE(?image_v)      AS ?image)
       (SAMPLE(?article_v)    AS ?wikipedia_en)
       (GROUP_CONCAT(DISTINCT ?alias_v; SEPARATOR="|") AS ?aliases_en)
WHERE {
  ?item wdt:P31/wdt:P279* wd:CLASS_QID .
  OPTIONAL { ?item rdfs:label    ?label_en_v . FILTER(LANG(?label_en_v) = "en") }
  OPTIONAL { ?item rdfs:label    ?label_fr_v . FILTER(LANG(?label_fr_v) = "fr") }
  OPTIONAL { ?item skos:altLabel ?alias_v    . FILTER(LANG(?alias_v)    = "en") }
  OPTIONAL { ?item wdt:P571  ?inception_v . }
  OPTIONAL { ?item wdt:P576  ?dissolution_v . }
  OPTIONAL { ?item wdt:P2046 ?area_v . }
  OPTIONAL { ?item wdt:P1082 ?population_v . }
  OPTIONAL { ?item wdt:P17   ?country_v . }
  OPTIONAL { ?item wdt:P625  ?coords_v . }
  OPTIONAL { ?item wdt:P18   ?image_v . }
  OPTIONAL {
    ?article_v schema:about ?item ;
               schema:isPartOf <https://en.wikipedia.org/> .
  }
}
GROUP BY ?item
ORDER BY ?item
LIMIT PAGE_LIMIT OFFSET PAGE_OFFSET
"""

QID_RE = re.compile(r"/entity/(Q\d+)$")


def _run_query(sparql: SPARQLWrapper, class_qid: str, offset: int, limit: int) -> list[dict]:
    q = (
        QUERY_TEMPLATE.replace("CLASS_QID", class_qid)
        .replace("PAGE_LIMIT", str(limit))
        .replace("PAGE_OFFSET", str(offset))
    )
    sparql.setQuery(q)
    sparql.setReturnFormat(JSON)
    for attempt in range(3):
        try:
            result = sparql.query().convert()
            return result["results"]["bindings"]
        except HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                wait = 70
                print(f"    HTTP 429; sleeping {wait}s then retrying...", flush=True)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("unreachable")


def extract_class(class_qid: str, label: str, force: bool = False) -> list[dict]:
    cache_path = RAW_DIR / f"{label}_{class_qid}.json"
    if cache_path.exists() and not force:
        print(f"  [{label}] cache hit: {cache_path.name}")
        return json.loads(cache_path.read_text(encoding="utf-8"))

    sparql = SPARQLWrapper(ENDPOINT, agent=USER_AGENT)
    rows: list[dict] = []
    offset = 0
    while True:
        print(f"  [{label}] fetch offset={offset} ...", flush=True)
        try:
            batch = _run_query(sparql, class_qid, offset, PAGE_SIZE)
        except Exception as exc:
            print(f"  [{label}] ERROR at offset {offset}: {exc}", file=sys.stderr)
            raise
        rows.extend(batch)
        print(f"  [{label}]   +{len(batch)} (total {len(rows)})")
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(SLEEP_BETWEEN_PAGES)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"  [{label}] cached {len(rows)} rows -> {cache_path.name}")
    return rows


def _qid_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    m = QID_RE.search(uri)
    return m.group(1) if m else None


def _val(row: dict, key: str) -> str | None:
    binding = row.get(key)
    if binding is None:
        return None
    v = binding.get("value")
    return v if v not in ("", None) else None


def _float_val(row: dict, key: str) -> float | None:
    """Coerce numeric bindings, ignoring malformed/generated-node values."""
    value = _val(row, key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def flatten_row(row: dict, classes_seen: list[str]) -> dict:
    return {
        "qid": _qid_from_uri(_val(row, "item")),
        "label_en": _val(row, "label_en"),
        "label_fr": _val(row, "label_fr"),
        "aliases_en": _val(row, "aliases_en") or "",
        "inception": _val(row, "inception"),
        "dissolution": _val(row, "dissolution"),
        "area_km2": _float_val(row, "area"),
        "population": _float_val(row, "population"),
        "country_qid": _qid_from_uri(_val(row, "country")),
        "coords": _val(row, "coords"),
        "image": _val(row, "image"),
        "wikipedia_en": _val(row, "wikipedia_en"),
        "wd_classes": list(classes_seen),
    }


def merge_into(rows_by_qid: dict[str, dict], flat: dict) -> None:
    qid = flat["qid"]
    if not qid:
        return
    existing = rows_by_qid.get(qid)
    if existing is None:
        rows_by_qid[qid] = flat
        return
    existing["wd_classes"] = sorted(set(existing["wd_classes"]) | set(flat["wd_classes"]))
    for k, v in flat.items():
        if k == "wd_classes":
            continue
        if existing.get(k) in (None, "", []) and v not in (None, "", []):
            existing[k] = v


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--class",
        dest="class_qid",
        default=None,
        help="Only extract this class QID (smoke test). If omitted, run all CLASSES.",
    )
    parser.add_argument("--force", action="store_true", help="Ignore cache, refetch.")
    args = parser.parse_args()

    if args.class_qid:
        targets = {args.class_qid: CLASSES.get(args.class_qid, args.class_qid)}
    else:
        targets = CLASSES

    rows_by_qid: dict[str, dict] = {}
    for class_qid, label in targets.items():
        print(f"[{label}] {class_qid}")
        rows = extract_class(class_qid, label, force=args.force)
        for row in rows:
            merge_into(rows_by_qid, flatten_row(row, [class_qid]))

    df = pd.DataFrame(rows_by_qid.values())
    print(f"\nUnique QIDs: {len(df)}")
    if df.empty:
        print("No rows. Exiting.")
        return

    before = len(df)
    df = df.dropna(subset=["inception"]).reset_index(drop=True)
    print(f"Dropped {before - len(df)} entries with no inception date; kept {len(df)}.")

    PARQUET_OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PARQUET_OUT, index=False)
    print(f"Wrote {PARQUET_OUT}")


if __name__ == "__main__":
    main()
