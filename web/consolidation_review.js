const card = document.querySelector("#consolidation-review-card");
const progress = document.querySelector("#consolidation-review-progress");
const status = document.querySelector("#consolidation-decision-status");
let current = null;
let total = 0;
let deferredOffset = 0;
let submitting = false;

function escapeHtml(value) { return String(value).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"})[c]); }
function formatYear(year) { return year == null ? "present" : year < 0 ? `${Math.abs(year)} BCE` : `${year} CE`; }
function links(item) { return item.wikidata ? `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(item.wikidata)}" target="_blank" rel="noopener noreferrer">Wikidata (${escapeHtml(item.wikidata)}) ↗</a>` : "No Wikidata item"; }

function candidateMarkup(candidate) {
  return `<article class="candidate"><strong>${escapeHtml(candidate.canonical_name)}</strong><span>${escapeHtml(candidate.entity_type)} · ${formatYear(candidate.dates[0])}–${formatYear(candidate.dates[1])}</span><span>${links(candidate)}</span><small>Name ${candidate.name_score.toFixed(1)} · ${candidate.geography_match ? "shared geography" : "different/unknown geography"} · ${candidate.date_contains ? "dates contain source" : candidate.date_overlap ? "dates overlap" : "dates do not overlap"}</small><div class="review-actions"><button type="button" data-decision="same_entity" data-target="${escapeHtml(candidate.id)}">Same entity</button><button type="button" data-decision="phase_of" data-target="${escapeHtml(candidate.id)}">Phase/aspect</button></div></article>`;
}

async function loadNext() {
  const response = await fetch(`/api/consolidation-reviews?limit=1&offset=${deferredOffset}`);
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json(); total = payload.total; current = payload.items[0] || null;
  progress.textContent = `${total} consolidation decisions remaining${deferredOffset ? ` · ${deferredOffset} deferred this session` : ""}`;
  if (!current) { card.innerHTML = "<h2>Queue complete</h2><p>No likely overlaps remain.</p>"; return; }
  card.innerHTML = `<p class="review-rank">Possible overlapping canonical entity</p><h2>${escapeHtml(current.canonical_name)}</h2><dl class="source-facts"><dt>Histomap ID</dt><dd>${escapeHtml(current.id)}</dd><dt>Type</dt><dd>${escapeHtml(current.entity_type)}</dd><dt>Dates</dt><dd>${formatYear(current.dates[0])}–${formatYear(current.dates[1])}</dd><dt>External page</dt><dd class="source-links">${links(current)}</dd></dl><h3 class="candidate-heading">Possible canonical targets</h3><div class="candidate-list">${current.candidates.map(candidateMarkup).join("")}</div><section class="all-entity-search"><h3>Find another target</h3><p>Search all active canonical entities.</p><form class="entity-search-form"><input type="search" minlength="2" placeholder="Entity name"><button type="submit">Search</button></form><div class="entity-search-results"></div></section><div class="review-actions"><button type="button" id="keep-independent">Keep independent</button><button type="button" id="defer-consolidation">Defer</button></div>`;
  card.querySelectorAll("[data-decision]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.decision, button.dataset.target)));
  card.querySelector("#keep-independent").addEventListener("click", () => decide("independent"));
  card.querySelector("#defer-consolidation").addEventListener("click", defer);
  card.querySelector(".entity-search-form").addEventListener("submit", search);
}

async function search(event) {
  event.preventDefault(); const input = event.currentTarget.querySelector("input"); const results = card.querySelector(".entity-search-results");
  const response = await fetch(`/api/polities/search?q=${encodeURIComponent(input.value)}&limit=8`);
  if (!response.ok) { results.textContent = "Search failed."; return; }
  const payload = await response.json();
  results.innerHTML = payload.items.filter((item) => item.polity_id !== current.id).map((item) => `<div class="search-result"><div><strong>${escapeHtml(item.canonical_name)}</strong><span>${escapeHtml(item.entity_type)} · ${formatYear(item.canonical_start)}–${formatYear(item.canonical_end)}</span></div><span class="review-actions"><button type="button" data-search-decision="same_entity" data-target="${escapeHtml(item.polity_id)}">Same</button><button type="button" data-search-decision="phase_of" data-target="${escapeHtml(item.polity_id)}">Phase</button></span></div>`).join("") || "No matches.";
  results.querySelectorAll("[data-search-decision]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.searchDecision, button.dataset.target)));
}

async function decide(decision, targetId = null) {
  if (!current || submitting) return; submitting = true; card.querySelectorAll("button").forEach((b) => { b.disabled = true; }); status.className = "decision-status pending"; status.textContent = "Saving consolidation…";
  try { const reviewed = current; const response = await fetch(`/api/consolidation-reviews/${encodeURIComponent(reviewed.id)}`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision,target_id:targetId})}); if (!response.ok) throw new Error((await response.json()).detail || await response.text()); deferredOffset = Math.min(deferredOffset, Math.max(0, total - 2)); status.className = "decision-status success"; status.textContent = `Saved ${reviewed.canonical_name}. Loading next…`; await loadNext(); }
  catch (error) { status.className = "decision-status error"; status.textContent = `Decision was not saved: ${error.message}`; card.querySelectorAll("button").forEach((b) => { b.disabled = false; }); }
  finally { submitting = false; }
}

function defer() { if (!current || submitting) return; deferredOffset = total > deferredOffset + 1 ? deferredOffset + 1 : 0; status.className = "decision-status success"; status.textContent = `Deferred ${current.canonical_name}.`; loadNext(); }
document.addEventListener("keydown", (event) => { if (!current || submitting || event.target.matches("input, textarea, button, a")) return; if (event.key.toLowerCase() === "k") decide("independent"); else if (event.key.toLowerCase() === "s") defer(); });
loadNext().catch((error) => { card.textContent = `Could not load consolidation reviews: ${error.message}`; });
