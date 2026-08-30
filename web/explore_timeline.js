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
function labelAwareFootprint(scale) {
  return (item) => {
    const bandStart = scale.x(item.start);
    const bandWidth = scale.width(item.start, item.end);
    const labelWidth = item.canonical_name.length * ESTIMATED_CHAR_WIDTH + LABEL_PADDING;
    const footprintWidth = Math.max(bandWidth, labelWidth);
    return { start: bandStart, end: bandStart + footprintWidth };
  };
}

function bandRect(svg, { x, y, width, height, cls, title, label, onZoom }) {
  const rect = svgEl("rect", { x, y, width, height, class: cls, rx: 2 });
  if (onZoom) {
    rect.classList.add("zoomable");
    rect.addEventListener("click", () => onZoom.handler(onZoom.start, onZoom.end));
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

function drawSeparator(svg, width, y) {
  svg.append(svgEl("line", { x1: 0, x2: width, y1: y, y2: y, class: "hierarchy-row-separator" }));
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

function drawTierLabel(svg, text, yStart, yEnd) {
  const yMid = (yStart + yEnd) / 2;
  const cx = LEFT_MARGIN / 2;
  const available = yEnd - yStart;
  const label = svgEl("text", { x: cx, y: yMid, class: "hierarchy-tier-label", transform: `rotate(-90, ${cx}, ${yMid})` });
  const words = text.split(" ");
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
    const lineHeight = 12;
    const startY = yMid - ((words.length - 1) * lineHeight) / 2;
    words.forEach((word, i) => {
      const tspan = svgEl("tspan", { x: cx, y: startY + i * lineHeight });
      tspan.textContent = word;
      label.append(tspan);
    });
  }
  svg.append(label);
  // Shrink-to-fit safety net: the longest line's rendered length becomes
  // the vertical footprint once rotated, so estimate it (same character-width
  // heuristic as labelAwareFootprint -- this `svg` isn't attached to the
  // document yet at this point in renderHierarchyTimeline, so a real
  // getComputedTextLength() measurement would silently return 0) and scale
  // the font down if it would still overflow this block -- clamped at a
  // floor so short row-blocks (like the thin geological row) never produce
  // illegibly tiny text.
  const maxLineLength = Math.max(...words.map((word) => word.length * ESTIMATED_CHAR_WIDTH));
  const budget = available - 6;
  if (maxLineLength > budget && budget > 0) {
    const scale = Math.max(0.75, budget / maxLineLength);
    label.style.fontSize = `${0.7 * scale}rem`;
  }
}

const POLITY_LANE_HEIGHT = 18;
const REGION_HEADER_HEIGHT = 16;
const MAX_POLITIES_PER_REGION = 15;

const countryNames = new Intl.DisplayNames(["en"], { type: "region" });

function countryLaneKey(polity) {
  const countries = polity.present_countries || [];
  if (countries.length === 1) return countries[0];
  return countries.length > 1 ? "__multiple" : "__unknown";
}

function countryLaneLabel(key) {
  if (key === "__multiple") return "Multiple present countries";
  if (key === "__unknown") return "Country unknown";
  return countryNames.of(key) || key;
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
    }));
  return {
    axis: { domain_start: start, domain_end: end, segment_break: start },
    chapters,
  };
}

// One global, sorted list of region keys across all chapters, so the same
// vertical position always means the same region no matter which chapter's
// band is drawn there -- a horizontal row is otherwise meaningless.
function collectRegionKeys(tree, groupBy) {
  if (groupBy === "none") return [];
  const keys = new Set();
  for (const chapter of tree.chapters) {
    const buckets = groupBy === "continent" ? chapter.polities_by_continent : chapter.polities_by_historical_region;
    for (const key of Object.keys(buckets)) keys.add(key);
  }
  return [...keys].sort();
}

// Row height per region = the lane count needed to pack ALL chapters'
// entries for that region together, so a real time-span overlap between
// two different chapters' polities is caught instead of hidden behind
// independent per-chapter lane indices sharing the same Y-offset.
function regionLaneCounts(tree, groupBy, regionKeys, scale) {
  const counts = {};
  const getRange = labelAwareFootprint(scale);
  for (const key of regionKeys) {
    const allEntries = tree.chapters.flatMap((chapter) => {
      const buckets = groupBy === "continent" ? chapter.polities_by_continent : chapter.polities_by_historical_region;
      return (buckets[key] || []).slice(0, MAX_POLITIES_PER_REGION);
    });
    const sorted = [...allEntries].sort((a, b) => a.start - b.start);
    const lanes = packIntoLanes(sorted, getRange);
    counts[key] = lanes.length;
  }
  return counts;
}

function measurePolitiesRowHeight(regionKeys, laneCounts) {
  let total = 0;
  for (const key of regionKeys) total += REGION_HEADER_HEIGHT + laneCounts[key] * POLITY_LANE_HEIGHT + 4;
  return total;
}

function renderPolitiesRow(svg, scale, tree, groupBy, regionKeys, laneCounts, y, onZoom) {
  if (groupBy === "none") return y;
  let rowY = y;
  const getRange = labelAwareFootprint(scale);
  for (const key of regionKeys) {
    const label = svgEl("text", { x: POLITIES_LABEL_X, y: rowY + REGION_HEADER_HEIGHT - 4, class: "hierarchy-region-label" });
    label.textContent = regionLabel(key);
    svg.append(label);
    rowY += REGION_HEADER_HEIGHT;
    const totalCount = tree.chapters.reduce((sum, chapter) => {
      const buckets = groupBy === "continent" ? chapter.polities_by_continent : chapter.polities_by_historical_region;
      return sum + (buckets[key]?.length || 0);
    }, 0);
    const allEntries = tree.chapters.flatMap((chapter) => {
      const buckets = groupBy === "continent" ? chapter.polities_by_continent : chapter.polities_by_historical_region;
      return (buckets[key] || []).slice(0, MAX_POLITIES_PER_REGION);
    });
    const sorted = [...allEntries].sort((a, b) => a.start - b.start);
    const lanes = packIntoLanes(sorted, getRange);
    lanes.forEach((lane, laneIndex) => {
      lane.forEach((polity) => {
        const curatedClass = polity.curated ? "curated" : "heuristic";
        bandRect(svg, {
          x: scale.x(polity.start), y: rowY + laneIndex * POLITY_LANE_HEIGHT,
          width: scale.width(polity.start, polity.end), height: POLITY_LANE_HEIGHT - 2,
          cls: `hierarchy-band hierarchy-band-polity ${curatedClass}`,
          title: `${polity.canonical_name} (${totalCount} in ${regionLabel(key)})`,
          label: polity.canonical_name,
          onZoom: { handler: onZoom, start: polity.start, end: polity.end ?? tree.axis.domain_end },
        });
      });
    });
    rowY += laneCounts[key] * POLITY_LANE_HEIGHT + 4;
  }
  return rowY;
}

// Two-level structure for "present-day country, organised by continent":
// continent -> sorted list of country keys present anywhere across chapters.
// Kept as a separate, parallel set of functions from the single-level
// region/continent grouping above -- not a generalization of it -- so this
// new mode can't destabilize the working single-level code path.
function collectCountryStructure(tree) {
  const structure = new Map();
  for (const chapter of tree.chapters) {
    for (const [continent, entries] of Object.entries(chapter.polities_by_continent)) {
      if (!structure.has(continent)) structure.set(continent, new Set());
      for (const polity of entries) structure.get(continent).add(countryLaneKey(polity));
    }
  }
  return [...structure.keys()].sort().map((continent) => ({
    continent,
    countries: [...structure.get(continent)].sort(),
  }));
}

function entriesForCountry(chapter, continent, country) {
  const all = chapter.polities_by_continent[continent] || [];
  return all.filter((polity) => countryLaneKey(polity) === country);
}

function countryLaneCounts(tree, structure, scale) {
  const counts = new Map();
  const getRange = labelAwareFootprint(scale);
  for (const { continent, countries } of structure) {
    for (const country of countries) {
      const allEntries = tree.chapters.flatMap((chapter) => entriesForCountry(chapter, continent, country).slice(0, MAX_POLITIES_PER_REGION));
      const sorted = [...allEntries].sort((a, b) => a.start - b.start);
      const lanes = packIntoLanes(sorted, getRange);
      counts.set(`${continent}::${country}`, lanes.length);
    }
  }
  return counts;
}

const CONTINENT_HEADER_HEIGHT = 18;

function measureCountryRowHeight(structure, laneCounts) {
  let total = 0;
  for (const { continent, countries } of structure) {
    total += CONTINENT_HEADER_HEIGHT;
    for (const country of countries) {
      total += REGION_HEADER_HEIGHT + laneCounts.get(`${continent}::${country}`) * POLITY_LANE_HEIGHT + 4;
    }
  }
  return total;
}

function renderCountryRow(svg, scale, tree, structure, laneCounts, y, onZoom) {
  let rowY = y;
  const getRange = labelAwareFootprint(scale);
  for (const { continent, countries } of structure) {
    const header = svgEl("text", { x: POLITIES_LABEL_X, y: rowY + CONTINENT_HEADER_HEIGHT - 5, class: "hierarchy-continent-label" });
    header.textContent = regionLabel(continent);
    svg.append(header);
    rowY += CONTINENT_HEADER_HEIGHT;
    for (const country of countries) {
      const countryLabel = svgEl("text", { x: POLITIES_LABEL_INDENT_X, y: rowY + REGION_HEADER_HEIGHT - 4, class: "hierarchy-region-label" });
      countryLabel.textContent = countryLaneLabel(country);
      svg.append(countryLabel);
      rowY += REGION_HEADER_HEIGHT;
      const allEntries = tree.chapters.flatMap((chapter) => entriesForCountry(chapter, continent, country).slice(0, MAX_POLITIES_PER_REGION));
      const sorted = [...allEntries].sort((a, b) => a.start - b.start);
      const lanes = packIntoLanes(sorted, getRange);
      lanes.forEach((lane, laneIndex) => {
        lane.forEach((polity) => {
          const curatedClass = polity.curated ? "curated" : "heuristic";
          bandRect(svg, {
            x: scale.x(polity.start), y: rowY + laneIndex * POLITY_LANE_HEIGHT,
            width: scale.width(polity.start, polity.end), height: POLITY_LANE_HEIGHT - 2,
            cls: `hierarchy-band hierarchy-band-polity ${curatedClass}`,
            title: `${polity.canonical_name} (${countryLaneLabel(country)})`,
            label: polity.canonical_name,
            onZoom: { handler: onZoom, start: polity.start, end: polity.end ?? tree.axis.domain_end },
          });
        });
      });
      rowY += laneCounts.get(`${continent}::${country}`) * POLITY_LANE_HEIGHT + 4;
    }
  }
  return rowY;
}

// Continent-grouped layout for the era and period rows: buckets an
// already-global (post cross-chapter fix), flat item list by
// primary_continent, then lane-packs each continent's items globally
// (across chapters, since these lists already are). Computed once and
// reused for both the height-measurement pass and the draw pass, so
// there's no possibility of the two diverging.
function continentGroupedLayout(items, scale, laneHeight) {
  const getRange = labelAwareFootprint(scale);
  const buckets = new Map();
  for (const item of items) {
    const key = item.primary_continent || "unclassified";
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(item);
  }
  const continents = [...buckets.keys()].sort();
  const rows = continents.map((continent) => {
    const sorted = [...buckets.get(continent)].sort((a, b) => a.start - b.start);
    const lanes = packIntoLanes(sorted, getRange);
    return { continent, lanes };
  });
  const height = rows.reduce((total, row) => total + REGION_HEADER_HEIGHT + row.lanes.length * laneHeight + 4, 0);
  return { rows, height };
}

function drawContinentGroupedRow(svg, scale, rows, y, laneHeight, cls, onZoom) {
  let rowY = y;
  for (const { continent, lanes } of rows) {
    const label = svgEl("text", { x: POLITIES_LABEL_X, y: rowY + REGION_HEADER_HEIGHT - 4, class: "hierarchy-region-label" });
    label.textContent = regionLabel(continent);
    svg.append(label);
    rowY += REGION_HEADER_HEIGHT;
    lanes.forEach((lane, laneIndex) => {
      lane.forEach((item) => {
        // Eras have no curated/heuristic distinction (_era_entry carries no
        // `curated` field) -- only periods do.
        const curatedClass = item.curated === undefined ? "" : (item.curated ? "curated" : "heuristic");
        bandRect(svg, {
          x: scale.x(item.start), y: rowY + laneIndex * laneHeight,
          width: scale.width(item.start, item.end), height: laneHeight - 2,
          cls: `hierarchy-band ${cls} ${curatedClass}`.trim(), title: item.canonical_name, label: item.canonical_name,
          onZoom: { handler: onZoom, start: item.start, end: item.end },
        });
      });
    });
    rowY += lanes.length * laneHeight + 4;
  }
  return rowY;
}

function renderHierarchyTimeline(tree, container, groupBy = "historical_region", onZoom = () => {}) {
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
  const rowGap = 6;

  // Pack eras and periods GLOBALLY across all chapters, not per chapter --
  // an item's real time span can extend past its own chapter's boundary,
  // so lane assignment needs cross-chapter awareness to avoid a collision
  // with a neighboring chapter's own lane-0 content. Additionally grouped
  // by continent (a fixed granularity, independent of the polities row's
  // own historical_region/continent/country toggle) so two chronologically
  // adjacent but geographically unrelated eras/periods don't share a lane.
  const visibleEras = tree.chapters.flatMap((chapter) => chapter.eras.filter((era) => !era.auto_generated));
  const eraLayout = continentGroupedLayout(visibleEras, scale, eraLaneHeight);
  const allPeriods = tree.chapters.flatMap((chapter) => chapter.eras.flatMap((era) => era.periods));
  const periodLayout = continentGroupedLayout(allPeriods, scale, periodLaneHeight);

  const eraRowHeight = eraLayout.height;
  const periodRowHeight = periodLayout.height;

  // Both the height number (needed now, before `height`/`svg` exist) and the
  // deferred drawing closure (called later, once `svg` exists) are prepared
  // here so the two grouping modes -- single-level region/continent vs.
  // two-level country-by-continent -- share one control-flow shape.
  let politiesRowHeight;
  let drawPolitiesRow;
  if (groupBy === "country") {
    const structure = collectCountryStructure(tree);
    const laneCounts = countryLaneCounts(tree, structure, scale);
    politiesRowHeight = measureCountryRowHeight(structure, laneCounts);
    drawPolitiesRow = (rowY) => renderCountryRow(svg, scale, tree, structure, laneCounts, rowY, onZoom);
  } else {
    const regionKeys = collectRegionKeys(tree, groupBy);
    const laneCounts = regionLaneCounts(tree, groupBy, regionKeys, scale);
    politiesRowHeight = measurePolitiesRowHeight(regionKeys, laneCounts);
    drawPolitiesRow = (rowY) => renderPolitiesRow(svg, scale, tree, groupBy, regionKeys, laneCounts, rowY, onZoom);
  }
  const height = geoRowHeight + chapterRowHeight + eraRowHeight + periodRowHeight + politiesRowHeight + rowGap * 5;

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
      onZoom: { handler: onZoom, start: chapter.start, end: chapter.end },
    });
  }
  y += chapterRowHeight + rowGap;
  sepY = y - rowGap / 2;
  drawSeparator(svg, width, sepY);
  drawTierLabel(svg, "Chapter", prevSepY, sepY);
  prevSepY = sepY;

  drawContinentGroupedRow(svg, scale, eraLayout.rows, y, eraLaneHeight, "hierarchy-band-era", onZoom);
  y += eraRowHeight + rowGap;
  sepY = y - rowGap / 2;
  drawSeparator(svg, width, sepY);
  drawTierLabel(svg, "Era", prevSepY, sepY);
  prevSepY = sepY;

  drawContinentGroupedRow(svg, scale, periodLayout.rows, y, periodLaneHeight, "hierarchy-band-period", onZoom);
  y += periodRowHeight + rowGap;
  sepY = y - rowGap / 2;
  drawSeparator(svg, width, sepY);
  drawTierLabel(svg, "Period", prevSepY, sepY);
  prevSepY = sepY;

  drawPolitiesRow(y);
  if (politiesRowHeight > 0) {
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
