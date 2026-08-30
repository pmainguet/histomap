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

// Row height per region = the max lane count needed by any single chapter
// for that region, so every chapter's entries fit within the shared row.
function regionLaneCounts(tree, groupBy, regionKeys, scale) {
  const counts = {};
  const getRange = labelAwareFootprint(scale);
  for (const key of regionKeys) {
    let maxLanes = 1;
    for (const chapter of tree.chapters) {
      const buckets = groupBy === "continent" ? chapter.polities_by_continent : chapter.polities_by_historical_region;
      const entries = buckets[key];
      if (!entries) continue;
      const lanes = packIntoLanes(entries.slice(0, MAX_POLITIES_PER_REGION), getRange);
      maxLanes = Math.max(maxLanes, lanes.length);
    }
    counts[key] = maxLanes;
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
    const label = svgEl("text", { x: 4, y: rowY + REGION_HEADER_HEIGHT - 4, class: "hierarchy-region-label" });
    label.textContent = regionLabel(key);
    svg.append(label);
    rowY += REGION_HEADER_HEIGHT;
    for (const chapter of tree.chapters) {
      const buckets = groupBy === "continent" ? chapter.polities_by_continent : chapter.polities_by_historical_region;
      const entries = buckets[key];
      if (!entries) continue;
      const shown = entries.slice(0, MAX_POLITIES_PER_REGION);
      const lanes = packIntoLanes(shown, getRange);
      lanes.forEach((lane, laneIndex) => {
        lane.forEach((polity) => {
          const curatedClass = polity.curated ? "curated" : "heuristic";
          bandRect(svg, {
            x: scale.x(polity.start), y: rowY + laneIndex * POLITY_LANE_HEIGHT,
            width: scale.width(polity.start, polity.end), height: POLITY_LANE_HEIGHT - 2,
            cls: `hierarchy-band hierarchy-band-polity ${curatedClass}`,
            title: `${polity.canonical_name} (${entries.length} in ${regionLabel(key)})`,
            label: polity.canonical_name,
            onZoom: { handler: onZoom, start: polity.start, end: polity.end ?? tree.axis.domain_end },
          });
        });
      });
    }
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
      let maxLanes = 1;
      for (const chapter of tree.chapters) {
        const entries = entriesForCountry(chapter, continent, country);
        if (!entries.length) continue;
        const lanes = packIntoLanes(entries.slice(0, MAX_POLITIES_PER_REGION), getRange);
        maxLanes = Math.max(maxLanes, lanes.length);
      }
      counts.set(`${continent}::${country}`, maxLanes);
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
    const header = svgEl("text", { x: 4, y: rowY + CONTINENT_HEADER_HEIGHT - 5, class: "hierarchy-continent-label" });
    header.textContent = regionLabel(continent);
    svg.append(header);
    rowY += CONTINENT_HEADER_HEIGHT;
    for (const country of countries) {
      const countryLabel = svgEl("text", { x: 12, y: rowY + REGION_HEADER_HEIGHT - 4, class: "hierarchy-region-label" });
      countryLabel.textContent = countryLaneLabel(country);
      svg.append(countryLabel);
      rowY += REGION_HEADER_HEIGHT;
      for (const chapter of tree.chapters) {
        const entries = entriesForCountry(chapter, continent, country);
        if (!entries.length) continue;
        const shown = entries.slice(0, MAX_POLITIES_PER_REGION);
        const lanes = packIntoLanes(shown, getRange);
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
      }
      rowY += laneCounts.get(`${continent}::${country}`) * POLITY_LANE_HEIGHT + 4;
    }
  }
  return rowY;
}

function renderHierarchyTimeline(tree, container, groupBy = "historical_region", onZoom = () => {}) {
  const width = Math.max(900, Math.min(4800, window.innerWidth - 80));
  const scale = createTimeScale(tree.axis.domain_start, tree.axis.domain_end, tree.axis.segment_break, width);

  const geoRowHeight = 28;
  const chapterRowHeight = 36;
  const eraLaneHeight = 24;
  const periodLaneHeight = 20;
  const rowGap = 6;

  // Pack eras and periods per chapter, left-to-right (chapters don't overlap).
  const getRange = labelAwareFootprint(scale);
  const chapterLayouts = tree.chapters.map((chapter) => {
    const visibleEras = chapter.eras.filter((era) => !era.auto_generated);
    const eraLanes = packIntoLanes([...visibleEras].sort((a, b) => a.start - b.start), getRange);
    const allPeriods = chapter.eras.flatMap((era) => era.periods);
    const periodLanes = packIntoLanes([...allPeriods].sort((a, b) => a.start - b.start), getRange);
    return { chapter, eraLanes, periodLanes };
  });
  const maxEraLanes = Math.max(1, ...chapterLayouts.map((c) => c.eraLanes.length));
  const maxPeriodLanes = Math.max(1, ...chapterLayouts.map((c) => c.periodLanes.length));

  const eraRowHeight = maxEraLanes * eraLaneHeight;
  const periodRowHeight = maxPeriodLanes * periodLaneHeight;

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
  drawSeparator(svg, width, y - rowGap / 2);

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
  drawSeparator(svg, width, y - rowGap / 2);

  chapterLayouts.forEach(({ eraLanes }) => {
    eraLanes.forEach((lane, laneIndex) => {
      lane.forEach((era) => {
        bandRect(svg, {
          x: scale.x(era.start), y: y + laneIndex * eraLaneHeight,
          width: scale.width(era.start, era.end), height: eraLaneHeight - 2,
          cls: "hierarchy-band hierarchy-band-era", title: era.canonical_name, label: era.canonical_name,
          onZoom: { handler: onZoom, start: era.start, end: era.end },
        });
      });
    });
  });
  y += eraRowHeight + rowGap;
  drawSeparator(svg, width, y - rowGap / 2);

  chapterLayouts.forEach(({ periodLanes }) => {
    periodLanes.forEach((lane, laneIndex) => {
      lane.forEach((period) => {
        const curatedClass = period.curated ? "curated" : "heuristic";
        bandRect(svg, {
          x: scale.x(period.start), y: y + laneIndex * periodLaneHeight,
          width: scale.width(period.start, period.end), height: periodLaneHeight - 2,
          cls: `hierarchy-band hierarchy-band-period ${curatedClass}`, title: period.canonical_name,
          label: period.canonical_name,
          onZoom: { handler: onZoom, start: period.start, end: period.end },
        });
      });
    });
  });
  y += periodRowHeight + rowGap;
  drawSeparator(svg, width, y - rowGap / 2);

  drawPolitiesRow(y);

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
