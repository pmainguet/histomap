import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
QID_PATTERN = re.compile(r"^Q\d+$")

YEAR_MIN = -10000
YEAR_MAX = 2100


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
    culture = "culture"
    people = "people"
    tribe = "tribe"
    archaeological_horizon = "archaeological_horizon"


class EntityRelationship(BaseModel):
    target: str
    kind: Literal[
        "political_parent",
        "political_successor",
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


class Polity(BaseModel):
    id: str
    canonical_name: str
    names: dict[str, str] = Field(default_factory=dict)
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    entity_type: EntityType = EntityType.polity
    entity_type_confidence: Confidence = Confidence.low
    entity_type_source_qids: list[str] = Field(default_factory=list)
    timeline_role: Literal["entity", "period", "both"] = "entity"
    relationships: list[EntityRelationship] = Field(default_factory=list)
    parent: str | None = None
    successors: list[str] = Field(default_factory=list)
    region: str | None = None
    culture_group: str | None = None
    geography: Geography = Field(default_factory=Geography)
    manual_overrides: list[str] = Field(default_factory=list)
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
        if self.end is not None and self.end <= self.start:
            raise ValueError("end must be > start (or null for still-extant)")
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
    source_urls: list[str] = Field(default_factory=list, min_length=1)

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
    relation: Literal["context", "part_of_periodization"] = "context"
    evidence: Literal["explicit", "derived", "suggested"]
    confidence: Confidence
    source_urls: list[str] = Field(default_factory=list, min_length=1)
    notes: str = ""
