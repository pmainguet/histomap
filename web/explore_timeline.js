function formatYear(year) {
  if (year === null || year === undefined) return "present";
  return year < 0 ? `${Math.abs(year).toLocaleString()} BCE` : `${year.toLocaleString()} CE`;
}

function svgEl(name, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}

let clipIdCounter = 0;
const LABEL_MIN_WIDTH = 30;

const ESTIMATED_CHAR_WIDTH = 6; // px per character at the .68rem label font -- no live text measurement, just a reasonable estimate
const LABEL_PADDING = 8;

// Returns a getRange function (for packIntoLanes) that accounts for label
// width, not just band width, so labels wider than their band don't
// visually collide with the next item's label in the same lane.
// `getLabel` defaults to canonical_name, but callers showing a
// country-suffixed label (see itemDisplayLabel) pass it in so the
// footprint accounts for the longer displayed text, not just the bare name.
function labelAwareFootprint(scale, getLabel = (item) => item.canonical_name) {
  return (item) => {
    const bandStart = scale.x(item.start);
    const bandWidth = scale.width(item.start, item.end);
    const labelWidth = getLabel(item).length * ESTIMATED_CHAR_WIDTH + LABEL_PADDING;
    const footprintWidth = Math.max(bandWidth, labelWidth);
    return { start: bandStart, end: bandStart + footprintWidth };
  };
}

function bandRect(svg, { x, y, width, height, cls, title, label, onZoom, fill }) {
  const rect = svgEl("rect", { x, y, width, height, class: cls, rx: 2 });
  // Era-linked color coding (see eraColor) is data-driven -- one color per
  // era id, not a fixed set of CSS classes -- so it's applied as an inline
  // style, which naturally overrides the class-based `fill` in styles.css
  // while leaving that class's fill-opacity/stroke-dasharray (the curated
  // vs heuristic placement signal) untouched.
  if (fill) rect.style.fill = fill;
  if (onZoom) {
    rect.classList.add("zoomable");
    // Click opens the detail panel (kind/id identify which record), not an
    // immediate zoom -- matches "/"'s pattern, where zoom is a button
    // inside the panel, not the click itself. See explore_details.js.
    rect.addEventListener("click", () => onZoom.handler(onZoom.kind, onZoom.id, onZoom.start, onZoom.end));
  }
  const titleEl = svgEl("title");
  titleEl.textContent = title;
  rect.append(titleEl);
  svg.append(rect);
  if (label && width >= LABEL_MIN_WIDTH) {
    const clipId = `hierarchy-clip-${clipIdCounter++}`;
    const clipPath = svgEl("clipPath", { id: clipId });
    clipPath.append(svgEl("rect", { x, y, width, height }));
    svg.append(clipPath);
    const textEl = svgEl("text", {
      x: x + 4, y: y + height / 2 + 4, class: "hierarchy-band-label", "clip-path": `url(#${clipId})`,
    });
    textEl.textContent = label;
    svg.append(textEl);
  }
  return rect;
}

// Solid line between tier row-blocks (Chapter/Era/Period/Civilizations &
// Cultures/Polities) -- a major structural boundary.
function drawSeparator(svg, width, y) {
  svg.append(svgEl("line", { x1: 0, x2: width, y1: y, y2: y, class: "hierarchy-row-separator" }));
}

// Dashed line between region/continent sub-groups *within* one tier
// row-block (e.g. between the "africa" and "asia" buckets inside the Era
// row) -- a lighter, minor grouping boundary, visually distinct from the
// solid tier-block separator above.
function drawRegionSeparator(svg, width, y) {
  svg.append(svgEl("line", { x1: 0, x2: width, y1: y, y2: y, class: "hierarchy-region-separator" }));
}

// Reserved gutter on the left where a persistent, vertically-written tier
// label (Chapter / Era / Period / ...) sits for each row-block, so the
// viewer always knows what a row means without scrolling back to a legend.
const LEFT_MARGIN = 90;

// The polities row also draws its own per-row region/continent/country
// content labels inside that same gutter. The rotated "Polities" tier
// label sits centered at LEFT_MARGIN / 2 with a real (measured) footprint
// of roughly +-8px around that center, so these start past its right
// edge to avoid colliding with it.
const POLITIES_LABEL_X = 58;
const POLITIES_LABEL_INDENT_X = 66;

// Padding between a row-block's own top edge (yStart) and the top of its
// gutter label's own footprint, once anchored near the top -- see below.
const TIER_LABEL_TOP_PADDING = 8;

function drawTierLabel(svg, text, yStart, yEnd) {
  const cx = LEFT_MARGIN / 2;
  const available = yEnd - yStart;
  const words = text.split(" ");
  const lineHeight = 12;
  // Estimated vertical footprint of the label once rotated (same
  // character-width heuristic as labelAwareFootprint -- this `svg` isn't
  // attached to the document yet at this point in renderHierarchyTimeline,
  // so a real getComputedTextLength() measurement would silently return 0).
  // text-anchor:middle centers each line's own text around the anchor's Y
  // coordinate (pre-rotation X, which becomes vertical post-rotation), so
  // anchoring near yStart + half that footprint -- instead of the block's
  // whole vertical midpoint -- puts the label right at the top of the row,
  // visible without scrolling down into a tall block (e.g. Polities).
  const maxLineLength = Math.max(...words.map((word) => word.length * ESTIMATED_CHAR_WIDTH));
  const anchorY = Math.min(yStart + TIER_LABEL_TOP_PADDING + maxLineLength / 2, yEnd - 4);
  const label = svgEl("text", { x: cx, y: anchorY, class: "hierarchy-tier-label", transform: `rotate(-90, ${cx}, ${anchorY})` });
  if (words.length === 1) {
    label.textContent = text;
  } else {
    // Multi-word labels ("Geological Epoch") stack as separate lines, one
    // word per line -- before rotation that's ordinary vertical line
    // spacing, but after the -90 rotation it becomes *horizontal* spread
    // (using the margin's spare width), while each line's own text length
    // becomes the vertical footprint. So a long tier name only needs to
    // fit its longest single word within a short row-block's height,
    // rather than the whole phrase.
    const startY = anchorY - ((words.length - 1) * lineHeight) / 2;
    words.forEach((word, i) => {
      const tspan = svgEl("tspan", { x: cx, y: startY + i * lineHeight });
      tspan.textContent = word;
      label.append(tspan);
    });
  }
  svg.append(label);
  // Shrink-to-fit safety net: scale the font down if the label's estimated
  // footprint would still overflow this block -- clamped at a floor so
  // short row-blocks (like the thin geological row) never produce illegibly
  // tiny text.
  const budget = available - TIER_LABEL_TOP_PADDING - 6;
  if (maxLineLength > budget && budget > 0) {
    const scale = Math.max(0.75, budget / maxLineLength);
    label.style.fontSize = `${0.7 * scale}rem`;
  }
}

const POLITY_LANE_HEIGHT = 18;
const REGION_HEADER_HEIGHT = 16;
const MAX_POLITIES_PER_REGION = 15;

const countryNames = new Intl.DisplayNames(["en"], { type: "region" });

function countryLaneKey(item) {
  const countries = item.present_countries || [];
  if (countries.length === 1) return countries[0];
  return countries.length > 1 ? "__multiple" : "__unknown";
}

function countryLaneLabel(key) {
  if (key === "__multiple") return "Multiple present countries";
  if (key === "__unknown") return "Country unknown";
  return countryNames.of(key) || key;
}

// Groups Asia's historical-region sub-splits (east/west/south/southeast/
// central Asia, from geoBucketKey) adjacent to each other and to plain
// "asia" in any alphabetically-sorted row, instead of scattered among
// unrelated continents/regions purely by string prefix (e.g. "central_asia"
// sorting next to "central_africa" rather than next to "east_asia"). Used by
// every row that groups by continent or historical region.
const ASIA_GROUP_KEYS = new Set(["asia", "central_asia", "east_asia", "south_asia", "southeast_asia", "west_asia"]);
function geoSortKey(key) {
  return ASIA_GROUP_KEYS.has(key) ? `asia~${key}` : key;
}
function sortGeoKeys(keys) {
  return [...keys].sort((a, b) => (geoSortKey(a) < geoSortKey(b) ? -1 : geoSortKey(a) > geoSortKey(b) ? 1 : 0));
}

function regionLabel(key) {
  if (key === "unclassified") return "Unclassified";
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Narrows a tree to a [start, end) window (used when zoomed in) --
// chapters/eras/periods/polities entirely outside the window are dropped,
// not just visually clamped, so downstream layout (lane packing, region
// buckets) only ever sees what's actually visible.
function filterTreeToRange(tree, start, end) {
  const overlaps = (s, e) => s < end && (e == null || e > start);
  const filterBuckets = (buckets) => {
    const out = {};
    for (const [key, entries] of Object.entries(buckets)) {
      const filtered = entries.filter((p) => overlaps(p.start, p.end));
      if (filtered.length) out[key] = filtered;
    }
    return out;
  };
  const chapters = tree.chapters
    .filter((c) => overlaps(c.start, c.end))
    .map((c) => ({
      ...c,
      eras: c.eras
        .filter((e) => overlaps(e.start, e.end))
        .map((e) => ({ ...e, periods: e.periods.filter((p) => overlaps(p.start, p.end)) })),
      polities_by_historical_region: filterBuckets(c.polities_by_historical_region),
      polities_by_continent: filterBuckets(c.polities_by_continent),
      civilizations: (c.civilizations || []).filter((item) => overlaps(item.start, item.end)),
    }));
  return {
    axis: { domain_start: start, domain_end: end, segment_break: start },
    chapters,
  };
}

// Era-linked color coding: a period (via `era_id`, known for free from tree
// nesting) or a Polities & Cultures entry (via `linked_era_id`, a
// date+geography heuristic match computed server-side -- see
// build_explore_tree.py's _linked_era_id) is colored to match the era it
// belongs to, so e.g. Sumer / Akkadian Empire / Uruk / Babylonia all read as
// one visual group (Mesopotamian Early States), even split across the
// Polities & Cultures row and the ordinary Period row. Eras themselves get
// colors from the same palette, keyed by their own id, so the era band and
// everything linked to it always match.
//
// Assignment is by sorted-index into the palette, not a hash: with only a
// couple dozen era ids total (a curated, slow-growing editorial set, not a
// per-record field), a hash collision is a real risk -- an earlier hash-based
// version collided Iron Age with Paleolithic, and 4 separate eras onto one
// color, defeating the whole point of the feature. Sorted-index assignment
// guarantees zero collisions as long as the era count stays within the
// palette size, and only degrades (repeats) gracefully past that. Built once
// per full (unzoomed) tree load -- see buildEraColorMap -- so it stays stable
// across zoom/filter re-renders rather than shifting as the visible era
// subset changes.
// 18 slots -- comfortably above the ~14 regional_era records that currently
// exist (a slow-growing, curated set; see build_explore_tree.py), so
// sorted-index assignment (below) stays collision-free with room to grow.
const ERA_COLOR_PALETTE = [
  "#8c422d", "#3d6b66", "#5b6b8c", "#8c7a2d", "#6b3d8c",
  "#2d8c5e", "#8c2d4f", "#4f8c2d", "#2d5b8c", "#8c5e2d",
  "#5e2d8c", "#2d8c8c", "#8c2d2d", "#2d8c2d", "#2d4f8c",
  "#8c6b2d", "#6b2d8c", "#2d8c6b",
];
function buildEraColorMap(tree) {
  const ids = new Set();
  for (const chapter of tree.chapters) for (const era of chapter.eras) ids.add(era.id);
  const sorted = [...ids].sort();
  const map = new Map();
  sorted.forEach((id, index) => map.set(id, ERA_COLOR_PALETTE[index % ERA_COLOR_PALETTE.length]));
  return map;
}
function eraColor(colorMap, eraId) {
  if (!eraId || !colorMap) return null;
  return colorMap.get(eraId) || null;
}

// Continent-level grouping (Asia further split by primary_historical_region,
// since "Asia" alone spans wildly different historical contexts -- e.g.
// Islamic Caliphates vs. Chinese Empire -- that continent-level grouping
// flattens together) is the one geography-grouping concept shared by the
// Period, Polities, and Civilizations & Cultures rows -- all three entry
// types carry primary_continent/primary_historical_region for this. The Era
// row alone stays flat (see flatLaneLayout); every continent besides Asia is
// untouched by the sub-split.
function geoBucketKey(item) {
  if (item.primary_continent === "asia" && item.primary_historical_region && item.primary_historical_region !== "unclassified") {
    return item.primary_historical_region;
  }
  return item.primary_continent || "unclassified";
}

// "Continent" mode shows one flat row per geography bucket with no further
// visual nesting -- but an item whose present_countries has exactly one
// value gets a "(Country)" suffix appended to its own label, so e.g. Jomon
// and Yayoi are still identifiable as both-Japan without "Country" mode's
// fuller sub-header nesting. Multi-country or unknown-country items are
// left alone (nothing useful to disambiguate, and it would misleadingly
// imply a single country).
function itemDisplayLabel(item, groupBy) {
  if (groupBy !== "continent") return item.canonical_name;
  const countries = item.present_countries || [];
  if (countries.length !== 1) return item.canonical_name;
  const name = countryNames.of(countries[0]) || countries[0];
  return `${item.canonical_name} (${name})`;
}

const CONTINENT_HEADER_HEIGHT = 18;

// Caps each geography bucket's total entry count (not per-chapter, unlike
// the old server-bucket-driven implementation this replaced) so a single
// hugely over-represented bucket can't blow up rendering -- the true count
// stays visible via each band's tooltip title.
function cappedByBucket(items, getKey, max) {
  const seen = new Map();
  return items.filter((item) => {
    const key = getKey(item);
    const count = (seen.get(key) || 0) + 1;
    seen.set(key, count);
    return count <= max;
  });
}

// Narrows a row's items to a single geography bucket (Continent mode) or a
// single present-day country (Country mode), for the "Filter to" control --
// hidden and inert when groupBy is "none" (see explore.js), so `geoFilter`
// is only ever meaningful alongside continent/country grouping.
function applyGeoFilter(items, groupBy, geoFilter) {
  if (!geoFilter || geoFilter === "all" || groupBy === "none") return items;
  if (groupBy === "continent") return items.filter((item) => geoBucketKey(item) === geoFilter);
  if (groupBy === "country") return items.filter((item) => countryLaneKey(item) === geoFilter);
  return items;
}

// Collects every distinct geography-bucket (Continent mode) or country
// (Country mode) key present across the period, polities, and civilizations
// rows combined, for populating the "Filter to" control's options -- one
// shared filter narrows all three grouped rows together (the Era row is
// unaffected; it never groups). Returns [{value, label}], sorted the same
// way each mode's own rows are (sortGeoKeys for continents, alphabetical
// country names for countries).
function collectGeoFilterOptions(tree, groupBy) {
  if (groupBy === "none") return [];
  const periods = tree.chapters.flatMap((chapter) => chapter.eras.flatMap((era) => era.periods));
  const polities = allPolitiesFlat(tree);
  const civilizations = tree.chapters.flatMap((chapter) => chapter.civilizations || []);
  const items = [...periods, ...polities, ...civilizations];
  if (groupBy === "continent") {
    const keys = sortGeoKeys(new Set(items.map(geoBucketKey)));
    return keys.map((key) => ({ value: key, label: regionLabel(key) }));
  }
  const keys = [...new Set(items.map(countryLaneKey))].sort((a, b) => countryLaneLabel(a).localeCompare(countryLaneLabel(b)));
  return keys.map((key) => ({ value: key, label: countryLaneLabel(key) }));
}

// Flattens every chapter's polities_by_continent buckets into one list. Each
// in-scope, non-civilization-lane polity is bucketed into exactly one
// continent (its own primary_continent) in exactly one chapter (Pass 2 in
// build_explore_tree.py), so this yields each such polity exactly once --
// safe to use as the canonical "all polities" source for grouping/filtering.
function allPolitiesFlat(tree) {
  return tree.chapters.flatMap((chapter) => Object.values(chapter.polities_by_continent).flat());
}

// Continent-grouped layout ("Continent" mode): buckets an already-global
// (post cross-chapter-fix), flat item list by geoBucketKey, then lane-packs
// each bucket's items globally. Used for the Period, Polities, and
// Civilizations & Cultures rows alike -- all three entry types carry the
// same geography fields. Computed once and reused for both the
// height-measurement pass and the draw pass, so the two can't diverge.
function continentGroupedLayout(items, scale, laneHeight, groupBy) {
  const getRange = labelAwareFootprint(scale, (item) => itemDisplayLabel(item, groupBy));
  const capped = cappedByBucket(items, geoBucketKey, MAX_POLITIES_PER_REGION);
  const buckets = new Map();
  for (const item of capped) {
    const key = geoBucketKey(item);
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(item);
  }
  const continents = sortGeoKeys(buckets.keys());
  const rows = continents.map((continent) => {
    const sorted = [...buckets.get(continent)].sort((a, b) => a.start - b.start);
    const lanes = packIntoLanes(sorted, getRange);
    return { continent, lanes };
  });
  const height = rows.reduce((total, row) => total + REGION_HEADER_HEIGHT + row.lanes.length * laneHeight + 4, 0);
  return { kind: "continent", rows, height };
}

// Two-level structure ("Country" mode): geography bucket (continent, Asia
// sub-split) -> present-day country -> lane-packed items. Same geoBucketKey
// outer grouping as continentGroupedLayout above, with one more level of
// sub-grouping by countryLaneKey within each bucket, so e.g. Jomon and
// Yayoi land in the same "Japan" sub-group under "East Asia". Shared by the
// Period, Polities, and Civilizations & Cultures rows.
function geoCountryGroupedLayout(items, scale, laneHeight) {
  const getRange = labelAwareFootprint(scale);
  const capped = cappedByBucket(items, geoBucketKey, MAX_POLITIES_PER_REGION);
  const geoBuckets = new Map();
  for (const item of capped) {
    const geoKey = geoBucketKey(item);
    if (!geoBuckets.has(geoKey)) geoBuckets.set(geoKey, new Map());
    const countryBuckets = geoBuckets.get(geoKey);
    const countryKey = countryLaneKey(item);
    if (!countryBuckets.has(countryKey)) countryBuckets.set(countryKey, []);
    countryBuckets.get(countryKey).push(item);
  }
  const geoKeys = sortGeoKeys(geoBuckets.keys());
  const groups = geoKeys.map((geoKey) => {
    const countryBuckets = geoBuckets.get(geoKey);
    const countryKeys = [...countryBuckets.keys()].sort((a, b) => countryLaneLabel(a).localeCompare(countryLaneLabel(b)));
    const countries = countryKeys.map((countryKey) => {
      const sorted = [...countryBuckets.get(countryKey)].sort((a, b) => a.start - b.start);
      const lanes = packIntoLanes(sorted, getRange);
      return { country: countryKey, lanes };
    });
    return { geo: geoKey, countries };
  });
  const height = groups.reduce((total, group) => {
    const groupHeight = group.countries.reduce((sum, c) => sum + REGION_HEADER_HEIGHT + c.lanes.length * laneHeight + 4, 0);
    return total + CONTINENT_HEADER_HEIGHT + groupHeight;
  }, 0);
  return { kind: "country", groups, height };
}

// Flat (non-grouped) lane layout, used for the Era row always (plain
// start-ascending order, no geography clustering intent), and for the
// Period/Polities & Cultures rows when groupBy is "none" (geography-
// clustering sort, see geoClusterSortKey below).
function flatLaneLayout(items, scale, laneHeight, sortFn = (a, b) => a.start - b.start) {
  const getRange = labelAwareFootprint(scale);
  const sorted = [...items].sort(sortFn);
  const lanes = packIntoLanes(sorted, getRange);
  return { kind: "flat", lanes, height: lanes.length * laneHeight };
}

// packIntoLanes' greedy placement only checks real start/end overlap, so
// feeding it items pre-sorted by geography (continent/Asia sub-split, then
// country, then start) still produces a fully correct, non-overlapping lane
// assignment -- but same-geography items now land in the same or adjacent
// lanes, one after another, giving a visually clustered read even with no
// group headers drawn (Group by "None" still shows no continent/country
// labels, per the control's own semantics -- see renderHierarchyTimeline).
function geoClusterSort(a, b) {
  const geoA = geoSortKey(geoBucketKey(a));
  const geoB = geoSortKey(geoBucketKey(b));
  if (geoA !== geoB) return geoA < geoB ? -1 : 1;
  const countryA = countryLaneLabel(countryLaneKey(a));
  const countryB = countryLaneLabel(countryLaneKey(b));
  if (countryA !== countryB) return countryA < countryB ? -1 : 1;
  return a.start - b.start; // numeric, so BCE (negative) years compare correctly
}

// Dispatches to the right layout function for the current groupBy mode.
// `groupBy` is ignored (always flat) when the caller passes "none" or
// omits it, matching the Era row's own always-flat behavior.
function groupedLayoutFor(items, scale, laneHeight, groupBy) {
  if (groupBy === "continent") return continentGroupedLayout(items, scale, laneHeight, groupBy);
  if (groupBy === "country") return geoCountryGroupedLayout(items, scale, laneHeight);
  return flatLaneLayout(items, scale, laneHeight, geoClusterSort);
}

// `getFill`/`getKind`/`getCls` let one draw function serve every row:
// `getFill(item)` returns an era-linked color (or null for the row's own
// default CSS color -- e.g. plain polities, which aren't era-colored),
// `getKind(item)` returns the detail-panel record kind ("era"/"period"/
// "polity"), and `getCls(item)` returns the per-item CSS class controlling
// its default fill/opacity -- all three are fixed per row except the merged
// Polities & Cultures row, where each entry is itself either a plain polity
// or a civilization/culture entry sourced from a polity or a period (see
// `item.source`, only set on civilization-lane entries).
function drawFlatLaneRow(svg, scale, lanes, y, laneHeight, cls, onZoom, domainEnd, opts = {}) {
  const getFill = opts.getFill || (() => null);
  const getKind = opts.getKind || (() => "period");
  const getCls = opts.getCls || (() => cls);
  lanes.forEach((lane, laneIndex) => {
    lane.forEach((item) => {
      bandRect(svg, {
        x: scale.x(item.start), y: y + laneIndex * laneHeight,
        width: scale.width(item.start, item.end), height: laneHeight - 2,
        cls: `hierarchy-band ${getCls(item)}`.trim(), title: item.canonical_name, label: item.canonical_name,
        fill: getFill(item),
        onZoom: { handler: onZoom, kind: getKind(item), id: item.id, start: item.start, end: item.end ?? domainEnd },
      });
    });
  });
  return y + lanes.length * laneHeight;
}

function drawContinentGroupedRow(svg, scale, rows, y, laneHeight, cls, onZoom, width, domainEnd, opts = {}) {
  const getFill = opts.getFill || (() => null);
  const getKind = opts.getKind || (() => "period");
  const getCls = opts.getCls || (() => cls);
  let rowY = y;
  rows.forEach(({ continent, lanes }, index) => {
    if (index > 0) drawRegionSeparator(svg, width, rowY - 2);
    const label = svgEl("text", { x: POLITIES_LABEL_X, y: rowY + REGION_HEADER_HEIGHT - 4, class: "hierarchy-region-label" });
    label.textContent = regionLabel(continent);
    svg.append(label);
    rowY += REGION_HEADER_HEIGHT;
    lanes.forEach((lane, laneIndex) => {
      lane.forEach((item) => {
        bandRect(svg, {
          x: scale.x(item.start), y: rowY + laneIndex * laneHeight,
          width: scale.width(item.start, item.end), height: laneHeight - 2,
          cls: `hierarchy-band ${getCls(item)}`.trim(), title: item.canonical_name, label: item.canonical_name,
          fill: getFill(item),
          onZoom: { handler: onZoom, kind: getKind(item), id: item.id, start: item.start, end: item.end ?? domainEnd },
        });
      });
    });
    rowY += lanes.length * laneHeight + 4;
  });
  return rowY;
}

function drawGeoCountryGroupedRow(svg, scale, groups, y, laneHeight, cls, onZoom, width, domainEnd, opts = {}) {
  const getFill = opts.getFill || (() => null);
  const getKind = opts.getKind || (() => "period");
  const getCls = opts.getCls || (() => cls);
  let rowY = y;
  groups.forEach(({ geo, countries }, groupIndex) => {
    if (groupIndex > 0) drawRegionSeparator(svg, width, rowY - 2);
    const header = svgEl("text", { x: POLITIES_LABEL_X, y: rowY + CONTINENT_HEADER_HEIGHT - 5, class: "hierarchy-continent-label" });
    header.textContent = regionLabel(geo);
    svg.append(header);
    rowY += CONTINENT_HEADER_HEIGHT;
    countries.forEach(({ country, lanes }, countryIndex) => {
      if (countryIndex > 0) drawRegionSeparator(svg, width, rowY - 2);
      const countryLabelEl = svgEl("text", { x: POLITIES_LABEL_INDENT_X, y: rowY + REGION_HEADER_HEIGHT - 4, class: "hierarchy-region-label" });
      countryLabelEl.textContent = countryLaneLabel(country);
      svg.append(countryLabelEl);
      rowY += REGION_HEADER_HEIGHT;
      lanes.forEach((lane, laneIndex) => {
        lane.forEach((item) => {
          bandRect(svg, {
            x: scale.x(item.start), y: rowY + laneIndex * laneHeight,
            width: scale.width(item.start, item.end), height: laneHeight - 2,
            cls: `hierarchy-band ${getCls(item)}`.trim(),
            title: `${item.canonical_name} (${countryLaneLabel(country)})`,
            label: item.canonical_name,
            fill: getFill(item),
            onZoom: { handler: onZoom, kind: getKind(item), id: item.id, start: item.start, end: item.end ?? domainEnd },
          });
        });
      });
      rowY += lanes.length * laneHeight + 4;
    });
  });
  return rowY;
}

// Dispatches to the right draw function for a layout object produced by
// groupedLayoutFor -- one call site for every grouped row (Period, Polities,
// Civilizations & Cultures), each passing its own `opts.getFill`/`getKind`.
function drawGroupedRow(svg, scale, layout, y, laneHeight, cls, onZoom, width, domainEnd, opts) {
  if (layout.kind === "continent") return drawContinentGroupedRow(svg, scale, layout.rows, y, laneHeight, cls, onZoom, width, domainEnd, opts);
  if (layout.kind === "country") return drawGeoCountryGroupedRow(svg, scale, layout.groups, y, laneHeight, cls, onZoom, width, domainEnd, opts);
  return drawFlatLaneRow(svg, scale, layout.lanes, y, laneHeight, cls, onZoom, domainEnd, opts);
}

function renderHierarchyTimeline(tree, container, options = {}, onZoom = () => {}) {
  // eraColorMap defaults to being built from the current (possibly zoomed)
  // tree when the caller doesn't pass one -- callers that zoom/filter should
  // pass a map built once from the full, unzoomed tree instead (see
  // explore.js), so era colors stay stable rather than shifting as the
  // visible era subset changes.
  const { groupBy = "continent", showPolities = true, geoFilter = null, eraColorMap = buildEraColorMap(tree) } = options;
  const width = Math.max(900, Math.min(4800, window.innerWidth - 80));
  const scale = createTimeScale(
    tree.axis.domain_start, tree.axis.domain_end, tree.axis.segment_break,
    width - LEFT_MARGIN, 0.1, LEFT_MARGIN,
  );

  // geoRowHeight is taller than the band content strictly needs. The
  // rotated tier label for this row is just the single word "Epoch", which
  // doesn't need the extra room, but the slack is harmless and keeps this
  // row visually distinct from the chapter row below it.
  const geoRowHeight = 48;
  const chapterRowHeight = 40;
  const eraLaneHeight = 24;
  const periodLaneHeight = 20;
  const civLaneHeight = 20;
  const polityLaneHeight = POLITY_LANE_HEIGHT;
  const rowGap = 6;

  // Pack eras, periods, civilizations, and polities GLOBALLY across all
  // chapters, not per chapter -- an item's real time span can extend past
  // its own chapter's boundary, so lane assignment needs cross-chapter
  // awareness to avoid a collision with a neighboring chapter's own lane-0
  // content.
  //
  // The era row is always flat (not grouped): there are only ever a
  // handful of eras active at once, so grouping by continent fragmented it
  // for little benefit. Period, Civilizations & Cultures, and Polities share
  // one grouping mode (groupBy) -- there are enough entries, at a finer
  // geographic mix, that grouping keeps chronologically adjacent but
  // geographically unrelated items from sharing a lane.
  const visibleEras = tree.chapters.flatMap((chapter) => chapter.eras.filter((era) => !era.auto_generated));
  const eraLayout = flatLaneLayout(visibleEras, scale, eraLaneHeight);

  const allPeriods = tree.chapters.flatMap((chapter) => chapter.eras.flatMap((era) => era.periods));
  const periodLayout = groupedLayoutFor(applyGeoFilter(allPeriods, groupBy, geoFilter), scale, periodLaneHeight, groupBy);

  // Civilizations & Cultures: always shown when it has content, independent
  // of the "Show polities" checkbox -- civilization/culture/people/tribe
  // entries (entity_type-tagged polities, civilization-backdrop periods) are
  // a distinct row from plain polities below, per explicit request ("in all
  // cases I should see the Civilization lane"). Shares groupBy/geoFilter
  // with the Period/Polities rows (same grouping mode everywhere).
  const civItems = tree.chapters.flatMap((chapter) => chapter.civilizations || []);
  const civLayout = groupedLayoutFor(applyGeoFilter(civItems, groupBy, geoFilter), scale, civLaneHeight, groupBy);

  const politiesItems = showPolities ? applyGeoFilter(allPolitiesFlat(tree), groupBy, geoFilter) : [];
  const politiesLayout = groupedLayoutFor(politiesItems, scale, polityLaneHeight, groupBy);

  const eraRowHeight = eraLayout.height;
  const periodRowHeight = periodLayout.height;
  // Zero when there's nothing to show (e.g. the row is hidden via
  // showPolities, or zoomed into a range with no entries) -- the row (and
  // its separator/tier label) is skipped entirely rather than drawing an
  // empty block, see below.
  const civBlockHeight = civLayout.height > 0 ? civLayout.height + rowGap : 0;
  const politiesRowHeight = showPolities ? politiesLayout.height : 0;

  const height = geoRowHeight + chapterRowHeight + eraRowHeight + periodRowHeight + civBlockHeight + politiesRowHeight + rowGap * 4;

  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, class: "hierarchy-chart" });

  let y = 0;
  let prevSepY = 0;
  const geoEnd = new Date().getFullYear();
  for (const epoch of GEOLOGICAL_EPOCHS) {
    const end = epoch.end === null ? geoEnd : epoch.end;
    const bx = scale.x(epoch.start);
    bandRect(svg, {
      x: bx, y, width: scale.width(epoch.start, end), height: geoRowHeight,
      cls: "hierarchy-band hierarchy-band-geo", title: epoch.name,
    });
  }
  y += geoRowHeight + rowGap;
  let sepY = y - rowGap / 2;
  drawSeparator(svg, width, sepY);
  drawTierLabel(svg, "Epoch", prevSepY, sepY);
  prevSepY = sepY;

  for (const chapter of tree.chapters) {
    bandRect(svg, {
      x: scale.x(chapter.start), y, width: scale.width(chapter.start, chapter.end), height: chapterRowHeight,
      cls: "hierarchy-band hierarchy-band-chapter",
      title: `${chapter.canonical_name} (${formatYear(chapter.start)} - ${formatYear(chapter.end)})`,
      label: chapter.canonical_name,
      onZoom: { handler: onZoom, kind: "chapter", id: chapter.id, start: chapter.start, end: chapter.end },
    });
  }
  y += chapterRowHeight + rowGap;
  sepY = y - rowGap / 2;
  drawSeparator(svg, width, sepY);
  drawTierLabel(svg, "Chapter", prevSepY, sepY);
  prevSepY = sepY;

  drawFlatLaneRow(svg, scale, eraLayout.lanes, y, eraLaneHeight, "hierarchy-band-era", onZoom, tree.axis.domain_end, {
    getFill: (item) => eraColor(eraColorMap, item.id),
    getKind: () => "era",
  });
  y += eraRowHeight + rowGap;
  sepY = y - rowGap / 2;
  drawSeparator(svg, width, sepY);
  drawTierLabel(svg, "Era", prevSepY, sepY);
  prevSepY = sepY;

  drawGroupedRow(svg, scale, periodLayout, y, periodLaneHeight, "hierarchy-band-period", onZoom, width, tree.axis.domain_end, {
    getFill: (item) => eraColor(eraColorMap, item.era_id),
    getKind: () => "period",
  });
  y += periodRowHeight + rowGap;
  sepY = y - rowGap / 2;
  drawSeparator(svg, width, sepY);
  drawTierLabel(svg, "Period", prevSepY, sepY);
  prevSepY = sepY;

  if (civLayout.height > 0) {
    drawGroupedRow(svg, scale, civLayout, y, civLaneHeight, "hierarchy-band-civilization", onZoom, width, tree.axis.domain_end, {
      getFill: (item) => eraColor(eraColorMap, item.linked_era_id),
      getKind: (item) => (item.source === "polity" ? "polity" : "period"),
    });
    y += civLayout.height + rowGap;
    sepY = y - rowGap / 2;
    drawSeparator(svg, width, sepY);
    drawTierLabel(svg, "Civilizations & Cultures", prevSepY, sepY);
    prevSepY = sepY;
  }

  if (showPolities && politiesRowHeight > 0) {
    drawGroupedRow(svg, scale, politiesLayout, y, polityLaneHeight, "hierarchy-band-polity", onZoom, width, tree.axis.domain_end, {
      getKind: () => "polity",
    });
    drawTierLabel(svg, "Polities", prevSepY, height);
  }

  // Year gridlines/axis labels, matching app.js's established treatment
  // (.grid-line spans the full chart height, .axis-label sits near the top),
  // so a 4-row chart spanning millions of years still has a date reference.
  for (const tickYear of scale.tickYears()) {
    const tickX = scale.x(tickYear);
    svg.append(svgEl("line", { x1: tickX, x2: tickX, y1: 0, y2: height, class: "grid-line" }));
    const label = svgEl("text", { x: tickX + 2, y: 10, class: "axis-label" });
    label.textContent = formatYear(tickYear);
    svg.append(label);
  }

  container.replaceChildren(svg);
  return { scale, height };
}
