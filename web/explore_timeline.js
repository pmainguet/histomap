function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);
}

function formatYear(year) {
  if (year === null || year === undefined) return "present";
  return year < 0 ? `${Math.abs(year).toLocaleString()} BCE` : `${year.toLocaleString()} CE`;
}

function svgEl(name, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}

function bandRect(svg, { x, y, width, height, cls, title, href }) {
  const group = href ? svgEl("a", { href }) : null;
  const rect = svgEl("rect", { x, y, width, height, class: cls, rx: 2 });
  const titleEl = svgEl("title");
  titleEl.textContent = title;
  rect.append(titleEl);
  if (group) { group.append(rect); svg.append(group); } else { svg.append(rect); }
  return rect;
}

function renderHierarchyTimeline(tree, container) {
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
  const height = geoRowHeight + chapterRowHeight + eraRowHeight + periodRowHeight + rowGap * 4;

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
      href: `/?era=${encodeURIComponent(chapter.id)}`,
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
        });
      });
    });
  });

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
