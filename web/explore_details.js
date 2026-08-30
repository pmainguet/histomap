// Informational detail panel for /explore -- mirrors app.js's showDetails/
// showPeriodDetails (the "/" timeline's panel) but read-only: dates,
// authority, geography, links. No editing actions (edit geography, edit
// entity type, edit period type, convert to entity) -- those stay on "/"
// as curation tools; /explore is a browse view. See ROADMAP.md.

const explorePanel = document.querySelector("#details");
const explorePanelBackdrop = document.querySelector("#detail-backdrop");

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);
}

function displayTerm(value) {
  return String(value).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

const exploreCountryNames = new Intl.DisplayNames(["en"], { type: "region" });

const TIER_KICKER = {
  macro_chapter: "Macro chapter",
  regional_era: "Regional era",
  period: "Period",
};

// A record's own id may not resolve (e.g. a broader_periods/successor
// pointing at something outside the currently-loaded set) -- fall back to
// a displayable version of the raw id rather than showing nothing.
function periodLabel(periodsById, id) {
  return periodsById.get(id)?.canonical_name || displayTerm(id);
}

function polityLabel(politiesById, id) {
  return politiesById.get(id)?.canonical_name || displayTerm(id);
}

function periodRefButton(periodsById, id) {
  const label = periodLabel(periodsById, id);
  return periodsById.has(id)
    ? `<button class="entity-link" type="button" data-explore-period-id="${escapeHtml(id)}">${escapeHtml(label)}</button>`
    : escapeHtml(label);
}

function polityRefButton(politiesById, id) {
  const label = polityLabel(politiesById, id);
  return politiesById.has(id)
    ? `<button class="entity-link" type="button" data-explore-polity-id="${escapeHtml(id)}">${escapeHtml(label)}</button>`
    : escapeHtml(label);
}

function externalLinksForPeriod(period) {
  const links = Object.entries(period.external_ids || {}).map(([source, value]) => {
    const url = String(value).startsWith("http") ? value
      : source === "wikidata" ? `https://www.wikidata.org/wiki/${encodeURIComponent(value)}` : "";
    return url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(displayTerm(source))} ↗</a>` : "";
  }).filter(Boolean);
  links.push(...(period.source_urls || []).map((url, index) =>
    `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Source ${index + 1} ↗</a>`));
  return links;
}

function externalLinksForPolity(polity) {
  const wikidata = polity.external_ids?.wikidata;
  const wikipedia = polity.external_ids?.wikipedia_en
    || (wikidata ? `https://www.wikidata.org/wiki/Special:GoToLinkedPage/enwiki/${encodeURIComponent(wikidata)}` : "");
  const seshat = polity.external_ids?.seshat || [];
  const centroid = polity.geography?.centroid;
  return [
    wikidata ? `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(wikidata)}" target="_blank" rel="noopener noreferrer">Wikidata (${escapeHtml(wikidata)}) ↗</a>` : "",
    wikipedia ? `<a href="${escapeHtml(wikipedia)}" target="_blank" rel="noopener noreferrer">Wikipedia (English) ↗</a>` : "",
    seshat.length ? `<a href="https://www.seshat-db.com/api/core/polities/?search=${encodeURIComponent(polity.canonical_name)}" target="_blank" rel="noopener noreferrer">Seshat (${escapeHtml(seshat.join(", "))}) ↗</a>` : "",
    centroid ? `<a href="https://www.openstreetmap.org/?mlat=${centroid.lat}&mlon=${centroid.lon}#map=5/${centroid.lat}/${centroid.lon}" target="_blank" rel="noopener noreferrer">View location ↗</a>` : "",
  ].filter(Boolean);
}

function renderPeriodDetails(period, ctx) {
  const { periodsById, politiesById, periodLinks, onZoomToRange } = ctx;
  const countries = (period.geography?.present_countries || []).map((code) => exploreCountryNames.of(code) || code);
  const contained = [...periodsById.values()].filter((candidate) => (candidate.broader_periods || []).includes(period.id));
  const predecessors = [...periodsById.values()].filter((candidate) => (candidate.successors || []).includes(period.id));
  const linked = periodLinks.filter((link) => link.period_id === period.id);
  const externalLinks = externalLinksForPeriod(period);

  explorePanel.innerHTML = `<button class="detail-close" type="button" aria-label="Close details">×</button>
    <p class="detail-kicker">${escapeHtml(TIER_KICKER[period.tier] || "Period")}</p>
    <h2>${escapeHtml(period.canonical_name)}</h2>
    <div class="detail-actions"><button class="zoom-explore" type="button">Zoom to this</button><button class="reset-explore" type="button">Full timeline</button></div>
    <p>${escapeHtml(period.notes || "Sourced chronological context; this record is not a polity.")}</p>
    <dl>
      <dt>Dates</dt><dd>${formatYear(period.start)}–${formatYear(period.end)}</dd>
      <dt>Period type</dt><dd>${escapeHtml(displayTerm(period.kind))}</dd>
      <dt>Authority</dt><dd>${escapeHtml(period.authority || "unknown")}</dd>
      <dt>Continents</dt><dd>${escapeHtml((period.geography?.continents || []).map(displayTerm).join(", ") || "unknown")}</dd>
      <dt>Present countries</dt><dd>${escapeHtml(countries.join(", ") || "unknown")}</dd>
      ${(period.geography?.historical_regions || []).length ? `<dt>Historical regions</dt><dd>${escapeHtml(period.geography.historical_regions.map(displayTerm).join(", "))}</dd>` : ""}
      ${(period.broader_periods || []).length ? `<dt>Part of</dt><dd>${period.broader_periods.map((id) => periodRefButton(periodsById, id)).join(", ")}</dd>` : ""}
      ${contained.length ? `<dt>Contains</dt><dd>${contained.map((item) => periodRefButton(periodsById, item.id)).join(", ")}</dd>` : ""}
      ${predecessors.length ? `<dt>Preceded by</dt><dd>${predecessors.map((item) => periodRefButton(periodsById, item.id)).join(", ")}</dd>` : ""}
      ${(period.successors || []).length ? `<dt>Followed by</dt><dd>${period.successors.map((id) => periodRefButton(periodsById, id)).join(", ")}</dd>` : ""}
      ${linked.length ? `<dt>Linked entities</dt><dd class="detail-links">${linked.map((link) => `${polityRefButton(politiesById, link.entity_id)} <small>${escapeHtml(link.evidence)}, ${escapeHtml(link.confidence)}</small>`).join("<br>")}</dd>` : ""}
      ${externalLinks.length ? `<dt>External pages</dt><dd class="detail-links">${externalLinks.join("<br>")}</dd>` : ""}
    </dl>`;

  wireExplorePanel(ctx, period.start, period.end);
  explorePanel.querySelectorAll("[data-explore-period-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = periodsById.get(button.dataset.explorePeriodId);
      if (target) renderPeriodDetails(target, ctx);
    });
  });
  explorePanel.querySelectorAll("[data-explore-polity-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = politiesById.get(button.dataset.explorePolityId);
      if (target) renderPolityDetails(target, ctx);
    });
  });
}

function renderPolityDetails(polity, ctx) {
  const { periodsById, politiesById, periodLinks, onZoomToRange } = ctx;
  const description = polity.text?.short_adult_en || polity.text?.long_en || polity.notes;
  const descriptionText = description || "Draft record; description pending review.";
  const aliases = [polity.names?.aliases_en?.replaceAll(" | ", ", "), polity.names?.fr].filter(Boolean).join("; ");
  const countries = (polity.geography?.present_countries || []).map((code) => exploreCountryNames.of(code) || code);
  const centroid = polity.geography?.centroid;
  const duration = polity.end == null ? null : polity.end - polity.start;
  const children = [...politiesById.values()].filter((candidate) => candidate.parent === polity.id);
  const predecessors = [...politiesById.values()].filter((candidate) => (candidate.successors || []).includes(polity.id));
  const relevantPeriods = periodLinks.filter((link) => link.entity_id === polity.id);
  const externalLinks = externalLinksForPolity(polity);

  explorePanel.innerHTML = `<button class="detail-close" type="button" aria-label="Close details">×</button>
    <h2>${escapeHtml(polity.canonical_name)}</h2>
    <div class="detail-actions"><button class="zoom-explore" type="button">Zoom to this</button><button class="reset-explore" type="button">Full timeline</button></div>
    <p>${escapeHtml(descriptionText)}</p>
    <dl>
      <dt>Dates</dt><dd>${formatYear(polity.start)}–${polity.end == null ? "present" : formatYear(polity.end)}${duration ? ` (${duration.toLocaleString()} years)` : ""}</dd>
      <dt>Entity type</dt><dd>${escapeHtml(displayTerm(polity.entity_type || "polity"))}</dd>
      ${aliases ? `<dt>Other names</dt><dd>${escapeHtml(aliases)}</dd>` : ""}
      ${polity.parent ? `<dt>Part of</dt><dd>${polityRefButton(politiesById, polity.parent)}</dd>` : ""}
      ${children.length ? `<dt>Contains</dt><dd>${children.map((item) => polityRefButton(politiesById, item.id)).join(", ")}</dd>` : ""}
      ${predecessors.length ? `<dt>Preceded by</dt><dd>${predecessors.map((item) => polityRefButton(politiesById, item.id)).join(", ")}</dd>` : ""}
      ${(polity.successors || []).length ? `<dt>Followed by</dt><dd>${polity.successors.map((id) => polityRefButton(politiesById, id)).join(", ")}</dd>` : ""}
      <dt>Continents</dt><dd>${escapeHtml((polity.geography?.continents || []).map(displayTerm).join(", ") || "unknown")}</dd>
      <dt>Present countries</dt><dd>${escapeHtml(countries.join(", ") || "unknown")}</dd>
      ${centroid ? `<dt>Approx. location</dt><dd>${centroid.lat.toFixed(2)}°, ${centroid.lon.toFixed(2)}°</dd>` : ""}
      <dt>Prominence</dt><dd>${Number(polity.prominence_score || 0).toFixed(2)} / 100 (${escapeHtml(polity.visibility_tier || "detailed")})</dd>
      <dt>Historical weight</dt><dd>${polity.weight_imputed ? "estimated" : "source-based"}</dd>
      ${(polity.sources || []).length ? `<dt>Data sources</dt><dd>${escapeHtml(polity.sources.map(displayTerm).join(", "))}</dd>` : ""}
      ${relevantPeriods.length ? `<dt>Historical periods</dt><dd class="detail-links">${relevantPeriods.map((link) => `${periodRefButton(periodsById, link.period_id)} <small>${escapeHtml(link.evidence)}, ${escapeHtml(link.confidence)}</small>`).join("<br>")}</dd>` : ""}
      ${externalLinks.length ? `<dt>External pages</dt><dd class="detail-links">${externalLinks.join("<br>")}</dd>` : ""}
    </dl>`;

  wireExplorePanel(ctx, polity.start, polity.end ?? ctx.domainEnd);
  explorePanel.querySelectorAll("[data-explore-polity-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = politiesById.get(button.dataset.explorePolityId);
      if (target) renderPolityDetails(target, ctx);
    });
  });
  explorePanel.querySelectorAll("[data-explore-period-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = periodsById.get(button.dataset.explorePeriodId);
      if (target) renderPeriodDetails(target, ctx);
    });
  });
}

function wireExplorePanel(ctx, start, end) {
  explorePanel.querySelector(".detail-close").addEventListener("click", closeExploreDetails);
  explorePanel.querySelector(".zoom-explore").addEventListener("click", () => {
    closeExploreDetails();
    ctx.onZoomToRange(start, end);
  });
  explorePanel.querySelector(".reset-explore").addEventListener("click", () => {
    closeExploreDetails();
    ctx.onResetZoom();
  });
  explorePanel.classList.add("is-open");
  explorePanelBackdrop.classList.add("is-open");
  explorePanel.setAttribute("aria-hidden", "false");
  explorePanel.querySelector(".detail-close").focus();
}

function closeExploreDetails() {
  explorePanel.classList.remove("is-open");
  explorePanelBackdrop.classList.remove("is-open");
  explorePanel.setAttribute("aria-hidden", "true");
}

explorePanelBackdrop.addEventListener("click", closeExploreDetails);

// kind: "chapter" | "era" | "period" -> periodsById; "polity" -> politiesById.
// Silently no-ops if the id isn't found (e.g. data not loaded yet) rather
// than throwing and breaking the click handler for every other band.
function showExploreDetails(kind, id, ctx) {
  if (kind === "polity") {
    const polity = ctx.politiesById.get(id);
    if (polity) renderPolityDetails(polity, ctx);
    return;
  }
  const period = ctx.periodsById.get(id);
  if (period) renderPeriodDetails(period, ctx);
}
