const card = document.querySelector("#type-review-card");
const progress = document.querySelector("#type-review-progress");
const status = document.querySelector("#type-decision-status");
const types = ["civilization", "polity", "subdivision", "micronation", "culture", "people", "tribe", "archaeological_horizon"];
let current = null;
let total = 0;
let deferredOffset = 0;
let submitting = false;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);
}

function displayTerm(value) {
  return String(value).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatYear(year) {
  if (year == null) return "present";
  return year < 0 ? `${Math.abs(year)} BCE` : `${year} CE`;
}

function typeExplanation(type) {
  return {
    civilization: "A broad and long-lived societal complex that may contain several cultures and polities. Examples: Ancient Egypt, Maya civilization.",
    polity: "A governed political organization, state, kingdom, empire, or comparable political unit. Examples: Roman Empire, Achaemenid Empire.",
    subdivision: "A canton, province, state, department, governorate, or other unit inside a larger political entity.",
    micronation: "A self-declared political project that lacks broad diplomatic recognition and is not treated as an ordinary sovereign polity.",
    culture: "A cultural or archaeological classification, not necessarily a state or a single people. Examples: Bell Beaker culture, Clovis culture.",
    people: "An ethnocultural population connected by shared identity, origin, language, or traditions. Examples: Franks, Māori.",
    tribe: "A socially or politically organized people without assuming sovereign statehood. Examples: Cherokee, Suebi.",
    archaeological_horizon: "A widespread archaeological trait or material horizon, not a political entity. Examples: Urnfield horizon, Châtelperronian horizon.",
  }[type];
}

function wikidataTypeLinks(qids) {
  return qids.map((qid) =>
    `<a data-type-qid="${escapeHtml(qid)}" href="https://www.wikidata.org/wiki/${encodeURIComponent(qid)}" target="_blank" rel="noopener noreferrer">${escapeHtml(qid)} ↗</a>`
  ).join(", ");
}

async function loadWikidataTypeLabels(reviewId, qids) {
  if (!qids.length) return;
  try {
    const parameters = new URLSearchParams({
      action: "wbgetentities", format: "json", formatversion: "2",
      ids: qids.join("|"), props: "labels", languages: "en", origin: "*",
    });
    const response = await fetch(`https://www.wikidata.org/w/api.php?${parameters}`);
    if (!response.ok) return;
    const entities = (await response.json()).entities || {};
    if (!current || current.id !== reviewId) return;
    qids.forEach((qid) => {
      const link = card.querySelector(`[data-type-qid="${qid}"]`);
      const label = entities[qid]?.labels?.en?.value;
      if (link && label) link.textContent = `${label} (${qid}) ↗`;
    });
  } catch (_) {
    // QID links remain usable when Wikidata is unavailable.
  }
}

async function loadNext() {
  const response = await fetch(`/api/type-reviews?limit=1&offset=${deferredOffset}`);
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  total = payload.total;
  current = payload.items[0] || null;
  const proposedGroup = current ? ` · Reviewing proposed ${displayTerm(current.proposed_type)} entities` : "";
  progress.textContent = `${total} type decisions remaining${proposedGroup}${deferredOffset ? ` · ${deferredOffset} deferred this session` : ""}`;
  if (!current) {
    card.innerHTML = "<h2>Queue complete</h2><p>All currently ambiguous entities have a reviewed type.</p>";
    return;
  }
  const wikidata = current.wikidata
    ? `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(current.wikidata)}" target="_blank" rel="noopener noreferrer">Wikidata (${escapeHtml(current.wikidata)}) ↗</a>` : "No Wikidata item";
  const wikipedia = current.wikipedia_en
    ? ` · <a href="${escapeHtml(current.wikipedia_en)}" target="_blank" rel="noopener noreferrer">Wikipedia (English) ↗</a>` : "";
  const evidence = (current.source_qids || []).map((qid) =>
    `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(qid)}" target="_blank" rel="noopener noreferrer">${escapeHtml(qid)} ↗</a>`).join(", ");
  const directTypeQids = current.direct_type_qids || [];
  card.innerHTML = `<p class="review-rank">Canonical Histomap entity to classify</p>
    <h2>${escapeHtml(current.canonical_name)}</h2>
    <p class="source-explanation">Choose the semantic type of this existing entity. The current proposal is <strong>${escapeHtml(displayTerm(current.proposed_type))}</strong> with ${escapeHtml(current.confidence)} confidence.</p>
    <dl class="source-facts">
      <dt>Histomap ID</dt><dd>${escapeHtml(current.id)}</dd>
      <dt>Dates</dt><dd>${formatYear(current.dates?.[0])}–${formatYear(current.dates?.[1])}</dd>
      <dt>Prominence</dt><dd>${Number(current.prominence_score || 0).toFixed(1)} / 100</dd>
      <dt>Record sources</dt><dd>${escapeHtml((current.sources || []).join(", ") || "not recorded")}</dd>
      <dt>External pages</dt><dd class="source-links">${wikidata}${wikipedia}</dd>
      <dt>Instance of (Wikidata)</dt><dd class="source-links">${wikidataTypeLinks(directTypeQids) || "Not recorded"}</dd>
      <dt>Classification evidence</dt><dd class="source-links">${evidence || "No mapped direct Wikidata type"}</dd>
      <dt>Why review is needed</dt><dd>${escapeHtml(current.reason)}</dd>
    </dl>
    <h3 class="candidate-heading">Choose an entity type</h3>
    <div class="type-choice-list">${types.map((type, index) => `<button type="button" class="type-choice ${type === current.proposed_type ? "is-proposed" : ""}" data-entity-type="${type}"><strong>${index + 1}. ${escapeHtml(displayTerm(type))}</strong><span>${escapeHtml(typeExplanation(type))}</span>${type === current.proposed_type ? "<small>Current automated proposal</small>" : ""}</button>`).join("")}</div>
    <div class="review-actions"><button id="defer-type" type="button">Defer</button></div>`;
  card.querySelectorAll(".type-choice").forEach((button) => button.addEventListener("click", () => decide(button.dataset.entityType)));
  card.querySelector("#defer-type").addEventListener("click", defer);
  loadWikidataTypeLabels(current.id, directTypeQids);
}

function disable(disabled) {
  card.querySelectorAll("button").forEach((button) => { button.disabled = disabled; });
}

async function decide(entityType) {
  if (!current || submitting) return;
  submitting = true;
  disable(true);
  status.className = "decision-status pending";
  status.textContent = "Saving classification…";
  try {
    const reviewed = current;
    const response = await fetch(`/api/type-reviews/${encodeURIComponent(reviewed.id)}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ entity_type: entityType }),
    });
    if (!response.ok) throw new Error((await response.json()).detail || await response.text());
    deferredOffset = Math.min(deferredOffset, Math.max(0, total - 2));
    status.className = "decision-status success";
    status.textContent = `Saved: ${reviewed.canonical_name} classified as ${displayTerm(entityType)}. Loading next…`;
    await loadNext();
  } catch (error) {
    status.className = "decision-status error";
    status.textContent = `Classification was not saved: ${error.message}`;
    disable(false);
  } finally {
    submitting = false;
  }
}

async function defer() {
  if (!current || submitting) return;
  deferredOffset = total > deferredOffset + 1 ? deferredOffset + 1 : 0;
  status.className = "decision-status success";
  status.textContent = `Deferred ${current.canonical_name}. Loading next…`;
  await loadNext();
}

document.addEventListener("keydown", (event) => {
  if (!current || submitting || event.target.matches("input, textarea, button, a, summary")) return;
  if (/^[1-8]$/.test(event.key)) {
    event.preventDefault();
    decide(types[Number(event.key) - 1]);
  } else if (event.key.toLowerCase() === "s") {
    event.preventDefault();
    defer();
  }
});

loadNext().catch((error) => { card.textContent = `Could not load type reviews: ${error.message}`; });
