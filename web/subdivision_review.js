const card = document.querySelector("#subdivision-review-card");
const progress = document.querySelector("#subdivision-review-progress");
const status = document.querySelector("#subdivision-decision-status");
let current = null;
let total = 0;
let deferredOffset = 0;
let submitting = false;

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);
}

function formatYear(year) {
  if (year == null) return "present";
  return year < 0 ? `${Math.abs(year)} BCE` : `${year} CE`;
}

function candidateButton(candidate, index, manual = false) {
  const evidence = manual ? "Manual search result" : (candidate.evidence || []).join("; ");
  const id = candidate.id || candidate.polity_id;
  return `<button type="button" class="type-choice parent-choice" data-parent-id="${escapeHtml(id)}">
    <strong>${index + 1}. ${escapeHtml(candidate.canonical_name)}</strong>
    <span>Histomap ID: ${escapeHtml(id)}</span>
    <small>${escapeHtml(evidence || "Canonical polity candidate")}</small>
  </button>`;
}

function bindChoices() {
  card.querySelectorAll(".parent-choice").forEach((button) => {
    button.addEventListener("click", () => confirmParent(button.dataset.parentId));
  });
}

async function searchParents() {
  const input = card.querySelector("#parent-search");
  const results = card.querySelector("#parent-search-results");
  const query = input.value.trim();
  if (query.length < 2) {
    results.innerHTML = "<p>Enter at least two characters.</p>";
    return;
  }
  const response = await fetch(`/api/polities/search?q=${encodeURIComponent(query)}&limit=10`);
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  const polities = payload.items.filter((item) => item.entity_type === "polity");
  results.innerHTML = polities.length
    ? polities.map((item, index) => candidateButton(item, index, true)).join("")
    : "<p>No polity matches found.</p>";
  bindChoices();
}

async function loadNext() {
  const response = await fetch(`/api/subdivision-reviews?limit=1&offset=${deferredOffset}`);
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  total = payload.total;
  current = payload.items[0] || null;
  progress.textContent = `${total} subdivision links remaining${deferredOffset ? ` · ${deferredOffset} deferred this session` : ""}`;
  if (!current) {
    card.innerHTML = "<h2>Queue complete</h2><p>Every classified subdivision has a confirmed parent polity.</p>";
    return;
  }
  const candidates = current.candidates || [];
  const wikidata = current.wikidata
    ? `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(current.wikidata)}" target="_blank" rel="noopener noreferrer">Wikidata (${escapeHtml(current.wikidata)}) ↗</a>`
    : "No Wikidata item";
  card.innerHTML = `<p class="review-rank">Subdivision awaiting parent polity</p>
    <h2>${escapeHtml(current.canonical_name)}</h2>
    <dl class="source-facts">
      <dt>Histomap ID</dt><dd>${escapeHtml(current.id)}</dd>
      <dt>Dates</dt><dd>${formatYear(current.dates?.[0])}–${formatYear(current.dates?.[1])}</dd>
      <dt>External page</dt><dd>${wikidata}</dd>
    </dl>
    <h3 class="candidate-heading">Suggested parent polities</h3>
    <div class="type-choice-list">${candidates.length ? candidates.slice(0, 9).map((item, index) => candidateButton(item, index)).join("") : "<p>No automatic parent was found. Search the canonical dataset below.</p>"}</div>
    <div class="parent-search"><label for="parent-search">Find another polity</label><div><input id="parent-search" type="search" placeholder="Name or Histomap ID"><button id="search-parent" type="button">Search</button></div><div id="parent-search-results" class="type-choice-list"></div></div>
    <div class="review-actions"><button id="defer-subdivision" type="button">Defer</button></div>`;
  bindChoices();
  card.querySelector("#search-parent").addEventListener("click", () => searchParents().catch(showError));
  card.querySelector("#parent-search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); searchParents().catch(showError); }
  });
  card.querySelector("#defer-subdivision").addEventListener("click", defer);
}

function showError(error) {
  status.className = "decision-status error";
  status.textContent = error.message;
}

async function confirmParent(parentId) {
  if (!current || submitting) return;
  submitting = true;
  status.className = "decision-status pending";
  status.textContent = "Saving subdivision link…";
  try {
    const reviewed = current;
    const response = await fetch(`/api/subdivision-reviews/${encodeURIComponent(reviewed.id)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ parent_id: parentId }),
    });
    if (!response.ok) throw new Error((await response.json()).detail || await response.text());
    deferredOffset = Math.min(deferredOffset, Math.max(0, total - 2));
    status.className = "decision-status success";
    status.textContent = `Saved: ${reviewed.canonical_name} is part of ${parentId}.`;
    await loadNext();
  } catch (error) {
    showError(error);
  } finally {
    submitting = false;
  }
}

async function defer() {
  if (!current || submitting) return;
  deferredOffset = total > deferredOffset + 1 ? deferredOffset + 1 : 0;
  status.className = "decision-status success";
  status.textContent = `Deferred ${current.canonical_name}.`;
  await loadNext();
}

document.addEventListener("keydown", (event) => {
  if (!current || submitting || event.target.matches("input, textarea, button, a, summary")) return;
  if (/^[1-9]$/.test(event.key)) {
    const candidate = current.candidates?.[Number(event.key) - 1];
    if (candidate) { event.preventDefault(); confirmParent(candidate.id); }
  } else if (event.key === "Enter" && current.candidates?.[0]) {
    event.preventDefault(); confirmParent(current.candidates[0].id);
  } else if (event.key.toLowerCase() === "s") {
    event.preventDefault(); defer();
  }
});

loadNext().catch(showError);
