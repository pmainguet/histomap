const card = document.querySelector("#period-review-card");
const progress = document.querySelector("#period-review-progress");
const status = document.querySelector("#period-decision-status");
const choices = [
  ["entity", "Entity row only", "A civilization, culture, people, or polity that acts as a historical subject. Example: Achaemenid Empire."],
  ["period", "Period overlay only", "A chronological interval used to contextualize entities. Example: European Bronze Age."],
  ["both", "Both, as linked records", "The source genuinely combines a societal subject and a named chronology. Example: Yayoi culture and Yayoi period."],
];
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

async function loadNext() {
  const response = await fetch(`/api/period-role-reviews?limit=1&offset=${deferredOffset}`);
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  total = payload.total;
  current = payload.items[0] || null;
  progress.textContent = `${total} period-role decisions remaining${deferredOffset ? ` · ${deferredOffset} deferred this session` : ""}`;
  if (!current) {
    card.innerHTML = "<h2>Queue complete</h2><p>All mixed period/entity records have been reviewed.</p>";
    return;
  }
  const wikidata = current.wikidata
    ? `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(current.wikidata)}" target="_blank" rel="noopener noreferrer">Wikidata (${escapeHtml(current.wikidata)}) ↗</a>` : "No Wikidata item";
  const wikipedia = current.wikipedia_en
    ? ` · <a href="${escapeHtml(current.wikipedia_en)}" target="_blank" rel="noopener noreferrer">Wikipedia (English) ↗</a>` : "";
  card.innerHTML = `<p class="review-rank">Mixed entity and period classification</p>
    <h2>${escapeHtml(current.canonical_name)}</h2>
    <p class="source-explanation">Wikidata places this item in a <strong>${escapeHtml(current.period_kinds.join(" / "))} period</strong> branch and Histomap currently treats it as <strong>${escapeHtml(current.entity_type)}</strong>.</p>
    <dl class="source-facts">
      <dt>Dates</dt><dd>${formatYear(current.dates?.[0])}–${formatYear(current.dates?.[1])}</dd>
      <dt>Prominence</dt><dd>${Number(current.prominence_score || 0).toFixed(1)} / 100</dd>
      <dt>External pages</dt><dd class="source-links">${wikidata}${wikipedia}</dd>
      <dt>Effective Wikidata types</dt><dd>${escapeHtml(current.direct_type_qids.join(", "))}</dd>
      <dt>Why review is needed</dt><dd>${escapeHtml(current.reason)}</dd>
    </dl>
    <h3 class="candidate-heading">Choose its timeline role</h3>
    <div class="type-choice-list">${choices.map(([value, label, explanation], index) => `<button type="button" class="type-choice" data-timeline-role="${value}"><strong>${index + 1}. ${label}</strong><span>${escapeHtml(explanation)}</span></button>`).join("")}</div>
    <div class="review-actions"><button id="defer-period" type="button">Defer</button></div>`;
  card.querySelectorAll(".type-choice").forEach((button) => button.addEventListener("click", () => decide(button.dataset.timelineRole)));
  card.querySelector("#defer-period").addEventListener("click", defer);
}

function disable(disabled) {
  card.querySelectorAll("button").forEach((button) => { button.disabled = disabled; });
}

async function decide(timelineRole) {
  if (!current || submitting) return;
  submitting = true;
  disable(true);
  status.className = "decision-status pending";
  status.textContent = "Saving timeline role…";
  try {
    const reviewed = current;
    const response = await fetch(`/api/period-role-reviews/${encodeURIComponent(reviewed.id)}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ timeline_role: timelineRole }),
    });
    if (!response.ok) throw new Error((await response.json()).detail || await response.text());
    deferredOffset = Math.min(deferredOffset, Math.max(0, total - 2));
    status.className = "decision-status success";
    status.textContent = `Saved ${reviewed.canonical_name} as ${timelineRole}. Loading next…`;
    await loadNext();
  } catch (error) {
    status.className = "decision-status error";
    status.textContent = `Decision was not saved: ${error.message}`;
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
  if (/^[1-3]$/.test(event.key)) {
    event.preventDefault();
    decide(choices[Number(event.key) - 1][0]);
  } else if (event.key.toLowerCase() === "s") {
    event.preventDefault();
    defer();
  }
});

loadNext().catch((error) => { card.textContent = `Could not load period-role reviews: ${error.message}`; });
