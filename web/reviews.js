const dashboard = document.querySelector("#review-dashboard");

const pipelines = [
  ["source_matching", "/review", "1. Match source records", "Reconcile incoming Seshat records with canonical Histomap entities before editing the resulting canonical set."],
  ["consolidation", "/consolidation-review", "2. Consolidate entities", "Decide whether similar canonical records are independent, duplicates, or dated phases/aspects of another entity."],
  ["entity_type", "/type-review", "3. Classify entities", "Choose whether each surviving record is a civilization, polity, subdivision, culture, people, tribe, micronation, or archaeological horizon."],
  ["subdivision_parent", "/subdivision-review", "4. Link subdivisions", "Confirm the containing polity for records classified as subdivisions."],
  ["period_role", "/period-review", "5. Review period roles", "Decide whether ambiguous records belong on the entity timeline, the period layer, or both."],
];

async function loadDashboard() {
  const response = await fetch("/api/review-dashboard");
  if (!response.ok) throw new Error(await response.text());
  const counts = (await response.json()).pipelines;
  dashboard.innerHTML = pipelines.map(([key, href, title, explanation]) => `
    <a class="review-pipeline-card" href="${href}">
      <span><strong>${title}</strong><small>${explanation}</small></span>
      <b>${Number(counts[key] || 0).toLocaleString()}<small>remaining</small></b>
    </a>`).join("");
}

loadDashboard().catch((error) => { dashboard.textContent = `Could not load review queues: ${error.message}`; });
