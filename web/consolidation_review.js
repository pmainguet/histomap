const card = document.querySelector("#consolidation-review-card");
const progress = document.querySelector("#consolidation-review-progress");
const progressFill = document.querySelector("#consolidation-progress-fill");
const status = document.querySelector("#consolidation-decision-status");
let current = null;
let total = 0;
let deferredOffset = 0;
let submitting = false;
// The first `total` seen this page load is the bar's 100% baseline -- there's
// no fixed denominator to compare against otherwise, so this tracks progress
// made in the current browsing session rather than all-time completion.
let progressBaseline = null;
// Chosen for AZERTY, not QWERTY: AZERTY swaps Q<->A and W<->Z, so the old
// QWERTY-adjacent picks (Q W E R T / A D F G H) landed on scattered,
// non-adjacent physical keys for an AZERTY typist. These follow AZERTY's own
// row layout instead -- row 1 (A Z E R T) for "Reviewed", row 2 (D F G H J)
// for "Candidate" -- skipping K/P/S/X/digits, already claimed elsewhere.
const detailKeys = ["A", "Z", "E", "R", "T"];
const inverseDetailKeys = ["D", "F", "G", "H", "J"];

// escapeHtml, formatYear live in common.js, loaded first on this page.
function links(item) { return item.wikidata ? `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(item.wikidata)}" target="_blank" rel="noopener noreferrer">Wikidata (${escapeHtml(item.wikidata)}) ↗</a>` : "No Wikidata item"; }
// Two-row bar chart on a shared timeline, so containment (one record's
// span fully inside the other's) is visible at a glance instead of having
// to compare two year ranges read out of separate table cells. Open ends
// ("present") are capped at 2100, matching the same cap the server's own
// date_contains/date_overlap checks use.
function timelineCoverage(candidateItem, reviewedItem) {
  const OPEN_END_CAP = 2100;
  const cEndRaw = candidateItem.dates[1], rEndRaw = reviewedItem.dates[1];
  const cStart = candidateItem.dates[0], cEnd = cEndRaw ?? OPEN_END_CAP;
  const rStart = reviewedItem.dates[0], rEnd = rEndRaw ?? OPEN_END_CAP;
  if (cStart == null || rStart == null) return "";
  const min = Math.min(cStart, rStart);
  const max = Math.max(cEnd, rEnd);
  // 2100 is only an internal cap for bar-width math, not a real date -- the
  // axis label should read "present" whenever the entity that reaches the
  // right edge is itself open-ended, not literally "2100 CE" (found live,
  // 1 September 2026).
  const maxIsOpenEnded = (max === cEnd && cEndRaw == null) || (max === rEnd && rEndRaw == null);
  const span = Math.max(1, max - min);
  const pct = (value) => ((value - min) / span) * 100;
  const bar = (start, end, cls, label) => {
    const left = pct(start);
    const width = Math.max(0.6, pct(end) - left);
    return `<div class="timeline-coverage-row"><span class="timeline-coverage-label">${escapeHtml(label)}</span><div class="timeline-coverage-track"><div class="timeline-coverage-bar ${cls}" style="left:${left}%;width:${width}%"></div></div></div>`;
  };
  return `<tr class="timeline-coverage-row-wrap"><td colspan="3"><div class="timeline-coverage">
    ${bar(rStart, rEnd, "timeline-coverage-reviewed", "Reviewed")}
    ${bar(cStart, cEnd, "timeline-coverage-candidate", "Candidate")}
    <div class="timeline-coverage-axis"><span>${formatYear(min)}</span><span>${maxIsOpenEnded ? formatYear(null) : formatYear(max)}</span></div>
  </div></td></tr>`;
}
// Filled in by loadWikidataEvidence() once sitelinks are fetched -- prefers
// the English Wikipedia article, falling back to whichever language
// edition exists.
function wikipediaPlaceholder(item) { return item.wikidata ? `<span data-wikipedia-link="${escapeHtml(item.wikidata)}">Loading…</span>` : "No Wikidata item"; }
// Filled in by loadWikidataEvidence() with the Wikidata P242 (locator map
// image) claim, when one exists -- a quick visual geography cross-check
// alongside the present-countries/centroid-distance fields.
function locatorMapPlaceholder(item) { return item.wikidata ? `<span data-locator-map="${escapeHtml(item.wikidata)}"></span>` : ""; }
// Filled in by loadWikidataEvidence() with the Wikidata P361 ("part of") /
// P150 ("contains administrative territorial entity") claims, when any
// exist -- direct hierarchy signals alongside the derived shared_p131/
// geography fields. property is the claim id (P361 or P150); dataAttr is
// the data-* attribute name the fetch step looks for.
function claimPlaceholder(item, dataAttr) { return item.wikidata ? `<span data-${dataAttr}="${escapeHtml(item.wikidata)}">Loading…</span>` : "No Wikidata item"; }
function partOfPlaceholder(item) { return claimPlaceholder(item, "part-of"); }
function containsPlaceholder(item) { return claimPlaceholder(item, "contains"); }
function typeLinks(item) { return (item.direct_type_qids || []).map((qid) => `<a data-wikidata-label="${escapeHtml(qid)}" href="https://www.wikidata.org/wiki/${encodeURIComponent(qid)}" target="_blank" rel="noopener noreferrer">${escapeHtml(qid)} ↗</a>`).join(", ") || "Not recorded"; }
function reasonsBanner(reasons) {
  return `<div class="proposal-reason"><strong>Why suggested:</strong><ul class="proposal-reason-list">${reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul></div>`;
}
function dateRange(item) { return `${formatYear(item.dates[0])}–${formatYear(item.dates[1])}`; }
function countries(item) { return escapeHtml((item.present_countries || []).join(", ") || "not recorded"); }
// Reviewed entity first (it's the record actually being decided about),
// candidate second -- and see the CSS for how that first value column is
// visually distinguished from the second.
function comparisonRow(label, reviewedValue, candidateValue, assessment = "") {
  return `<tr class="${assessment ? `comparison-${assessment}` : ""}"><th scope="row">${label}</th><td>${reviewedValue}</td><td>${candidateValue}</td></tr>`;
}
// Highlights the button matching the server's suggested_decision (derived
// from date-nesting, documented Wikidata succession links, coordinate
// distance, and same-Wikidata-item-but-mismatched-dates checks) so the
// direction doesn't have to be worked out by hand each time. key/label
// render as `<kbd>key</kbd> label`, matching the Independent/Discard/Defer
// buttons' shortcut display. hint, when given, shows as a title tooltip --
// e.g. detail_of/candidate_detail_of on a still-open-ended ("present")
// entity still submits fine (a detail entity keeps its own start/end
// unchanged, open or not), but is worth flagging so the reviewer isn't
// surprised either way.
function recommendableButton(decision, candidate, key, label, hint = null) {
  const recommended = candidate.suggested_decision === decision;
  const classes = recommended ? ' class="recommended-decision"' : "";
  return `<button type="button" data-decision="${decision}" data-target="${escapeHtml(candidate.id)}"${classes}${hint ? ` title="${escapeHtml(hint)}"` : ""}><kbd>${escapeHtml(String(key))}</kbd> ${label}</button>`;
}

// Opens /explore in a new tab, zoomed to and with the detail panel already
// open on the given entity -- convenient when the entity IS published/
// visible there (its own geography editor, entity-type dropdown, etc.).
// Not every queue entry is guaranteed to be, though -- editFieldsMarkup()
// below is the reliable fallback that works regardless (found live, 1
// September 2026).
function exploreLink(id) {
  return `<a class="explore-edit-link" href="/explore?entity=${encodeURIComponent(id)}" target="_blank" rel="noopener noreferrer">Edit in /explore ↗</a>`;
}

// A collapsible raw-fields JSON editor, right on the review card -- reads
// straight from server-side `metadata` (GET /api/polities/{id}), so it
// always finds the entity even when it isn't published in /data.json (the
// gap that made the /explore link above insufficient on its own). Lazily
// fetches on first open, not eagerly for every candidate. Saves via the
// same PATCH /api/polities/{id}/fields endpoint /explore's own editor
// uses, then reloads the current queue item so corrected data (dates,
// suggested_decision, etc.) shows immediately without losing your place.
function editFieldsMarkup(id) {
  return `<details class="detail-edit" data-entity-id="${escapeHtml(id)}">
    <summary>Edit fields</summary>
    <textarea class="detail-raw-textarea" name="raw-fields" aria-label="Raw record fields (JSON)" rows="14" spellcheck="false">Loading…</textarea>
    <div class="detail-edit-row"><button type="button" class="raw-edit-save">Save fields</button></div>
    <p class="detail-edit-status" role="status"></p>
  </details>`;
}

function wireEditFields() {
  card.querySelectorAll(".detail-edit[data-entity-id]").forEach((details) => {
    const id = details.dataset.entityId;
    const textarea = details.querySelector(".detail-raw-textarea");
    const status = details.querySelector(".detail-edit-status");
    const setStatus = (message, isError) => {
      status.textContent = message;
      status.classList.toggle("is-error", Boolean(isError));
    };
    details.addEventListener("toggle", async () => {
      if (!details.open || textarea.dataset.loaded) return;
      try {
        const response = await fetch(`/api/polities/${encodeURIComponent(id)}`);
        if (!response.ok) throw new Error((await response.json()).detail || await response.text());
        textarea.value = JSON.stringify(await response.json(), null, 2);
        textarea.dataset.loaded = "true";
      } catch (error) {
        setStatus(`Could not load: ${error.message}`, true);
      }
    });
    details.querySelector(".raw-edit-save").addEventListener("click", async () => {
      let fields;
      try {
        fields = JSON.parse(textarea.value);
      } catch (error) {
        setStatus(`Invalid JSON: ${error.message}`, true);
        return;
      }
      try {
        const response = await fetch(`/api/polities/${encodeURIComponent(id)}/fields`, {
          method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(fields),
        });
        if (!response.ok) throw new Error((await response.json()).detail || await response.text());
        setStatus("Saved. Reloading…", false);
        await loadNext();
      } catch (error) {
        setStatus(`Not saved: ${error.message}`, true);
      }
    });
  });
}

function candidateMarkup(candidate, index) {
  const independentRecommended = candidate.suggested_decision === "independent";
  const reviewedOpenEnded = current.dates[1] == null;
  const candidateOpenEnded = candidate.dates[1] == null;
  return `<article class="candidate consolidation-candidate">
    <div class="candidate-main">
      <p class="candidate-number">Candidate ${index + 1}</p><div class="comparison-heading"><strong>${escapeHtml(candidate.canonical_name)}</strong><span class="evidence-badge ${candidate.confidence}">${escapeHtml(candidate.confidence)} confidence</span>${exploreLink(candidate.id)}</div>
      <p class="wikidata-description" data-wikidata-description="${escapeHtml(candidate.wikidata || "")}"></p>
      ${editFieldsMarkup(candidate.id)}
      <div class="comparison-table-wrap"><table class="comparison-table"><thead><tr><th>Field</th><th>Reviewed entity</th><th>Candidate</th></tr></thead><tbody>
        ${comparisonRow("Name", escapeHtml(current.canonical_name), escapeHtml(candidate.canonical_name), candidate.exact_name_match ? "match" : "review")}
        ${comparisonRow("Instance of", `<span class="source-links">${typeLinks(current)}</span>`, `<span class="source-links">${typeLinks(candidate)}</span>`)}
        ${comparisonRow("Wikidata", `<span class="source-links">${links(current)}</span>`, `<span class="source-links">${links(candidate)}</span>`, candidate.same_wikidata ? "match" : "review")}
        ${comparisonRow("Wikipedia", `<span class="source-links">${wikipediaPlaceholder(current)}</span>`, `<span class="source-links">${wikipediaPlaceholder(candidate)}</span>`)}
        ${comparisonRow("Part of", `<span class="source-links">${partOfPlaceholder(current)}</span>`, `<span class="source-links">${partOfPlaceholder(candidate)}</span>`, (candidate.reviewed_part_of_candidate || candidate.candidate_part_of_reviewed) ? "match" : "")}
        ${comparisonRow("Contains", `<span class="source-links">${containsPlaceholder(current)}</span>`, `<span class="source-links">${containsPlaceholder(candidate)}</span>`)}
        ${comparisonRow("Type", escapeHtml(current.entity_type), escapeHtml(candidate.entity_type), candidate.type_match ? "match" : "conflict")}
        ${comparisonRow("Dates", dateRange(current), dateRange(candidate), candidate.date_contains ? "match" : candidate.date_overlap ? "review" : "conflict")}
        ${timelineCoverage(candidate, current)}
        ${comparisonRow("Present countries", countries(current), countries(candidate), candidate.geography_match ? "match" : (!candidate.present_countries.length || !current.present_countries.length) ? "unknown" : "conflict")}
        ${comparisonRow("Locator map", locatorMapPlaceholder(current), locatorMapPlaceholder(candidate))}
      </tbody></table></div>
      ${index === 0 ? "" : reasonsBanner(candidate.reasons)}
    </div>
    <div class="candidate-actions-column">
      <div class="review-actions relationship-directions">${recommendableButton("same_entity", candidate, index + 1, "Same entity")}<button type="button" data-decision="independent"${independentRecommended ? ' class="recommended-decision"' : ""}><kbd>K</kbd> Independent entity</button>${recommendableButton("detail_of", candidate, detailKeys[index], "Reviewed → detail of candidate", reviewedOpenEnded ? "Reviewed entity is still open-ended (present)" : null)}${recommendableButton("candidate_detail_of", candidate, inverseDetailKeys[index], "Candidate → detail of reviewed", candidateOpenEnded ? "Candidate is still open-ended (present)" : null)}</div>
      <div class="review-actions candidate-entity-actions"><button type="button" data-decision="discarded" class="danger"><kbd>X</kbd> Discard from Histomap</button><button type="button" data-action="defer"><kbd>S</kbd> Defer</button></div>
    </div>
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
    // P361 ("part of") and P150 ("contains administrative territorial
    // entity") claims reference OTHER Wikidata items, whose labels weren't
    // part of the batch above -- one shared second, lighter fetch (labels
    // only) resolves both, same two-step pattern typeLinks()'s own
    // data-wikidata-label elements already rely on for direct_type_qids.
    const claimRows = [
      { attr: "part-of", property: "P361" },
      { attr: "contains", property: "P150" },
    ].map(({ attr, property }) => {
      const elements = [...card.querySelectorAll(`[data-${attr}]`)];
      const targetsBySource = new Map(); // source qid -> [target qid, ...]
      elements.forEach((element) => {
        const qid = element.dataset[attr === "part-of" ? "partOf" : attr];
        const targets = (entities[qid]?.claims?.[property] || [])
          .map((claim) => claim?.mainsnak?.datavalue?.value?.id)
          .filter(Boolean);
        targetsBySource.set(qid, targets);
      });
      return { elements, attr, targetsBySource };
    });
    const allTargetQids = [...new Set(claimRows.flatMap((row) => [...row.targetsBySource.values()]).flat())];
    let targetLabels = {};
    if (allTargetQids.length) {
      const targetParameters = new URLSearchParams({action:"wbgetentities",format:"json",formatversion:"2",ids:allTargetQids.join("|"),props:"labels",languages:"en",origin:"*"});
      const targetResponse = await fetch(`https://www.wikidata.org/w/api.php?${targetParameters}`);
      if (targetResponse.ok && current && current.id === item.id) {
        targetLabels = (await targetResponse.json()).entities || {};
      }
    }
    claimRows.forEach(({ elements, attr, targetsBySource }) => {
      elements.forEach((element) => {
        const qid = element.dataset[attr === "part-of" ? "partOf" : attr];
        const targets = targetsBySource.get(qid) || [];
        if (!targets.length) { element.textContent = "Not recorded"; return; }
        element.innerHTML = targets
          .map((targetQid) => `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(targetQid)}" target="_blank" rel="noopener noreferrer">${escapeHtml(targetLabels[targetQid]?.labels?.en?.value || targetQid)} ↗</a>`)
          .join(", ");
      });
    });
  } catch (_) { /* Linked QIDs remain available when Wikidata is unavailable. */ }
}

async function loadNext() {
  const response = await fetch(`/api/consolidation-reviews?limit=1&offset=${deferredOffset}`);
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json(); total = payload.total; current = payload.items[0] || null;
  progress.textContent = `${total} canonical identity decisions remaining${deferredOffset ? ` · ${deferredOffset} deferred this session` : ""}`;
  if (progressBaseline === null || total > progressBaseline) progressBaseline = total;
  const resolvedThisSession = Math.max(0, progressBaseline - total);
  progressFill.style.width = `${progressBaseline > 0 ? Math.round((resolvedThisSession / progressBaseline) * 100) : 0}%`;
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
  // Just title + subtitle here -- the rest of what this record is (dates,
  // type, present countries, Wikidata) already appears as the "Reviewed
  // entity" column in each candidate's comparison table below, so a second
  // copy up here was pure duplication.
  // Candidate 1's reasons move up here as a banner (candidateMarkup skips
  // rendering its own copy for index 0) -- it's the top-scored candidate,
  // usually the one carrying whatever Suggested badge is showing, so its
  // reasoning is worth seeing before scrolling into the comparison table.
  const topReasonsBanner = current.candidates[0] ? reasonsBanner(current.candidates[0].reasons) : "";
  card.innerHTML = `<p class="review-rank"><span class="record-badge">Histomap entity</span> Canonical record being checked</p><h2>${escapeHtml(current.canonical_name)}${exploreLink(current.id)}</h2><p class="wikidata-description" data-wikidata-description="${escapeHtml(current.wikidata || "")}"></p>${editFieldsMarkup(current.id)}${topReasonsBanner}${candidateSection}`;
  card.querySelectorAll("[data-decision]").forEach((button) => button.addEventListener("click", () => decide(button.dataset.decision, button.dataset.target)));
  card.querySelectorAll('[data-action="defer"]').forEach((button) => button.addEventListener("click", defer));
  wireEditFields();
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
  } else if (detailKeys.includes(event.key.toUpperCase())) {
    const candidate = current.candidates[detailKeys.indexOf(event.key.toUpperCase())];
    if (!candidate) return;
    event.preventDefault();
    decide("detail_of", candidate.id);
  } else if (inverseDetailKeys.includes(event.key.toUpperCase())) {
    const candidate = current.candidates[inverseDetailKeys.indexOf(event.key.toUpperCase())];
    if (!candidate) return;
    event.preventDefault();
    decide("candidate_detail_of", candidate.id);
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
