import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
QID_PATTERN = re.compile(r"^Q\d+$")

YEAR_MIN = -3_000_000
# The dataset's own modeled-timeline ceiling (macro_contemporary_world's own
# end year, generate_modern_regional_eras.py) -- a fixed domain boundary, not
# "today". Distinct from CURRENT_YEAR below; conflating the two was a real
# latent bug risk (found during the 2026-08-31 simplification pass) -- do not
# merge them into one constant.
YEAR_MAX = 2100
# "Today", for computing a still-active entity's current age/duration
# (compute_prominence.py's longevity component, and the open-ended-polity
# date-overlap fallbacks in generate_modern_regional_eras.py/reconcile.py/
# suggest_period_links.py). Computed once at import time rather than
# hardcoded (it previously was, as a literal `2026` in four separate files)
# so it can't silently go stale the way a hardcoded year does every January.
CURRENT_YEAR = datetime.now(timezone.utc).year


class Confidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    legendary = "legendary"


class VisibilityTier(str, Enum):
    global_ = "global"
    regional = "regional"
    detailed = "detailed"


class Eligibility(str, Enum):
    accepted = "accepted"
    review = "review"
    excluded = "excluded"


class EntityType(str, Enum):
    polity = "polity"
    civilization = "civilization"
    subdivision = "subdivision"
    micronation = "micronation"
    culture = "culture"
    people = "people"
    tribe = "tribe"
    archaeological_horizon = "archaeological_horizon"


class EntityRelationship(BaseModel):
    target: str
    kind: Literal[
        "political_parent",
        "political_successor",
        "administrative_part_of",
        "cultural_component",
        "associated_people",
        "archaeological_sequence",
        "cultural_sequence",
        "part_of_civilization",
    ]
    evidence: Literal["explicit", "derived", "suggested"] = "explicit"
    confidence: Confidence = Confidence.medium
    source_qids: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)

    @field_validator("target")
    @classmethod
    def _target_id(cls, value: str) -> str:
        if not ID_PATTERN.match(value):
            raise ValueError("relationship target must be a canonical snake_case ID")
        return value

    @field_validator("source_qids")
    @classmethod
    def _source_qids(cls, values: list[str]) -> list[str]:
        if any(not QID_PATTERN.match(value) for value in values):
            raise ValueError("relationship source_qids must contain Wikidata QIDs")
        return sorted(set(values))


class ExternalIds(BaseModel):
    wikidata: str | None = None
    wikipedia_en: str | None = None
    seshat: list[str] = Field(default_factory=list)

    @field_validator("seshat", mode="before")
    @classmethod
    def _seshat_list(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("wikidata")
    @classmethod
    def _qid(cls, v: str | None) -> str | None:
        if v is not None and not QID_PATTERN.match(v):
            raise ValueError("wikidata id must match ^Q\\d+$")
        return v

    @field_validator("wikipedia_en")
    @classmethod
    def _english_wikipedia_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("https://en.wikipedia.org/wiki/"):
            raise ValueError("wikipedia_en must be an English Wikipedia article URL")
        return value


class Text(BaseModel):
    short_child_en: str = ""
    short_adult_en: str = ""
    long_en: str = ""


class Centroid(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Geography(BaseModel):
    continents: list[str] = Field(default_factory=list)
    primary_continent: str | None = None
    historical_regions: list[str] = Field(default_factory=list)
    primary_historical_region: str | None = None
    present_countries: list[str] = Field(default_factory=list)
    centroid: Centroid | None = None
    confidence: Confidence | None = None

    @field_validator("present_countries")
    @classmethod
    def _country_codes(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[A-Z]{2}", value) for value in values):
            raise ValueError("present_countries must contain ISO alpha-2 codes")
        return sorted(set(values))

    @model_validator(mode="after")
    def _primary_is_a_known_continent(self) -> "Geography":
        if self.primary_continent is not None and self.primary_continent not in self.continents:
            raise ValueError("primary_continent must also appear in continents")
        if self.primary_continent is None and len(self.continents) == 1:
            self.primary_continent = self.continents[0]
        return self

    @model_validator(mode="after")
    def _primary_is_a_known_historical_region(self) -> "Geography":
        if self.primary_historical_region is not None and self.primary_historical_region not in self.historical_regions:
            raise ValueError("primary_historical_region must also appear in historical_regions")
        if self.primary_historical_region is None and len(self.historical_regions) == 1:
            self.primary_historical_region = self.historical_regions[0]
        return self


class Polity(BaseModel):
    id: str
    canonical_name: str
    names: dict[str, str] = Field(default_factory=dict)
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    entity_type: EntityType = EntityType.polity
    entity_type_confidence: Confidence = Confidence.low
    entity_type_source_qids: list[str] = Field(default_factory=list)
    entity_type_reviewed_against: list[EntityType] = Field(default_factory=list)
    timeline_role: Literal["entity", "period", "both", "retired"] = "entity"
    consolidation_status: Literal["independent", "same_entity", "discarded"] | None = None
    consolidated_into: str | None = None
    # The id of the entity this one is a detail of -- replaces the old
    # phase_of (which manufactured a Period record and retired the polity)
    # and part_of (which retyped entity_type to subdivision) consolidation
    # mechanisms. See docs/plans/2026-09-01-detail-of-merge-design.md.
    detail_of: str | None = None
    # Generic bucket preserving old field values under their original names
    # for records migrated away from a retired mechanism (phase_of/part_of
    # consolidation_status) -- a historical record, never read back by
    # anything live.
    deprecated: dict[str, Any] | None = None
    relationships: list[EntityRelationship] = Field(default_factory=list)
    successors: list[str] = Field(default_factory=list)
    geography: Geography = Field(default_factory=Geography)
    manual_overrides: list[str] = Field(default_factory=list)
    # Explicit, editable era/period id this entity is grouped/colored with on
    # /explore -- a plain field, not derived from a heuristic. Was seeded
    # 2026-08-31 from build_explore_tree.py's date+geography match heuristic
    # (the same one rank_candidates uses elsewhere) as a one-time starting
    # point; from here on it's curator-set only, no on-the-fly recomputation.
    linked_era_id: str | None = None
    # Explicit, editable macro-chapter id this entity is grouped under on
    # /explore -- a plain field, not derived from a heuristic. Was seeded
    # 2026-08-31 from build_explore_tree.py's best_chapter_for_polity()
    # date-overlap heuristic as a one-time starting point; from here on it's
    # curator-set only. Takes precedence over both the period_links.yaml-
    # curated path and the heuristic when set (an explicit human decision is
    # the strongest signal there is).
    linked_chapter_id: str | None = None
    # Specific kind of governed political entity (sultanate, khanate, duchy,
    # principality, ...), distinct from entity_type -- entity_type only
    # distinguishes polity/civilization/subdivision/micronation/culture/
    # people/tribe/archaeological_horizon, with no room to record which kind
    # of polity. Auto-derived from Wikidata direct type where
    # pipeline/backfill_entity_types.py's GOVERNMENT_FORM_QIDS has a mapping;
    # None when it doesn't (a plain "country" or "empire" has no more
    # specific form to record). Editable like any other field once set.
    government_form: str | None = None
    start: int
    end: int | None = None
    start_confidence: Confidence
    end_confidence: Confidence
    weight_by_era: dict[int, float] = Field(default_factory=dict)
    weight_imputed: bool = False
    prominence_score: float = Field(default=0, ge=0, le=100)
    prominence_components: dict[str, float] = Field(default_factory=dict)
    visibility_tier: VisibilityTier = VisibilityTier.detailed
    visibility_override: VisibilityTier | None = None
    eligibility: Eligibility = Eligibility.review
    icon: str | None = None
    text: Text = Field(default_factory=Text)
    notes: str = ""
    sources: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _id_snake(cls, v: str) -> str:
        if not ID_PATTERN.match(v):
            raise ValueError("id must be snake_case starting with a letter")
        return v

    @field_validator("entity_type_source_qids")
    @classmethod
    def _entity_type_qids(cls, values: list[str]) -> list[str]:
        if any(not QID_PATTERN.match(value) for value in values):
            raise ValueError("entity_type_source_qids must contain Wikidata QIDs")
        return sorted(set(values))

    @field_validator("start", "end")
    @classmethod
    def _year_range(cls, v: int | None) -> int | None:
        if v is not None and not (YEAR_MIN <= v <= YEAR_MAX):
            raise ValueError(f"year must be in [{YEAR_MIN}, {YEAR_MAX}]")
        return v

    @model_validator(mode="after")
    def _check(self) -> "Polity":
        if self.consolidation_status == "same_entity" and not self.consolidated_into:
            raise ValueError("a consolidated entity requires consolidated_into")
        if self.detail_of and self.detail_of == self.id:
            raise ValueError("detail_of cannot reference the entity's own id")
        if self.end is not None and self.end < self.start:
            raise ValueError("end must be >= start (or null for still-extant)")
        for year, w in self.weight_by_era.items():
            if not (1 <= w <= 10):
                raise ValueError(f"weight_by_era value {w} at year {year} must be in [1, 10]")
            if not (YEAR_MIN <= year <= YEAR_MAX):
                raise ValueError(f"weight_by_era year {year} out of range")
        return self


class Transition(BaseModel):
    id: str
    year: int = Field(ge=YEAR_MIN, le=YEAR_MAX)
    kind: Literal["split", "merge", "succession"]
    from_ids: list[str] = Field(alias="from", min_length=1)
    to_ids: list[str] = Field(alias="to", min_length=1)
    label: str
    notes: str = ""
    source_urls: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _transition_id(cls, value: str) -> str:
        if not ID_PATTERN.match(value):
            raise ValueError("transition id must be snake_case")
        return value

    @model_validator(mode="after")
    def _shape_matches_kind(self) -> "Transition":
        if self.kind == "split" and (len(self.from_ids) != 1 or len(self.to_ids) < 2):
            raise ValueError("a split requires one source and at least two targets")
        if self.kind == "merge" and (len(self.from_ids) < 2 or len(self.to_ids) != 1):
            raise ValueError("a merge requires at least two sources and one target")
        return self


class Period(BaseModel):
    id: str
    canonical_name: str
    kind: Literal["historical", "archaeological", "protohistorical", "prehistorical"]
    tier: Literal["macro_chapter", "regional_era", "period"] = "period"
    start: int
    end: int
    start_confidence: Confidence = Confidence.medium
    end_confidence: Confidence = Confidence.medium
    geography: Geography = Field(default_factory=Geography)
    broader_periods: list[str] = Field(default_factory=list)
    successors: list[str] = Field(default_factory=list)
    authority: str
    external_ids: dict[str, str] = Field(default_factory=dict)
    notes: str = ""
    source_urls: list[str] = Field(default_factory=list)
    # See Polity.linked_era_id -- same field, same purpose, for Civilizations
    # & Cultures lane periods (which never nest under an era via
    # broader_periods, so have no other era-color signal).
    linked_era_id: str | None = None
    # See Polity.linked_chapter_id -- same field, same purpose. Civilizations
    # & Cultures lane periods currently have no curated chapter path at all
    # (only the heuristic), so this is their only override.
    linked_chapter_id: str | None = None
    # See Polity.government_form -- same field, same purpose (e.g. a
    # "phase or aspect of" period like Ayyubid Sultanate benefits from
    # recording it was a sultanate). Not auto-populated for periods today;
    # editable manually.
    government_form: str | None = None
    # Whether this period belongs in the Civilizations & Cultures lane rather
    # than the ordinary Period row. Explicit, editable -- not derived from a
    # heuristic. Was seeded 2026-08-31 from
    # pipeline/build_explore_tree.py::_is_civilization_lane_period()'s old
    # fallback logic (True when authority == CIVILIZATION_BACKDROP_AUTHORITY,
    # a real signal, OR "civilization"/"culture" appears in canonical_name, a
    # name-substring guess) as a one-time starting point; from here on it's
    # curator-set only, checked first ahead of both signals. None means "not
    # yet reviewed" and falls back to that same old logic during the
    # transition -- see pipeline/seed_civilization_lane_flags.py.
    civilization_lane: bool | None = None

    @field_validator("id")
    @classmethod
    def _period_id(cls, value: str) -> str:
        if not ID_PATTERN.match(value):
            raise ValueError("period id must be snake_case starting with a letter")
        return value

    @field_validator("start", "end")
    @classmethod
    def _period_year_range(cls, value: int) -> int:
        if not YEAR_MIN <= value <= YEAR_MAX:
            raise ValueError(f"year must be in [{YEAR_MIN}, {YEAR_MAX}]")
        return value

    @model_validator(mode="after")
    def _period_dates(self) -> "Period":
        if self.end <= self.start:
            raise ValueError("period end must be after start")
        return self


class PeriodLink(BaseModel):
    period_id: str
    entity_id: str
    relation: Literal["context", "part_of_periodization", "phase_of", "defines"] = "context"
    evidence: Literal["explicit", "derived", "suggested"]
    confidence: Confidence
    source_urls: list[str] = Field(default_factory=list, min_length=1)
    notes: str = ""
