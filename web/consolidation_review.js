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

// escapeHtml, formatYear live in common.js, loaded first on this page.
function links(item) { return item.wikidata ? `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(item.wikidata)}" target="_blank" rel="noopener noreferrer">Wikidata (${escapeHtml(item.wikidata)}) ↗</a>` : "No Wikidata item"; }
// Two-row bar chart on a shared timeline, so containment (one record's
// span fully inside the other's) is visible at a glance instead of having
// to compare two year ranges read out of separate table cells. Open ends
// ("present") are capped at 2100, matching the same cap the server's own
// date_contains/date_overlap checks use.
function timelineCoverage(candidateItem, reviewedItem) {
  const OPEN_END_CAP = 2100;
  const cStart = candidateItem.dates[0], cEnd = candidateItem.dates[1] ?? OPEN_END_CAP;
  const rStart = reviewedItem.dates[0], rEnd = reviewedItem.dates[1] ?? OPEN_END_CAP;
  if (cStart == null || rStart == null) return "";
  const min = Math.min(cStart, rStart);
  const max = Math.max(cEnd, rEnd);
  const span = Math.max(1, max - min);
  const pct = (value) => ((value - min) / span) * 100;
  const bar = (start, end, cls, label) => {
    const left = pct(start);
    const width = Math.max(0.6, pct(end) - left);
    return `<div class="timeline-coverage-row"><span class="timeline-coverage-label">${escapeHtml(label)}</span><div class="timeline-coverage-track"><div class="timeline-coverage-bar ${cls}" style="left:${left}%;width:${width}%"></div></div></div>`;
  };
  return `<div class="timeline-coverage">
    ${bar(cStart, cEnd, "timeline-coverage-candidate", "Candidate")}
    ${bar(rStart, rEnd, "timeline-coverage-reviewed", "Reviewed")}
    <div class="timeline-coverage-axis"><span>${formatYear(min)}</span><span>${formatYear(max)}</span></div>
  </div>`;
}
// Filled in by loadWikidataEvidence() once sitelinks are fetched -- prefers
// the English Wikipedia article, falling back to whichever language
// edition exists.
function wikipediaPlaceholder(item) { return item.wikidata ? `<span data-wikipedia-link="${escapeHtml(item.wikidata)}">Loading…</span>` : "No Wikidata item"; }
// Filled in by loadWikidataEvidence() with the Wikidata P242 (locator map
// image) claim, when one exists -- a quick visual geography cross-check
// alongside the present-countries/centroid-distance fields.
function locatorMapPlaceholder(item) { return item.wikidata ? `<span data-locator-map="${escapeHtml(item.wikidata)}"></span>` : ""; }
function typeLinks(item) { return (item.direct_type_qids || []).map((qid) => `<a data-wikidata-label="${escapeHtml(qid)}" href="https://www.wikidata.org/wiki/${encodeURIComponent(qid)}" target="_blank" rel="noopener noreferrer">${escapeHtml(qid)} ↗</a>`).join(", ") || "Not recorded"; }
function dateRange(item) { return `${formatYear(item.dates[0])}–${formatYear(item.dates[1])}`; }
function countries(item) { return escapeHtml((item.present_countries || []).join(", ") || "not recorded"); }
function comparisonRow(label, candidateValue, reviewedValue, assessment = "") {
  return `<tr class="${assessment ? `comparison-${assessment}` : ""}"><th scope="row">${label}</th><td>${candidateValue}</td><td>${reviewedValue}</td></tr>`;
}
// Highlights the button matching the server's suggested_decision (derived
// from date-nesting, documented Wikidata succession links, coordinate
// distance, and same-Wikidata-item-but-mismatched-dates checks) so the
// direction doesn't have to be worked out by hand each time. key/label
// render as `<kbd>key</kbd> label`, matching the Independent/Discard/Defer
// buttons' shortcut display. disabledReason, when given, disables the
// button with a title tooltip instead of letting the click reach the server
// and bounce off a rejected-decision error (a phase_of/candidate_phase_of
// decision writes a Period record, which needs a finite end date -- same
// reasoning the "Broad period/era" button already applies).
function recommendableButton(decision, candidate, key, label, disabledReason = null) {
  // Never badge a disabled button -- recommending an action that can't
  // actually be taken here is more confusing than showing no suggestion.
  const recommended = !disabledReason && candidate.suggested_decision === decision;
  return `<button type="button" data-decision="${decision}" data-target="${escapeHtml(candidate.id)}"${recommended ? ' class="recommended-decision"' : ""}${disabledReason ? ` disabled title="${escapeHtml(disabledReason)}"` : ""}><kbd>${escapeHtml(String(key))}</kbd> ${label}</button>`;
}

function candidateMarkup(candidate, index) {
  const independentRecommended = candidate.suggested_decision === "independent";
  const reviewedOpenEnded = current.dates[1] == null;
  const candidateOpenEnded = candidate.dates[1] == null;
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
      ${comparisonRow("Wikipedia", `<span class="source-links">${wikipediaPlaceholder(candidate)}</span>`, `<span class="source-links">${wikipediaPlaceholder(current)}</span>`)}
      ${comparisonRow("Locator map", locatorMapPlaceholder(candidate), locatorMapPlaceholder(current))}
    </tbody></table></div>
    ${timelineCoverage(candidate, current)}
    <div class="review-actions relationship-directions">${recommendableButton("same_entity", candidate, index + 1, "Same entity")}${recommendableButton("phase_of", candidate, phaseKeys[index], "Reviewed → phase of candidate", reviewedOpenEnded ? "A phase needs a finite end date on the reviewed entity -- it's still open-ended (present)" : null)}${recommendableButton("candidate_phase_of", candidate, inversePhaseKeys[index], "Candidate → phase of reviewed", candidateOpenEnded ? "A phase needs a finite end date on the candidate -- it's still open-ended (present)" : null)}${recommendableButton("part_of", candidate, partKeys[index], "Reviewed → part of candidate")}${recommendableButton("candidate_part_of", candidate, inversePartKeys[index], "Candidate → part of reviewed")}</div>
    <div class="review-actions candidate-entity-actions"><button type="button" data-decision="independent"${independentRecommended ? ' class="recommended-decision"' : ""}><kbd>K</kbd> Independent entity</button><button type="button" data-decision="discarded" class="danger"><kbd>X</kbd> Discard from Histomap</button><button type="button" data-action="defer"><kbd>S</kbd> Defer</button></div>
    <p class="proposal-reason"><strong>Why suggested:</strong> ${escapeHtml(candidate.reasons.join("; "))}.</p>
  </article>`;
}

// Sitelink keys that carry a "wiki" suffix but aren't a language Wikipedia
// edition -- excluded so the Wikipedia-link fallback never lands on Commons,
// Wikidata's own item page, etc.
const NON_LANGUAGE_WIKIS = new Set([
  "commonswiki", "wikidatawiki", "specieswiki", "metawiki", "mediawikiwiki",
  "testwiki", "wikimaniawiki", "wikifunctionswiki", "incubatorwiki",
  "outreachwiki", "betawikiversitywiki", "donatewiki", "foundationwiki",
  "loginwiki", "votewiki",
]);
function pickWikipediaSitelink(sitelinks) {
  if (!sitelinks) return null;
  if (sitelinks.enwiki) return sitelinks.enwiki;
  const fallbackKey = Object.keys(sitelinks).find((key) => key.endsWith("wiki") && !NON_LANGUAGE_WIKIS.has(key));
  return fallbackKey ? sitelinks[fallbackKey] : null;
}

async function loadWikidataEvidence(item) {
  const qids = [...new Set([item.wikidata, ...(item.direct_type_qids || []), ...item.candidates.flatMap((candidate) => [candidate.wikidata, ...(candidate.direct_type_qids || [])])].filter(Boolean))];
  if (!qids.length) return;
  try {
    const parameters = new URLSearchParams({action:"wbgetentities",format:"json",formatversion:"2",ids:qids.join("|"),props:"labels|descriptions|sitelinks/urls|claims",languages:"en",origin:"*"});
    const response = await fetch(`https://www.wikidata.org/w/api.php?${parameters}`);
    if (!response.ok || !current || current.id !== item.id) return;
    const entities = (await response.json()).entities || {};
    card.querySelectorAll("[data-wikidata-label]").forEach((link) => { const qid = link.dataset.wikidataLabel; const label = entities[qid]?.labels?.en?.value; if (label) link.textContent = `${label} (${qid}) ↗`; });
    card.querySelectorAll("[data-wikidata-description]").forEach((element) => { const description = entities[element.dataset.wikidataDescription]?.descriptions?.en?.value; element.textContent = description || "No English Wikidata description."; });
    card.querySelectorAll("[data-wikipedia-link]").forEach((element) => {
      const sitelink = pickWikipediaSitelink(entities[element.dataset.wikipediaLink]?.sitelinks);
      if (sitelink) {
        const lang = sitelink.site.replace(/wiki$/, "") || "en";
        element.innerHTML = `<a href="${escapeHtml(sitelink.url)}" target="_blank" rel="noopener noreferrer">Wikipedia (${escapeHtml(lang)}) ↗</a>`;
      } else {
        element.textContent = "No Wikipedia article";
      }
    });
    card.querySelectorAll("[data-locator-map]").forEach((element) => {
      const filename = entities[element.dataset.locatorMap]?.claims?.P242?.[0]?.mainsnak?.datavalue?.value;
      if (!filename) return;
      const fileUrl = `https://commons.wikimedia.org/wiki/Special:FilePath/${encodeURIComponent(filename)}`;
      element.innerHTML = `<a href="${fileUrl}" target="_blank" rel="noopener noreferrer"><img src="${fileUrl}?width=220" alt="Locator map" loading="lazy" class="locator-map-image"></a>`;
    });
  } catch (_) { /* Linked QIDs remain available when Wikidata is unavailable. */ }
}

async function loadNext() {
  const response = await fetch(`/api/consolidation-reviews?limit=1&offset=${deferredOffset}`);
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json(); total = payload.total; current = payload.items[0] || null;
  progress.textContent = `${total} canonical identity decisions remaining${deferredOffset ? ` · ${deferredOffset} deferred this session` : ""}`;
  if (!current) { card.innerHTML = "<h2>Queue complete</h2><p>No unresolved identity or period-role cases remain.</p>"; return; }
  // Independent/Discard/Defer live on each candidate card (candidateMarkup)
  // so they sit next to the evidence that motivates them. With no
  // candidates there's no card to hold them, so this fallback keeps its own
  // copy. "Broad period/era" has no card-level button either -- <kbd>P</kbd>
  // (see the keydown handler) remains the only way to make that decision,
  // since it isn't tied to any specific candidate the way the others are.
  const candidateSection = current.candidates.length
    ? `<h3 class="candidate-heading">Other canonical Histomap records with compatible evidence</h3><div class="candidate-list">${current.candidates.map(candidateMarkup).join("")}</div>`
    : `<p class="proposal-reason">No compatible canonical target was suggested. Decide whether this is an independent entity or belongs on the period layer.</p><div class="review-actions"><button type="button" data-decision="independent"><kbd>K</kbd> Independent entity</button><button type="button" data-decision="discarded" class="danger"><kbd>X</kbd> Discard from Histomap</button><button type="button" data-action="defer"><kbd>S</kbd> Defer</button></div>`;
  card.innerHTML = `<p class="review-rank"><span class="record-badge">Histomap entity</span> Canonical record being checked</p><h2>${escapeHtml(current.canonical_name)}</h2><p class="wikidata-description" data-wikidata-description="${escapeHtml(current.wikidata || "")}"></p><dl class="source-facts"><dt>Histomap ID</dt><dd>${escapeHtml(current.id)}</dd><dt>Type</dt><dd>${escapeHtml(current.entity_type)}</dd><dt>Dates</dt><dd>${formatYear(current.dates[0])}–${formatYear(current.dates[1])}</dd><dt>Present countries</dt><dd>${escapeHtml(current.present_countries.join(", ") || "not recorded")}</dd><dt>Instance of</dt><dd class="source-links">${typeLinks(current)}</dd><dt>External page</dt><dd class="source-links">${links(current)}</dd></dl>${candidateSection}`;
  card.querySelectorAll("[data-decision]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.decision, button.dataset.target)));
  card.querySelectorAll('[data-action="defer"]').forEach((button) => button.addEventListener("click", defer));
  loadWikidataEvidence(current);
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
    event.preventDefault();
    if (current.dates[1] == null) {
      status.className = "decision-status error";
      status.textContent = "A phase needs a finite end date on the reviewed entity -- it's still open-ended (present).";
    } else {
      decide("phase_of", candidate.id);
    }
  } else if (inversePhaseKeys.includes(event.key.toUpperCase())) {
    const candidate = current.candidates[inversePhaseKeys.indexOf(event.key.toUpperCase())];
    if (!candidate) return;
    event.preventDefault();
    if (candidate.dates[1] == null) {
      status.className = "decision-status error";
      status.textContent = "A phase needs a finite end date on the candidate -- it's still open-ended (present).";
    } else {
      decide("candidate_phase_of", candidate.id);
    }
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
