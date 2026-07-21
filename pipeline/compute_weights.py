"""Compute reproducible polity band weights from population, area, and complexity."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "pipeline" / "weights.toml"
HYDE_PATH = ROOT / "sources" / "hyde_pop_by_polity.parquet"
MADDISON_PATH = ROOT / "sources" / "maddison_by_polity.parquet"
SESHAT_PATH = ROOT / "sources" / "seshat_timeseries.parquet"
REPORT_PATH = ROOT / "reports" / "weight_summary.md"


def bucket_year(year: int, interval: int) -> int:
    return (int(year) // interval) * interval


def consolidate_population(
    hyde: pd.DataFrame,
    maddison: pd.DataFrame,
    interval: int,
    hyde_exclusions: set[str] | None = None,
) -> pd.DataFrame:
    hyde = hyde[~hyde["polity_id"].isin(hyde_exclusions or set())]
    frames = []
    for source, frame in (("hyde", hyde), ("maddison", maddison)):
        selected = frame[["polity_id", "year", "population"]].copy()
        selected["source"] = source
        selected["bucket"] = selected["year"].map(lambda year: bucket_year(year, interval))
        frames.append(selected)
    combined = pd.concat(frames, ignore_index=True).dropna(subset=["population"])
    rows = []
    for (polity_id, bucket), group in combined.groupby(["polity_id", "bucket"]):
        preferred = group[group["source"] == "maddison"]
        chosen = preferred if not preferred.empty else group
        rows.append(
            {
                "polity_id": polity_id,
                "year": int(bucket),
                "population": float(chosen["population"].median()),
                "population_source": "maddison" if not preferred.empty else "hyde",
            }
        )
    return pd.DataFrame(rows)


def interpolate_feature(rows: pd.DataFrame, year: int, column: str) -> float:
    available = rows.dropna(subset=[column]).sort_values("year")
    if available.empty:
        return float("nan")
    return float(np.interp(year, available["year"], available[column]))


def normalize_weights(frame: pd.DataFrame, config: dict) -> pd.DataFrame:
    result = frame.copy()
    coefficients = config["coefficients"]
    settings = config["normalization"]
    result["population_log10"] = np.log10(result["population"].clip(lower=0) + 1)
    result["century"] = result["year"].map(lambda year: bucket_year(year, 100))
    result["area_missing"] = result["area_km2_log10"].isna()
    result["complexity_missing"] = result["social_complexity_index"].isna()
    for column in ("area_km2_log10", "social_complexity_index"):
        era_median = result.groupby("century")[column].transform("median")
        result[column] = result[column].fillna(era_median).fillna(result[column].median()).fillna(0)
    result["raw_weight"] = (
        coefficients["population"] * result["population_log10"]
        + coefficients["area"] * result["area_km2_log10"]
        + coefficients["complexity"]
        * (result["social_complexity_index"] / settings["complexity_scale"] * 10)
    )
    upper = result.groupby("century")["raw_weight"].transform(
        lambda values: float(values.quantile(settings["percentile"]))
    )
    lower = result.groupby("century")["raw_weight"].transform(
        lambda values: float(values.quantile(settings["lower_percentile"]))
    )
    spread = (upper - lower).clip(lower=0.000001)
    result["weight"] = (1 + 9 * (result["raw_weight"] - lower) / spread).clip(
        settings["minimum_weight"], settings["maximum_weight"]
    )
    result["weight_imputed"] = (
        (result["population_source"] == "hyde")
        | result["area_missing"]
        | result["complexity_missing"]
    )
    return result


def run() -> dict[str, int]:
    config = tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    interval = int(config["normalization"]["interval_years"])
    documents = []
    seshat_ids_by_polity = {}
    for path in (ROOT / "polities").glob("*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        documents.append((path, document))
        seshat_ids_by_polity[document["id"]] = (document.get("external_ids") or {}).get(
            "seshat", []
        )
    maddison = pd.read_parquet(MADDISON_PATH)
    direct_types = yaml.safe_load((ROOT / "sources" / "wikidata_direct_types.json").read_text())
    sovereign_qids = {
        qid
        for qid, metadata in direct_types.items()
        if {"Q6256", "Q3624078"} & set(metadata.get("types", []))
    }
    maddison_ids = set(maddison["polity_id"])
    unmapped_modern = {
        document["id"]
        for _, document in documents
        if document.get("end") is None
        and (document.get("external_ids") or {}).get("wikidata") in sovereign_qids
        and document["id"] not in maddison_ids
    }
    population = consolidate_population(
        pd.read_parquet(HYDE_PATH), maddison, interval, unmapped_modern
    )
    seshat = pd.read_parquet(SESHAT_PATH)
    seshat_by_id = {key: group for key, group in seshat.groupby("seshat_id")}

    areas = []
    complexities = []
    for row in population.itertuples(index=False):
        source_rows = [
            seshat_by_id[seshat_id]
            for seshat_id in seshat_ids_by_polity.get(row.polity_id, [])
            if seshat_id in seshat_by_id
        ]
        combined = pd.concat(source_rows, ignore_index=True) if source_rows else pd.DataFrame()
        areas.append(
            interpolate_feature(combined, row.year, "area_km2_log10")
            if not combined.empty
            else float("nan")
        )
        complexities.append(
            interpolate_feature(combined, row.year, "social_complexity_index")
            if not combined.empty
            else float("nan")
        )
    population["area_km2_log10"] = areas
    population["social_complexity_index"] = complexities
    weighted = normalize_weights(population, config)
    by_polity = {key: group for key, group in weighted.groupby("polity_id")}

    updated = 0
    measured = 0
    for path, document in documents:
        if document.get("entity_type", "polity") in {
            "culture", "people", "tribe", "archaeological_horizon"
        }:
            document["weight_by_era"] = {int(document["start"]): 3}
            document["weight_imputed"] = True
            document["sources"] = sorted(
                set(document.get("sources", [])) - {"hyde", "maddison"}
            )
            path.write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            continue
        rows = by_polity.get(document["id"])
        if rows is None:
            generated_sources = {"hyde", "maddison"} & set(document.get("sources", []))
            if generated_sources:
                document["weight_by_era"] = {int(document["start"]): 5}
                document["weight_imputed"] = True
                document["sources"] = sorted(set(document.get("sources", [])) - generated_sources)
                path.write_text(
                    yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
                )
            continue
        document["weight_by_era"] = {
            int(row.year): round(float(row.weight), 2)
            for row in rows.sort_values("year").itertuples(index=False)
            if document["start"] <= row.year <= (document.get("end") or 2100)
        }
        if not document["weight_by_era"]:
            continue
        document["weight_imputed"] = bool(rows["weight_imputed"].any())
        sources = set(document.get("sources", []))
        sources.update(rows["population_source"].unique())
        document["sources"] = sorted(sources)
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
        updated += 1
        measured += not document["weight_imputed"]

    lines = [
        "# Weight computation",
        "",
        f"- Updated polities: {updated:,}",
        f"- Polity-era weights: {len(weighted):,}",
        f"- Fully measured polities: {measured:,}",
        f"- Imputed polities: {updated - measured:,}",
        f"- Era interval: {interval} years",
        "",
        "HYDE centroid-radius populations and missing area/complexity values remain explicitly",
        "imputed. Maddison population overrides HYDE for mapped modern sovereign states.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"updated": updated, "measured": measured, "eras": len(weighted)}


if __name__ == "__main__":
    counts = run()
    print(
        f"Weights: updated={counts['updated']:,}, eras={counts['eras']:,}, "
        f"fully_measured={counts['measured']:,}"
    )
