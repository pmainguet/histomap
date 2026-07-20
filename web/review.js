const card = document.querySelector("#review-card");
const progress = document.querySelector("#review-progress");
const jobStatus = document.querySelector("#job-status");
let current = null;
let total = 0;
let deferredOffset = 0;

function candidateMarkup(candidate, index) {
  const links = (candidate.source_links || []).map((link) => `<a href="${link.url}" target="_blank" rel="noopener noreferrer" data-source-link>${link.label} ↗</a>`).join(" · ");
  return `<article class="candidate">
    <strong>${index + 1}. ${candidate.canonical_name}</strong>
    <span>${candidate.polity_id}</span>
    <small>Total ${candidate.total_score.toFixed(1)} · name ${candidate.name_score.toFixed(1)} · dates ${candidate.date_score.toFixed(1)} · geography ${candidate.geography_score.toFixed(1)}</small>
    <span class="source-links">${links || "No external identifier"}</span>
    <button class="accept-candidate" data-polity-id="${candidate.polity_id}">Accept this match</button>
  </article>`;
}

function sourceLinksMarkup(links) {
  return links.map((link) => `<a href="${link.url}" target="_blank" rel="noopener noreferrer">${link.label} ↗</a>`).join(" · ");
}

async function loadNext() {
  const response = await fetch(`/api/reviews?limit=1&offset=${deferredOffset}`);
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  total = payload.total;
  current = payload.items[0] || null;
  progress.textContent = `${total} prioritized decisions remaining${deferredOffset ? ` · ${deferredOffset} deferred this session` : ""}`;
  if (!current) {
    card.innerHTML = "<h2>Queue complete</h2><p>Apply the saved decisions to reconciliation.</p>";
    return;
  }
  const parts = current.priority_components;
  card.innerHTML = `<p class="review-rank">Priority ${current.review_priority.toFixed(1)}</p>
    <h2>${current.seshat_name}</h2>
    <p>${current.start_year} to ${current.end_year} · ${current.seshat_id}</p>
    <p class="source-links">${sourceLinksMarkup(current.source_links || [])}</p>
    <p class="score-breakdown">Source ${parts.source_importance.toFixed(0)} · candidate impact ${parts.candidate_impact.toFixed(0)} · quality ${parts.quality.toFixed(0)} · ambiguity ${parts.ambiguity.toFixed(0)}</p>
    <div class="candidate-list">${current.candidates.map(candidateMarkup).join("")}</div>
    <div class="review-actions"><button id="reject" class="danger">Reject candidates</button><button id="defer">Defer</button></div>`;
  card.querySelectorAll(".accept-candidate").forEach((button) => button.addEventListener("click", () => decide("accept", button.dataset.polityId)));
  card.querySelector("#reject").addEventListener("click", () => decide("reject"));
  card.querySelector("#defer").addEventListener("click", () => decide("defer"));
}

async function decide(decision, polityId = null) {
  if (!current) return;
  const response = await fetch(`/api/reviews/${encodeURIComponent(current.seshat_id)}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, polity_id: polityId }),
  });
  if (!response.ok) throw new Error(await response.text());
  if (decision === "defer") {
    deferredOffset = total > deferredOffset + 1 ? deferredOffset + 1 : 0;
    await loadNext();
    return;
  }
  deferredOffset = Math.min(deferredOffset, Math.max(0, total - 2));
  await loadNext();
}

async function startAction(action) {
  const response = await fetch(`/api/actions/${action}`, { method: "POST" });
  if (!response.ok) throw new Error(await response.text());
  jobStatus.textContent = `${action} running…`;
  pollJob();
}

async function pollJob() {
  const job = await fetch("/api/actions/status").then((response) => response.json());
  jobStatus.textContent = job.status === "running" ? `${job.action} running…` : `${job.action || "pipeline"}: ${job.status}`;
  if (job.status === "running") setTimeout(pollJob, 1000);
  if (job.status === "complete") loadNext();
}

document.querySelector("#apply-decisions").addEventListener("click", () => startAction("reconcile"));
document.querySelector("#build-data").addEventListener("click", () => startAction("build"));
document.addEventListener("keydown", (event) => {
  if (!current || event.target.matches("input, textarea")) return;
  if (/^[1-5]$/.test(event.key) && current.candidates[Number(event.key) - 1]) decide("accept", current.candidates[Number(event.key) - 1].polity_id);
  if (event.key.toLowerCase() === "r") decide("reject");
  if (event.key.toLowerCase() === "s") decide("defer");
});

loadNext().catch((error) => { card.textContent = `Could not load reviews: ${error.message}`; });
