"""Serve Histomap pages and a constrained local review/pipeline API."""

from __future__ import annotations

import asyncio
import json
import math
import sys
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import yaml

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rapidfuzz import fuzz

from pipeline.review_cli import pending_records, polity_metadata, save_decision
from schema import Geography

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_ACTIONS = {
    "apply-reviews": ["-m", "pipeline.apply_review_decisions"],
    "reconcile": ["pipeline/reconcile.py"],
    "build": ["-m", "pipeline.rebuild_timeline"],
    "compute-weights": ["pipeline/compute_weights.py"],
}
EQUINOX_URL = (
    "https://github.com/seshatdb/Equinox_Data/blob/master/"
    "Equinox_on_GitHub_June9_2022.xlsx"
)
CONTINENTS = ["africa", "asia", "europe", "north_america", "south_america", "oceania", "antarctica"]


def english_wikipedia_url(external_ids: dict) -> str | None:
    if external_ids.get("wikipedia_en"):
        return str(external_ids["wikipedia_en"])
    if external_ids.get("wikidata"):
        return (
            "https://www.wikidata.org/wiki/Special:GoToLinkedPage/"
            f"enwiki/{external_ids['wikidata']}"
        )
    return None


class ReviewDecision(BaseModel):
    decision: Literal["accept", "reject", "defer"]
    polity_id: str | None = None


class GeographyUpdate(BaseModel):
    continents: list[str]
    primary_continent: str | None = None
    present_countries: list[str]


def clean_json(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: clean_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_json(item) for item in value]
    return value


def add_source_links(record: dict, metadata: dict[str, dict]) -> dict:
    enriched = dict(record)
    source_name = record.get("seshat_long_name") or record["seshat_name"]
    enriched["source_links"] = [
        {
            "label": "Seshat polity search",
            "url": "https://www.seshat-db.com/api/core/polities/?search="
            + quote(str(source_name)),
        },
        {"label": "Equinox 2020 workbook", "url": EQUINOX_URL},
        {
            "label": "Google search",
            "url": "https://www.google.com/search?q=" + quote(str(source_name)),
        },
    ]
    enriched_candidates = []
    for candidate in record.get("candidates", []):
        enriched_candidate = dict(candidate)
        document = metadata.get(candidate["polity_id"], {})
        external_ids = document.get("external_ids") or {}
        enriched_candidate["canonical_start"] = document.get("start")
        enriched_candidate["canonical_end"] = document.get("end")
        enriched_candidate["canonical_sources"] = document.get("sources", [])
        enriched_candidate["external_ids"] = external_ids
        links = []
        if external_ids.get("wikidata"):
            links.append(
                {
                    "label": "Wikidata",
                    "url": f"https://www.wikidata.org/wiki/{external_ids['wikidata']}",
                }
            )
        wikipedia_url = english_wikipedia_url(external_ids)
        if wikipedia_url:
            links.append({"label": "Wikipedia (English)", "url": wikipedia_url})
        if external_ids.get("seshat"):
            links.append(
                {
                    "label": "Seshat polity search",
                    "url": "https://www.seshat-db.com/api/core/polities/?search="
                    + quote(str(document.get("canonical_name", candidate["canonical_name"]))),
                }
            )
        comparison_query = f"{candidate['canonical_name']} vs {source_name}"
        links.append(
            {
                "label": "Google comparison",
                "url": "https://www.google.com/search?q=" + quote(comparison_query),
            }
        )
        enriched_candidate["source_links"] = links
        enriched_candidates.append(enriched_candidate)
    enriched["candidates"] = enriched_candidates
    return enriched


def search_polities(query: str, metadata: dict[str, dict], limit: int = 10) -> list[dict]:
    query = query.strip()
    ranked = []
    for polity_id, document in metadata.items():
        if document.get("eligibility") == "excluded":
            continue
        names = [str(document.get("canonical_name", "")), polity_id]
        for key, value in (document.get("names") or {}).items():
            if key == "aliases_en":
                names.extend(part.strip() for part in str(value).split("|") if part.strip())
            elif value:
                names.append(str(value))
        score = max(float(fuzz.WRatio(query, name)) for name in names if name)
        exact_alias = any(query.casefold() == name.casefold() for name in names if name)
        ranked.append((not exact_alias, -score, str(document.get("canonical_name", "")), polity_id))
    results = []
    for _, negative_score, _, polity_id in sorted(ranked)[:limit]:
        document = metadata[polity_id]
        external_ids = document.get("external_ids") or {}
        links = []
        if external_ids.get("wikidata"):
            links.append({"label": "Wikidata", "url": f"https://www.wikidata.org/wiki/{external_ids['wikidata']}"})
        wikipedia_url = english_wikipedia_url(external_ids)
        if wikipedia_url:
            links.append({"label": "Wikipedia (English)", "url": wikipedia_url})
        results.append(
            {
                "polity_id": polity_id,
                "canonical_name": document.get("canonical_name", polity_id),
                "canonical_start": document.get("start"),
                "canonical_end": document.get("end"),
                "canonical_sources": document.get("sources", []),
                "source_links": links,
                "search_score": round(-negative_score, 1),
            }
        )
    return results


def create_app(root: Path = ROOT) -> FastAPI:
    application = FastAPI(title="Histomap", version="0.1.0")
    web_dir = root / "web"
    reports_dir = root / "reports"
    review_path = reports_dir / "seshat_reconciliation.jsonl"
    decisions_path = reports_dir / "seshat_review_decisions.jsonl"
    polities_dir = root / "polities"
    metadata = polity_metadata(polities_dir)
    country_metadata_path = root / "sources" / "wikidata_country_metadata.json"
    country_metadata = (
        json.loads(country_metadata_path.read_text(encoding="utf-8"))
        if country_metadata_path.exists()
        else {}
    )
    country_options = {
        info["iso2"]: info.get("label", info["iso2"])
        for info in country_metadata.values()
        if info.get("iso2") and len(info["iso2"]) == 2
    }
    review_queue = pending_records(review_path, decisions_path, metadata=metadata)
    reviews_by_id = {record["seshat_id"]: record for record in review_queue}
    job = {"status": "idle", "action": None, "output": "", "returncode": None}
    job_lock = asyncio.Lock()

    def refresh_review_queue() -> None:
        metadata.clear()
        metadata.update(polity_metadata(polities_dir))
        review_queue.clear()
        review_queue.extend(pending_records(review_path, decisions_path, metadata=metadata))
        reviews_by_id.clear()
        reviews_by_id.update((record["seshat_id"], record) for record in review_queue)

    def refresh_separate_entities() -> None:
        for path in polities_dir.glob("seshat_*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            metadata[document["id"]] = document

    application.mount("/static", StaticFiles(directory=web_dir), name="static")

    @application.get("/", include_in_schema=False)
    async def timeline() -> FileResponse:
        return FileResponse(web_dir / "index.html")

    @application.get("/review", include_in_schema=False)
    async def review_page() -> FileResponse:
        return FileResponse(web_dir / "review.html")

    @application.get("/data.json", include_in_schema=False)
    async def data() -> FileResponse:
        path = root / "data.json"
        if not path.exists():
            raise HTTPException(404, "Run the build action first")
        return FileResponse(path)

    @application.get("/transitions.json", include_in_schema=False)
    async def transitions() -> FileResponse:
        path = root / "transitions.json"
        if not path.exists():
            raise HTTPException(404, "Run the build action first")
        return FileResponse(path)

    @application.get("/api/reviews")
    async def reviews(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)) -> dict:
        items = [add_source_links(record, metadata) for record in review_queue[offset : offset + limit]]
        return clean_json({"total": len(review_queue), "offset": offset, "items": items})

    @application.get("/api/polities/search")
    async def search_all_polities(
        q: str = Query(..., min_length=2), limit: int = Query(10, ge=1, le=25)
    ) -> dict:
        return clean_json({"query": q, "items": search_polities(q, metadata, limit)})

    @application.get("/api/options/geography")
    async def geography_options() -> dict:
        return {
            "continents": CONTINENTS,
            "countries": [
                {"code": code, "label": label}
                for code, label in sorted(country_options.items(), key=lambda item: item[1])
            ],
        }

    @application.patch("/api/polities/{polity_id}/geography")
    async def update_polity_geography(polity_id: str, request: GeographyUpdate) -> dict:
        document = metadata.get(polity_id)
        path = polities_dir / f"{polity_id}.yaml"
        if document is None or not path.exists():
            raise HTTPException(404, "Unknown Histomap entity")
        unknown_continents = sorted(set(request.continents) - set(CONTINENTS))
        unknown_countries = sorted(set(request.present_countries) - set(country_options))
        if unknown_continents:
            raise HTTPException(422, f"Unknown continents: {', '.join(unknown_continents)}")
        if unknown_countries:
            raise HTTPException(422, f"Unknown country codes: {', '.join(unknown_countries)}")
        existing = document.get("geography") or {}
        geography = Geography.model_validate(
            {
                "continents": sorted(set(request.continents)),
                "primary_continent": request.primary_continent,
                "present_countries": sorted(set(request.present_countries)),
                "centroid": existing.get("centroid"),
                "confidence": "high",
            }
        ).model_dump(mode="json", exclude_none=True)
        document["geography"] = geography
        document["manual_overrides"] = sorted(
            set(document.get("manual_overrides", [])) | {"geography"}
        )
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        metadata[polity_id] = document
        return {
            "status": "saved",
            "polity_id": polity_id,
            "geography": geography,
            "manual_overrides": document["manual_overrides"],
        }

    @application.post("/api/reviews/{seshat_id}")
    async def decide_review(seshat_id: str, request: ReviewDecision) -> dict:
        record = reviews_by_id.get(seshat_id)
        if record is None:
            raise HTTPException(404, "Review is not pending")
        if request.decision == "defer":
            return {"status": "deferred", "seshat_id": seshat_id}
        decision = {"seshat_id": seshat_id, "decision": request.decision}
        if request.decision == "accept":
            target = metadata.get(request.polity_id or "")
            if target is None or target.get("eligibility") == "excluded":
                raise HTTPException(422, "polity_id must identify an eligible Histomap entity")
            decision["polity_id"] = request.polity_id
        save_decision(decision, decisions_path)
        reviews_by_id.pop(seshat_id, None)
        review_queue.remove(record)
        return {"status": "saved", **decision}

    async def run_action(action: str) -> None:
        async with job_lock:
            job.update(status="running", action=action, output="", returncode=None)
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                *ALLOWED_ACTIONS[action],
                cwd=root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await process.communicate()
            job.update(
                status="complete" if process.returncode == 0 else "failed",
                output=output.decode("utf-8", errors="replace")[-20000:],
                returncode=process.returncode,
            )
            if process.returncode == 0 and action == "reconcile":
                refresh_review_queue()
            elif process.returncode == 0 and action == "apply-reviews":
                refresh_separate_entities()

    @application.post("/api/actions/{action}", status_code=202)
    async def start_action(action: str) -> dict:
        if action not in ALLOWED_ACTIONS:
            raise HTTPException(404, "Unknown action")
        if job["status"] in {"queued", "running"}:
            raise HTTPException(409, f"{job['action']} is already running")
        job.update(status="queued", action=action, output="", returncode=None)
        asyncio.create_task(run_action(action))
        return {"status": "accepted", "action": action}

    @application.get("/api/actions/status")
    async def action_status() -> dict:
        return job.copy()

    @application.get("/web", include_in_schema=False)
    async def old_web_path() -> RedirectResponse:
        return RedirectResponse("/")

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.app:app", host="127.0.0.1", port=8000, reload=False)
