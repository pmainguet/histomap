function formatYear(year) {
  if (year === null || year === undefined) return "present";
  return year < 0 ? `${Math.abs(year).toLocaleString()} BCE` : `${year.toLocaleString()} CE`;
}

function svgEl(name, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}

function bandRect(svg, { x, y, width, height, cls, title, onZoom }) {
  const rect = svgEl("rect", { x, y, width, height, class: cls, rx: 2 });
  if (onZoom) {
    rect.classList.add("zoomable");
    rect.addEventListener("click", () => onZoom.handler(onZoom.start, onZoom.end));
  }
  const titleEl = svgEl("title");
  titleEl.textContent = title;
  rect.append(titleEl);
  svg.append(rect);
  return rect;
}

const POLITY_LANE_HEIGHT = 18;
const REGION_HEADER_HEIGHT = 16;
const MAX_POLITIES_PER_REGION = 15;

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
function regionLaneCounts(tree, groupBy, regionKeys) {
  const counts = {};
  for (const key of regionKeys) {
    let maxLanes = 1;
    for (const chapter of tree.chapters) {
      const buckets = groupBy === "continent" ? chapter.polities_by_continent : chapter.polities_by_historical_region;
      const entries = buckets[key];
      if (!entries) continue;
      const lanes = packIntoLanes(entries.slice(0, MAX_POLITIES_PER_REGION));
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
      const lanes = packIntoLanes(shown);
      lanes.forEach((lane, laneIndex) => {
        lane.forEach((polity) => {
          const curatedClass = polity.curated ? "curated" : "heuristic";
          bandRect(svg, {
            x: scale.x(polity.start), y: rowY + laneIndex * POLITY_LANE_HEIGHT,
            width: scale.width(polity.start, polity.end), height: POLITY_LANE_HEIGHT - 2,
            cls: `hierarchy-band hierarchy-band-polity ${curatedClass}`,
            title: `${polity.canonical_name} (${entries.length} in ${regionLabel(key)})`,
            onZoom: { handler: onZoom, start: polity.start, end: polity.end ?? tree.axis.domain_end },
          });
        });
      });
    }
    rowY += laneCounts[key] * POLITY_LANE_HEIGHT + 4;
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
  const chapterLayouts = tree.chapters.map((chapter) => {
    const eraLanes = packIntoLanes([...chapter.eras].sort((a, b) => a.start - b.start));
    const allPeriods = chapter.eras.flatMap((era) => era.periods);
    const periodLanes = packIntoLanes([...allPeriods].sort((a, b) => a.start - b.start));
    return { chapter, eraLanes, periodLanes };
  });
  const maxEraLanes = Math.max(1, ...chapterLayouts.map((c) => c.eraLanes.length));
  const maxPeriodLanes = Math.max(1, ...chapterLayouts.map((c) => c.periodLanes.length));

  const eraRowHeight = maxEraLanes * eraLaneHeight;
  const periodRowHeight = maxPeriodLanes * periodLaneHeight;
  const regionKeys = collectRegionKeys(tree, groupBy);
  const laneCounts = regionLaneCounts(tree, groupBy, regionKeys);
  const politiesRowHeight = measurePolitiesRowHeight(regionKeys, laneCounts);
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

  for (const chapter of tree.chapters) {
    bandRect(svg, {
      x: scale.x(chapter.start), y, width: scale.width(chapter.start, chapter.end), height: chapterRowHeight,
      cls: "hierarchy-band hierarchy-band-chapter",
      title: `${chapter.canonical_name} (${formatYear(chapter.start)} - ${formatYear(chapter.end)})`,
      onZoom: { handler: onZoom, start: chapter.start, end: chapter.end },
    });
  }
  y += chapterRowHeight + rowGap;

  chapterLayouts.forEach(({ eraLanes }) => {
    eraLanes.forEach((lane, laneIndex) => {
      lane.forEach((era) => {
        bandRect(svg, {
          x: scale.x(era.start), y: y + laneIndex * eraLaneHeight,
          width: scale.width(era.start, era.end), height: eraLaneHeight - 2,
          cls: "hierarchy-band hierarchy-band-era", title: era.canonical_name,
          onZoom: { handler: onZoom, start: era.start, end: era.end },
        });
      });
    });
  });
  y += eraRowHeight + rowGap;

  chapterLayouts.forEach(({ periodLanes }) => {
    periodLanes.forEach((lane, laneIndex) => {
      lane.forEach((period) => {
        const curatedClass = period.curated ? "curated" : "heuristic";
        bandRect(svg, {
          x: scale.x(period.start), y: y + laneIndex * periodLaneHeight,
          width: scale.width(period.start, period.end), height: periodLaneHeight - 2,
          cls: `hierarchy-band hierarchy-band-period ${curatedClass}`, title: period.canonical_name,
          onZoom: { handler: onZoom, start: period.start, end: period.end },
        });
      });
    });
  });
  y += periodRowHeight + rowGap;

  renderPolitiesRow(svg, scale, tree, groupBy, regionKeys, laneCounts, y, onZoom);

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
