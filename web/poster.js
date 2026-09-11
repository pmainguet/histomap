// Minimal generation surface for the printable poster (ROADMAP.md item
// 3b) -- style, a year range, and that's it, per explicit request. See
// docs/plans/2026-09-08-poster-visualization-design.md.

const form = document.querySelector("#poster-form");
const status = document.querySelector("#poster-status");

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const style = document.querySelector("#poster-style").value;
  const widthSource = document.querySelector("#poster-width-source").value;
  const start = document.querySelector("#poster-start").value;
  const end = document.querySelector("#poster-end").value;
  if (Number(end) <= Number(start)) {
    status.textContent = "\"To year\" must be after \"From year\".";
    status.classList.add("error");
    return;
  }
  status.classList.remove("error");
  status.textContent = "Opening in a new tab…";
  const url = `/api/poster.svg?style=${encodeURIComponent(style)}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&width_source=${encodeURIComponent(widthSource)}`;
  window.open(url, "_blank", "noopener");
});
