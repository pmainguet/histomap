const chart = document.querySelector("#chart");
const details = document.querySelector("#details");
const summary = document.querySelector("#summary");
const startInput = document.querySelector("#year-start");
const endInput = document.querySelector("#year-end");

const palette = ["#a9563f", "#d0913d", "#59755e", "#51758e", "#725c87", "#9a6f72", "#797044"];
let polities = [];

function formatYear(year) {
  if (year < 0) return `${Math.abs(year)} BCE`;
  return `${year} CE`;
}

function hash(text) {
  let value = 0;
  for (const char of text) value = ((value << 5) - value + char.charCodeAt(0)) | 0;
  return Math.abs(value);
}

function weightAt(polity, year) {
  const points = Object.entries(polity.weight_by_era).map(([y, w]) => [+y, +w]).sort((a, b) => a[0] - b[0]);
  if (!points.length) return 1;
  if (year <= points[0][0]) return points[0][1];
  if (year >= points.at(-1)[0]) return points.at(-1)[1];
  const upper = points.findIndex(([pointYear]) => pointYear >= year);
  const [y0, w0] = points[upper - 1];
  const [y1, w1] = points[upper];
  return w0 + (w1 - w0) * ((year - y0) / (y1 - y0));
}

function showDetails(polity) {
  const description = polity.text?.short_adult_en || polity.notes || "Draft record; description pending review.";
  details.innerHTML = `<h2>${polity.canonical_name}</h2>
    <p>${description}</p>
    <dl><dt>Dates</dt><dd>${formatYear(polity.start)}–${polity.end == null ? "present" : formatYear(polity.end)}</dd>
    <dt>Region</dt><dd>${polity.region || "unclassified"}</dd>
    <dt>Confidence</dt><dd>${polity.start_confidence} / ${polity.end_confidence}</dd></dl>`;
}

function svgElement(name, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
  return element;
}

function render() {
  const yearStart = Number(startInput.value);
  const yearEnd = Number(endInput.value);
  if (!Number.isFinite(yearStart) || !Number.isFinite(yearEnd) || yearEnd <= yearStart) {
    chart.innerHTML = '<p class="error">Choose an end year later than the start year.</p>';
    return;
  }
  const visible = polities.filter((p) => p.start < yearEnd && (p.end == null || p.end > yearStart));
  const width = Math.max(760, visible.length * 58 + 110);
  const height = Math.max(900, (yearEnd - yearStart) * .7);
  const margin = { top: 35, right: 20, bottom: 25, left: 88 };
  const innerHeight = height - margin.top - margin.bottom;
  const y = (year) => margin.top + ((year - yearStart) / (yearEnd - yearStart)) * innerHeight;
  const svg = svgElement("svg", { viewBox: `0 0 ${width} ${height}`, width, height });

  const tickStep = Math.max(50, 10 ** Math.floor(Math.log10((yearEnd - yearStart) / 8)));
  for (let year = Math.ceil(yearStart / tickStep) * tickStep; year <= yearEnd; year += tickStep) {
    svg.append(svgElement("line", { x1: margin.left, x2: width - margin.right, y1: y(year), y2: y(year), class: "grid-line" }));
    const label = svgElement("text", { x: margin.left - 10, y: y(year) + 4, "text-anchor": "end", class: "axis-label" });
    label.textContent = formatYear(year);
    svg.append(label);
  }

  visible.sort((a, b) => a.start - b.start || a.canonical_name.localeCompare(b.canonical_name));
  visible.forEach((polity, index) => {
    const start = Math.max(yearStart, polity.start);
    const end = Math.min(yearEnd, polity.end ?? yearEnd);
    const mid = start + (end - start) / 2;
    const bandWidth = 12 + weightAt(polity, mid) * 4;
    const center = margin.left + 35 + index * 58;
    const path = svgElement("path", {
      d: `M ${center - bandWidth / 2} ${y(start)} L ${center + bandWidth / 2} ${y(start)} L ${center + bandWidth / 2} ${y(end)} L ${center - bandWidth / 2} ${y(end)} Z`,
      fill: palette[hash(polity.culture_group || polity.id) % palette.length],
      opacity: polity.start_confidence === "low" ? .55 : .86,
      class: "band",
      tabindex: "0",
    });
    path.addEventListener("mouseenter", () => showDetails(polity));
    path.addEventListener("focus", () => showDetails(polity));
    const title = svgElement("title");
    title.textContent = `${polity.canonical_name}: ${formatYear(polity.start)}–${polity.end == null ? "present" : formatYear(polity.end)}`;
    path.append(title);
    svg.append(path);
  });

  chart.replaceChildren(svg);
  summary.textContent = `${visible.length} of ${polities.length} polities visible`;
}

document.querySelector("#apply").addEventListener("click", render);

try {
  const response = await fetch("../data.json");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  polities = await response.json();
  if (polities.length) {
    startInput.value = Math.min(...polities.map((p) => p.start));
    endInput.value = Math.max(...polities.map((p) => p.end ?? new Date().getFullYear()));
  }
  render();
} catch (error) {
  chart.innerHTML = `<p class="error">Could not load data.json (${error.message}). Run the build and serve commands from the repository root.</p>`;
}
