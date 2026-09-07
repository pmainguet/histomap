"""Serve Histomap pages and a constrained local review/pipeline API."""

from __future__ import annotations

import asyncio
import json
import math
import re
import sys
import unicodedata
from pathlib import Path
from typing import Literal

import yaml

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from rapidfuzz import fuzz

from pipeline.review_cli import polity_metadata
from pipeline.backfill_entity_types import normalized_relationship_kind, relationship_kind
from pipeline.historical_regions import historical_region_for_country
from schema import Geography, Period, Polity

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_ACTIONS = {
    "apply-reviews": ["-m", "pipeline.apply_review_decisions"],
    "reconcile": ["pipeline/reconcile.py"],
    "build": ["-m", "pipeline.rebuild_timeline"],
    "compute-weights": ["pipeline/compute_weights.py"],
}
CONTINENTS = ["africa", "asia", "europe", "north_america", "south_america", "oceania", "antarctica"]
# ROADMAP.md item 0 bis: which of Polity.relationships' 8 EntityRelationship
# kinds (see schema.py) read as literal containment/derivation -- "this
# entity IS a phase, component, or governed part of that one" -- the
# detail_of shape. political_successor is deliberately excluded (two
# sequential, distinct entities, not a container relationship, same
# reasoning as documented_successor elsewhere in this file);
# associated_people is a loose demographic/ethnic association, not a
# hierarchy claim. Kinds picked live, 7 September 2026.
DETAIL_OF_RELATIONSHIP_KINDS = {
    "political_parent", "administrative_part_of", "cultural_component",
    "archaeological_sequence", "cultural_sequence", "part_of_civilization",
}
# present_countries answers "which modern country is this historical
# territory in today" -- a dissolved state is never a valid answer to
# that, so these never belong in the picker built from country_metadata
# (Wikidata's own country records, which include defunct states with
# their own ISO codes). Found live, 7 September 2026, via a user report
# ("Soviet Union" showing up next to "Russia"); see
# pipeline/drop_defunct_country_codes.py for the matching data cleanup.
# YU (Yugoslavia) deliberately stays OUT of this set -- see
# historical_regions.py's own docstring for why it's a legitimate code
# here, unlike SU/CS/DD.
DEFUNCT_COUNTRY_CODES = {"SU", "CS", "DD"}


def english_wikipedia_url(external_ids: dict) -> str | None:
    if external_ids.get("wikipedia_en"):
        return str(external_ids["wikipedia_en"])
    if external_ids.get("wikidata"):
        return (
            "https://www.wikidata.org/wiki/Special:GoToLinkedPage/"
            f"enwiki/{external_ids['wikidata']}"
        )
    return None


class GeographyUpdate(BaseModel):
    continents: list[str]
    primary_continent: str | None = None
    present_countries: list[str]


class EntityTypeUpdate(BaseModel):
    entity_type: Literal[
        "polity",
        "civilization",
        "subdivision",
        "micronation",
        "culture",
        "people",
        "tribe",
        "archaeological_horizon",
    ]


class PeriodPromotionUpdate(BaseModel):
    entity_type: Literal[
        "polity", "civilization", "subdivision", "micronation", "culture", "people",
        "tribe", "archaeological_horizon",
    ]


class ConsolidationDecision(BaseModel):
    decision: Literal[
        "independent", "same_entity", "detail_of",
        "candidate_detail_of", "period", "discarded",
    ]
    target_id: str | None = None


class PolityCreate(BaseModel):
    canonical_name: str = Field(min_length=1)
    entity_type: Literal[
        "polity", "civilization", "subdivision", "micronation", "culture", "people",
        "tribe", "archaeological_horizon",
    ] = "polity"
    start: int
    end: int | None = None
    present_countries: list[str] = Field(min_length=1)


class PeriodCreate(BaseModel):
    canonical_name: str = Field(min_length=1)
    start: int
    end: int
    present_countries: list[str] = Field(min_length=1)


def slugify_entity_id(name: str, taken_ids: set[str]) -> str:
    """Turn a canonical_name into a unique snake_case id matching
    schema.py's ID_PATTERN (snake_case, starting with a letter). Same
    normalization as pipeline/wd_to_yaml.py's slugify(), duplicated here
    rather than imported -- that module pulls in pandas for its Parquet
    conversion, too heavy to import here for a few lines of string logic.
    Collisions (ids are a single namespace shared by polities and periods,
    see validate_period_detail_of) get a numeric suffix."""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_") or "entity"
    if not base[0].isalpha():
        base = f"entity_{base}"
    candidate = base
    suffix = 2
    while candidate in taken_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def derive_geography_for_countries(
    present_countries: list[str], iso2_to_continents: dict[str, list[str]]
) -> dict:
    """Builds the same geography a curator would normally fill in by hand
    (or that enrich_geography.py/derive_historical_regions.py backfill
    later) at creation time, so a newly created record is placed
    sensibly in /explore's tree right away rather than showing
    "Unclassified" until the next full pipeline run."""
    countries = sorted(set(present_countries))
    continents = sorted({c for code in countries for c in iso2_to_continents.get(code, [])})
    regions = sorted({r for code in countries if (r := historical_region_for_country(code))})
    geography: dict = {"present_countries": countries, "continents": continents}
    if regions:
        geography["historical_regions"] = regions
    return geography


def find_delete_blockers(
    target_id: str,
    metadata: dict[str, dict],
    periods_dir: Path,
    transitions_path: Path,
    period_links_path: Path,
) -> list[str]:
    """Scans every place a Histomap id can be referenced from, so a hard
    delete (unlike the "discarded" consolidation decision, which keeps the
    record on disk as an audit trail) can never silently leave a dangling
    reference that fails the next build.py run. Mirrors what build.py's
    own validators check (validate_entity_relationships,
    validate_period_detail_of, validate_transitions) plus
    period_links.yaml, which isn't schema-validated for dangling
    references at all. Deliberately does not check linked_era_id/
    linked_chapter_id -- those are a soft /explore grouping hint, not a
    hard schema reference build.py fails on."""
    blockers: list[str] = []
    for other_id, document in metadata.items():
        if other_id == target_id:
            continue
        if document.get("detail_of") == target_id:
            blockers.append(f"polity {other_id} is a detail_of this record")
        if target_id in (document.get("successors") or []):
            blockers.append(f"polity {other_id} lists this record as a successor")
        if any(relationship.get("target") == target_id for relationship in document.get("relationships") or []):
            blockers.append(f"polity {other_id} has a relationship pointing to this record")
    for path in periods_dir.glob("*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        other_id = document.get("id", path.stem)
        if other_id == target_id:
            continue
        if document.get("detail_of") == target_id:
            blockers.append(f"period {other_id} is a detail_of this record")
        if target_id in (document.get("successors") or []):
            blockers.append(f"period {other_id} lists this record as a successor")
        if target_id in (document.get("broader_periods") or []):
            blockers.append(f"period {other_id} lists this record as a broader_period")
    if transitions_path.exists():
        for item in yaml.safe_load(transitions_path.read_text(encoding="utf-8")) or []:
            if target_id in (item.get("from") or []) or target_id in (item.get("to") or []):
                blockers.append(f"transition {item.get('id')} references this record")
    if period_links_path.exists():
        for item in yaml.safe_load(period_links_path.read_text(encoding="utf-8")) or []:
            if item.get("period_id") == target_id or item.get("entity_id") == target_id:
                blockers.append(
                    f"period_links entry ({item.get('period_id')} / {item.get('entity_id')}) references this record"
                )
    return blockers


def clean_json(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: clean_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_json(item) for item in value]
    return value


def search_polities(query: str, metadata: dict[str, dict], limit: int = 10) -> list[dict]:
    query = query.strip()
    ranked = []
    for polity_id, document in metadata.items():
        if document.get("eligibility") == "excluded" or document.get("timeline_role") == "retired":
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
                "entity_type": document.get("entity_type", "polity"),
                "canonical_start": document.get("start"),
                "canonical_end": document.get("end"),
                "canonical_sources": document.get("sources", []),
                "source_links": links,
                "search_score": round(-negative_score, 1),
            }
        )
    return results


def search_periods(query: str, periods_dir: Path, limit: int = 10) -> list[dict]:
    """Same purpose as search_polities, for periods -- backs the period
    detail_of picker (a period's detail_of target can be another period).
    Periods aren't held in an in-memory store the way polities are (see
    every other period endpoint in this file), so this reads the directory
    fresh each call -- fine at this dataset's scale (~100 periods)."""
    query = query.strip()
    documents: dict[str, dict] = {}
    ranked = []
    for path in periods_dir.glob("*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        period_id = document.get("id", path.stem)
        documents[period_id] = document
        name = str(document.get("canonical_name", period_id))
        score = max(float(fuzz.WRatio(query, candidate)) for candidate in (name, period_id) if candidate)
        exact = query.casefold() in {name.casefold(), period_id.casefold()}
        ranked.append((not exact, -score, name, period_id))
    results = []
    for _, negative_score, name, period_id in sorted(ranked)[:limit]:
        document = documents[period_id]
        results.append({
            "period_id": period_id,
            "canonical_name": name,
            "canonical_start": document.get("start"),
            "canonical_end": document.get("end"),
            "search_score": round(-negative_score, 1),
        })
    return results


def create_app(root: Path = ROOT) -> FastAPI:
    application = FastAPI(title="Histomap", version="0.1.0")
    web_dir = root / "web"
    reports_dir = root / "reports"
    period_role_review_path = reports_dir / "period_role_review.jsonl"
    relationship_cache_path = root / "sources" / "wikidata_relationships.json"
    direct_types_path = root / "sources" / "wikidata_direct_types.json"
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
        if info.get("iso2") and len(info["iso2"]) == 2 and info["iso2"] not in DEFUNCT_COUNTRY_CODES
    }
    # iso2 -> continents, for derive_geography_for_countries() at creation
    # time -- same reverse index enrich_geography.py's
    # backfill_continents_from_present_countries() builds, kept local here
    # since that module's own loader lives behind a heavier import chain.
    iso2_to_continents: dict[str, list[str]] = {}
    for info in country_metadata.values():
        iso2 = info.get("iso2")
        if iso2 and info.get("continents"):
            iso2_to_continents.setdefault(iso2, sorted(set(info["continents"])))
    relationship_rows = (
        json.loads(relationship_cache_path.read_text(encoding="utf-8"))
        if relationship_cache_path.exists()
        else []
    )
    direct_types = (
        json.loads(direct_types_path.read_text(encoding="utf-8"))
        if direct_types_path.exists()
        else {}
    )
    # qid -> set of P131 ("located in the administrative territorial entity")
    # targets, for consolidation_review_queue()'s shared-location signal.
    p131_by_qid: dict[str, set[str]] = {}
    # qid -> set of qids linked by a documented Wikidata succession statement
    # (P155 follows, P156 followed by, P1365 replaces, P1366 replaced by),
    # both directions folded together -- for consolidation_review_queue()'s
    # "these are two distinct, sequential polities" signal. Same cache
    # pipeline.enrich_relationships.py already uses to populate `successors`.
    succession_qids: dict[str, set[str]] = {}
    # qid -> set of qids it's directly documented as P361 ("part of"), or
    # that are documented as P527 ("has part") of it -- both mean "this qid
    # is part of that qid". For consolidation_review_queue()'s part_of/
    # candidate_part_of suggestion: a direct Wikidata claim between the two
    # records under review, not just a shared third-party parent the way
    # p131_by_qid is.
    part_of_qids: dict[str, set[str]] = {}
    for row in relationship_rows:
        source, prop, target = row.get("source"), row.get("property"), row.get("target")
        if not source or not target:
            continue
        if prop == "P131":
            p131_by_qid.setdefault(source, set()).add(target)
        elif prop in {"P155", "P156", "P1365", "P1366"}:
            succession_qids.setdefault(source, set()).add(target)
            succession_qids.setdefault(target, set()).add(source)
        elif prop == "P361":
            part_of_qids.setdefault(source, set()).add(target)
        elif prop == "P527":
            part_of_qids.setdefault(target, set()).add(source)
    period_role_queue: list[dict] = []

    def refresh_period_role_queue() -> None:
        period_role_queue.clear()
        if not period_role_review_path.exists():
            return
        for line in period_role_review_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            document = metadata.get(record["id"])
            if not document or document.get("timeline_role", "entity") == "retired":
                continue
            if "timeline_role" in (document.get("manual_overrides") or []):
                continue
            record["wikipedia_en"] = english_wikipedia_url(document.get("external_ids") or {})
            period_role_queue.append(record)

    refresh_period_role_queue()
    job = {"status": "idle", "action": None, "output": "", "returncode": None}
    job_lock = asyncio.Lock()

    def refresh_metadata() -> None:
        """Reload every polities/*.yaml from disk. Only trigger today is a `reconcile`
        run (kept as an API-triggerable hook, no dedicated review page anymore --
        see ROADMAP.md's review-workflow-trim note)."""
        metadata.clear()
        metadata.update(polity_metadata(polities_dir))

    def refresh_separate_entities() -> None:
        for path in polities_dir.glob("seshat_*.yaml"):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            metadata[document["id"]] = document

    consolidation_stopwords = {
        "ancient", "caliphate", "confederation", "county", "democratic", "duchy",
        "dynasty", "empire", "federation", "government", "great", "kingdom",
        "northern", "people", "principality", "province", "republic", "southern",
        "state", "sultanate", "united", "western", "eastern",
        "califat", "comte", "duche", "dynastie", "etat", "gouvernement", "publique",
        "royaume", "sultanat",
        # Generic government-form/noble-title nouns and disambiguator words --
        # the same category as duchy/kingdom/empire/sultanate above, just an
        # incomplete enumeration until three real false-positive candidate
        # pairs were found live, 3 September 2026: "Margraviate of
        # Brandenburg-Kustrin" vs "Margraviate of Moravia" (shared only
        # "margraviate"), "Butuan (historical polity)" vs "Tondo (historical
        # polity)" (shared only "historical"/"polity", from the parenthetical
        # disambiguator wiki editors add to distinguish same-named places, not
        # a place name itself), and "Electorate of Hanover" vs "Electorate of
        # Mainz" (shared only "electorate"). Grepping canonical_name across
        # the dataset for the same class of word found this fuller set, all
        # verified as genuinely generic (never distinguishing) via a sample of
        # their real uses (e.g. "Dominion of Ceylon", "Colony of Jamaica",
        # "Commonwealth of England", "Governorate of Montenegro", "Regency of
        # Algiers", "Palatinate-Simmern" vs "Palatinate-Neuburg" -- distinct
        # entities that would otherwise token-match on "palatinate" alone).
        "archduchy", "autonomy", "banate", "chiefdom", "colony", "commonwealth",
        "despotate", "dominion", "electorate", "emirate", "exarchate",
        "governorate", "historical", "imamate", "khanate", "landgraviate",
        "mandate", "margravate", "margraviate", "marquisate", "oligarchy",
        "palatinate", "polity", "protectorate", "regency", "satrapy",
        "shogunate", "tetrarchy", "tsardom", "viscounty",
        # Second sweep, requested directly ("Mandate", "Government", "Canton"
        # named explicitly) -- same grep-the-dataset-and-sample-real-uses
        # discipline as the first sweep found a further batch: "Canton of
        # Aargau" vs every other "Canton of X" (26 Swiss cantons alone would
        # all token-match each other on "canton"), "X Horde" (Golden/Blue/
        # White/Great/Nogai/Bukey/Skewbald -- seven distinct Mongol/Central
        # Asian hordes), "X Confederacy"/"Beylik of X"/"March of X"/"X
        # Territory"/"X Union"/"X Oblast"/"X District"/"X Domain"/"X League"
        # -- all the same pattern: a shared generic institutional-type word
        # with zero place-name evidence.
        "beylik", "canton", "confederacy", "district", "domain", "horde",
        "league", "march", "oblast", "realm", "territory", "union",
        # Third sweep, found live 3 September 2026: "Second Portuguese
        # Republic" vs "Second Polish Republic" (shared only the ordinal
        # "second" -- "republic" already stopworded, "portuguese"/"polish"
        # don't match) and "Mongol Military Government" vs "United States
        # Military Government of the Philippine Islands" (shared only
        # "military"/"government" -- "government" already stopworded,
        # "military" was not). Ordinals are their own closed, safe-to-list
        # category (32 "First ..." records alone span Brazil, Bulgaria,
        # Czechoslovakia, Bavaria, Haiti, France, Greece, Hungary, Mexico,
        # Nigeria, the Philippines, Portugal, Armenia, Austria, Iraq,
        # Seychelles, South Korea, Venezuela, Saudi Arabia, Syria, Myanmar
        # -- all "Nth Republic/Empire/State"-named, none related to each
        # other). "military"/"provisional"/"administration"/"civil"/
        # "colonial"/"revolutionary"/"transitional"/"national"/"occupation"
        # are the same government-TYPE-adjective category as "military" --
        # verified via the dataset the same way (e.g. 19 different
        # "Provisional Government of X" records, one per unrelated
        # country). Deliberately NOT adding "new"/"old" (integral parts of
        # real place names -- "New Spain", "New Zealand", "New Granada" --
        # unlike a pure institutional-type word) or "central" (a genuine
        # geographic qualifier like "Central Africa"/"Central America",
        # the same role Minor/Major/Upper/Lower/Inner/Outer already have
        # via SUBDIVISION_QUALIFIERS below, not a content-free noun).
        "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
        "eighth", "ninth", "tenth",
        "military", "provisional", "administration", "administrative",
        "civil", "colonial", "revolutionary", "transitional", "national",
        "occupation",
        # Same batch, found live: "Prince-Bishopric of Chur" vs
        # "Prince-Bishopric of Toul" (shared only "bishopric"/"prince" --
        # 32 different Prince-Bishoprics of the Holy Roman Empire alone
        # would all token-match each other on this pair of words). Verified
        # "prince" alone is generic too, not just in this compound title,
        # via "Prince of Castelbuono"/"Prince of Leonforte" (different
        # Sicilian princedoms) and "Prince Edward Island" (a place named
        # after a person's title, not evidence of relation to any other
        # "prince"-named entity).
        "abbey", "archbishopric", "bishopric", "diocese", "prince",
        # Fourth sweep, found live: "Kachi Plain - Ceramic Neolithic" vs
        # "Neolithic Crete" (shared only "neolithic" -- an archaeological
        # chronological-stage word, same category as "ancient"/"historical"
        # above, not a place) and "Socialist Republic of Croatia" vs
        # "Socialist Republic of Montenegro" (shared only "socialist"/
        # "republic" -- "republic" already stopworded, "socialist" was not,
        # despite "democratic" already being covered). Auditing the same
        # class of word broadly (political-ideology adjectives,
        # archaeological-period terms, and generic-grandeur/legitimacy
        # modifiers, the same role "great" already plays above) found a
        # much larger gap: 77 different "Free City/State of X" records
        # alone (Menton, Danzig, Krakow, Anhalt, Brunswick, Coburg, Costa
        # Rica, Fiume, Mecklenburg, Oldenburg, Prussia, Saxe-*, ...), 60
        # "Soviet" and 49 "Socialist" records (mostly overlapping Soviet
        # Socialist Republics, but not entirely), 30+ "Imperial"
        # (17 different "Free Imperial City of X" plus 6 "Imperial City of
        # X"), 23 "Grand" (17 "Grand Duchy of X", 4 "Grand Principality of
        # X"), 16 "Federal" ("Federal Republic of X" across Cameroon,
        # Central America, Yugoslavia, Mindanao, ...), plus smaller but
        # equally generic categories (sovereign, independent, royal, holy,
        # supreme, chalcolithic, classical, tribal, fascist, communist,
        # clan, nationalist, pagan, islamic, early/late/middle as
        # chronological-stage words). All sampled and verified generic
        # (never a real place/proper-noun component) before adding.
        "neolithic", "chalcolithic", "classical", "early", "late", "middle",
        "islamic", "tribal", "pagan",
        "socialist", "soviet", "communist", "fascist", "nationalist", "clan",
        "free", "imperial", "grand", "federal", "sovereign", "independent",
        "royal", "holy", "supreme",
        # Fifth sweep, found live: "Latium - Bronze Age" vs "Middle Bronze Age
        # in Central Anatolia" (shared only "bronze" -- same archaeological
        # three-age-system chronological-stage word as "neolithic"/
        # "chalcolithic" above, not a place or identity marker) and
        # "Giudicato of Logudoro" vs "Giudicato of Gallura" (different
        # Wikidata QIDs, shared only "giudicato" -- a generic medieval
        # Sardinian judicial-kingdom title, same role as "bishopric"/
        # "prince" above; 4 real distinct Giudicati -- Logudoro, Gallura,
        # Cagliari, Arborea -- all share the word).
        "bronze", "giudicato",
        # Same fifth sweep, three more generic government-form/title words
        # in the same category as "bishopric"/"prince"/"giudicato" above,
        # each confirmed via differing Wikidata QIDs: "Signoria of Volterra"
        # vs "Signoria of Milan" (Q95993051 vs Q15890801, "signoria" is the
        # generic term for a medieval/renaissance Italian city-state
        # government), "Lordship of Bologna" vs "Lordship of Carpi"
        # (Q64576860 vs Q3477825), and "Rus' Khaganate" vs "Second Turkic
        # Khaganate" (Q1618896 vs Q4833446, "khaganate" is the generic term
        # for a Turkic/Mongolic steppe-empire government, same role as
        # "sultanate"/"emirate").
        "signoria", "lordship", "khaganate",
        # Same fifth sweep: "Calvinist Republic of Brussels" vs "Calvinist
        # Republic of Ghent" (distinct Wikidata items, near-identical dates
        # -- siblings from the same 1577-1585 Calvinist Republics of the Low
        # Countries wave, each in a different Flemish city -- same category
        # as "socialist"/"communist" above, a political-religious movement
        # descriptor, not a place).
        "calvinist",
        # Same fifth sweep: "Sheikhdom of al-'Irqa" vs "Sheikhdom of
        # al-Hawra" -- distinct Wikidata items, identical dates (1900-1967,
        # both South Arabian protectorate-era sheikhdoms) -- "sheikhdom" is
        # the generic term, same category as "sultanate"/"emirate"/
        # "khanate" above.
        "sheikhdom",
        # Same fifth sweep: "Waldamt Laurenzi" vs "Waldamt Sebaldi" --
        # distinct administrative departments of the Imperial City of
        # Nuremberg (named after different city parishes, St. Lorenz vs St.
        # Sebald), confirmed genuinely distinct despite extra proximity
        # evidence (~15km apart, same administrative parent) -- expected
        # for sibling departments of the same city, not evidence of
        # identity. "waldamt" is the generic German administrative-unit
        # term, same category as "vassal state"/"historical territory".
        "waldamt",
        # Same fifth sweep: "Angadh Estate" vs "Kapshi Estate" -- no shared
        # Wikidata item, share only "estate" -- the generic term for a
        # princely estate of the British Raj (dozens of distinct "X Estate"
        # jagirs/princely estates), same category as "state" above.
        "estate",
        # Same fifth sweep: "Lamidat de Mindif" vs "Lamidat of Tibati" --
        # different Wikidata QIDs, share only "lamidat" -- the generic term
        # for a traditional Fulani chiefdom of northern Cameroon, same
        # category as "sheikhdom"/"emirate" above.
        "lamidat",
    }

    def consolidation_tokens(document: dict) -> set[str]:
        names = [document.get("canonical_name", "")]
        names.extend((document.get("names") or {}).values())
        return {
            token
            for name in names
            for token in re.findall(r"[a-z0-9]+", str(name).casefold())
            if len(token) >= 4 and token not in consolidation_stopwords
        }

    def consolidation_names(document: dict) -> set[str]:
        """canonical_name is always included regardless of length -- it's the
        primary designation, and two records sharing it verbatim is
        meaningful even when short (e.g. "Peru"). Aliases/translations are
        filtered to >= 6 normalized characters: they're collision-prone at
        short lengths -- the State of Qi's alias "Chi" and Chile's alias
        "CHI" both normalize to "chi", which without this filter marked an
        unrelated pair "exact name match" (found live, 31 August 2026)."""
        canonical_raw = strip_year_range_suffix(str(document.get("canonical_name", "")))
        canonical = re.sub(r"[^a-z0-9]+", " ", canonical_raw.casefold()).strip()
        result = {canonical} if canonical else set()
        alias_values = []
        for key, value in (document.get("names") or {}).items():
            alias_values.extend(str(value).split("|") if key == "aliases_en" else [value])
        for value in alias_values:
            normalized = re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()
            if len(normalized) >= 6:
                result.add(normalized)
        return result

    def centroid_distance_km(a: dict | None, b: dict | None) -> float | None:
        """Great-circle distance between two Geography.centroid dicts, or
        None if either is missing. Coarse (spherical-Earth) approximation --
        plenty precise for "same city" vs. "different continent"."""
        if not a or not b or a.get("lat") is None or b.get("lat") is None:
            return None
        lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
        d_lat, d_lon = lat2 - lat1, lon2 - lon1
        h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
        return 2 * 6371 * math.asin(math.sqrt(min(1, h)))

    # Some canonical_name values carry a disambiguating year-range suffix --
    # "State of Thuringia (1920-1952)", "Kingdom of Hungary (1867-1918)" --
    # to distinguish them from other Histomap records for the same place.
    # Left in place, that suffix breaks any trailing-substring name check
    # (it no longer ends with "of Thuringia") even though the underlying
    # name plainly does match. Strip it before comparing.
    YEAR_RANGE_SUFFIX_RE = re.compile(r"\s*\([0-9]{1,4}\s*[-–—]\s*(?:present|[0-9]{1,4})\)\s*$", re.IGNORECASE)

    def strip_year_range_suffix(name: str) -> str:
        return YEAR_RANGE_SUFFIX_RE.sub("", name)

    # A place's name appearing as the very first word(s) of a record,
    # immediately followed by one of these, means "an administrative/military
    # body OF that place, operating elsewhere" (United States Army Military
    # Government IN KOREA), not "a specific government OF that place" --
    # the true geographic anchor is wherever the name says it operated, not
    # the owning place named up front. Found live, 1 September 2026.
    REGIME_EXCLUDED_FOLLOWERS = {
        "army", "navy", "forces", "government", "administration", "command",
        "occupation", "mission", "legation", "corps", "authority", "garrison",
    }
    # "Minor/Lesser/Major/Greater/Upper/Lower/Inner/Outer <place>" (or the
    # reverse order) denotes a geographic SUBDIVISION of that place (Scythia
    # Minor is part of Scythia, Asia Minor is part of Asia, Upper Egypt is
    # part of Egypt) -- a spatial qualifier, not a regime/era qualifier.
    # Found live, 1 September 2026 (Scythia Minor was wrongly suggested
    # phase_of Scythia via the general regime-naming check).
    SUBDIVISION_QUALIFIERS = {"minor", "lesser", "major", "greater", "upper", "lower", "inner", "outer"}

    def name_is_regime_of(inner_name: str, outer_name: str) -> bool:
        """True when inner_name reads as a specific government/era of
        outer_name. Two checks, covering the common English shapes
        regardless of where outer_name's own words fall in inner_name:
        - outer_name's exact words appear anywhere in inner_name at a word
          boundary -- "Kingdom of Hungary" (suffix), "Francoist Spain"
          (suffix), "Spain under the Restoration" (prefix), "Republic of
          the Congo" (mid-sentence, multi-word outer) all match this one
          check. Excludes a match at the very start when immediately
          followed by an administrative/military noun (see
          REGIME_EXCLUDED_FOLLOWERS above) -- that's ownership, not
          identity.
        - any single word of inner_name is a demonym-style prefix/suffix
          match of outer_name (Syria/Syrian, Brunei/Bruneian, Brazil/
          Brazilian), catching "Syrian Federation" and "First Brazilian
          Republic" without a full demonym dictionary; irregular demonyms
          (France/French) aren't caught. Only applies when outer_name is a
          single word -- otherwise a short leading word of a multi-word
          outer_name (e.g. "United" in "United Belgian States") can
          spuriously prefix-match an unrelated multi-word name that starts
          the same way (found live, 1 September 2026).
        Neither check can, by name shape alone, distinguish a genuine
        regime name from a genuinely distinct compound-name/demonym-
        adjacent place that happens to share the shape (West Virginia is
        not a regime of Virginia; India is not a regime named by
        "Indiana") -- callers gate on a finite end as the real safety
        rail: real regime names almost always concluded, while a distinct
        place that's still open-ended won't pass that gate even if the
        name shape matches (found live, 1 September 2026). See also
        name_is_subdivision_of_place() for the geographic-qualifier shape,
        which is deliberately excluded here."""
        inner = re.sub(r"[^a-z0-9 ]+", " ", strip_year_range_suffix(inner_name).casefold()).strip()
        outer = re.sub(r"[^a-z0-9 ]+", " ", strip_year_range_suffix(outer_name).casefold()).strip()
        if not outer or not inner or inner == outer:
            return False
        words = inner.split(" ")
        outer_words = outer.split(" ")
        n = len(outer_words)
        for i in range(len(words) - n + 1):
            if words[i:i + n] == outer_words:
                if i == 0 and i + n < len(words) and words[i + n] in REGIME_EXCLUDED_FOLLOWERS:
                    continue
                return True
        if len(outer) < 4 or " " in outer:
            return False
        return any(
            len(word) >= 4 and (word.startswith(outer) or outer.startswith(word))
            for word in words
        )

    def name_is_subdivision_of_place(inner_name: str, outer_name: str) -> bool:
        """True when inner_name reads as a geographic SUBDIVISION of
        outer_name via a spatial qualifier -- Minor/Lesser/Major/Greater/
        Upper/Lower/Inner/Outer immediately next to the place name, in
        either order (Scythia Minor, Asia Minor, Upper Egypt). Matches even
        with a trailing disambiguator after the qualifier is removed
        ("Scythia Minor (Crimea)" -> "scythia crimea" still starts with
        "scythia"), the same tolerance name_is_regime_of() has for extra
        surrounding words. Distinct from name_is_regime_of()'s naming
        shapes, which denote a period of government, not a spatial subset
        -- callers exclude a subdivision match from counting as regime_of
        evidence, and count it as part_of evidence instead."""
        inner = re.sub(r"[^a-z0-9 ]+", " ", strip_year_range_suffix(inner_name).casefold()).strip()
        outer = re.sub(r"[^a-z0-9 ]+", " ", strip_year_range_suffix(outer_name).casefold()).strip()
        if not outer or not inner or inner == outer:
            return False
        words = inner.split(" ")
        for i, word in enumerate(words):
            if word not in SUBDIVISION_QUALIFIERS:
                continue
            remainder = " ".join(words[:i] + words[i + 1:])
            if f" {outer} " in f" {remainder} ":
                return True
        return False

    def consolidation_review_queue() -> list[dict]:
        refresh_period_role_queue()
        active = {
            entity_id: document
            for entity_id, document in metadata.items()
            if document.get("timeline_role", "entity") not in {"retired", "period"}
            and document.get("eligibility") != "excluded"
            and not document.get("consolidation_status")
            and not document.get("detail_of")
        }
        token_index: dict[str, set[str]] = {}
        name_index: dict[str, set[str]] = {}
        qid_index: dict[str, set[str]] = {}
        tokens_by_id = {}
        canonical_tokens_by_id = {}
        names_by_id = {}
        for entity_id, document in active.items():
            tokens = consolidation_tokens(document)
            tokens_by_id[entity_id] = tokens
            canonical_tokens_by_id[entity_id] = {
                token for token in re.findall(r"[a-z0-9]+", str(document.get("canonical_name", "")).casefold())
                if len(token) >= 4 and token not in consolidation_stopwords
            }
            names_by_id[entity_id] = consolidation_names(document)
            for token in tokens:
                token_index.setdefault(token, set()).add(entity_id)
            for name in names_by_id[entity_id]:
                name_index.setdefault(name, set()).add(entity_id)
            qid = (document.get("external_ids") or {}).get("wikidata")
            if qid:
                qid_index.setdefault(qid, set()).add(entity_id)
        # entity_id -> ids it has a documented DETAIL_OF_RELATIONSHIP_KINDS
        # relationship to (source: Polity.relationships, already resolved to
        # Histomap ids -- see ROADMAP.md item 0 bis). Same shape as
        # part_of_qids/succession_qids above, just keyed by Histomap id
        # instead of Wikidata QID, so no id-resolution step is needed.
        relationship_targets_by_id: dict[str, set[str]] = {}
        for entity_id, document in active.items():
            relationship_targets_by_id[entity_id] = {
                relationship["target"]
                for relationship in document.get("relationships") or []
                if relationship.get("kind") in DETAIL_OF_RELATIONSHIP_KINDS
                and relationship.get("target") in active
                and relationship.get("target") != entity_id
            }
        # Reverse direction: other_id -> ids that document a relationship
        # TO other_id -- lets the pair reach the queue from either side, the
        # same way part_of_qids/succession_qids do for the QID-based signal.
        relationship_sources_by_target: dict[str, set[str]] = {}
        for source_id, targets in relationship_targets_by_id.items():
            for target_id in targets:
                relationship_sources_by_target.setdefault(target_id, set()).add(source_id)
        queue = []
        for entity_id, document in active.items():
            possible = {
                other_id
                for token in tokens_by_id[entity_id]
                if len(token_index[token]) <= 12
                for other_id in token_index[token]
                if other_id != entity_id
            }
            possible.update(
                other_id for name in names_by_id[entity_id]
                for other_id in name_index[name] if other_id != entity_id
            )
            source_qid = (document.get("external_ids") or {}).get("wikidata")
            possible.update(other_id for other_id in qid_index.get(source_qid, set()) if other_id != entity_id)
            # A documented Wikidata relationship (P361/P527 part-of, or
            # P155/P156/P1365/P1366 succession) is real evidence about these
            # two specific records even with zero name/token overlap --
            # without this, a record whose name shares nothing with its
            # documented successor never even reaches the candidate pool
            # (found live, 1 September 2026: "United States Army Military
            # Government in Korea" only had "United States" as a candidate,
            # via an incidental name-prefix match, even though Wikidata
            # directly documents its real successor, "First Republic of
            # South Korea" -- a completely different name, so it never
            # entered the pool without this).
            possible.update(
                other_id
                for related_qid in (part_of_qids.get(source_qid, set()) | succession_qids.get(source_qid, set()))
                for other_id in qid_index.get(related_qid, set())
                if other_id != entity_id
            )
            # ROADMAP.md item 0 bis: a documented Polity.relationships entry
            # (either direction) is the same class of evidence as the
            # Wikidata QID-based part_of_qids/succession_qids block above,
            # just already resolved to Histomap ids -- reaches the pool the
            # same way, regardless of name/token overlap.
            possible.update(relationship_targets_by_id.get(entity_id, set()))
            possible.update(relationship_sources_by_target.get(entity_id, set()))
            candidates = []
            source_name = str(document.get("canonical_name", entity_id))
            source_prominence = float(document.get("prominence_score", 0))
            source_countries = set((document.get("geography") or {}).get("present_countries", []))
            for other_id in possible:
                other = active[other_id]
                other_prominence = float(other.get("prominence_score", 0))
                if other_prominence < source_prominence:
                    continue
                name_score = float(fuzz.WRatio(source_name, str(other.get("canonical_name", other_id))))
                other_countries = set((other.get("geography") or {}).get("present_countries", []))
                geography_match = bool(source_countries & other_countries)
                # Missing present_countries data on BOTH sides is unknown,
                # not a green light -- it must not stand in for an actual
                # overlap when deciding a suggestion (found live, 1 September
                # 2026). But when only one side has no geography of its own
                # (e.g. a phase record that never got present_countries
                # populated) while the other side does, that's not a
                # conflict either -- a phase reasonably shares its matched
                # entity's location, so it's treated as compatible too
                # (Republic of Georgia 1990-1992 vs. Georgia, found live, 1
                # September 2026). geography_conflict is the separate,
                # genuinely informative case: both sides HAVE data and it
                # doesn't overlap.
                geography_compatible = geography_match or bool(source_countries) != bool(other_countries)
                geography_conflict = bool(source_countries and other_countries and not geography_match)
                # Exact containment, no fuzz -- a start/end year that misses
                # by even one year does not count (found live, 1 September
                # 2026: an earlier tolerance here masked genuine boundary
                # mismatches as well as forgiving real estimate noise).
                date_contains = (
                    other.get("start") is not None
                    and document.get("start") is not None
                    and other["start"] <= document["start"]
                    and (
                        other.get("end") is None
                        or (document.get("end") is not None and other["end"] >= document["end"])
                    )
                )
                # Mirror of date_contains: the REVIEWED entity's own dates
                # contain the candidate's (e.g. France 481-present containing
                # French First Republic 1792-1804) -- the candidate is the
                # bounded phase here, not the reviewed entity.
                reverse_date_contains = (
                    document.get("start") is not None
                    and other.get("start") is not None
                    and document["start"] <= other["start"]
                    and (
                        document.get("end") is None
                        or (other.get("end") is not None and document["end"] >= other["end"])
                    )
                )
                source_end = document.get("end") if document.get("end") is not None else 2100
                other_end = other.get("end") if other.get("end") is not None else 2100
                date_overlap = document.get("start") is not None and other.get("start") is not None and max(document["start"], other["start"]) < min(source_end, other_end)
                shared_tokens = tokens_by_id[entity_id] & tokens_by_id[other_id]
                shared_canonical_tokens = canonical_tokens_by_id[entity_id] & canonical_tokens_by_id[other_id]
                exact_name_match = bool(names_by_id[entity_id] & names_by_id[other_id])
                same_wikidata = bool(source_qid and source_qid == (other.get("external_ids") or {}).get("wikidata"))
                other_qid = (other.get("external_ids") or {}).get("wikidata")
                # Independent-of-name corroborating signals: do these two records
                # actually refer to the same place? A shared alias (e.g. "New
                # Holland" used historically for both Dutch Brazil and colonial
                # Australia) says nothing about location -- these do.
                coordinate_km = centroid_distance_km(
                    (document.get("geography") or {}).get("centroid"),
                    (other.get("geography") or {}).get("centroid"),
                )
                coordinate_conflict = coordinate_km is not None and coordinate_km > 1500
                coordinate_match = coordinate_km is not None and coordinate_km <= 300
                shared_p131 = bool(
                    source_qid and other_qid
                    and p131_by_qid.get(source_qid) and p131_by_qid.get(other_qid)
                    and p131_by_qid[source_qid] & p131_by_qid[other_qid]
                )
                # A documented Wikidata succession statement (follows/followed
                # by/replaces/replaced by) between the two items is direct
                # evidence they're two distinct, sequential polities, not one
                # entity under two names -- e.g. Batavian Republic and Batavian
                # Commonwealth share a "Batavian Commonwealth" alias, but
                # Wikidata's own P155/P156 chain documents them as successive
                # states (found live, 31 August 2026).
                documented_successor = bool(
                    source_qid and other_qid and other_qid in succession_qids.get(source_qid, set())
                )
                # A genuine same_wikidata match ought to carry matching dates
                # (both records are pulled from the same Wikidata item's own
                # start/end). A same_wikidata candidate whose dates diverge by
                # more than a few years usually means one record has the
                # WRONG QID -- e.g. this dataset's Roman Republic and Ancient
                # Rome both carry Q1747689, but cover different centuries.
                # That's a data bug to fix at the source, not an identity
                # decision, so it demotes confidence and blocks the
                # phase_of/same_entity suggestion rather than masquerading as
                # an ordinary recommendation (found live, 31 August 2026).
                dates_roughly_equal = (
                    document.get("start") is not None and other.get("start") is not None
                    and abs(document["start"] - other["start"]) <= 5
                    and (document.get("end") is None) == (other.get("end") is None)
                    and (document.get("end") is None or abs(document["end"] - other["end"]) <= 5)
                )
                possible_qid_conflict = same_wikidata and not dates_roughly_equal
                # A shared alias between two DISTINCT Wikidata items whose
                # dates plain don't overlap is the "reused the name, different
                # era" shape -- Free City of Danzig/Duchy of Limburg (resolved
                # by hand earlier this session) and Bourbon Restoration in
                # France/Kingdom of France (the restored monarchy genuinely
                # was called "Kingdom of France" again, 24 years after the
                # first Kingdom of France record's own end date). Distinct
                # from documented_successor, which needs an explicit Wikidata
                # P155/P156/P1365/P1366 edge -- not every such pair has one.
                no_overlap_alias_reuse = exact_name_match and not same_wikidata and not date_overlap
                # Two DISTINCT Wikidata items, DIFFERENT names (no
                # exact_name_match -- ruling out "same institution, renamed"),
                # but essentially IDENTICAL date ranges (both starting/ending
                # together) is the signature of siblings born from the same
                # founding/partition event rather than one being a phase of
                # the other -- e.g. Canton of Appenzell Innerrhoden and
                # Ausserrhoden, both 1513-present, split from the single
                # original Appenzell canton and never one contained in the
                # other's timeline. A true phase_of has temporal
                # precedence (the phase's span nests inside the continuous
                # polity's own, usually with a DIFFERENT start) -- identical
                # starts point the other way (found live, 31 August 2026).
                dates_essentially_identical = (
                    document.get("start") is not None and other.get("start") is not None
                    and abs(document["start"] - other["start"]) <= 3
                    and (document.get("end") is None) == (other.get("end") is None)
                    and (document.get("end") is None or abs(document["end"] - other["end"]) <= 3)
                )
                likely_siblings = (
                    dates_essentially_identical and not same_wikidata and not exact_name_match
                )
                # "<regime type> of <the other record's name>" (Federal
                # People's Republic of Yugoslavia / Yugoslavia, Islamic
                # Emirate of Afghanistan / Afghanistan) is a reliable enough
                # naming pattern for "a specific government of this place" to
                # stand alongside exact_name_match for the phase_of
                # direction check below -- it catches genuine phases whose
                # alias data is incomplete, without reopening the West
                # Virginia/Virginia false positive (a compound place name,
                # not this pattern).
                #
                # The pattern alone is ambiguous, though: "Realm of New
                # Zealand" also reads as "<X> of New Zealand", but the Realm
                # is the BROADER constitutional entity New Zealand belongs
                # to, not a phase of New Zealand's own history -- the
                # opposite of the Yugoslavia case (found live, 1 September
                # 2026). The reliable tell is that a genuine regime-of-place
                # PHASE is, definitionally, a completed episode -- Federal
                # People's Republic of Yugoslavia ran 1945-1963, then the
                # country took a new name. Two still-open-ended ("present")
                # entities matching this naming shape means the "regime"
                # side is far more likely a broader container. So the
                # pattern only counts toward suggesting phase_of/
                # candidate_phase_of when the "regime" side has actually
                # ended -- but it still counts as identity evidence either
                # way (regime_of_*_name, unfiltered) for no_identity_signal,
                # since the two records plainly ARE related even when the
                # direction is ambiguous.
                # Computed BEFORE regime_of_*_name below so a subdivision
                # match (Scythia Minor/Scythia) can be subtracted from it --
                # "Minor" et al. denote a spatial subset, not a regime/era.
                subdivision_of_candidate_name = name_is_subdivision_of_place(
                    str(document.get("canonical_name", "")), str(other.get("canonical_name", ""))
                )
                subdivision_of_reviewed_name = name_is_subdivision_of_place(
                    str(other.get("canonical_name", "")), str(document.get("canonical_name", ""))
                )
                regime_of_candidate_name = name_is_regime_of(
                    str(document.get("canonical_name", "")), str(other.get("canonical_name", ""))
                ) and not subdivision_of_candidate_name
                regime_of_reviewed_name = name_is_regime_of(
                    str(other.get("canonical_name", "")), str(document.get("canonical_name", ""))
                ) and not subdivision_of_reviewed_name
                regime_of_candidate = regime_of_candidate_name and document.get("end") is not None
                regime_of_reviewed = regime_of_reviewed_name and other.get("end") is not None
                # A direct Wikidata P361 ("part of")/P527 ("has part") claim
                # BETWEEN the two records under review -- stronger than
                # shared_p131 (a shared third-party parent), since it's a
                # documented claim about these two specific items. Doesn't
                # need a finite-end gate the way phase_of does: a part_of
                # decision writes a subdivision-parent link, not a Period
                # record. Found live, 1 September 2026 (New Zealand's own
                # P361 claim names Realm of New Zealand directly). Kept
                # Wikidata-only (unlike regime_of_candidate_name) because
                # it also counts as phase_of naming evidence below --
                # subdivision_part_of_* deliberately does NOT, since a
                # naming-only spatial qualifier should never suggest phase_of.
                reviewed_part_of_candidate = bool(
                    source_qid and other_qid and other_qid in part_of_qids.get(source_qid, set())
                )
                candidate_part_of_reviewed = bool(
                    source_qid and other_qid and source_qid in part_of_qids.get(other_qid, set())
                )
                # ROADMAP.md item 0 bis: same idea as reviewed_part_of_
                # candidate/candidate_part_of_reviewed just above, sourced
                # from Polity.relationships (already Histomap-id-resolved)
                # instead of a raw Wikidata QID claim.
                documented_relationship_detail_of = other_id in relationship_targets_by_id.get(entity_id, set())
                documented_relationship_candidate_detail_of = entity_id in relationship_targets_by_id.get(other_id, set())
                # The bare naming-qualifier version of part_of evidence,
                # gated on geography_compatible (actual overlap, or one side
                # missing data and inheriting the other's -- same rule as
                # everywhere else, not a stricter one just because there's no
                # documented Wikidata claim backing it up the way P361 does:
                # Scythia Minor's own present_countries isn't recorded, and
                # requiring a literal overlap wrongly withheld the
                # suggestion entirely, found live, 1 September 2026).
                # Deliberately kept separate from reviewed_part_of_candidate/
                # candidate_part_of_reviewed above -- only used for the
                # plain part_of/candidate_part_of branches, never as phase_of
                # naming evidence.
                subdivision_part_of_candidate = subdivision_of_candidate_name and geography_compatible
                subdivision_part_of_reviewed = subdivision_of_reviewed_name and geography_compatible
                # No strong identity anchor at all -- whatever got this
                # candidate into the queue was geography + date-overlap +
                # fuzzy/token name similarity alone, not a shared Wikidata
                # item, a shared name/alias, or the regime-of-place pattern
                # above.
                no_identity_signal = (
                    not same_wikidata and not exact_name_match
                    and not regime_of_candidate_name and not regime_of_reviewed_name
                    and not subdivision_of_candidate_name and not subdivision_of_reviewed_name
                    and not reviewed_part_of_candidate and not candidate_part_of_reviewed
                    and not documented_relationship_detail_of and not documented_relationship_candidate_detail_of
                )
                if not (
                    same_wikidata
                    # no_overlap_alias_reuse (exact_name_match, distinct
                    # Wikidata items, zero date overlap) is excluded here --
                    # completely disjoint dates on their own already say
                    # these are independent entities (a name reused for a
                    # different era), not something needing manual review.
                    # same_wikidata/documented_successor/part_of matches
                    # still surface regardless of date overlap via their own
                    # clauses below -- this only narrows the exact-name-match
                    # path. Found live, 7 September 2026.
                    or (
                        exact_name_match and not coordinate_conflict and not documented_successor
                        and not no_overlap_alias_reuse
                    )
                    or reviewed_part_of_candidate or candidate_part_of_reviewed
                    or subdivision_part_of_candidate or subdivision_part_of_reviewed
                    or documented_relationship_detail_of or documented_relationship_candidate_detail_of
                    # A documented Wikidata succession claim only warrants a
                    # look when dates AND geography actually overlap/match --
                    # a clean sequential handover (one ends where the next
                    # begins, no overlap) is always "independent" by
                    # explicit policy, so reviewing it achieves nothing; it's
                    # only the same-dates/same-geography case that's ever
                    # actually ambiguous. Name/token score is still bypassed
                    # when dates and geography DO match, since the
                    # succession claim alone is strong enough evidence on
                    # its own (found live, 1 September 2026). Found live, 7
                    # September 2026 (Yemen Republic/Yemen: a clean 1990
                    # handover, no overlap -- always independent, reviewing
                    # it is pure noise).
                    or (documented_successor and date_overlap and geography_compatible)
                    or (
                        date_overlap and geography_compatible
                        and ((shared_canonical_tokens and name_score >= 60) or name_score >= 88)
                    )
                ):
                    continue
                rarity_bonus = max(
                    (max(4, 16 - len(token_index[token])) for token in shared_tokens),
                    default=0,
                )
                type_match = document.get("entity_type", "polity") == other.get("entity_type", "polity")
                score = name_score + rarity_bonus + sum(
                    bonus
                    for bonus, condition in (
                        (20, same_wikidata and not possible_qid_conflict),
                        (12, exact_name_match and not coordinate_conflict and not documented_successor and not no_overlap_alias_reuse),
                        (8, regime_of_candidate or regime_of_reviewed),
                        (10, reviewed_part_of_candidate or candidate_part_of_reviewed),
                        (10, documented_relationship_detail_of or documented_relationship_candidate_detail_of),
                        (8, subdivision_part_of_candidate or subdivision_part_of_reviewed),
                        (8, geography_match),
                        (8, date_contains),
                        (6, date_overlap),
                        (6, coordinate_match),
                        (4, type_match),
                        (4, shared_p131),
                        (-25, coordinate_conflict),
                        (-25, documented_successor),
                        (-25, no_overlap_alias_reuse),
                        (-15, possible_qid_conflict),
                        (-15, likely_siblings),
                    )
                    if condition
                )
                reasons = []
                if same_wikidata:
                    reasons.append("same Wikidata item")
                if exact_name_match:
                    reasons.append(
                        "shares an alias, but centroids are far apart -- likely coincidental" if coordinate_conflict
                        else "shares an alias, but Wikidata documents them as sequential polities (follows/replaces), not the same entity" if documented_successor
                        else "shares an alias with a distinct Wikidata item and non-overlapping dates -- likely the same name reused for a different era" if no_overlap_alias_reuse
                        else "exact canonical name or alias"
                    )
                if regime_of_candidate:
                    reasons.append("reviewed entity's name reads as a specific government of the candidate")
                if regime_of_reviewed:
                    reasons.append("candidate's name reads as a specific government of the reviewed entity")
                if reviewed_part_of_candidate:
                    reasons.append("Wikidata: reviewed entity is directly documented as part of the candidate")
                if candidate_part_of_reviewed:
                    reasons.append("Wikidata: candidate is directly documented as part of the reviewed entity")
                if subdivision_part_of_candidate:
                    reasons.append("reviewed entity's name reads as a geographic subdivision of the candidate")
                if subdivision_part_of_reviewed:
                    reasons.append("candidate's name reads as a geographic subdivision of the reviewed entity")
                if documented_relationship_detail_of:
                    reasons.append("Histomap: reviewed entity's own relationships record it as part of/derived from the candidate")
                if documented_relationship_candidate_detail_of:
                    reasons.append("Histomap: candidate's own relationships record it as part of/derived from the reviewed entity")
                if documented_successor:
                    reasons.append("Wikidata: documented successor relationship (follows/followed by or replaces/replaced by)")
                if likely_siblings:
                    reasons.append(
                        "distinct Wikidata items with essentially identical date ranges and different names -- "
                        "likely siblings from the same founding/partition event, not the same entity"
                    )
                elif no_identity_signal:
                    reasons.append(
                        "no shared Wikidata item or name/alias match -- likely a different entity, "
                        "not the same or a phase of it"
                    )
                if shared_canonical_tokens:
                    reasons.append(f"shared identity term: {', '.join(sorted(shared_canonical_tokens))}")
                if geography_match:
                    reasons.append("shared present-day geography")
                elif geography_conflict:
                    reasons.append("conflicting geography")
                if coordinate_conflict:
                    reasons.append(f"centroids ~{round(coordinate_km):,}km apart")
                elif coordinate_match:
                    reasons.append(f"centroids ~{round(coordinate_km)}km apart -- same location")
                if shared_p131:
                    reasons.append("Wikidata: located in the same administrative entity")
                if date_contains:
                    reasons.append("target dates contain source")
                elif reverse_date_contains:
                    reasons.append("reviewed entity's dates contain candidate")
                elif date_overlap:
                    reasons.append("dates overlap")
                else:
                    reasons.append("dates do not overlap")
                if not type_match:
                    reasons.append("different entity types")
                if possible_qid_conflict:
                    reasons.append(
                        "same Wikidata item, but date ranges are too different for genuine identity -- "
                        "check for a misattributed Wikidata id before deciding"
                    )
                # Bakes the same direction-of-nesting judgment a reviewer
                # would otherwise work out by hand (see Syria/Syrian Arab
                # Republic, France/French First Republic, German Reich/German
                # Empire, all resolved live this way) directly into the
                # suggestion, so it doesn't have to be re-derived manually
                # every time. Left null wherever the evidence doesn't clearly
                # point one way -- an ordinary manual review, same as before.
                #
                # phase_of/candidate_phase_of additionally require
                # exact_name_match, not just a shared token + date-containment
                # + geography: West Virginia (candidate: Virginia) has all
                # three (nested dates, shared "virginia" token, same country,
                # even a shared P131 target -- West Virginia genuinely was
                # part of Virginia once), but it is NOT a phase of Virginia --
                # it seceded in 1863 and both states have coexisted separately
                # ever since. That partition/split shape is structurally
                # different from a true phase_of (Bourbon Restoration/Kingdom
                # of France, Miguel Iglesias government/Peruvian Republic):
                # in a real phase_of, the candidate's identity IS what the
                # reviewed entity was called/was during that span, not a
                # parallel entity it split off from (found live, 31 August
                # 2026). A shared full name/alias is the reliable
                # discriminator every verified phase_of case had in common.
                # phase_of/candidate_phase_of do NOT require a finite end on
                # the entity that would be retired -- an open-ended phase is
                # a legitimate outcome (e.g. a country's current-era phase is
                # still "present"), and the backend approximates a missing
                # end date rather than refusing the decision. The regime_of_*
                # naming path still carries its own finite-end requirement
                # (see name_is_regime_of() gating above): a "<regime> of
                # <place>" name pattern alone, with no other evidence, is
                # ambiguous between "a completed phase of that place" and "a
                # broader, still-ongoing container that happens to share the
                # naming pattern" (e.g. Realm of New Zealand vs. New Zealand)
                # -- date_contains and geography_compatible alone can't tell
                # those apart when both sides are still open, so that
                # specific path keeps requiring a concluded regime. exact_name_match
                # and a direct Wikidata part-of relationship carry no such
                # ambiguity and don't need it (found live, 1 September 2026).
                if possible_qid_conflict:
                    suggested_decision = None
                elif same_wikidata:
                    suggested_decision = "same_entity"
                elif (
                    # A "follows/followed by" claim alone means "chronologically
                    # sequential", which usually does mean two distinct states --
                    # but a more specific structural fact about the SAME pair
                    # wins when it's also documented: either a direct P361
                    # "part of" claim (Latvian Soviet Socialist Republic has
                    # both a P361 claim to Latvia AND a documented successor
                    # relationship, but the P361 claim plus exact date nesting
                    # correctly describes a phase, not a distinct successor
                    # state -- found live, 1 September 2026), or the regime-of-
                    # place naming pattern with its own finite-end gate already
                    # satisfied (Commonwealth realm of Mauritius reads as "<X>
                    # of Mauritius", has a finite end (1992), and its dates nest
                    # exactly inside Mauritius's -- also a phase, not a
                    # successor state, even though Wikidata separately documents
                    # a successor claim too -- found live, 1 September 2026).
                    (
                        documented_successor
                        and not reviewed_part_of_candidate and not candidate_part_of_reviewed
                        and not regime_of_candidate and not regime_of_reviewed
                        and not documented_relationship_detail_of and not documented_relationship_candidate_detail_of
                    )
                    or coordinate_conflict or no_overlap_alias_reuse or likely_siblings
                ):
                    suggested_decision = "independent"
                elif (
                    date_contains and geography_compatible
                    and (exact_name_match or regime_of_candidate or reviewed_part_of_candidate)
                ):
                    # A direct P361/P527 relationship counts as phase_of
                    # naming evidence too, when it comes with clean date
                    # nesting AND the reviewed side has actually ended: that
                    # combination -- Wikidata directly relates the two
                    # records, and one's span sits entirely inside the
                    # other's, which has since continued past it -- is what
                    # a genuine phase looks like, even when Wikidata's own
                    # P361 claim is really describing "this was this place,
                    # under a different name, for a while" rather than
                    # literal spatial containment. Czechoslovak Socialist
                    # Republic (1948-1990) has a P361 claim to Czechoslovakia
                    # (1918-1992) but is a phase of it, not a physical part
                    # the way New Zealand is part of the Realm of New
                    # Zealand (found live, 1 September 2026 -- checked
                    # before the plain part_of branches below, so a
                    # genuinely nested, concluded phase wins that
                    # interpretation over the weaker structural default).
                    suggested_decision = "detail_of"
                elif (
                    reverse_date_contains and geography_compatible
                    and (exact_name_match or regime_of_reviewed or candidate_part_of_reviewed)
                ):
                    suggested_decision = "candidate_detail_of"
                elif reviewed_part_of_candidate or subdivision_part_of_candidate or documented_relationship_detail_of:
                    suggested_decision = "detail_of"
                elif candidate_part_of_reviewed or subdivision_part_of_reviewed or documented_relationship_candidate_detail_of:
                    suggested_decision = "candidate_detail_of"
                elif no_identity_signal:
                    # Reached the queue with no strong identity anchor at all
                    # (no shared Wikidata item, no shared name/alias) --
                    # whatever included it was geography + date-overlap +
                    # fuzzy/token name similarity alone. Every verified
                    # example of that exact shape this session (West
                    # Virginia/Virginia, Canton of Appenzell Innerrhoden/
                    # Ausserrhoden, Kingdom of Wessex/Kingdom of Essex) turned
                    # out to be genuinely distinct entities. Defaulting to
                    # "independent" here is the safer direction to be wrong
                    # in: worst case a reviewer clicks past an overeager
                    # suggestion, versus the alternative of silently leaving
                    # the common case unaddressed (found live, 31 August
                    # 2026).
                    suggested_decision = "independent"
                else:
                    suggested_decision = None
                candidates.append(
                    {
                        "id": other_id,
                        "canonical_name": other.get("canonical_name", other_id),
                        "entity_type": other.get("entity_type", "polity"),
                        "dates": [other.get("start"), other.get("end")],
                        "wikidata": (other.get("external_ids") or {}).get("wikidata"),
                        "score": round(score, 1),
                        "name_score": round(name_score, 1),
                        "geography_match": geography_match,
                        "date_contains": date_contains,
                        "reverse_date_contains": reverse_date_contains,
                        "date_overlap": date_overlap,
                        "exact_name_match": exact_name_match,
                        "same_wikidata": same_wikidata,
                        "type_match": type_match,
                        "coordinate_distance_km": round(coordinate_km) if coordinate_km is not None else None,
                        "coordinate_conflict": coordinate_conflict,
                        "shared_p131": shared_p131,
                        "documented_successor": documented_successor,
                        "possible_qid_conflict": possible_qid_conflict,
                        "no_overlap_alias_reuse": no_overlap_alias_reuse,
                        "likely_siblings": likely_siblings,
                        "no_identity_signal": no_identity_signal,
                        "regime_of_candidate": regime_of_candidate,
                        "regime_of_reviewed": regime_of_reviewed,
                        "reviewed_part_of_candidate": reviewed_part_of_candidate,
                        "candidate_part_of_reviewed": candidate_part_of_reviewed,
                        "subdivision_part_of_candidate": subdivision_part_of_candidate,
                        "subdivision_part_of_reviewed": subdivision_part_of_reviewed,
                        "documented_relationship_detail_of": documented_relationship_detail_of,
                        "documented_relationship_candidate_detail_of": documented_relationship_candidate_detail_of,
                        "suggested_decision": suggested_decision,
                        "confidence": (
                            "high" if not possible_qid_conflict and not no_overlap_alias_reuse
                            and (
                                same_wikidata
                                or (
                                    exact_name_match and geography_compatible
                                    and not coordinate_conflict and not documented_successor
                                )
                            )
                            else "medium"
                        ),
                        "reasons": reasons,
                        "present_countries": sorted(other_countries),
                        "direct_type_qids": sorted(set((direct_types.get((other.get("external_ids") or {}).get("wikidata")) or {}).get("types", []))),
                    }
                )
            candidates.sort(key=lambda item: (-item["score"], item["canonical_name"]))
            # Direct policy, live, 7 September 2026: if every candidate's own
            # suggested_decision is "independent", the answer is already
            # known -- reviewing it achieves nothing, same reasoning as the
            # date-overlap exclusions above. Kept in the queue whenever at
            # least one candidate suggests a real relationship
            # (same_entity/detail_of/candidate_detail_of) OR is genuinely
            # ambiguous (suggested_decision is None, no confident
            # recommendation either way) -- only a unanimous "independent"
            # across every candidate is skipped. This is a presentation
            # filter only, same as the date-overlap fixes -- nothing gets
            # auto-written to consolidation_status; the entity simply
            # doesn't need a human decision made for it.
            if candidates and any(c["suggested_decision"] != "independent" for c in candidates):
                queue.append(
                    {
                        "id": entity_id,
                        "canonical_name": source_name,
                        "entity_type": document.get("entity_type", "polity"),
                        "dates": [document.get("start"), document.get("end")],
                        "wikidata": (document.get("external_ids") or {}).get("wikidata"),
                        "prominence_score": source_prominence,
                        "present_countries": sorted(source_countries),
                        "direct_type_qids": sorted(set((direct_types.get(source_qid) or {}).get("types", []))),
                        "candidates": candidates[:5],
                    }
                )
        queue_by_id = {item["id"]: item for item in queue}
        for period_record in period_role_queue:
            document = active.get(period_record["id"])
            if not document:
                continue
            item = queue_by_id.get(period_record["id"])
            if item is None:
                # Policy, live, 7 September 2026: this fallback entry is
                # the sole reason a candidate-less item ever reaches the
                # queue at all -- it exists specifically to surface a
                # genuine entity/period ambiguity that has no
                # consolidation candidate to reconcile against. The
                # frontend renders it with period-role framing (see
                # consolidation_review.js), not the identity-matching
                # framing used for real candidates.
                qid = (document.get("external_ids") or {}).get("wikidata")
                item = {
                    "id": document["id"], "canonical_name": document["canonical_name"],
                    "entity_type": document.get("entity_type", "polity"),
                    "dates": [document.get("start"), document.get("end")],
                    "wikidata": qid,
                    "prominence_score": float(document.get("prominence_score", 0)),
                    "present_countries": sorted((document.get("geography") or {}).get("present_countries", [])),
                    "direct_type_qids": sorted(set((direct_types.get(qid) or {}).get("types", []))),
                    "candidates": [],
                }
                queue.append(item)
                queue_by_id[item["id"]] = item
            item["period_role_candidate"] = True
            item["period_reason"] = period_record.get("reason", "Ambiguous entity and period role")
        queue.sort(key=lambda item: (
            0 if item["candidates"] and item["candidates"][0]["confidence"] == "high" else 1,
            0 if item["candidates"] else 1,
            -(item["candidates"][0]["score"] if item["candidates"] else 0),
            -item["prominence_score"], item["canonical_name"],
        ))
        return queue

    def write_period_record(
        document: dict,
        authority: str,
        notes: str,
        source_urls: list[str],
        promoted_from: str,
    ) -> str:
        """Write the period-overlay YAML companion of a polity, and return its id."""
        period_id = f"{document['id']}_period"
        qid = (document.get("external_ids") or {}).get("wikidata")
        periods_dir = root / "periods"
        periods_dir.mkdir(exist_ok=True)
        period = {
            "id": period_id,
            "canonical_name": document["canonical_name"],
            "start": document["start"],
            "end": document["end"],
            "start_confidence": document.get("start_confidence", "low"),
            "end_confidence": document.get("end_confidence", "low"),
            "geography": document.get("geography") or {},
            "broader_periods": [],
            "successors": [],
            "authority": authority,
            "external_ids": {"wikidata": qid} if qid else {},
            "notes": notes,
            "source_urls": source_urls,
            "promoted_from": promoted_from,
        }
        (periods_dir / f"{period_id}.yaml").write_text(
            yaml.safe_dump(period, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        return period_id

    def append_period_link(
        period_id: str,
        entity_id: str,
        relation: str,
        source_urls: list[str],
        notes: str,
    ) -> None:
        """Add a period_links.yaml entry unless that period/entity pair is already linked."""
        links_path = root / "period_links.yaml"
        links = yaml.safe_load(links_path.read_text(encoding="utf-8")) if links_path.exists() else []
        links = links or []
        if any(
            link.get("period_id") == period_id and link.get("entity_id") == entity_id
            for link in links
        ):
            return
        links.append(
            {
                "period_id": period_id,
                "entity_id": entity_id,
                "relation": relation,
                "evidence": "explicit",
                "confidence": "high",
                "source_urls": source_urls,
                "notes": notes,
            }
        )
        links_path.write_text(yaml.safe_dump(links, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def save_consolidation(entity_id: str, decision: str, target_id: str | None) -> dict:
        document = metadata.get(entity_id)
        if (
            not document or document.get("timeline_role") == "retired"
            or document.get("consolidation_status") or document.get("detail_of")
        ):
            raise HTTPException(404, "Consolidation review is not pending")
        if decision == "independent":
            document["consolidation_status"] = "independent"
            document["manual_overrides"] = sorted(set(document.get("manual_overrides", [])) | {"consolidation"})
            (polities_dir / f"{entity_id}.yaml").write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            metadata[entity_id] = document
            return document
        if decision == "discarded":
            document["timeline_role"] = "retired"
            document["eligibility"] = "excluded"
            document["consolidation_status"] = "discarded"
            document["manual_overrides"] = sorted(
                set(document.get("manual_overrides", [])) | {"consolidation", "eligibility"}
            )
            document["notes"] = (
                document.get("notes", "").rstrip()
                + " Editorially discarded as outside Histomap scope."
            ).strip()
            (polities_dir / f"{entity_id}.yaml").write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            metadata[entity_id] = document
            return document
        target = metadata.get(target_id or "")
        if not target or target_id == entity_id or target.get("timeline_role") == "retired":
            raise HTTPException(422, "target_id must identify another active entity")
        if decision == "same_entity":
            document["timeline_role"] = "retired"
            document["consolidation_status"] = "same_entity"
            document["consolidated_into"] = target_id
            document["manual_overrides"] = sorted(set(document.get("manual_overrides", [])) | {"consolidation"})
            aliases = {
                item.strip()
                for item in str((target.get("names") or {}).get("aliases_en", "")).split("|")
                if item.strip()
            }
            aliases.add(document["canonical_name"])
            target.setdefault("names", {})["aliases_en"] = " | ".join(sorted(aliases))
            target["sources"] = sorted(set(target.get("sources", [])) | set(document.get("sources", [])))
            target["manual_overrides"] = sorted(set(target.get("manual_overrides", [])) | {"consolidation"})
            (polities_dir / f"{target_id}.yaml").write_text(
                yaml.safe_dump(target, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            (polities_dir / f"{entity_id}.yaml").write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            metadata[entity_id] = document
            metadata[target_id] = target
            return document
        if decision == "detail_of":
            # No finite-end requirement and no Period record -- a detail
            # entity stays a live Polity with its own start/end, same as
            # before the decision. Replaces the old phase_of (which
            # manufactured a Period and retired the entity) and part_of
            # (which retyped entity_type to subdivision) mechanisms; see
            # docs/plans/2026-09-01-detail-of-merge-design.md.
            document["detail_of"] = target_id
            document["manual_overrides"] = sorted(set(document.get("manual_overrides", [])) | {"consolidation"})
            (polities_dir / f"{entity_id}.yaml").write_text(
                yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            metadata[entity_id] = document
            return document
        raise HTTPException(422, f"Unsupported consolidation decision: {decision}")

    def save_entity_type(polity_id: str, entity_type: str) -> dict:
        document = metadata.get(polity_id)
        path = polities_dir / f"{polity_id}.yaml"
        if document is None or not path.exists():
            raise HTTPException(404, "Unknown Histomap entity")
        def add_typed_relationship(source: dict, target: dict, legacy_kind: str) -> None:
            kind = relationship_kind(
                source.get("entity_type", "polity"), target.get("entity_type", "polity"), legacy_kind
            )
            relationships = source.setdefault("relationships", [])
            if any(item.get("kind") == kind and item.get("target") == target["id"] for item in relationships):
                return
            qid = (source.get("external_ids") or {}).get("wikidata")
            relationships.append(
                {
                    "target": target["id"],
                    "kind": kind,
                    "evidence": "derived",
                    "confidence": "medium",
                    "source_urls": [f"https://www.wikidata.org/wiki/{qid}"] if qid else [],
                }
            )

        document["entity_type"] = entity_type
        document["entity_type_confidence"] = "high"
        document["entity_type_source_qids"] = []
        document["manual_overrides"] = sorted(
            set(document.get("manual_overrides", [])) | {"entity_type"}
        )
        changed = {polity_id}
        if document.get("parent"):
            target = metadata.get(document["parent"])
            if target:
                add_typed_relationship(document, target, "parent")
            if entity_type not in {"polity", "subdivision"} or (
                target and target.get("entity_type", "polity") != "polity"
            ):
                document["parent"] = None
        retained_successors = []
        for target_id in document.get("successors", []):
            target = metadata.get(target_id)
            if target:
                add_typed_relationship(document, target, "successor")
            if entity_type == "polity" and target and target.get("entity_type", "polity") == "polity":
                retained_successors.append(target_id)
        document["successors"] = retained_successors
        for candidate_id, candidate in metadata.items():
            if candidate_id == polity_id:
                continue
            candidate_changed = False
            if any(
                relationship.get("target") == polity_id
                for relationship in candidate.get("relationships") or []
            ):
                candidate_changed = True
            if candidate.get("parent") == polity_id:
                add_typed_relationship(candidate, document, "parent")
                candidate_changed = True
                if candidate.get("entity_type", "polity") != "polity" or entity_type != "polity":
                    candidate["parent"] = None
                    candidate_changed = True
            if polity_id in (candidate.get("successors") or []):
                add_typed_relationship(candidate, document, "successor")
                candidate_changed = True
                if candidate.get("entity_type", "polity") != "polity" or entity_type != "polity":
                    candidate["successors"] = [item for item in candidate["successors"] if item != polity_id]
                    candidate_changed = True
            if candidate_changed:
                changed.add(candidate_id)
        for changed_id in changed:
            changed_document = metadata[changed_id]
            normalized_relationships = []
            seen_relationships = set()
            for relationship in changed_document.get("relationships") or []:
                relationship = dict(relationship)
                target = metadata.get(relationship.get("target"))
                if target:
                    relationship["kind"] = normalized_relationship_kind(
                        changed_document.get("entity_type", "polity"),
                        target.get("entity_type", "polity"),
                        relationship["kind"],
                    )
                key = (relationship.get("kind"), relationship.get("target"))
                if key in seen_relationships:
                    continue
                seen_relationships.add(key)
                normalized_relationships.append(relationship)
            changed_document["relationships"] = normalized_relationships
            (polities_dir / f"{changed_id}.yaml").write_text(
                yaml.safe_dump(changed_document, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
        metadata[polity_id] = document
        return document


    def save_timeline_role(polity_id: str, timeline_role: str) -> dict:
        document = metadata.get(polity_id)
        path = polities_dir / f"{polity_id}.yaml"
        if document is None or not path.exists():
            raise HTTPException(404, "Unknown Histomap entity")
        if timeline_role in {"period", "both"} and document.get("end") is None:
            raise HTTPException(422, "A period overlay requires a finite end date")
        document["timeline_role"] = timeline_role
        document["manual_overrides"] = sorted(
            set(document.get("manual_overrides", [])) | {"timeline_role"}
        )
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
        period_id = None
        if timeline_role in {"period", "both"}:
            qid = (document.get("external_ids") or {}).get("wikidata")
            source_urls = [f"https://www.wikidata.org/wiki/{qid}"] if qid else []
            period_id = write_period_record(
                document,
                authority="Wikidata period classification",
                notes="Period overlay created by an editorial period-role decision.",
                source_urls=source_urls,
                promoted_from=polity_id,
            )
            if timeline_role == "both":
                append_period_link(
                    period_id,
                    polity_id,
                    relation="part_of_periodization",
                    source_urls=source_urls,
                    notes="Same Wikidata item has distinct entity and period roles.",
                )
        metadata[polity_id] = document
        return {"document": document, "period_id": period_id}

    BUILD_ARTIFACT_FILES = (
        "data.json", "transitions.json", "periods.json", "period_links.json", "explore_tree.json",
    )

    @application.middleware("http")
    async def no_cache_static(request, call_next):
        """Force browsers to revalidate (not silently reuse a stale copy of)
        every /static/* file, and every build artifact at the repo root
        (data.json, explore_tree.json, ...), on each load. Without this, the
        default FileResponse/StaticFiles response carries only ETag/
        Last-Modified -- no explicit Cache-Control -- so browsers apply RFC
        7234 heuristic freshness and can serve an old cached copy for a
        while after a deploy or a rebuild, with no visible sign anything is
        stale. Bit this session's own live testing repeatedly (explore.js,
        consolidation_review.js) before being root-caused here for
        /static/* -- then bit it again, 7 September 2026, for the build
        artifacts specifically: converting a polity to a period and
        rebuilding correctly updated data.json/explore_tree.json on disk,
        but /explore kept showing the stale pre-rebuild version until a hard
        refresh, since these routes (registered separately, see
        register_build_artifact below) weren't covered by the original
        /static/*-only fix. `no-cache` still allows a cheap 304 on an
        unchanged file -- it forces revalidation, not a full re-download.
        """
        response = await call_next(request)
        if request.url.path.startswith("/static/") or request.url.path.lstrip("/") in BUILD_ARTIFACT_FILES:
            response.headers["Cache-Control"] = "no-cache"
        return response

    application.mount("/static", StaticFiles(directory=web_dir), name="static")

    def register_page(route: str, filename: str) -> None:
        """Serve one static HTML page from web/."""

        async def page() -> FileResponse:
            return FileResponse(web_dir / filename)

        application.add_api_route(route, page, include_in_schema=False)

    for page_route, page_file in (
        ("/reviews", "reviews.html"),
        ("/explore", "explore.html"),
        ("/consolidation-review", "consolidation_review.html"),
    ):
        register_page(page_route, page_file)

    def register_build_artifact(filename: str) -> None:
        """Serve one build output from the repo root, 404ing until it exists."""

        async def artifact() -> FileResponse:
            path = root / filename
            if not path.exists():
                raise HTTPException(404, "Run the build action first")
            return FileResponse(path)

        application.add_api_route(f"/{filename}", artifact, include_in_schema=False)

    for artifact_file in BUILD_ARTIFACT_FILES:
        register_build_artifact(artifact_file)

    @application.get("/api/review-dashboard")
    async def review_dashboard() -> dict:
        refresh_period_role_queue()
        consolidation_queue = consolidation_review_queue()
        return {
            "pipelines": {
                "consolidation": len(consolidation_queue),
            },
            "breakdowns": {
                "consolidation": {
                    "high": sum(1 for item in consolidation_queue if item["candidates"] and item["candidates"][0]["confidence"] == "high"),
                    "medium": sum(1 for item in consolidation_queue if item["candidates"] and item["candidates"][0]["confidence"] == "medium"),
                    "period_role": sum(1 for item in consolidation_queue if item.get("period_role_candidate")),
                }
            },
        }

    @application.get("/api/consolidation-reviews")
    async def consolidation_reviews(
        offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)
    ) -> dict:
        queue = consolidation_review_queue()
        return clean_json({"total": len(queue), "offset": offset, "items": queue[offset : offset + limit]})

    @application.post("/api/consolidation-reviews/{entity_id}")
    async def decide_consolidation_review(entity_id: str, request: ConsolidationDecision) -> dict:
        if request.decision == "candidate_detail_of":
            candidate_id = request.target_id or ""
            candidate = metadata.get(candidate_id)
            reviewed = metadata.get(entity_id)
            if not candidate or not reviewed or candidate_id == entity_id:
                raise HTTPException(422, "target_id must identify another active entity")
            save_consolidation(candidate_id, "detail_of", entity_id)
            save_consolidation(entity_id, "independent", None)
            return {
                "status": "saved", "entity_id": entity_id,
                "decision": request.decision, "target_id": candidate_id,
            }
        if request.decision == "period":
            result = save_timeline_role(entity_id, request.decision)
            return {
                "status": "saved", "entity_id": entity_id, "decision": request.decision,
                "target_id": None, "period_id": result["period_id"],
            }
        document = save_consolidation(entity_id, request.decision, request.target_id)
        return {
            "status": "saved", "entity_id": entity_id,
            "decision": request.decision,
            "target_id": document.get("consolidated_into") or document.get("detail_of"),
        }

    @application.post("/api/polities")
    async def create_polity(request: PolityCreate) -> dict:
        """ROADMAP.md item 0: minimal hand-authoring path for a polity that
        doesn't already exist via Wikidata ingestion or a period conversion.
        Requires present_countries (unlike every other geography field on
        this record) so the new entity is never placed as "Unclassified"
        -- geography drives /explore's grouping."""
        taken_ids = set(metadata.keys()) | {path.stem for path in (root / "periods").glob("*.yaml")}
        polity_id = slugify_entity_id(request.canonical_name, taken_ids)
        document = {
            "id": polity_id,
            "canonical_name": request.canonical_name,
            "entity_type": request.entity_type,
            "entity_type_confidence": "high",
            "start": request.start,
            "end": request.end,
            "start_confidence": "low",
            "end_confidence": "low",
            "eligibility": "accepted",
            "sources": ["histomap_editorial"],
            "geography": derive_geography_for_countries(request.present_countries, iso2_to_continents),
        }
        try:
            validated = Polity.model_validate(document).model_dump(mode="json")
        except ValidationError as exc:
            raise HTTPException(422, str(exc)) from exc
        (polities_dir / f"{polity_id}.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        metadata[polity_id] = document
        return {"status": "created", "polity_id": polity_id, "document": clean_json(validated)}

    @application.post("/api/periods")
    async def create_period(request: PeriodCreate) -> dict:
        """Period counterpart to create_polity above. Period.end is
        required by schema (no open-ended periods), unlike a polity's."""
        taken_ids = set(metadata.keys()) | {path.stem for path in (root / "periods").glob("*.yaml")}
        period_id = slugify_entity_id(request.canonical_name, taken_ids)
        document = {
            "id": period_id,
            "canonical_name": request.canonical_name,
            "start": request.start,
            "end": request.end,
            "authority": "Histomap editorial: manually created",
            "geography": derive_geography_for_countries(request.present_countries, iso2_to_continents),
        }
        try:
            validated = Period.model_validate(document).model_dump(mode="json")
        except ValidationError as exc:
            raise HTTPException(422, str(exc)) from exc
        (root / "periods" / f"{period_id}.yaml").write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        return {"status": "created", "period_id": period_id, "document": clean_json(validated)}

    @application.delete("/api/polities/{polity_id}")
    async def delete_polity(polity_id: str) -> dict:
        """Hard delete -- unlike the "discarded" consolidation decision
        (which keeps the record on disk as an audit trail), this removes
        the YAML file permanently. Refuses (409) rather than silently
        breaking the next build if any other record still references this
        one -- see find_delete_blockers."""
        path = polities_dir / f"{polity_id}.yaml"
        if not path.exists() or metadata.get(polity_id) is None:
            raise HTTPException(404, "Unknown Histomap entity")
        blockers = find_delete_blockers(
            polity_id, metadata, root / "periods", root / "transitions.yaml", root / "period_links.yaml"
        )
        if blockers:
            raise HTTPException(409, "Cannot delete -- still referenced: " + "; ".join(blockers))
        path.unlink()
        metadata.pop(polity_id, None)
        return {"status": "deleted", "polity_id": polity_id}

    @application.delete("/api/periods/{period_id}")
    async def delete_period(period_id: str) -> dict:
        """Period counterpart to delete_polity above."""
        path = root / "periods" / f"{period_id}.yaml"
        if not path.exists():
            raise HTTPException(404, "Unknown Histomap period")
        blockers = find_delete_blockers(
            period_id, metadata, root / "periods", root / "transitions.yaml", root / "period_links.yaml"
        )
        if blockers:
            raise HTTPException(409, "Cannot delete -- still referenced: " + "; ".join(blockers))
        path.unlink()
        return {"status": "deleted", "period_id": period_id}

    @application.get("/api/polities/search")
    async def search_all_polities(
        q: str = Query(..., min_length=2), limit: int = Query(10, ge=1, le=25)
    ) -> dict:
        return clean_json({"query": q, "items": search_polities(q, metadata, limit)})

    @application.get("/api/periods/search")
    async def search_all_periods(
        q: str = Query(..., min_length=2), limit: int = Query(10, ge=1, le=25)
    ) -> dict:
        return clean_json({"query": q, "items": search_periods(q, root / "periods", limit)})

    @application.get("/api/polities/{polity_id}")
    async def get_polity(polity_id: str) -> dict:
        """Returns one polity's full raw fields, straight from the
        in-memory metadata store -- unlike /data.json (the published set,
        which excludes retired/excluded entities), this always finds any
        entity still resolvable by id, matching what a reviewer sees in
        /consolidation-review's queue even when it isn't published/visible
        in /explore (found live, 1 September 2026 -- a queue entry that
        wasn't rendered in /explore's tree needed direct editing here
        instead)."""
        document = metadata.get(polity_id)
        if document is None:
            raise HTTPException(404, "Unknown Histomap entity")
        return clean_json(document)

    @application.get("/api/options/geography")
    async def geography_options() -> dict:
        return {
            "continents": CONTINENTS,
            "countries": [
                {
                    "code": code,
                    "label": label,
                    "continents": sorted(
                        {
                            continent
                            for info in country_metadata.values()
                            if info.get("iso2") == code
                            for continent in info.get("continents", [])
                            if continent in CONTINENTS
                        }
                    ),
                }
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
                # historical_regions/primary_historical_region aren't edited by
                # this form (continents/countries are the only controls) --
                # preserve whatever was already there instead of silently
                # dropping it, which every save through this endpoint used to
                # do (found via norwegian_jarldom_of_orkney.yaml, 2026-08-31).
                "historical_regions": existing.get("historical_regions") or [],
                "primary_historical_region": existing.get("primary_historical_region"),
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

    @application.patch("/api/polities/{polity_id}/entity-type")
    async def update_entity_type(polity_id: str, request: EntityTypeUpdate) -> dict:
        document = save_entity_type(
            polity_id, request.entity_type
        )
        return {
            "status": "saved",
            "polity_id": polity_id,
            "entity_type": request.entity_type,
            "entity_type_confidence": "high",
            "manual_overrides": document["manual_overrides"],
        }

    @application.post("/api/polities/{polity_id}/convert-to-period")
    async def convert_polity_to_period(polity_id: str, keep_entity: bool = False) -> dict:
        """Direct, ungated counterpart to promote-to-entity below -- demotes a
        polity to a period-role overlay (mirrors the consolidation review
        queue's "period" decision via the same save_timeline_role helper, but
        callable for any polity from the /explore side panel, not just one
        that happens to be queued for consolidation review). `keep_entity`
        selects timeline_role "both" instead of "period" -- the polity stays
        visible as its own entity *and* gets a period_links.yaml-linked
        period companion, for the rare case where the same Wikidata item
        genuinely has distinct entity and period roles. This was previously
        only reachable via the now-retired /period-review page; see
        STATUS.md."""
        timeline_role = "both" if keep_entity else "period"
        result = save_timeline_role(polity_id, timeline_role)
        return {
            "status": "saved", "polity_id": polity_id,
            "timeline_role": timeline_role, "period_id": result["period_id"],
        }

    def save_merged_fields(
        path: Path,
        record_id: str,
        fields: dict,
        model: type[BaseModel],
        missing_message: str,
        mismatch_message: str,
    ) -> tuple[dict, list[str]]:
        """Merge an arbitrary subset of fields onto a YAML record, validate the
        result against its full schema, and write it back.

        Returns the merged document and the list of fields that actually
        changed. `id` can never be changed this way (it would desync the
        record from its filename)."""
        if not path.exists():
            raise HTTPException(404, missing_message)
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if document.get("id") != record_id:
            raise HTTPException(409, mismatch_message)
        merged = {**document, **fields, "id": record_id}
        try:
            merged_normalized = model.model_validate(merged).model_dump(mode="json")
        except ValidationError as exc:
            raise HTTPException(422, str(exc)) from exc
        # Compares normalized (schema-defaulted) values on both sides, not the
        # raw dicts -- the panel's raw editor round-trips through /data.json's
        # fully-expanded model dump, so a field a human never touched (e.g.
        # tier, implicit in the hand-authored YAML via its schema default)
        # would otherwise show up as "changed" the moment it becomes explicit
        # in the submission, falsely bloating manual_overrides.
        try:
            original_normalized = model.model_validate(document).model_dump(mode="json")
        except ValidationError:
            original_normalized = document
        changed = sorted(
            key for key in fields
            if key != "id" and original_normalized.get(key) != merged_normalized.get(key)
        )
        if changed:
            merged["manual_overrides"] = sorted(set(merged.get("manual_overrides") or []) | set(changed))
        path.write_text(yaml.safe_dump(merged, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return merged, changed

    @application.patch("/api/polities/{polity_id}/fields")
    async def update_polity_fields(polity_id: str, fields: dict) -> dict:
        """General-purpose polity editor: unlike the single-field endpoints
        above (entity-type, geography), this can edit anything in the YAML
        file, including fields with no dedicated UI/endpoint (timeline_role,
        dates, weight_by_era, etc.)."""
        merged, changed = save_merged_fields(
            polities_dir / f"{polity_id}.yaml",
            polity_id,
            fields,
            Polity,
            "Unknown Histomap entity",
            "Polity file ID does not match requested polity",
        )
        metadata[polity_id] = merged
        return {"status": "saved", "polity_id": polity_id, "changed": changed, "document": merged}

    @application.patch("/api/periods/{period_id}/fields")
    async def update_period_fields(period_id: str, fields: dict) -> dict:
        """Period counterpart to update_polity_fields above -- can edit
        anything in a period's YAML file, including `tier` and
        `broader_periods`, neither of which has any other UI/endpoint today."""
        merged, changed = save_merged_fields(
            root / "periods" / f"{period_id}.yaml",
            period_id,
            fields,
            Period,
            "Unknown Histomap period",
            "Period file ID does not match requested period",
        )
        return {"status": "saved", "period_id": period_id, "changed": changed, "document": merged}

    @application.post("/api/periods/{period_id}/promote-to-entity")
    async def promote_period_to_entity(period_id: str, request: PeriodPromotionUpdate) -> dict:
        period_path = root / "periods" / f"{period_id}.yaml"
        if not period_path.exists():
            raise HTTPException(404, "Unknown Histomap period")
        period = yaml.safe_load(period_path.read_text(encoding="utf-8")) or {}
        if period.get("id") != period_id:
            raise HTTPException(409, "Period file ID does not match requested period")

        entity_id = period_id.removesuffix("_period")
        entity_path = polities_dir / f"{entity_id}.yaml"
        if entity_path.exists():
            entity = yaml.safe_load(entity_path.read_text(encoding="utf-8")) or {}
        else:
            qid = (period.get("external_ids") or {}).get("wikidata")
            entity = {
                "id": entity_id,
                "canonical_name": period["canonical_name"],
                "names": {},
                "external_ids": {"wikidata": qid} if qid else {},
                "successors": [],
                "start": period["start"],
                "end": period["end"],
                "start_confidence": period.get("start_confidence", "low"),
                "end_confidence": period.get("end_confidence", "low"),
                "weight_by_era": {},
                "weight_imputed": True,
                "icon": None,
                "text": {"short_child_en": "", "short_adult_en": "", "long_en": ""},
                "notes": period.get("notes", "Promoted from a Histomap period."),
                "sources": ["wikidata"] if qid else ["histomap_editorial"],
                "prominence_score": 0,
                "eligibility": "accepted",
                "geography": period.get("geography") or {},
                "relationships": [],
            }
        entity.update({
            "entity_type": request.entity_type,
            "entity_type_confidence": "high",
            "entity_type_source_qids": [],
            "timeline_role": "entity",
            "eligibility": "accepted",
        })
        entity.pop("consolidation_status", None)
        entity.pop("consolidated_into", None)
        entity["manual_overrides"] = sorted(
            set(entity.get("manual_overrides", [])) | {"consolidation", "entity_type", "timeline_role"}
        )
        entity_path.write_text(
            yaml.safe_dump(entity, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        metadata[entity_id] = entity

        links_path = root / "period_links.yaml"
        links = yaml.safe_load(links_path.read_text(encoding="utf-8")) if links_path.exists() else []
        links = [link for link in (links or []) if link.get("period_id") != period_id]
        links_path.write_text(yaml.safe_dump(links, sort_keys=False, allow_unicode=True), encoding="utf-8")
        period_path.unlink()
        return {
            "status": "saved",
            "period_id": period_id,
            "entity_id": entity_id,
            "entity": entity,
        }

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
                refresh_metadata()
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
        return RedirectResponse("/explore")

    @application.get("/", include_in_schema=False)
    async def root_redirect() -> RedirectResponse:
        # The original Timeline page (web/index.html + web/app.js) is retired;
        # /explore is the primary workspace root now. See ROADMAP.md item 0.
        return RedirectResponse("/explore")

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.app:app", host="127.0.0.1", port=8000, reload=False)
