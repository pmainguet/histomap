function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);
}

function formatYear(year) {
  if (year === null || year === undefined) return "present";
  return year < 0 ? `${Math.abs(year).toLocaleString()} BCE` : `${year.toLocaleString()} CE`;
}

function renderChapter(chapter) {
  const topNames = chapter.top_entities.map((e) => escapeHtml(e.canonical_name)).join(", ") || "no linked entities yet";
  return `
    <a class="chapter-tile" href="/?era=${encodeURIComponent(chapter.id)}">
      <h2>${escapeHtml(chapter.canonical_name)}</h2>
      <p class="chapter-span">${formatYear(chapter.start)} – ${formatYear(chapter.end)}</p>
      <p class="chapter-count">${chapter.entity_count.toLocaleString()} entities</p>
      <p class="chapter-top">${topNames}</p>
    </a>`;
}

async function main() {
  const grid = document.querySelector("#chapter-grid");
  try {
    const response = await fetch("/explore_index.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const chapters = await response.json();
    grid.innerHTML = chapters.map(renderChapter).join("");
  } catch (error) {
    grid.innerHTML = `<p class="error">Could not load explore_index.json (${error.message}). Run the build command from the repository root.</p>`;
  }
}

main();
