const card = document.querySelector("#consolidation-review-card");
const progress = document.querySelector("#consolidation-review-progress");
const status = document.querySelector("#consolidation-decision-status");
let current = null;
let total = 0;
let deferredOffset = 0;
let submitting = false;
const phaseKeys = ["Q", "W", "E", "R", "T"];
const partKeys = ["Y", "U", "I", "O", "L"];
const inversePhaseKeys = ["A", "D", "F", "G", "H"];
const inversePartKeys = ["Z", "C", "V", "B", "N"];

function escapeHtml(value) { return String(value).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"})[c]); }
function formatYear(year) { return year == null ? "present" : year < 0 ? `${Math.abs(year)} BCE` : `${year} CE`; }
function links(item) { return item.wikidata ? `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(item.wikidata)}" target="_blank" rel="noopener noreferrer">Wikidata (${escapeHtml(item.wikidata)}) ↗</a>` : "No Wikidata item"; }
function typeLinks(item) { return (item.direct_type_qids || []).map((qid) => `<a data-wikidata-label="${escapeHtml(qid)}" href="https://www.wikidata.org/wiki/${encodeURIComponent(qid)}" target="_blank" rel="noopener noreferrer">${escapeHtml(qid)} ↗</a>`).join(", ") || "Not recorded"; }
function dateRange(item) { return `${formatYear(item.dates[0])}–${formatYear(item.dates[1])}`; }
function countries(item) { return escapeHtml((item.present_countries || []).join(", ") || "not recorded"); }
function comparisonRow(label, candidateValue, reviewedValue, assessment = "") {
  return `<tr class="${assessment ? `comparison-${assessment}` : ""}"><th scope="row">${label}</th><td>${candidateValue}</td><td>${reviewedValue}</td></tr>`;
}

function candidateMarkup(candidate, index) {
  return `<article class="candidate consolidation-candidate">
    <p class="candidate-number">Candidate ${index + 1}</p><div class="comparison-heading"><strong>${escapeHtml(candidate.canonical_name)}</strong><span class="evidence-badge ${candidate.confidence}">${escapeHtml(candidate.confidence)} confidence</span></div>
    <p class="wikidata-description" data-wikidata-description="${escapeHtml(candidate.wikidata || "")}"></p>
    <div class="comparison-table-wrap"><table class="comparison-table"><thead><tr><th>Field</th><th>Candidate</th><th>Reviewed entity</th></tr></thead><tbody>
      ${comparisonRow("Name", escapeHtml(candidate.canonical_name), escapeHtml(current.canonical_name), candidate.exact_name_match ? "match" : "review")}
      ${comparisonRow("Histomap ID", escapeHtml(candidate.id), escapeHtml(current.id))}
      ${comparisonRow("Type", escapeHtml(candidate.entity_type), escapeHtml(current.entity_type), candidate.type_match ? "match" : "conflict")}
      ${comparisonRow("Dates", dateRange(candidate), dateRange(current), candidate.date_contains ? "match" : candidate.date_overlap ? "review" : "conflict")}
      ${comparisonRow("Present countries", countries(candidate), countries(current), candidate.geography_match ? "match" : (!candidate.present_countries.length || !current.present_countries.length) ? "unknown" : "conflict")}
      ${comparisonRow("Instance of", `<span class="source-links">${typeLinks(candidate)}</span>`, `<span class="source-links">${typeLinks(current)}</span>`)}
      ${comparisonRow("Wikidata", `<span class="source-links">${links(candidate)}</span>`, `<span class="source-links">${links(current)}</span>`, candidate.same_wikidata ? "match" : "review")}
    </tbody></table></div>
    <p class="proposal-reason"><strong>Why suggested:</strong> ${escapeHtml(candidate.reasons.join("; "))}.</p>
    <div class="review-actions relationship-directions"><button type="button" data-decision="same_entity" data-target="${escapeHtml(candidate.id)}">${index + 1}. Same entity</button><button type="button" data-decision="phase_of" data-target="${escapeHtml(candidate.id)}">${phaseKeys[index]}. Reviewed → phase of candidate</button><button type="button" data-decision="candidate_phase_of" data-target="${escapeHtml(candidate.id)}">${inversePhaseKeys[index]}. Candidate → phase of reviewed</button><button type="button" data-decision="part_of" data-target="${escapeHtml(candidate.id)}">${partKeys[index]}. Reviewed → part of candidate</button><button type="button" data-decision="candidate_part_of" data-target="${escapeHtml(candidate.id)}">${inversePartKeys[index]}. Candidate → part of reviewed</button></div>
  </article>`;
}

async function loadWikidataEvidence(item) {
  const qids = [...new Set([item.wikidata, ...(item.direct_type_qids || []), ...item.candidates.flatMap((candidate) => [candidate.wikidata, ...(candidate.direct_type_qids || [])])].filter(Boolean))];
  if (!qids.length) return;
  try {
    const parameters = new URLSearchParams({action:"wbgetentities",format:"json",formatversion:"2",ids:qids.join("|"),props:"labels|descriptions",languages:"en",origin:"*"});
    const response = await fetch(`https://www.wikidata.org/w/api.php?${parameters}`);
    if (!response.ok || !current || current.id !== item.id) return;
    const entities = (await response.json()).entities || {};
    card.querySelectorAll("[data-wikidata-label]").forEach((link) => { const qid = link.dataset.wikidataLabel; const label = entities[qid]?.labels?.en?.value; if (label) link.textContent = `${label} (${qid}) ↗`; });
    card.querySelectorAll("[data-wikidata-description]").forEach((element) => { const description = entities[element.dataset.wikidataDescription]?.descriptions?.en?.value; element.textContent = description || "No English Wikidata description."; });
  } catch (_) { /* Linked QIDs remain available when Wikidata is unavailable. */ }
}

async function loadNext() {
  const response = await fetch(`/api/consolidation-reviews?limit=1&offset=${deferredOffset}`);
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json(); total = payload.total; current = payload.items[0] || null;
  progress.textContent = `${total} canonical identity decisions remaining${deferredOffset ? ` · ${deferredOffset} deferred this session` : ""}`;
  if (!current) { card.innerHTML = "<h2>Queue complete</h2><p>No unresolved identity or period-role cases remain.</p>"; return; }
  const canBePeriod = current.dates[1] != null;
  const periodActions = canBePeriod ? `<section class="period-role-actions"><h3>Broad time period or era</h3><p>Use only for chronology shared by several civilizations, polities, or cultures—for example the Bronze Age, Hellenistic period, Early Middle Ages, or Victorian era. Do not use this for a phase belonging to one polity.</p><div class="review-actions"><button type="button" data-decision="period"><kbd>P</kbd> Broad period/era</button></div></section>` : "";
  const candidateSection = current.candidates.length ? `<h3 class="candidate-heading">Other canonical Histomap records with compatible evidence</h3><div class="candidate-list">${current.candidates.map(candidateMarkup).join("")}</div>` : `<p class="proposal-reason">No compatible canonical target was suggested. Decide whether this is an independent entity or belongs on the period layer.</p>`;
  card.innerHTML = `<p class="review-rank"><span class="record-badge">Histomap entity</span> Canonical record being checked</p><h2>${escapeHtml(current.canonical_name)}</h2><p class="wikidata-description" data-wikidata-description="${escapeHtml(current.wikidata || "")}"></p><dl class="source-facts"><dt>Histomap ID</dt><dd>${escapeHtml(current.id)}</dd><dt>Type</dt><dd>${escapeHtml(current.entity_type)}</dd><dt>Dates</dt><dd>${formatYear(current.dates[0])}–${formatYear(current.dates[1])}</dd><dt>Present countries</dt><dd>${escapeHtml(current.present_countries.join(", ") || "not recorded")}</dd><dt>Instance of</dt><dd class="source-links">${typeLinks(current)}</dd><dt>External page</dt><dd class="source-links">${links(current)}</dd></dl>${candidateSection}${periodActions}<section class="all-entity-search"><h3>Choose another parent polity</h3><p>Search here when the reviewed record is a phase or constituent part of a polity that was not suggested. For sibling phases, select their shared parent and review each sibling separately.</p><form class="entity-search-form"><input type="search" minlength="2" placeholder="Parent polity name"><button type="submit">Search</button></form><div class="entity-search-results"></div></section><div class="review-actions"><button type="button" id="keep-independent"><kbd>K</kbd> Independent entity</button><button type="button" id="discard-entity" class="danger"><kbd>X</kbd> Discard from Histomap</button><button type="button" id="defer-consolidation"><kbd>S</kbd> Defer</button></div>`;
  card.querySelectorAll("[data-decision]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.decision, button.dataset.target)));
  card.querySelector("#keep-independent").addEventListener("click", () => decide("independent"));
  card.querySelector("#discard-entity").addEventListener("click", () => decide("discarded"));
  card.querySelector("#defer-consolidation").addEventListener("click", defer);
  card.querySelector(".entity-search-form").addEventListener("submit", search);
  loadWikidataEvidence(current);
}

async function search(event) {
  event.preventDefault(); const input = event.currentTarget.querySelector("input"); const results = card.querySelector(".entity-search-results");
  const response = await fetch(`/api/polities/search?q=${encodeURIComponent(input.value)}&limit=8`);
  if (!response.ok) { results.textContent = "Search failed."; return; }
  const payload = await response.json();
  results.innerHTML = payload.items.filter((item) => item.polity_id !== current.id).map((item) => `<div class="search-result"><div><strong>${escapeHtml(item.canonical_name)}</strong><span><span class="record-badge">Histomap entity</span> ${escapeHtml(item.entity_type)} · ${formatYear(item.canonical_start)}–${formatYear(item.canonical_end)}</span></div><span class="review-actions"><button type="button" data-search-decision="same_entity" data-target="${escapeHtml(item.polity_id)}">Same entity</button><button type="button" data-search-decision="phase_of" data-target="${escapeHtml(item.polity_id)}">Phase of this polity</button><button type="button" data-search-decision="part_of" data-target="${escapeHtml(item.polity_id)}">Part of this polity</button></span></div>`).join("") || "No matches.";
  results.querySelectorAll("[data-search-decision]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.searchDecision, button.dataset.target)));
}

async function decide(decision, targetId = null) {
  if (!current || submitting) return;
  submitting = true; card.querySelectorAll("button").forEach((button) => { button.disabled = true; }); status.className = "decision-status pending"; status.textContent = "Saving canonical identity decision…";
  try { const reviewed = current; const response = await fetch(`/api/consolidation-reviews/${encodeURIComponent(reviewed.id)}`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision,target_id:targetId})}); if (!response.ok) throw new Error((await response.json()).detail || await response.text()); deferredOffset = Math.min(deferredOffset, Math.max(0, total - 2)); status.className = "decision-status success"; status.textContent = `Saved ${reviewed.canonical_name}. Loading next…`; await loadNext(); }
  catch (error) { status.className = "decision-status error"; status.textContent = `Decision was not saved: ${error.message}`; card.querySelectorAll("button").forEach((button) => { button.disabled = false; }); }
  finally { submitting = false; }
}

function defer() { if (!current || submitting) return; deferredOffset = total > deferredOffset + 1 ? deferredOffset + 1 : 0; status.className = "decision-status success"; status.textContent = `Deferred ${current.canonical_name}.`; loadNext(); }
document.addEventListener("keydown", (event) => {
  if (!current || submitting || event.target.matches("input, textarea")) return;
  const digit = event.code.match(/^Digit([1-5])$/)?.[1] || event.key.match(/^[1-5]$/)?.[0];
  if (digit) {
    const candidate = current.candidates[Number(digit) - 1];
    if (!candidate) return;
    event.preventDefault();
    decide("same_entity", candidate.id);
  } else if (phaseKeys.includes(event.key.toUpperCase())) {
    const candidate = current.candidates[phaseKeys.indexOf(event.key.toUpperCase())];
    if (!candidate) return;
    event.preventDefault(); decide("phase_of", candidate.id);
  } else if (inversePhaseKeys.includes(event.key.toUpperCase())) {
    const candidate = current.candidates[inversePhaseKeys.indexOf(event.key.toUpperCase())];
    if (!candidate) return;
    event.preventDefault(); decide("candidate_phase_of", candidate.id);
  } else if (partKeys.includes(event.key.toUpperCase())) {
    const candidate = current.candidates[partKeys.indexOf(event.key.toUpperCase())];
    if (!candidate) return;
    event.preventDefault(); decide("part_of", candidate.id);
  } else if (inversePartKeys.includes(event.key.toUpperCase())) {
    const candidate = current.candidates[inversePartKeys.indexOf(event.key.toUpperCase())];
    if (!candidate) return;
    event.preventDefault(); decide("candidate_part_of", candidate.id);
  } else if (event.key.toLowerCase() === "k") {
    event.preventDefault(); decide("independent");
  } else if (event.key.toLowerCase() === "p") {
    event.preventDefault();
    if (current.dates[1] == null) {
      status.className = "decision-status error";
      status.textContent = "Period choices require a finite end date; this record is still open-ended.";
    } else {
      decide("period");
    }
  } else if (event.key.toLowerCase() === "x") {
    event.preventDefault(); decide("discarded");
  } else if (event.key.toLowerCase() === "s") {
    event.preventDefault(); defer();
  }
});
loadNext().catch((error) => { card.textContent = `Could not load canonical consolidation reviews: ${error.message}`; });
