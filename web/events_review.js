// ROADMAP.md item 5 / docs/plans/2026-09-07-events-lane-design.md: a
// simple review queue for hand-authored events. Deliberately NOT
// consolidation-review's one-at-a-time/scored-candidates flow -- a
// hand-authored event already has its detail_of/bounds chosen by whoever
// created it, so this just resolves and lists what each one is attached
// to, for a reviewer to confirm or reject, all at once.

const list = document.querySelector("#events-review-list");
const progress = document.querySelector("#events-review-progress");
const status = document.querySelector("#events-review-status");

function setStatus(message, isError) {
  status.textContent = message;
  status.classList.toggle("is-error", Boolean(isError));
}

function attachmentSummary(item) {
  const detailOf = (item.detail_of_targets || [])
    .map((target) => `detail of ${escapeHtml(target.canonical_name)}`);
  const bounds = (item.bounds_targets || [])
    .map((target) => `${escapeHtml(target.edge)} of ${escapeHtml(target.canonical_name)} (${formatYear(target.start)}–${formatYear(target.end)})`);
  const parts = [...detailOf, ...bounds];
  return parts.length ? parts.join(", ") : "Not attached to anything yet.";
}

function eventCardHtml(item) {
  return `<article class="review-card compact-review-card" data-event-id="${escapeHtml(item.id)}">
    <h2>${escapeHtml(item.canonical_name)}</h2>
    <p>${formatYear(item.year)}</p>
    <p class="proposal-reason">${attachmentSummary(item)}</p>
    <div class="review-actions">
      <button type="button" class="events-review-accept">Accept</button>
      <button type="button" class="events-review-reject danger">Reject</button>
    </div>
  </article>`;
}

async function decide(eventId, decision) {
  const response = await fetch(`/api/events-review/${encodeURIComponent(eventId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`);
}

function wireCard(card) {
  const eventId = card.dataset.eventId;
  card.querySelector(".events-review-accept").addEventListener("click", async () => {
    try {
      await decide(eventId, "accepted");
      card.remove();
      setStatus("Accepted. Run a build for it to appear on /explore.", false);
      updateProgress();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
  card.querySelector(".events-review-reject").addEventListener("click", async () => {
    try {
      await decide(eventId, "excluded");
      card.remove();
      setStatus("Rejected -- the record stays on disk (audit trail), just excluded.", false);
      updateProgress();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
}

function updateProgress() {
  const remaining = list.querySelectorAll("[data-event-id]").length;
  progress.textContent = `${remaining} event${remaining === 1 ? "" : "s"} pending review`;
}

async function load() {
  const response = await fetch("/api/events-review");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const payload = await response.json();
  if (!payload.items.length) {
    list.innerHTML = "<p>No events pending review.</p>";
    progress.textContent = "0 events pending review";
    return;
  }
  list.innerHTML = payload.items.map(eventCardHtml).join("");
  list.querySelectorAll("[data-event-id]").forEach(wireCard);
  updateProgress();
}

load().catch((error) => {
  list.textContent = `Could not load the events review queue (${error.message}).`;
});
