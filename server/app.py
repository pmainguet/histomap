"""Serve Histomap pages and a constrained local review/pipeline API."""

from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipeline.review_cli import pending_records, polity_metadata, save_decision

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_ACTIONS = {
    "reconcile": ["pipeline/reconcile.py"],
    "build": ["build.py"],
    "compute-weights": ["pipeline/compute_weights.py"],
}
EQUINOX_URL = (
    "https://github.com/seshatdb/Equinox_Data/blob/master/"
    "Equinox_on_GitHub_June9_2022.xlsx"
)


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


def create_app(root: Path = ROOT) -> FastAPI:
    application = FastAPI(title="Histomap", version="0.1.0")
    web_dir = root / "web"
    reports_dir = root / "reports"
    review_path = reports_dir / "seshat_reconciliation.jsonl"
    decisions_path = reports_dir / "seshat_review_decisions.jsonl"
    polities_dir = root / "polities"
    metadata = polity_metadata(polities_dir)
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

    @application.post("/api/reviews/{seshat_id}")
    async def decide_review(seshat_id: str, request: ReviewDecision) -> dict:
        record = reviews_by_id.get(seshat_id)
        if record is None:
            raise HTTPException(404, "Review is not pending")
        if request.decision == "defer":
            return {"status": "deferred", "seshat_id": seshat_id}
        decision = {"seshat_id": seshat_id, "decision": request.decision}
        if request.decision == "accept":
            candidate_ids = {candidate["polity_id"] for candidate in record["candidates"]}
            if request.polity_id not in candidate_ids:
                raise HTTPException(422, "polity_id must identify one of the proposed candidates")
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
