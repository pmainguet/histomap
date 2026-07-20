const chart = document.querySelector("#chart");
const details = document.querySelector("#details");
const detailBackdrop = document.querySelector("#detail-backdrop");
const summary = document.querySelector("#summary");
const entitySearchInput = document.querySelector("#entity-search");
const entityOptions = document.querySelector("#entity-options");
const startInput = document.querySelector("#year-start");
const endInput = document.querySelector("#year-end");
const visibilityInput = document.querySelector("#visibility");
const readingLevelInput = document.querySelector("#reading-level");
const historicalGroupInput = document.querySelector("#historical-group");
const continentInput = document.querySelector("#continent");
const countryInput = document.querySelector("#country");
const colorLegend = document.querySelector("#color-legend");

const geographyColors = {
  africa: "#b56f55",
  asia: "#c6964f",
  europe: "#687f69",
  north_america: "#66899b",
  south_america: "#806f99",
  oceania: "#a6747b",
  antarctica: "#82969b",
  unknown: "#8b867d",
};
const geographyOrder = ["africa", "asia", "europe", "north_america", "south_america", "oceania", "antarctica", "unknown"];
let polities = [];
let detailTrigger = null;
let selectedPolity = null;
let focusedPolityId = null;
const collapsedGeographies = new Set();
const countryNames = new Intl.DisplayNames(["en"], { type: "region" });

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);
}

function displayTerm(value) {
  return String(value).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function entityLink(id) {
  const entity = polities.find((candidate) => candidate.id === id);
  const label = entity?.canonical_name || displayTerm(id);
  return entity ? `<button class="entity-link" type="button" data-entity-id="${escapeHtml(id)}">${escapeHtml(label)}</button>` : escapeHtml(label);
}

function formatYear(year) {
  if (year < 0) return `${Math.abs(year)} BCE`;
  return `${year} CE`;
}

function geographyGroup(polity) {
  const continents = polity.geography?.continents || [];
  if (polity.geography?.primary_continent) return polity.geography.primary_continent;
  if (continents.length) return geographyOrder.find((continent) => continents.includes(continent)) || continents[0];
  return "unknown";
}

function weightAt(polity, year) {
  const points = Object.entries(polity.weight_by_era).map(([y, w]) => [+y, +w]).sort((a, b) => a[0] - b[0]);
  if (!points.length) return 1;
  if (year <= points[0][0]) return points[0][1];
  if (year >= points.at(-1)[0]) return points.at(-1)[1];
  const upper = points.findIndex(([pointYear]) => pointYear >= year);
  const [y0, w0] = points[upper - 1];
  const [y1, w1] = points[upper];
  return w0 + (w1 - w0) * ((year - y0) / (y1 - y0));
}

function showDetails(polity, trigger = null) {
  selectedPolity = polity;
  if (trigger) detailTrigger = trigger;
  const description = readingLevelInput.value === "child"
    ? polity.text?.short_child_en || polity.text?.short_adult_en || polity.notes
    : polity.text?.short_adult_en || polity.text?.long_en || polity.notes;
  const descriptionText = description || "Draft record; description pending review.";
  const aliases = [polity.names?.aliases_en?.replaceAll(" | ", ", "), polity.names?.fr].filter(Boolean).join("; ");
  const countries = (polity.geography?.present_countries || []).map((code) => countryNames.of(code) || code);
  const centroid = polity.geography?.centroid;
  const duration = polity.end == null ? null : polity.end - polity.start;
  const successors = polity.successors || [];
  const wikidata = polity.external_ids?.wikidata;
  const wikipedia = polity.external_ids?.wikipedia_en || (wikidata ? `https://www.wikidata.org/wiki/Special:GoToLinkedPage/enwiki/${encodeURIComponent(wikidata)}` : "");
  const seshat = polity.external_ids?.seshat || [];
  const sources = (polity.sources || []).map(displayTerm);
  const externalLinks = [
    wikidata ? `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(wikidata)}" target="_blank" rel="noopener noreferrer">Wikidata (${escapeHtml(wikidata)}) ↗</a>` : "",
    wikipedia ? `<a href="${escapeHtml(wikipedia)}" target="_blank" rel="noopener noreferrer">Wikipedia (English) ↗</a>` : "",
    seshat.length ? `<a href="https://www.seshat-db.com/api/core/polities/?search=${encodeURIComponent(polity.canonical_name)}" target="_blank" rel="noopener noreferrer">Seshat (${escapeHtml(seshat.join(", "))}) ↗</a>` : "",
    centroid ? `<a href="https://www.openstreetmap.org/?mlat=${centroid.lat}&mlon=${centroid.lon}#map=5/${centroid.lat}/${centroid.lon}" target="_blank" rel="noopener noreferrer">View location ↗</a>` : "",
  ].filter(Boolean);
  details.innerHTML = `<button class="detail-close" type="button" aria-label="Close entity details">×</button>
    <h2>${escapeHtml(polity.canonical_name)}</h2>
    <p>${escapeHtml(descriptionText)}</p>
    <dl>
      <dt>Dates</dt><dd>${formatYear(polity.start)}–${polity.end == null ? "present" : formatYear(polity.end)}${duration ? ` (${duration.toLocaleString()} years)` : ""}</dd>
      ${aliases ? `<dt>Other names</dt><dd>${escapeHtml(aliases)}</dd>` : ""}
      <dt>Historical grouping</dt><dd>${escapeHtml(polity.region || "unclassified")}</dd>
      ${polity.parent ? `<dt>Part of</dt><dd>${entityLink(polity.parent)}</dd>` : ""}
      ${successors.length ? `<dt>Followed by</dt><dd>${successors.map(entityLink).join(", ")}</dd>` : ""}
      <dt>Continents</dt><dd>${escapeHtml((polity.geography?.continents || []).map(displayTerm).join(", ") || "unknown")}</dd>
      <dt>Present countries</dt><dd>${escapeHtml(countries.join(", ") || "unknown")}</dd>
      ${centroid ? `<dt>Approx. location</dt><dd>${centroid.lat.toFixed(2)}°, ${centroid.lon.toFixed(2)}°</dd>` : ""}
      <dt>Geography confidence</dt><dd>${escapeHtml(polity.geography?.confidence || "unknown")}</dd>
      <dt>Prominence</dt><dd>${Number(polity.prominence_score || 0).toFixed(2)} / 100 (${escapeHtml(polity.visibility_tier || "detailed")})</dd>
      <dt>Historical weight</dt><dd>${polity.weight_imputed ? "estimated" : "source-based"}</dd>
      <dt>Review status</dt><dd>${escapeHtml(polity.eligibility || "review")}</dd>
      <dt>Date confidence</dt><dd>start ${escapeHtml(polity.start_confidence || "unknown")}; end ${escapeHtml(polity.end_confidence || "unknown")}</dd>
      ${sources.length ? `<dt>Data sources</dt><dd>${escapeHtml(sources.join(", "))}</dd>` : ""}
      ${externalLinks.length ? `<dt>External pages</dt><dd class="detail-links">${externalLinks.join("<br>")}</dd>` : ""}
    </dl>
    `;
  details.querySelectorAll("[data-entity-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const entity = polities.find((candidate) => candidate.id === button.dataset.entityId);
      if (entity) showDetails(entity);
    });
  });
  details.querySelector(".detail-close").addEventListener("click", closeDetails);
  details.classList.add("is-open");
  detailBackdrop.classList.add("is-open");
  details.setAttribute("aria-hidden", "false");
  details.querySelector(".detail-close").focus();
}

function closeDetails() {
  details.classList.remove("is-open");
  detailBackdrop.classList.remove("is-open");
  details.setAttribute("aria-hidden", "true");
  detailTrigger?.focus();
}

detailBackdrop.addEventListener("click", closeDetails);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && details.classList.contains("is-open")) closeDetails();
});

function svgElement(name, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  return element;
}

function confidenceLevel(polity) {
  const rank = { high: 0, medium: 1, low: 2, legendary: 3 };
  const values = [polity.start_confidence, polity.end_confidence].filter(Boolean);
  return values.sort((a, b) => (rank[b] ?? 2) - (rank[a] ?? 2))[0] || "low";
}

function niceTickStep(span) {
  const rough = span / 9;
  const power = 10 ** Math.floor(Math.log10(rough));
  const ratio = rough / power;
  return (ratio <= 1 ? 1 : ratio <= 2 ? 2 : ratio <= 5 ? 5 : 10) * power;
}

function render() {
  const yearStart = Number(startInput.value);
  const yearEnd = Number(endInput.value);
  if (!Number.isFinite(yearStart) || !Number.isFinite(yearEnd) || yearEnd <= yearStart) {
    chart.innerHTML = '<p class="error">Choose an end year later than the start year.</p>';
    return;
  }
  const tierRank = { global: 0, regional: 1, detailed: 2 };
  const selectedRank = tierRank[visibilityInput.value];
  const matched = polities.filter(
    (p) =>
      p.eligibility !== "excluded" &&
      (p.id === focusedPolityId || visibilityInput.value === "detailed" || p.eligibility === "accepted") &&
      (!historicalGroupInput.value || p.region === historicalGroupInput.value) &&
      (!continentInput.value || (p.geography?.continents || []).includes(continentInput.value)) &&
      (!countryInput.value || (p.geography?.present_countries || []).includes(countryInput.value)) &&
      (p.id === focusedPolityId || tierRank[p.visibility_tier || "detailed"] <= selectedRank) &&
      p.start < yearEnd &&
      (p.end == null || p.end > yearStart),
  );
  matched.sort((a, b) => {
    const groupDifference = geographyOrder.indexOf(geographyGroup(a)) - geographyOrder.indexOf(geographyGroup(b));
    return groupDifference || a.start - b.start || a.canonical_name.localeCompare(b.canonical_name);
  });
  const span = yearEnd - yearStart;
  const rowHeight = 25;
  const laneHeaderHeight = 27;
  const margin = { top: 48, right: 24, bottom: 24, left: 24 };
  const pixelsPerYear = Math.max(.2, Math.min(2, 1500 / span));
  const width = Math.max(900, Math.min(4800, span * pixelsPerYear + margin.left + margin.right));
  const groups = geographyOrder
    .map((name) => ({ name, items: matched.filter((polity) => geographyGroup(polity) === name) }))
    .filter((group) => group.items.length);
  const visible = groups.flatMap((group) => collapsedGeographies.has(group.name) ? [] : group.items);
  const height = Math.max(180, visible.length * rowHeight + groups.length * laneHeaderHeight + margin.top + margin.bottom);
  const innerWidth = width - margin.left - margin.right;
  const x = (year) => margin.left + ((year - yearStart) / span) * innerWidth;
  const svg = svgElement("svg", { viewBox: `0 0 ${width} ${height}`, width, height });
  const definitions = svgElement("defs");
  svg.append(definitions);

  const rowCenters = new Map();
  let laneY = margin.top;
  for (const group of groups) {
    const collapsed = collapsedGeographies.has(group.name);
    const laneHeight = laneHeaderHeight + (collapsed ? 0 : group.items.length * rowHeight);
    svg.append(svgElement("rect", { x: margin.left, y: laneY, width: innerWidth, height: laneHeight, class: "swimlane" }));
    svg.append(svgElement("rect", { x: margin.left, y: laneY, width: 4, height: laneHeight, fill: geographyColors[group.name] }));
    const laneToggle = svgElement("rect", {
      x: margin.left + 4, y: laneY, width: innerWidth - 4, height: laneHeaderHeight,
      class: "swimlane-toggle", tabindex: "0", role: "button",
      "data-geography": group.name,
      "aria-label": `${collapsed ? "Expand" : "Collapse"} ${displayTerm(group.name)} swimlane`,
    });
    const toggleGroup = (restoreFocus = false) => {
      if (collapsedGeographies.has(group.name)) collapsedGeographies.delete(group.name);
      else collapsedGeographies.add(group.name);
      render();
      if (restoreFocus) chart.querySelector(`[data-geography="${group.name}"]`)?.focus();
    };
    laneToggle.addEventListener("click", () => toggleGroup());
    laneToggle.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggleGroup(true);
      }
    });
    svg.append(laneToggle);
    const laneLabel = svgElement("text", { x: margin.left + 11, y: laneY + 18, class: "swimlane-label" });
    laneLabel.textContent = `${collapsed ? "▸" : "▾"} ${displayTerm(group.name)} · ${group.items.length}`;
    svg.append(laneLabel);
    if (!collapsed) group.items.forEach((polity, index) => rowCenters.set(polity.id, laneY + laneHeaderHeight + index * rowHeight + rowHeight / 2));
    laneY += laneHeight;
  }

  const tickStep = niceTickStep(span);
  for (let year = Math.ceil(yearStart / tickStep) * tickStep; year <= yearEnd; year += tickStep) {
    svg.append(svgElement("line", { x1: x(year), x2: x(year), y1: margin.top - 10, y2: height - margin.bottom, class: "grid-line" }));
    const label = svgElement("text", { x: x(year), y: margin.top - 20, "text-anchor": "middle", class: "axis-label" });
    label.textContent = formatYear(year);
    svg.append(label);
  }

  visible.forEach((polity, index) => {
    const start = Math.max(yearStart, polity.start);
    const end = Math.min(yearEnd, polity.end ?? yearEnd);
    const mid = start + (end - start) / 2;
    const bandHeight = Math.min(rowHeight - 3, 6 + weightAt(polity, mid) * 1.55);
    const center = rowCenters.get(polity.id);
    const bandX = x(start);
    const bandWidth = Math.max(2, x(end) - bandX);
    const confidence = confidenceLevel(polity);
    const path = svgElement("rect", {
      x: bandX,
      y: center - bandHeight / 2,
      width: bandWidth,
      height: bandHeight,
      rx: "1",
      fill: geographyColors[geographyGroup(polity)] || geographyColors.unknown,
      opacity: { high: .92, medium: .74, low: .52, legendary: .38 }[confidence],
      class: `band confidence-${confidence}`,
      tabindex: "0",
      "data-polity-id": polity.id,
    });
    path.addEventListener("click", () => showDetails(polity, path));
    path.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        showDetails(polity, path);
      }
    });
    const title = svgElement("title");
    title.textContent = `${polity.canonical_name}: ${formatYear(polity.start)}–${polity.end == null ? "present" : formatYear(polity.end)}`;
    path.append(title);
    svg.append(path);

    if (bandWidth >= 18) {
      const clipId = `band-label-${index}`;
      const clipPath = svgElement("clipPath", { id: clipId });
      clipPath.append(
        svgElement("rect", {
          x: bandX + 3,
          y: center - bandHeight / 2,
          width: Math.max(0, bandWidth - 6),
          height: bandHeight,
        }),
      );
      definitions.append(clipPath);
      const label = svgElement("text", {
        x: bandX + 6,
        y: center + 4,
        "text-anchor": "start",
        "clip-path": `url(#${clipId})`,
        class: "band-label",
      });
      label.textContent = polity.canonical_name;
      svg.append(label);
    }
  });

  chart.replaceChildren(svg);
  colorLegend.innerHTML = `<span>Band color</span>${groups.map((group) => `<i style="--legend-color:${geographyColors[group.name]}"></i>${escapeHtml(displayTerm(group.name))}`).join("")}`;
  const collapsedCount = groups.filter((group) => collapsedGeographies.has(group.name)).length;
  summary.textContent = `${matched.length} of ${polities.length} polities matched${collapsedCount ? ` · ${collapsedCount} lane${collapsedCount === 1 ? "" : "s"} collapsed` : ""}`;
}

document.querySelector("#apply").addEventListener("click", render);
visibilityInput.addEventListener("change", render);
readingLevelInput.addEventListener("change", () => {
  if (selectedPolity && details.classList.contains("is-open")) showDetails(selectedPolity);
});
historicalGroupInput.addEventListener("change", render);
continentInput.addEventListener("change", render);
countryInput.addEventListener("change", render);

function findEntity(query) {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return null;
  const names = (polity) => [
    polity.id,
    polity.canonical_name,
    ...(polity.names?.aliases_en || "").split("|"),
  ].map((value) => value.trim().toLocaleLowerCase());
  const exact = polities.filter((polity) => names(polity).includes(needle));
  const partial = polities.filter((polity) => names(polity).some((value) => value.includes(needle)));
  return (exact.length ? exact : partial).sort((a, b) => Number(b.prominence_score || 0) - Number(a.prominence_score || 0))[0] || null;
}

function selectEntity() {
  if (!entitySearchInput.value.trim()) {
    focusedPolityId = null;
    render();
    return;
  }
  const polity = findEntity(entitySearchInput.value);
  if (!polity) {
    summary.textContent = `No entity found for "${entitySearchInput.value}"`;
    return;
  }
  focusedPolityId = polity.id;
  entitySearchInput.value = polity.canonical_name;
  historicalGroupInput.value = "";
  continentInput.value = "";
  countryInput.value = "";
  collapsedGeographies.delete(geographyGroup(polity));
  if (polity.start < Number(startInput.value)) startInput.value = Math.floor(polity.start / 100) * 100;
  const polityEnd = polity.end ?? new Date().getFullYear();
  if (polityEnd > Number(endInput.value)) endInput.value = Math.ceil(polityEnd / 100) * 100;
  render();
  const band = chart.querySelector(`[data-polity-id="${polity.id}"]`);
  if (band) showDetails(polity, band);
}

entitySearchInput.addEventListener("change", selectEntity);
entitySearchInput.addEventListener("search", () => {
  if (!entitySearchInput.value) selectEntity();
});
entitySearchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    selectEntity();
  }
});

function populateSelect(select, values, formatter = (value) => value) {
  for (const value of [...values].sort()) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = formatter(value);
    select.append(option);
  }
}

try {
  const response = await fetch("/data.json");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  polities = await response.json();
  for (const name of [...new Set(polities.map((polity) => polity.canonical_name))].sort()) {
    const option = document.createElement("option");
    option.value = name;
    entityOptions.append(option);
  }
  populateSelect(
    continentInput,
    new Set(polities.flatMap((p) => p.geography?.continents || [])),
    (value) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()),
  );
  populateSelect(historicalGroupInput, new Set(polities.map((p) => p.region).filter(Boolean)), displayTerm);
  populateSelect(countryInput, new Set(polities.flatMap((p) => p.geography?.present_countries || [])));
  if (polities.length) {
    startInput.value = Math.max(-8000, Math.min(...polities.map((p) => p.start)));
    endInput.value = new Date().getFullYear();
  }
  render();
} catch (error) {
  chart.innerHTML = `<p class="error">Could not load data.json (${error.message}). Run the build and serve commands from the repository root.</p>`;
}
