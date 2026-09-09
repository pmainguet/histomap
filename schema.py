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
    # ROADMAP.md item 1 (9 September 2026) -- short_child_en/short_adult_en
    # (the adult/child reading-level split) retired: the toggle that would
    # have shown short_child_en lived in the old "/" timeline, retired 31
    # August 2026, and was never ported to /explore, so short_child_en had
    # no display surface at all; short_adult_en's one live use (the detail
    # panel's description fallback) is now long_en's job instead. Extra
    # keys on old YAML are silently dropped by Pydantic's extra="ignore",
    # same as every other retired field this session (parent,
    # visibility_tier, ...) -- no mass YAML rewrite needed.
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

    @staticmethod
    def _resolved_primary(
        primary: str | None, options: list[str], primary_field: str, options_field: str
    ) -> str | None:
        if primary is not None and primary not in options:
            raise ValueError(f"{primary_field} must also appear in {options_field}")
        if primary is None and len(options) == 1:
            return options[0]
        return primary

    @model_validator(mode="after")
    def _resolve_primaries(self) -> "Geography":
        self.primary_continent = self._resolved_primary(
            self.primary_continent, self.continents, "primary_continent", "continents"
        )
        self.primary_historical_region = self._resolved_primary(
            self.primary_historical_region,
            self.historical_regions,
            "primary_historical_region",
            "historical_regions",
        )
        return self


class Polity(BaseModel):
    id: str
    canonical_name: str
    names: dict[str, str] = Field(default_factory=dict)
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    # Added 2026-09-08 (ROADMAP.md item 6) -- Period/Event/Transition already
    # carried this field; Polity did not, so source_urls set in many
    # hand-authored polity YAML files (Aztec Empire, etc.) was silently
    # dropped by Pydantic's default extra="ignore" and never reached
    # data.json. Purely additive: existing records with no source_urls set
    # default to an empty list, unaffected.
    source_urls: list[str] = Field(default_factory=list)
    # ROADMAP.md item 3b (printable poster visualization) -- how many years
    # this polity's band takes to ease in/out at its start/end, instead of
    # snapping to full width instantly. Both default to None, meaning the
    # poster renderer's own default (15 years) applies; set a larger value
    # only to hand-author a genuinely gradual historical decline (a slow
    # multi-decade collapse) rather than an ordinary boundary taper. See
    # docs/plans/2026-09-08-poster-visualization-design.md.
    fade_in_years: int | None = None
    fade_out_years: int | None = None
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
    eligibility: Eligibility = Eligibility.review
    # ROADMAP.md item 1 (9 September 2026) -- retired: never rendered
    # anywhere in /explore (grepped web/*.js, zero references), and only
    # one polity in the whole dataset ever had it set. Extra keys on old
    # YAML are silently dropped by extra="ignore".
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
    # Whether this period belongs in the top-level Epoch lane (e.g.
    # Holocene) rather than the ordinary chapter/era-nested Period row.
    # Explicit, curator-set only -- no name-heuristic fallback like
    # civilization_lane has, since there's no pre-existing corpus of
    # un-flagged epoch records to backfill a guess for (this field and its
    # first users, Holocene/Greenlandian/Northgrippian/Meghalayan, were all
    # introduced together, 8 September 2026). See
    # pipeline/build_explore_tree.py::_is_epoch_lane_period().
    epoch_lane: bool = False
    # Set only when this period was generated by a save_timeline_role()
    # promotion (server/app.py) -- the id of the source polity. None for
    # every hand-authored period and for the unrelated Civilizations &
    # Cultures lane auto-generation. Turns the implicit "<polity_id>_period"
    # filename convention into an explicit, schema-validated back-reference
    # -- see docs/plans/2026-09-05-polity-period-conversion-friction-design.md.
    promoted_from: str | None = None
    # See Polity.detail_of -- same field, same purpose, for periods: a
    # period can be a detail of another period (e.g. Initial Jomon -> Jomon
    # period) or of a polity. The reverse is NOT allowed -- a polity's own
    # detail_of stays restricted to polity targets only (see
    # validate_entity_relationships in build.py). Found live, 7 September
    # 2026.
    detail_of: str | None = None
    # See Polity.deprecated -- same field, same purpose: a generic bucket
    # preserving old field values under their original names for records
    # migrated away from a retired mechanism. First user: `kind` (retired 7
    # September 2026 -- see pipeline/migrate_period_kind_to_deprecated.py),
    # moved here rather than discarded so the old historical/archaeological/
    # protohistorical/prehistorical classification isn't lost.
    deprecated: dict[str, Any] | None = None

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
        if self.detail_of and self.detail_of == self.id:
            raise ValueError("detail_of cannot reference the entity's own id")
        return self


class PeriodLink(BaseModel):
    period_id: str
    entity_id: str
    relation: Literal["context", "part_of_periodization", "phase_of", "defines"] = "context"
    evidence: Literal["explicit", "derived", "suggested"]
    confidence: Confidence
    source_urls: list[str] = Field(default_factory=list, min_length=1)


class EventBound(BaseModel):
    """One period (any Period.tier -- macro_chapter/regional_era/period all
    qualify) an Event starts or ends. A list on Event.bounds, not a single
    value -- the same real event is routinely the shared boundary between
    two adjacent periods (it ends one, starts the next)."""
    target: str
    edge: Literal["start", "end"]


class Event(BaseModel):
    """ROADMAP.md item 5: a dated historical event, distinct from Transition
    (which stays exactly what it already is -- a polity-to-polity
    succession/split/merge fact driving the transition arrows). An Event is
    broader: not necessarily a polity handover, and can attach two
    independent, optional ways -- see
    docs/plans/2026-09-07-events-lane-design.md for the full design:

    - `detail_of`: Polity ids (civilization/culture/etc. are all
      entity_type values on Polity, not a separate model) this event is a
      detail of -- rendered nested under that entity's existing detail_of
      children, the same recursive mechanism polities/periods already use.
    - `bounds`: periods this event starts or ends -- rendered in one
      shared Events lane on /explore (positioned by `year`), regardless of
      which Period.tier it bounds.

    Both are optional and independent; a real event can be neither (not
    yet placed), either, or both at once.

    A single `year`, not a start/end range like Period/Polity -- matches
    Transition's own existing shape (also a single `year`), and a
    multi-year event (e.g. "Bronze Age Collapse") just picks its
    conventionally-cited year, same tradeoff Transition already accepts."""
    id: str
    canonical_name: str
    year: int
    detail_of: list[str] = Field(default_factory=list)
    bounds: list[EventBound] = Field(default_factory=list)
    # Gates visibility, unlike Polity/Period's own eligibility (which
    # never blocks /explore -- "publish everything, check later"): an
    # event's whole point is confirming detail_of/bounds actually points
    # at the right place before it renders anywhere, so `review` (the
    # default) is excluded from events.json until a reviewer accepts it.
    # See build.py's publication filter.
    eligibility: Eligibility = Eligibility.review
    external_ids: ExternalIds = Field(default_factory=ExternalIds)
    authority: str
    notes: str = ""
    source_urls: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _event_id(cls, value: str) -> str:
        if not ID_PATTERN.match(value):
            raise ValueError("event id must be snake_case starting with a letter")
        return value

    @field_validator("year")
    @classmethod
    def _event_year_range(cls, value: int) -> int:
        if not YEAR_MIN <= value <= YEAR_MAX:
            raise ValueError(f"year must be in [{YEAR_MIN}, {YEAR_MAX}]")
        return value

    @field_validator("bounds")
    @classmethod
    def _bounds_no_duplicate_targets(cls, value: list[EventBound]) -> list[EventBound]:
        seen = {(bound.target, bound.edge) for bound in value}
        if len(seen) != len(value):
            raise ValueError("bounds must not repeat the same (target, edge) pair")
        return value
