const dashboard = document.querySelector("#review-dashboard");

const pipelines = [
  ["consolidation", "/consolidation-review", "Resolve identity and chronology", "Decide whether a record is independent, a duplicate, a phase of a specific polity, or a broad period/era shared by many entities."],
];

async function loadDashboard() {
  const response = await fetch("/api/review-dashboard");
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  const counts = payload.pipelines;
  const breakdowns = payload.breakdowns || {};
  dashboard.innerHTML = pipelines.map(([key, href, title, explanation]) => `
    <a class="review-pipeline-card" href="${href}">
      <span><strong>${title}</strong><small>${explanation}</small>${breakdowns[key] ? `<small>${Number(breakdowns[key].high).toLocaleString()} high-confidence overlaps · ${Number(breakdowns[key].medium).toLocaleString()} other overlaps · ${Number(breakdowns[key].period_role).toLocaleString()} period-role cases</small>` : ""}</span>
      <b>${Number(counts[key] || 0).toLocaleString()}<small>remaining</small></b>
    </a>`).join("");
}

loadDashboard().catch((error) => { dashboard.textContent = `Could not load review queues: ${error.message}`; });
