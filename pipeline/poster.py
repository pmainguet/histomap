"""Printable poster visualization (ROADMAP.md item 3b): renders an SVG of
polities as organic flowing bands, in the style of the 1931 Histomap of
World History. See docs/plans/2026-09-08-poster-visualization-design.md
for the full design and the mockup it was brainstormed from.

This module is split into a pure, unit-testable core (taper math, lineage
grouping, stacking, path building -- no file I/O) and a thin integration
layer (render_poster_svg) that loads the published build artifacts and
calls into the core. server/app.py's /api/poster.svg endpoint is the only
caller of render_poster_svg."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_FADE_YEARS = 15
TOP_N_POLITIES = 60
WIDTH_BASE = 3.0
WIDTH_PER_PROMINENCE = 5.1
# prominence_score is 0-100 (ranks polities against each other for display,
# see server/app.py); rescaled to roughly the 1-10 range width_px expects,
# so a polity with no per-era weight data still gets a sensible width.
PROMINENCE_SCORE_MAX = 100.0
PROMINENCE_SCALE_MIN = 1.0
PROMINENCE_SCALE_MAX = 10.0

Style = Literal["authentic", "stacked"]
# "prominence" (default): every polity gets a flat width across its whole
# span, from its prominence_score -- today's only behavior. "population":
# Civilizations & Cultures entities with a HYDE-derived population curve
# (see pipeline/extract_hyde_by_civilization.py) get a real multi-keyframe
# width that grows and shrinks with their own population over time;
# everything else (no curve on file) falls back to the flat prominence
# width, same as "prominence" mode -- see _load_population_keyframes/
# _build_polities.
WidthSource = Literal["prominence", "population"]


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def width_px(prominence: float) -> float:
    return WIDTH_BASE + prominence * WIDTH_PER_PROMINENCE


def scale_prominence_score(prominence_score: float) -> float:
    """Rescale a 0-100 prominence_score to the ~1-10 range width_px
    expects, for a polity with no per-era weight curve of its own."""
    fraction = max(0.0, min(1.0, prominence_score / PROMINENCE_SCORE_MAX))
    return PROMINENCE_SCALE_MIN + fraction * (PROMINENCE_SCALE_MAX - PROMINENCE_SCALE_MIN)


def scale_population(population: float, min_log: float, max_log: float) -> float:
    """Log-scale a population count to the same ~1-10 range width_px
    expects -- mirrors the /explore Population lane's own log-scale
    treatment (web/explore_timeline.js's populationHeight): population
    spans orders of magnitude across a civilization's lifespan, so a
    linear scale would flatten every early-era sample to a sliver next to
    a late one. min_log/max_log come from *this one entity's own* curve
    (see _load_population_keyframes), not the whole dataset -- a single
    shared global range is dominated by whichever open-ended entity's
    modern annual HYDE tail reaches the highest (tens of millions), which
    squashes every other entity's own, much narrower, real growth into a
    barely-visible sliver of the 1-10 scale. Per-entity scaling also
    matches the extraction script's own documented caveat that *absolute*
    cross-entity population comparison isn't reliable anyway (each
    entity's country-mask overcounting bias differs by how much of its
    present_countries' modern territory it actually occupied) -- this
    makes every band's *own* width responsive to its *own* history
    instead, which is what "draw the width of the civilization lane"
    asked for. Stable across different poster year-range selections for
    the same entity (min_log/max_log come from that entity's whole cached
    curve, not just the requested window)."""
    if population <= 0:
        return PROMINENCE_SCALE_MIN
    if max_log <= min_log:
        return PROMINENCE_SCALE_MAX
    fraction = (math.log10(population) - min_log) / (max_log - min_log)
    fraction = max(0.0, min(1.0, fraction))
    return PROMINENCE_SCALE_MIN + fraction * (PROMINENCE_SCALE_MAX - PROMINENCE_SCALE_MIN)


def taper_factor(year: float, boundary_year: float, total_years: float, direction: Literal["in", "out"]) -> float:
    """Symmetric pan-in/pan-out: ramps 0->1 (direction="in") or 1->0
    ("out") over a window straddling boundary_year -- 2/3 of total_years
    before it, 1/3 after -- so the official date sits inside the ramp
    rather than at either edge of it. Confirmed timing (10-before/5-after
    for the default 15-year window); a longer total_years just scales the
    same shape, for a genuinely gradual historical decline.

    total_years <= 0 means an instantaneous edge -- no ramp at all."""
    if total_years <= 0:
        if direction == "in":
            return 1.0 if year >= boundary_year else 0.0
        return 1.0 if year <= boundary_year else 0.0
    pre = total_years * (2 / 3)
    post = total_years * (1 / 3)
    u = (year - (boundary_year - pre)) / (pre + post)
    s = smoothstep(u)
    return s if direction == "in" else 1 - s


@dataclass
class Keyframe:
    """year -> a value already scaled to width_px's ~1-10 input range.
    `prominence` is the name from this module's original (and still
    default) data source, but any PosterPolity can carry more than the
    flat 2-keyframe curve _build_polities gives a prominence_score-only
    polity -- see _load_population_keyframes for the other source, a real
    multi-point curve from HYDE-derived population data."""
    year: int
    prominence: float


@dataclass
class PosterPolity:
    """One polity as the poster renderer sees it -- a canonical_name, an
    id, and a prominence curve over exactly its own active years. x is
    assigned later, by the layout pass (independent per-lineage column for
    "authentic", computed from the shared-pool stack for "stacked")."""
    id: str
    label: str
    keyframes: list[Keyframe]
    fade_in_years: int | None = None
    fade_out_years: int | None = None
    lineage_id: str = field(default="")

    def __post_init__(self) -> None:
        if len(self.keyframes) < 2:
            raise ValueError(f"polity {self.id} needs at least 2 keyframes")
        if not self.lineage_id:
            self.lineage_id = self.id

    @property
    def start(self) -> int:
        return self.keyframes[0].year

    @property
    def end(self) -> int:
        return self.keyframes[-1].year

    def natural_prominence_at(self, year: int) -> float:
        clamped = max(self.start, min(self.end, year))
        for a, b in zip(self.keyframes, self.keyframes[1:]):
            if a.year <= clamped <= b.year:
                t = (clamped - a.year) / ((b.year - a.year) or 1)
                return a.prominence + (b.prominence - a.prominence) * t
        return self.keyframes[-1].prominence

    def taper(self, year: int, max_year_no_fade_out: int | None = None) -> float:
        """The pan-in/pan-out factor (0-1) at `year`, independent of the
        natural prominence curve -- see effective_prominence_at."""
        fade_in = self.fade_in_years if self.fade_in_years is not None else DEFAULT_FADE_YEARS
        skip_fade_out = max_year_no_fade_out is not None and self.end >= max_year_no_fade_out
        fade_out = 0 if skip_fade_out else (
            self.fade_out_years if self.fade_out_years is not None else DEFAULT_FADE_YEARS
        )
        factor = taper_factor(year, self.start, fade_in, "in") if fade_in > 0 else (1.0 if year >= self.start else 0.0)
        if fade_out > 0:
            factor *= taper_factor(year, self.end, fade_out, "out")
        return factor

    def effective_prominence_at(self, year: int, max_year_no_fade_out: int | None = None) -> float:
        return self.natural_prominence_at(year) * self.taper(year, max_year_no_fade_out)


def compute_lineages(polities: list[PosterPolity], edges: list[tuple[str, str]]) -> None:
    """Union-find over successor/detail_of edges among exactly the given
    polities (edges to a polity outside the selected set are ignored --
    it isn't on the poster, so it can't anchor a lineage). Sets each
    polity's lineage_id to its connected component's representative,
    in place."""
    parent = {p.id: p.id for p in polities}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    ids = {p.id for p in polities}
    for a, b in edges:
        if a in ids and b in ids:
            union(a, b)
    for p in polities:
        p.lineage_id = find(p.id)


def order_lineages(polities: list[PosterPolity]) -> list[str]:
    """Lineage ids, left-to-right, ordered by each lineage's earliest
    polity start year."""
    earliest: dict[str, int] = {}
    for p in polities:
        current = earliest.get(p.lineage_id)
        if current is None or p.start < current:
            earliest[p.lineage_id] = p.start
    return sorted(earliest, key=lambda lineage_id: earliest[lineage_id])


def select_top_polities(
    candidates: list[PosterPolity],
    start_year: int,
    end_year: int,
    prominence_score: dict[str, float],
    top_n: int = TOP_N_POLITIES,
    priority_ids: frozenset[str] = frozenset(),
) -> list[PosterPolity]:
    """Polities overlapping [start_year, end_year], ranked by
    prominence_score, capped to top_n. Overlap, not full containment --
    a polity that starts before start_year or ends after end_year still
    shows (tapered at whichever edge falls inside the window).

    priority_ids (used by width_source="population" -- see
    _build_polities) go in ahead of the prominence ranking, as long as
    they overlap the window: a Civilizations & Cultures entity's own
    prominence_score rarely if ever wins a top_n spot against major world
    empires, so without this, "population" mode would select the exact
    same 60 polities as "prominence" mode and render identically -- the
    whole point of the mode is to actually show these entities' width
    tracking their own population. The remaining top_n - len(priority)
    slots still go to the highest-prominence remaining candidates, same
    as before; empty (the default) leaves this identical to the prior
    behavior."""
    overlapping = [p for p in candidates if p.start <= end_year and p.end >= start_year]
    priority = [p for p in overlapping if p.id in priority_ids]
    rest = [p for p in overlapping if p.id not in priority_ids]
    priority.sort(key=lambda p: prominence_score.get(p.id, 0.0), reverse=True)
    rest.sort(key=lambda p: prominence_score.get(p.id, 0.0), reverse=True)
    return (priority + rest)[:top_n]


@dataclass
class StackedSample:
    year: int
    x_left: float
    x_right: float


def stack_polities(
    polities: list[PosterPolity],
    lineage_order: list[str],
    year_range: tuple[int, int],
    step: int,
    canvas_x0: float,
    canvas_x1: float,
    epsilon: float = 0.15,
) -> dict[str, list[StackedSample]]:
    """The "100% Stacked" style's core: at every sampled year, every
    active polity's width is its share of total effective prominence
    among everything active that year, and all active polities together
    always fill [canvas_x0, canvas_x1] edge-to-edge. Order within a year
    is lineage first (by lineage_order), then by each polity's own start
    year within its lineage -- keeps a lineage's own polities contiguous
    and stable left-to-right as they succeed one another."""
    lineage_rank = {lineage_id: i for i, lineage_id in enumerate(lineage_order)}
    start_year, end_year = year_range
    samples: dict[str, list[StackedSample]] = {p.id: [] for p in polities}
    max_year_no_fade_out = end_year

    def fade_reach(years: int) -> float:
        return years * (2 / 3)

    year = start_year
    while year <= end_year:
        active = []
        for p in polities:
            fade_in = p.fade_in_years if p.fade_in_years is not None else DEFAULT_FADE_YEARS
            fade_out = p.fade_out_years if p.fade_out_years is not None else DEFAULT_FADE_YEARS
            window_start = p.start - fade_reach(fade_in)
            window_end = p.end + fade_out * (1 / 3) if p.end < max_year_no_fade_out else p.end
            if window_start <= year <= window_end:
                active.append(p)
        if active:
            active.sort(key=lambda p: (lineage_rank.get(p.lineage_id, len(lineage_rank)), p.start))
            proms = [max(p.effective_prominence_at(year, max_year_no_fade_out), epsilon) for p in active]
            total = sum(proms)
            cx = canvas_x0
            for p, prom in zip(active, proms):
                w = (prom / total) * (canvas_x1 - canvas_x0)
                samples[p.id].append(StackedSample(year, cx, cx + w))
                cx += w
        year += step
    return samples


def path_from_stacked_samples(samples: list[StackedSample], year_to_y) -> str:
    if len(samples) < 2:
        return ""
    left = [f"{s.x_left:.1f},{year_to_y(s.year):.1f}" for s in samples]
    right = [f"{s.x_right:.1f},{year_to_y(s.year):.1f}" for s in reversed(samples)]
    return f"M {' L '.join(left)} L {' L '.join(right)} Z"


def _hash01(seed: float) -> float:
    x = math.sin(seed * 999.1) * 10000
    return x - int(x)


_JITTER_CONTROL_POINTS = 7  # per whole band, regardless of its span or how
# finely `step` samples the taper curve -- matches the mockup's own
# "linear-jitter" mode, which subdivided each keyframe interval into only
# 5-6 steps. Jittering independently at every fine sample instead (one
# random offset every `step` years, for potentially hundreds of points on
# a centuries-long band) produced a dense, regular sawtooth -- not the
# sparse, organic hand-drawn wobble intended. A handful of widely-spaced
# control offsets, smoothly interpolated between, reads as hand-drawn;
# independent noise at every sample point reads as corrugated cardboard.


def _band_jitter(lo: int, hi: int, seed: int, amp: float, year: int) -> float:
    if amp <= 0 or hi <= lo:
        return 0.0
    span = hi - lo
    t = (year - lo) / span * (_JITTER_CONTROL_POINTS - 1)
    i = max(0, min(_JITTER_CONTROL_POINTS - 2, int(t)))
    local_t = smoothstep(t - i)
    a = (_hash01(seed * 71 + i) - 0.5) * 2 * amp
    b = (_hash01(seed * 71 + i + 1) - 0.5) * 2 * amp
    return a + (b - a) * local_t


def authentic_path(
    polity: PosterPolity,
    lineage_x: float,
    year_range: tuple[int, int],
    step: int,
    year_to_y,
    jitter_amp: float = 3.0,
) -> str:
    """Style "authentic": a polity's own band, centered on its lineage's
    fixed x, independent of every other lineage -- the counterpart to
    stack_polities for the non-stacked style. Small deterministic jitter
    on the half-width, echoing the 1931 original's hand-drawn edges."""
    start_year, end_year = year_range
    max_year_no_fade_out = end_year
    lo = max(start_year, polity.start)
    hi = min(end_year, polity.end)
    if lo >= hi:
        return ""
    years = list(range(lo, hi, step)) + [hi]
    seed = hash(polity.id) % 100000
    left, right = [], []
    for year in years:
        prom = polity.effective_prominence_at(year, max_year_no_fade_out)
        hw = width_px(prom) + _band_jitter(lo, hi, seed, jitter_amp, year)
        hw = max(2.0, hw)
        y = year_to_y(year)
        left.append(f"{lineage_x - hw:.1f},{y:.1f}")
        right.append(f"{lineage_x + hw:.1f},{y:.1f}")
    right.reverse()
    return f"M {' L '.join(left)} L {' L '.join(right)} Z"


# -- Integration layer: loads the published build artifacts and renders a
# complete SVG document. Everything above this line is pure and
# unit-tested without touching the filesystem; this part is exercised by
# tests/test_poster.py's smoke tests and, live, by /api/poster.svg.

_PALETTE = [
    ("#c8503e", "#7a2c20"), ("#d1a52c", "#7c5d16"), ("#3f6b3a", "#213a1e"),
    ("#5c4083", "#2e2046"), ("#3d7a8c", "#1f4550"), ("#a8664a", "#5c3324"),
    ("#6b8c3f", "#37481f"), ("#8c5c7a", "#472e3d"),
]
_INK = "#241a12"
_PAPER = "#e9dcb9"
_EVENT_COLOR = "#9c6a12"
_MARGIN_X0 = 60.0
_MARGIN_TOP = 90.0
_MARGIN_BOTTOM = 40.0
_GUTTER_LANE_W = 26.0
_GUTTER_GAP = 4.0
_LINEAGE_PITCH = 90.0
_STACKED_CONTENT_W = 640.0


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_population_keyframes(root: Path) -> dict[str, list[Keyframe]]:
    """Loads population_by_civilization.json (build.py's copy-through of
    pipeline/extract_hyde_by_civilization.py's cached extraction -- same
    pattern as population_by_continent.json), keyed by entity id, each
    value a real multi-point curve rather than the flat 2-keyframe curve
    _build_polities gives a prominence_score-only polity. Returns {} if
    the file doesn't exist yet on this machine or is empty -- callers
    treat that exactly like "no curve for this entity", same graceful
    fallback web/explore.js's buildPopulationSeries already uses for the
    /explore Population lane. An entity with fewer than 2 sample years in
    its range (PosterPolity needs >= 2 keyframes) is skipped here, not
    passed through as an unusable single-point curve. Each entity is
    log-scaled against its *own* min/max population (see scale_population's
    own docstring for why, not a single range shared across every entity)."""
    path = root / "population_by_civilization.json"
    if not path.exists():
        return {}
    rows = _load_json(path)
    if not rows:
        return {}
    by_entity: dict[str, list[tuple[int, int]]] = {}
    for row in rows:
        by_entity.setdefault(row["entity_id"], []).append((row["year"], row["population"]))
    keyframes: dict[str, list[Keyframe]] = {}
    for entity_id, points in by_entity.items():
        if len(points) < 2:
            continue
        logs = [math.log10(population) for _, population in points if population > 0]
        if not logs:
            continue
        min_log, max_log = min(logs), max(logs)
        keyframes[entity_id] = [
            Keyframe(year, scale_population(population, min_log, max_log)) for year, population in sorted(points)
        ]
    return keyframes


def _build_polities(
    raw_polities: list[dict],
    start_year: int,
    end_year: int,
    top_n: int = TOP_N_POLITIES,
    population_keyframes: dict[str, list[Keyframe]] | None = None,
) -> tuple[list[PosterPolity], dict[str, float]]:
    candidates = []
    prominence_score: dict[str, float] = {}
    for record in raw_polities:
        start, end = record.get("start"), record.get("end")
        if start is None:
            continue
        effective_end = end if end is not None else end_year
        if effective_end <= start:
            continue
        score = record.get("prominence_score") or 0.0
        prominence_score[record["id"]] = score
        # A population curve for this entity (see _load_population_keyframes)
        # replaces the flat prominence-based width when width_source=
        # "population" was requested -- render_poster_svg only passes
        # population_keyframes at all in that mode, so this is unchanged
        # (flat 2-keyframe) behavior whenever it's None/empty/missing this
        # entity. Flat-extended to the record's own [start, effective_end]
        # at either end where the curve itself starts later or ends earlier
        # (HYDE's sample years don't necessarily land exactly on this
        # entity's own recorded start/end) -- keeps PosterPolity.start/.end
        # (== keyframes[0]/[-1].year) matching the record, not the curve's
        # own narrower coverage, so overlap checks below stay accurate.
        curve = (population_keyframes or {}).get(record["id"])
        if curve:
            keyframes = list(curve)
            if keyframes[0].year > start:
                keyframes.insert(0, Keyframe(start, keyframes[0].prominence))
            if keyframes[-1].year < effective_end:
                keyframes.append(Keyframe(effective_end, keyframes[-1].prominence))
        else:
            keyframes = [Keyframe(start, scale_prominence_score(score)), Keyframe(effective_end, scale_prominence_score(score))]
        candidates.append(
            PosterPolity(
                id=record["id"],
                label=record["canonical_name"],
                keyframes=keyframes,
                fade_in_years=record.get("fade_in_years"),
                fade_out_years=record.get("fade_out_years"),
            )
        )
    priority_ids = frozenset((population_keyframes or {}).keys())
    selected = select_top_polities(candidates, start_year, end_year, prominence_score, top_n, priority_ids=priority_ids)
    edges = []
    by_id = {record["id"]: record for record in raw_polities}
    for p in selected:
        record = by_id[p.id]
        for successor_id in record.get("successors") or []:
            edges.append((p.id, successor_id))
        if record.get("detail_of"):
            edges.append((p.id, record["detail_of"]))
    compute_lineages(selected, edges)
    return selected, prominence_score


def _rotated_label(x: float, y: float, text: str, size: float, color: str) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="start" '
        f'transform="rotate(-90, {x:.1f}, {y:.1f})" '
        f'style="font:700 {size}px sans-serif; fill:{color}; letter-spacing:.08em;">{_esc(text)}</text>'
    )


def render_poster_svg(
    style: Style, start_year: int, end_year: int, root: Path = ROOT, width_source: WidthSource = "prominence"
) -> str:
    """Renders the poster as a complete, standalone SVG document string.
    style: "authentic" (independent per-lineage columns) or "stacked"
    (100% of the canvas width, shared proportionally every year).
    width_source: "prominence" (default, every band flat-width across its
    span) or "population" (Civilizations & Cultures entities with a HYDE-
    derived curve on file get a real width that tracks their own
    population over time -- see _load_population_keyframes; everything
    else still falls back to the flat prominence width). root defaults to
    the real repo root; server/app.py's create_app(root=...) passes its
    own root through here, so a test server reads its isolated
    temp-directory build artifacts instead of the real ones.

    Known v1 simplifications (see docs/plans/2026-09-08-poster-visualization-
    design.md): no per-lineage civilization/region background wash yet;
    palette is a fixed rotation by lineage index, not tied to region
    semantics; labels are placed at each polity's own midpoint year without
    the mockup's font-size-to-available-width capping."""
    if end_year <= start_year:
        raise ValueError("end_year must be after start_year")

    raw_polities = _load_json(root / "data.json")
    raw_periods = _load_json(root / "periods.json")
    raw_events = _load_json(root / "events.json")
    population_keyframes = _load_population_keyframes(root) if width_source == "population" else {}
    polities, _ = _build_polities(raw_polities, start_year, end_year, population_keyframes=population_keyframes)
    lineage_order = order_lineages(polities) if polities else []

    height = max(600.0, min(4000.0, (end_year - start_year) * 1.4))
    y0, y1 = _MARGIN_TOP, height - _MARGIN_BOTTOM

    def year_to_y(year: float) -> float:
        return y0 + (year - start_year) / (end_year - start_year) * (y1 - y0)

    parts: list[str] = []
    content_x0 = _MARGIN_X0

    if style == "stacked":
        content_x1 = content_x0 + _STACKED_CONTENT_W
        step = max(1, (end_year - start_year) // 400)
        samples = stack_polities(polities, lineage_order, (start_year, end_year), step, content_x0, content_x1)
        lineage_color = {lineage_id: _PALETTE[i % len(_PALETTE)] for i, lineage_id in enumerate(lineage_order)}
        for p in polities:
            fill, line = lineage_color.get(p.lineage_id, _PALETTE[0])
            d = path_from_stacked_samples(samples[p.id], year_to_y)
            if d:
                parts.append(f'<path d="{d}" fill="{fill}" stroke="{line}" stroke-width="1.1"/>')
        for p in polities:
            pts = samples[p.id]
            if not pts:
                continue
            widest = max(pts, key=lambda s: s.x_right - s.x_left)
            mid_x = (widest.x_left + widest.x_right) / 2
            hw = (widest.x_right - widest.x_left) / 2
            fs = max(7.0, min(15.0, hw * 0.55))
            parts.append(
                f'<text x="{mid_x:.1f}" y="{year_to_y(widest.year) + fs * 0.32:.1f}" '
                f'text-anchor="middle" style="font:700 {fs:.1f}px serif; fill:{_INK};">{_esc(p.label)}</text>'
            )
    else:
        content_x1 = content_x0 + max(_LINEAGE_PITCH, len(lineage_order) * _LINEAGE_PITCH)
        lineage_x = {
            lineage_id: content_x0 + (i + 0.5) * _LINEAGE_PITCH for i, lineage_id in enumerate(lineage_order)
        }
        lineage_color = {lineage_id: _PALETTE[i % len(_PALETTE)] for i, lineage_id in enumerate(lineage_order)}
        step = max(1, (end_year - start_year) // 300)
        for p in polities:
            fill, line = lineage_color.get(p.lineage_id, _PALETTE[0])
            x = lineage_x.get(p.lineage_id, content_x0)
            d = authentic_path(p, x, (start_year, end_year), step, year_to_y)
            if d:
                parts.append(f'<path d="{d}" fill="{fill}" stroke="{line}" stroke-width="1.1"/>')
                mid_year = max(start_year, min(end_year, (p.start + p.end) // 2))
                fs = max(7.0, min(15.0, width_px(p.effective_prominence_at(mid_year, end_year)) * 0.5))
                parts.append(
                    f'<text x="{x:.1f}" y="{year_to_y(mid_year) + fs * 0.32:.1f}" '
                    f'text-anchor="middle" style="font:700 {fs:.1f}px serif; fill:{_INK};">{_esc(p.label)}</text>'
                )

    # Year axis, both margins.
    tick_step = max(50, round((end_year - start_year) / 12 / 50) * 50)
    year = start_year - (start_year % tick_step)
    while year <= end_year:
        if start_year <= year <= end_year:
            y = year_to_y(year)
            label = f"{-year} BC" if year < 0 else f"{year} AD"
            parts.append(f'<line x1="{content_x0 - 4}" x2="{content_x1 + 4}" y1="{y:.1f}" y2="{y:.1f}" stroke="{_INK}" stroke-width="0.5" opacity="0.35"/>')
            parts.append(f'<text x="{content_x0 - 8:.1f}" y="{y - 3:.1f}" text-anchor="end" style="font:700 9px sans-serif; fill:{_INK};">{label}</text>')
        year += tick_step

    # Events -- ticks in the left margin.
    visible_events = [e for e in raw_events if start_year <= e["year"] <= end_year]
    for event in visible_events:
        y = year_to_y(event["year"])
        parts.append(f'<circle cx="{content_x0 - 20:.1f}" cy="{y:.1f}" r="3" fill="{_EVENT_COLOR}"/>')
        parts.append(f'<text x="{content_x0 - 14:.1f}" y="{y + 3:.1f}" style="font:700 italic 7.5px sans-serif; fill:{_EVENT_COLOR};">{_esc(event["canonical_name"])}</text>')

    # Right-hand gutter: Epoch + Chapter (both genuinely global tiers,
    # unlike Era/Period -- see design doc) + Events.
    epochs = [p for p in raw_periods if p.get("epoch_lane")]
    chapters = [p for p in raw_periods if p.get("tier") == "macro_chapter"]
    g0 = content_x1 + 14
    x_epoch, x_chapter, x_events = g0, g0 + _GUTTER_LANE_W + _GUTTER_GAP, g0 + 2 * (_GUTTER_LANE_W + _GUTTER_GAP)
    epoch_fill, chapter_fill, events_fill = "#c9bd9c", "#d7b98a", "#efe6cf"
    for x, fill, label, records in (
        (x_epoch, epoch_fill, "EPOCH", epochs),
        (x_chapter, chapter_fill, "CHAPTER", chapters),
    ):
        parts.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{_GUTTER_LANE_W}" height="{y1 - y0:.1f}" fill="{fill}" stroke="{_INK}" stroke-width="0.6"/>')
        for record in records:
            r_start, r_end = max(start_year, record["start"]), min(end_year, record["end"])
            if r_end <= r_start:
                continue
            ry0, ry1 = year_to_y(r_start), year_to_y(r_end)
            if record is not records[0] or len(records) > 1:
                parts.append(f'<line x1="{x:.1f}" x2="{x + _GUTTER_LANE_W:.1f}" y1="{ry0:.1f}" y2="{ry0:.1f}" stroke="{_INK}" stroke-width="0.7"/>')
            mid = (ry0 + ry1) / 2
            parts.append(_rotated_label(x + _GUTTER_LANE_W / 2 + 4, mid, record["canonical_name"], 8.5, _INK))
        parts.append(_rotated_label(x + _GUTTER_LANE_W / 2 + 4, y0 - 6, label, 8, _INK))
    parts.append(f'<rect x="{x_events:.1f}" y="{y0:.1f}" width="{_GUTTER_LANE_W}" height="{y1 - y0:.1f}" fill="{events_fill}" stroke="{_INK}" stroke-width="0.6"/>')
    parts.append(_rotated_label(x_events + _GUTTER_LANE_W / 2 + 4, y0 - 6, "EVENTS", 8, _EVENT_COLOR))
    for event in visible_events:
        y = year_to_y(event["year"])
        parts.append(f'<circle cx="{x_events + _GUTTER_LANE_W / 2:.1f}" cy="{y:.1f}" r="3" fill="{_EVENT_COLOR}"/>')

    total_width = x_events + _GUTTER_LANE_W + 20
    body = "\n".join(parts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_width:.1f} {height:.1f}">'
        f'<rect x="0" y="0" width="{total_width:.1f}" height="{height:.1f}" fill="{_PAPER}"/>'
        f'{body}'
        f'</svg>'
    )
