import re
from enum import Enum

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


class ExternalIds(BaseModel):
    wikidata: str | None = None
    seshat: str | None = None

    @field_validator("wikidata")
    @classmethod
    def _qid(cls, v: str | None) -> str | None:
        if v is not None and not QID_PATTERN.match(v):
            raise ValueError("wikidata id must match ^Q\\d+$")
        return v


class Text(BaseModel):
    short_child_en: str = ""
    short_adult_en: str = ""
    long_en: str = ""


class Centroid(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Geography(BaseModel):
    continents: list[str] = Field(default_factory=list)
    present_countries: list[str] = Field(default_factory=list)
    centroid: Centroid | None = None
    confidence: Confidence | None = None

    @field_validator("present_countries")
    @classmethod
    def _country_codes(cls, values: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[A-Z]{2}", value) for value in values):
            raise ValueError("present_countries must contain ISO alpha-2 codes")
        return sorted(set(values))


class Polity(BaseModel):
    id: str
    canonical_name: str
    names: dict[str, str] = Field(default_factory=dict)
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    parent: str | None = None
    successors: list[str] = Field(default_factory=list)
    region: str | None = None
    culture_group: str | None = None
    geography: Geography = Field(default_factory=Geography)
    start: int
    end: int | None = None
    start_confidence: Confidence
    end_confidence: Confidence
    weight_by_era: dict[int, float] = Field(default_factory=dict)
    weight_imputed: bool = False
    prominence_score: float = Field(default=0, ge=0, le=100)
    visibility_tier: VisibilityTier = VisibilityTier.detailed
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
