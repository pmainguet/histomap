// Shared, small utility functions used across every page (Timeline, Explore,
// and the /reviews family). Loaded as a plain classic script (not a module)
// so its top-level declarations become real globals -- every other page
// script, whether classic (explore*.js) or `type="module"` (app.js and the
// review pages), can call these as bare identifiers; a module's own scope
// chain falls through to the shared global scope for anything it doesn't
// declare itself. Must be the first <script> tag on any page that uses it.
//
// Two functions were deliberately NOT centralized here despite looking like
// duplicates at first glance -- they have real behavioral differences, found
// during the 2026-08-31 simplification pass:
// - app.js's own formatYear has no null/undefined handling (its callers
//   never pass one) and explore_timeline.js's own formatYear both handles
//   "present" AND comma-formats large numbers (`.toLocaleString()`) -- the
//   version here matches the /reviews family's own (no comma formatting).
//   Each of those two files keeps its own definition; loading this file on
//   their pages is still safe (a classic-script redeclaration of the same
//   global name is a harmless last-one-wins overwrite, and a module's own
//   top-level declaration shadows the global within its own module scope
//   without touching it at all).

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[character]);
}

function displayTerm(value) {
  return String(value).replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatYear(year) {
  return year == null ? "present" : year < 0 ? `${Math.abs(year)} BCE` : `${year} CE`;
}

function svgEl(name, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}
