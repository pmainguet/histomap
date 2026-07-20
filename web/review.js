const card = document.querySelector("#review-card");
const progress = document.querySelector("#review-progress");
const decisionStatus = document.querySelector("#decision-status");
const jobStatus = document.querySelector("#job-status");
let current = null;
let total = 0;
let deferredOffset = 0;
let submitting = false;
let activeActionButton = null;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);
}

function formatYear(year) {
  if (year == null) return "present";
  return year < 0 ? `${Math.abs(year)} BCE` : `${year} CE`;
}

function score(value) {
  return Number(value ?? 0).toFixed(1);
}

function sourceLinksMarkup(links) {
  return links.map((link) => `<a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link.label)} &nearr;</a>`).join(" &middot; ");
}

function candidateMarkup(candidate, index) {
  const links = sourceLinksMarkup(candidate.source_links || []);
  const sources = (candidate.canonical_sources || []).map((source) => source.replaceAll("_", " ")).join(", ");
  return `<article class="candidate">
    <p class="candidate-number">Possible Histomap match ${index + 1}</p>
    <strong>${escapeHtml(candidate.canonical_name)}</strong>
    <dl class="candidate-facts">
      <dt>Histomap ID</dt><dd>${escapeHtml(candidate.polity_id)}</dd>
      <dt>Canonical dates</dt><dd>${formatYear(candidate.canonical_start)}&ndash;${formatYear(candidate.canonical_end)}</dd>
      <dt>Record sources</dt><dd>${escapeHtml(sources || "not recorded")}</dd>
      <dt>External pages</dt><dd class="source-links">${links || "No Wikidata, Wikipedia, or Seshat link recorded"}</dd>
    </dl>
    <div class="match-score"><strong>${score(candidate.total_score)} / 100</strong><span>Overall weighted match score</span></div>
    ${candidate.exact_name_match ? '<p class="exact-match">Exact normalized name match</p>' : ""}
    <details class="score-details"><summary>How this score was calculated</summary>
      <dl><dt>Name similarity</dt><dd>${score(candidate.name_score)} / 100</dd>
      <dt>Date overlap</dt><dd>${score(candidate.date_score)} / 100</dd>
      <dt>Geography compatibility</dt><dd>${score(candidate.geography_score)} / 100</dd>
      <dt>Political type compatibility</dt><dd>${score(candidate.type_score)} / 100</dd></dl>
      <p>This is a ranking aid, not the probability that the match is correct.</p>
    </details>
    <button class="accept-candidate" data-polity-id="${escapeHtml(candidate.polity_id)}">Accept this match</button>
  </article>`;
}

async function loadNext() {
  const response = await fetch(`/api/reviews?limit=1&offset=${deferredOffset}`);
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  total = payload.total;
  current = payload.items[0] || null;
  progress.textContent = `${total} prioritized decisions remaining${deferredOffset ? ` - ${deferredOffset} deferred this session` : ""}`;
  if (!current) {
    card.innerHTML = "<h2>Queue complete</h2><p>Apply the saved decisions to reconciliation.</p>";
    return;
  }
  const parts = current.priority_components;
  const alternateName = current.seshat_long_name && current.seshat_long_name !== current.seshat_name
    ? `<dt>Seshat long name</dt><dd>${escapeHtml(current.seshat_long_name)}</dd>`
    : "";
  card.innerHTML = `<p class="review-rank">Source record to reconcile</p>
    <h2>${escapeHtml(current.seshat_name)}</h2>
    <p class="source-explanation">This name and date range come from the <strong>Seshat Equinox dataset</strong>. Decide whether it represents one of the existing Histomap records below.</p>
    <dl class="source-facts"><dt>Source</dt><dd>Seshat Global History Databank</dd>
      <dt>Seshat polity ID</dt><dd>${escapeHtml(current.seshat_id)}</dd>
      ${alternateName}
      <dt>Source dates</dt><dd>${formatYear(current.start_year)}&ndash;${formatYear(current.end_year)}</dd>
      <dt>Source pages</dt><dd class="source-links">${sourceLinksMarkup(current.source_links || []) || "No source link available"}</dd></dl>
    <details class="priority-details"><summary>Why this decision appears now (priority ${current.review_priority.toFixed(1)} / 100)</summary>
      <dl><dt>Historical importance of source record</dt><dd>${parts.source_importance.toFixed(0)} / 100</dd>
      <dt>Impact of proposed candidates</dt><dd>${parts.candidate_impact.toFixed(0)} / 100</dd>
      <dt>Best match quality</dt><dd>${parts.quality.toFixed(0)} / 100</dd>
      <dt>Ambiguity requiring review</dt><dd>${parts.ambiguity.toFixed(0)} / 100</dd></dl></details>
    <h3 class="candidate-heading">Possible existing Histomap records</h3>
    <div class="candidate-list">${current.candidates.map(candidateMarkup).join("")}</div>
    <section class="all-entity-search">
      <h3>Search all Histomap entities</h3>
      <p>Use this when the correct entity is missing from the proposed matches.</p>
      <form id="entity-search-form" class="entity-search-form">
        <input id="entity-search" type="search" value="${escapeHtml(current.seshat_long_name || current.seshat_name)}" aria-label="Search all Histomap entities" minlength="2">
        <button type="submit">Search</button>
      </form>
      <div id="entity-search-results" class="entity-search-results" aria-live="polite"></div>
    </section>
    <div class="review-actions"><button id="reject" class="danger">No match — keep as separate entity</button><button id="defer">Defer</button></div>`;
  card.querySelectorAll(".accept-candidate").forEach((button) => button.addEventListener("click", () => decide("accept", button.dataset.polityId)));
  card.querySelector("#reject").addEventListener("click", () => decide("reject"));
  card.querySelector("#defer").addEventListener("click", () => decide("defer"));
  card.querySelector("#entity-search-form").addEventListener("submit", searchAllEntities);
}

async function searchAllEntities(event) {
  event.preventDefault();
  const query = card.querySelector("#entity-search").value.trim();
  const results = card.querySelector("#entity-search-results");
  if (query.length < 2) {
    results.textContent = "Enter at least two characters.";
    return;
  }
  results.textContent = "Searching…";
  try {
    const response = await fetch(`/api/polities/search?q=${encodeURIComponent(query)}&limit=10`);
    if (!response.ok) throw new Error(await response.text());
    const payload = await response.json();
    if (!payload.items.length) {
      results.textContent = "No Histomap entities found.";
      return;
    }
    results.innerHTML = payload.items.map((candidate) => `<article class="search-result">
      <div><strong>${escapeHtml(candidate.canonical_name)}</strong>
        <span>${formatYear(candidate.canonical_start)}–${formatYear(candidate.canonical_end)} · ${score(candidate.search_score)} name match</span>
        <span class="source-links">${sourceLinksMarkup(candidate.source_links || [])}</span></div>
      <button type="button" class="accept-search-result" data-polity-id="${escapeHtml(candidate.polity_id)}">Accept this match</button>
    </article>`).join("");
    results.querySelectorAll(".accept-search-result").forEach((button) => {
      button.addEventListener("click", () => decide("accept", button.dataset.polityId));
    });
  } catch (error) {
    results.textContent = `Search failed: ${error.message}`;
  }
}

function setDecisionControlsDisabled(disabled) {
  card.querySelectorAll(".accept-candidate, .accept-search-result, #reject, #defer").forEach((button) => {
    button.disabled = disabled;
  });
}

async function decide(decision, polityId = null) {
  if (!current || submitting) return;
  submitting = true;
  setDecisionControlsDisabled(true);
  decisionStatus.className = "decision-status pending";
  decisionStatus.textContent = "Saving decision…";
  try {
    const reviewed = current;
    const candidate = reviewed.candidates.find((item) => item.polity_id === polityId);
    const response = await fetch(`/api/reviews/${encodeURIComponent(reviewed.seshat_id)}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, polity_id: polityId }),
    });
    if (!response.ok) throw new Error(await response.text());
    if (decision === "defer") {
      deferredOffset = total > deferredOffset + 1 ? deferredOffset + 1 : 0;
      decisionStatus.textContent = `Deferred ${reviewed.seshat_name}. Loading the next item…`;
    } else {
      deferredOffset = Math.min(deferredOffset, Math.max(0, total - 2));
      decisionStatus.textContent = decision === "accept"
        ? `Saved: ${reviewed.seshat_name} matched to ${candidate?.canonical_name || polityId}. Loading the next item…`
        : `Saved: ${reviewed.seshat_name} has no matching candidate. Loading the next item…`;
    }
    decisionStatus.className = "decision-status success";
    await loadNext();
  } catch (error) {
    decisionStatus.className = "decision-status error";
    decisionStatus.textContent = `Decision was not saved: ${error.message}`;
    setDecisionControlsDisabled(false);
  } finally {
    submitting = false;
  }
}

async function startAction(action) {
  const button = action === "apply-reviews"
    ? document.querySelector("#apply-decisions")
    : document.querySelector("#build-data");
  activeActionButton = button;
  setActionButtonState(button, "running");
  jobStatus.textContent = "";
  try {
    const response = await fetch(`/api/actions/${action}`, { method: "POST" });
    if (!response.ok) throw new Error(await response.text());
    pollJob();
  } catch (error) {
    setActionButtonState(button, "failed");
    jobStatus.textContent = `Action failed: ${error.message}`;
  }
}

function setActionButtonState(button, state) {
  if (!button.dataset.label) button.dataset.label = button.textContent.trim();
  const label = escapeHtml(button.dataset.label);
  button.classList.toggle("is-running", state === "running");
  button.disabled = state === "running";
  button.setAttribute("aria-busy", state === "running" ? "true" : "false");
  if (state === "running") {
    button.innerHTML = `<span class="button-spinner" aria-hidden="true"></span><span>${label}</span>`;
  } else if (state === "complete") {
    button.innerHTML = `<span class="button-check" aria-hidden="true">✓</span><span>Done</span>`;
    window.setTimeout(() => setActionButtonState(button, "idle"), 1800);
  } else if (state === "failed") {
    button.innerHTML = `<span aria-hidden="true">×</span><span>Failed</span>`;
    window.setTimeout(() => setActionButtonState(button, "idle"), 2500);
  } else {
    button.innerHTML = label;
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

async function pollJob() {
  const job = await fetch("/api/actions/status").then((response) => response.json());
  if (job.status === "queued" || job.status === "running") setTimeout(pollJob, 500);
  if (job.status === "complete") {
    setActionButtonState(activeActionButton, "complete");
    jobStatus.textContent = "";
    loadNext();
  } else if (job.status === "failed") {
    setActionButtonState(activeActionButton, "failed");
    jobStatus.textContent = "Action failed. Check the server output for details.";
  }
}

document.querySelector("#apply-decisions").addEventListener("click", () => startAction("apply-reviews"));
document.querySelector("#build-data").addEventListener("click", () => startAction("build"));
document.addEventListener("keydown", (event) => {
  if (!current || submitting || event.target.matches("input, textarea, button, a, summary")) return;
  const candidate = /^[1-5]$/.test(event.key) ? current.candidates[Number(event.key) - 1] : null;
  if (candidate) {
    event.preventDefault();
    decide("accept", candidate.polity_id);
  } else if (event.key.toLowerCase() === "r") {
    event.preventDefault();
    decide("reject");
  } else if (event.key.toLowerCase() === "s") {
    event.preventDefault();
    decide("defer");
  }
});

loadNext().catch((error) => { card.textContent = `Could not load reviews: ${error.message}`; });
