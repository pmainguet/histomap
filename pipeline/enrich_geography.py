"""Assign present-day country and continent geography to canonical polities."""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
PARQUET_PATH = ROOT / "sources" / "wikidata.parquet"
RELATIONSHIP_CACHE = ROOT / "sources" / "wikidata_relationships.json"
COUNTRY_CACHE = ROOT / "sources" / "wikidata_country_metadata.json"
BOUNDARIES_PATH = ROOT / "sources" / "ne_110m_admin_0_countries.geojson"
HIGH_RES_BOUNDARIES_PATH = ROOT / "sources" / "ne_10m_admin_0_countries.geojson"
REPORT_PATH = ROOT / "reports" / "geography_coverage.md"


def field_locked(document: dict, field: str) -> bool:
    return field in set(document.get("manual_overrides", []))
NATURAL_EARTH_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_110m_admin_0_countries.geojson"
)
HIGH_RES_BOUNDARIES_URL = (
    "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"
)
API_URL = "https://www.wikidata.org/w/api.php"
USER_AGENT = "histomap/0.1 (https://github.com/pmainguet/histomap)"
BATCH_SIZE = 50
CONTINENT_QIDS = {
    "Q15": "africa",
    "Q18": "south_america",
    "Q46": "europe",
    "Q48": "asia",
    "Q49": "north_america",
    "Q51": "antarctica",
    "Q538": "oceania",
}
POINT_RE = re.compile(r"Point\(([-+\d.]+)\s+([-+\d.]+)\)")


def parse_point(value: object) -> tuple[float, float] | None:
    if value is None or pd.isna(value):
        return None
    match = POINT_RE.fullmatch(str(value).strip())
    if not match:
        return None
    return float(match.group(1)), float(match.group(2))


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous[:2]
        x2, y2 = current[:2]
        if (y1 > lat) != (y2 > lat):
            crossing = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < crossing:
                inside = not inside
        previous = current
    return inside


def point_in_polygon(lon: float, lat: float, polygon: list[list[list[float]]]) -> bool:
    return point_in_ring(lon, lat, polygon[0]) and not any(
        point_in_ring(lon, lat, hole) for hole in polygon[1:]
    )


def locate_point(lon: float, lat: float, features: list[dict]) -> tuple[str, str] | None:
    for feature in features:
        geometry = feature.get("geometry") or {}
        polygons = (
            [geometry.get("coordinates", [])]
            if geometry.get("type") == "Polygon"
            else geometry.get("coordinates", [])
            if geometry.get("type") == "MultiPolygon"
            else []
        )
        if any(point_in_polygon(lon, lat, polygon) for polygon in polygons):
            properties = feature.get("properties", {})
            iso = properties.get("ISO_A2_EH") or properties.get("ISO_A2")
            continent = str(properties.get("CONTINENT", "")).lower().replace(" ", "_")
            if iso and len(iso) == 2 and iso != "-99":
                return iso.upper(), continent
    return None


def point_segment_distance(
    lon: float, lat: float, start: list[float], end: list[float]
) -> float:
    """Return an approximate planar distance in degrees for coastal fallback matching."""
    x1, y1 = start[:2]
    x2, y2 = end[:2]
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(lon - x1, lat - y1)
    amount = max(
        0.0,
        min(1.0, ((lon - x1) * dx + (lat - y1) * dy) / (dx * dx + dy * dy)),
    )
    return math.hypot(lon - (x1 + amount * dx), lat - (y1 + amount * dy))


def locate_near_coast(
    lon: float, lat: float, features: list[dict], max_distance: float = 0.5
) -> tuple[str, str] | None:
    """Find a unique nearby country when coarse polygons leave a small coastal gap."""
    matches: list[tuple[float, str, str]] = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        polygons = (
            [geometry.get("coordinates", [])]
            if geometry.get("type") == "Polygon"
            else geometry.get("coordinates", [])
            if geometry.get("type") == "MultiPolygon"
            else []
        )
        distances = [
            point_segment_distance(lon, lat, ring[index - 1], ring[index])
            for polygon in polygons
            for ring in polygon
            for index in range(len(ring))
        ]
        properties = feature.get("properties", {})
        iso = properties.get("ISO_A2_EH") or properties.get("ISO_A2")
        continent = str(properties.get("CONTINENT", "")).lower().replace(" ", "_")
        if distances and iso and len(iso) == 2 and iso != "-99":
            matches.append((min(distances), iso.upper(), continent))
    matches.sort()
    if not matches or matches[0][0] > max_distance:
        return None
    if len(matches) > 1 and matches[1][0] - matches[0][0] < 0.05:
        return None
    return matches[0][1], matches[0][2]


def load_boundaries(offline: bool = False, high_resolution: bool = False) -> list[dict]:
    path = HIGH_RES_BOUNDARIES_PATH if high_resolution else BOUNDARIES_PATH
    url = HIGH_RES_BOUNDARIES_URL if high_resolution else NATURAL_EARTH_URL
    if not path.exists():
        if offline:
            raise ValueError("Natural Earth boundary cache is missing")
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=120) as response:  # noqa: S310 - fixed HTTPS endpoint
            payload = response.read()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return json.loads(path.read_text(encoding="utf-8"))["features"]


def _claim_values(entity: dict, prop: str) -> list[object]:
    values = []
    for claim in entity.get("claims", {}).get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if value is not None:
            values.append(value)
    return values


def _fetch_country_batch(qids: list[str]) -> dict[str, dict]:
    params = urlencode(
        {
            "action": "wbgetentities",
            "format": "json",
            "formatversion": "2",
            "ids": "|".join(qids),
            "props": "claims|labels",
            "languages": "en",
        }
    )
    request = Request(f"{API_URL}?{params}", headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response:  # noqa: S310 - fixed HTTPS endpoint
                entities = json.load(response).get("entities", {})
            result = {}
            for qid in qids:
                entity = entities.get(qid, {})
                iso_values = [value for value in _claim_values(entity, "P297") if isinstance(value, str)]
                continent_values = [
                    value.get("id")
                    for value in _claim_values(entity, "P30")
                    if isinstance(value, dict) and value.get("id")
                ]
                result[qid] = {
                    "label": entity.get("labels", {}).get("en", {}).get("value", qid),
                    "iso2": iso_values[0].upper() if iso_values else None,
                    "continents": sorted(
                        {CONTINENT_QIDS[value] for value in continent_values if value in CONTINENT_QIDS}
                    ),
                }
            return result
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def country_metadata(qids: set[str], offline: bool = False) -> dict[str, dict]:
    cache = json.loads(COUNTRY_CACHE.read_text(encoding="utf-8")) if COUNTRY_CACHE.exists() else {}
    missing = sorted(qids - set(cache))
    if offline and missing:
        raise ValueError(f"country metadata cache is missing {len(missing)} QIDs")
    batches = [missing[index : index + BATCH_SIZE] for index in range(0, len(missing), BATCH_SIZE)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_fetch_country_batch, batch) for batch in batches]
        for future in as_completed(futures):
            cache.update(future.result())
            COUNTRY_CACHE.parent.mkdir(parents=True, exist_ok=True)
            COUNTRY_CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
    return cache


def geography_category(geography: dict) -> str:
    if geography.get("present_countries"):
        return "country"
    if geography.get("continents"):
        return "continent_only"
    if geography.get("centroid"):
        return "centroid_only"
    return "unknown"


def run(offline: bool = False, only_missing: bool = False) -> dict[str, int]:
    boundaries = load_boundaries(offline, high_resolution=only_missing)
    frame = pd.read_parquet(PARQUET_PATH, columns=["qid", "coords", "country_qid"])
    records = {str(row["qid"]): row for row in frame.to_dict(orient="records")}
    p17: dict[str, set[str]] = {}
    if RELATIONSHIP_CACHE.exists():
        for link in json.loads(RELATIONSHIP_CACHE.read_text(encoding="utf-8")):
            if link["property"] == "P17":
                p17.setdefault(link["source"], set()).add(link["target"])
    for qid, record in records.items():
        country = record.get("country_qid")
        if country is not None and not pd.isna(country):
            p17.setdefault(qid, set()).add(str(country))
    metadata = country_metadata(set().union(*p17.values()) if p17 else set(), offline)

    counts = {"country": 0, "continent_only": 0, "centroid_only": 0, "unknown": 0}
    by_tier: dict[str, dict[str, int]] = {}
    for path in POLITIES_DIR.glob("*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        existing_geography = document.get("geography") or {}
        missing_with_centroid = bool(existing_geography.get("centroid")) and not any(
            existing_geography.get(key) for key in ("continents", "present_countries")
        )
        if field_locked(document, "geography") or (only_missing and not missing_with_centroid):
            category = geography_category(existing_geography)
            counts[category] += 1
            tier = document.get("visibility_tier", "detailed")
            by_tier.setdefault(tier, {key: 0 for key in counts})[category] += 1
            continue
        qid = (document.get("external_ids") or {}).get("wikidata")
        record = records.get(qid, {})
        point = parse_point(record.get("coords"))
        if point is None and existing_geography.get("centroid"):
            centroid = existing_geography["centroid"]
            point = float(centroid["lon"]), float(centroid["lat"])
        countries: set[str] = set()
        continents: set[str] = set()
        for country_qid in p17.get(qid, set()):
            info = metadata.get(country_qid, {})
            if info.get("iso2") and len(info["iso2"]) == 2:
                countries.add(info["iso2"])
            continents.update(info.get("continents", []))
        located = locate_point(*point, boundaries) if point else None
        if located is None and point and only_missing:
            located = locate_near_coast(*point, boundaries)
        if located:
            countries.add(located[0])
            if located[1]:
                continents.add(located[1])
        confidence = "medium" if p17.get(qid) else "low" if located else None
        if not countries and not continents and not point and any(
            existing_geography.get(key) for key in ("continents", "present_countries", "centroid")
        ):
            geography = existing_geography
            countries = set(existing_geography.get("present_countries", []))
            continents = set(existing_geography.get("continents", []))
        else:
            geography = {
                "continents": sorted(continents),
                "present_countries": sorted(countries),
                "centroid": {"lat": point[1], "lon": point[0]} if point else None,
                "confidence": confidence,
            }
            if len(continents) > 1 and located and located[1]:
                geography["primary_continent"] = located[1]
        document["geography"] = geography
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
        category = (
            "country"
            if countries
            else "continent_only"
            if continents
            else "centroid_only"
            if point
            else "unknown"
        )
        counts[category] += 1
        tier = document.get("visibility_tier", "detailed")
        by_tier.setdefault(tier, {key: 0 for key in counts})[category] += 1

    lines = ["# Geography coverage", "", "## Overall", ""]
    lines.extend(f"- {key.replace('_', ' ').title()}: {value:,}" for key, value in counts.items())
    for tier, values in sorted(by_tier.items()):
        lines.extend(["", f"## {tier.title()}", ""])
        lines.extend(f"- {key.replace('_', ' ').title()}: {value:,}" for key, value in values.items())
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Only fill records with a centroid but no country or continent",
    )
    args = parser.parse_args()
    counts = run(offline=args.offline, only_missing=args.only_missing)
    print("Geography enrichment: " + ", ".join(f"{key}={value}" for key, value in counts.items()))


if __name__ == "__main__":
    main()
