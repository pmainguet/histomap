// Detail + edit panel for /explore -- mirrors app.js's showDetails/
// showPeriodDetails (the "/" timeline's panel), plus its own editing
// actions: convert a polity's entity_type or demote it to a period
// (POST .../convert-to-period), convert a period to an entity/polity
// (POST .../promote-to-entity), and a general "Edit fields" raw editor
// (PATCH .../fields) for anything else in the record (tier,
// broader_periods, dates, ...) that has no dedicated control. See
// STATUS.md's "review workspace" section for why this replaced the
// earlier read-only-only design.
//
// IMPORTANT: /explore's chart bands (which row/lane something renders in)
// come from the separately pre-built explore_tree.json, not from the
// politiesById/periodsById maps these edits update live -- an edit here
// updates the detail panel and the in-memory cache immediately, but the
// chart itself only reflects it after the next `build` run. Every save
// confirmation says so explicitly.

const explorePanel = document.querySelector("#details");
const explorePanelBackdrop = document.querySelector("#detail-backdrop");

const ENTITY_TYPE_OPTIONS = [
  "polity", "civilization", "subdivision", "micronation",
  "culture", "people", "tribe", "archaeological_horizon",
];
const REBUILD_NOTE = "Saved. The record is updated; run a build for /explore's chart bands to reflect it.";

async function postJson(url, method, body) {
  const response = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
  return payload;
}

function optionsHtml(options, selected) {
  return options.map((value) =>
    `<option value="${escapeHtml(value)}"${value === selected ? " selected" : ""}>${escapeHtml(displayTerm(value))}</option>`
  ).join("");
}

// Geography editor -- polities only (periods have no geography endpoint).
// Mirrors app.js's geographyEditorMarkup/syncContinentsFromCountries/
// saveGeography ("/"'s own equivalent) closely enough that the two stay easy
// to compare, just renamed to this file's detail-* class convention.
function geographyEditorHtml(polity, geographyOptions) {
  const selectedContinents = new Set(polity.geography?.continents || []);
  const selectedCountries = new Set(polity.geography?.present_countries || []);
  const countries = [...(geographyOptions?.countries || [])].sort((a, b) => {
    const selectedDifference = Number(selectedCountries.has(b.code)) - Number(selectedCountries.has(a.code));
    return selectedDifference || a.label.localeCompare(b.label);
  });
  return `<details class="detail-geography-edit">
    <summary>Edit geography</summary>
    <fieldset><legend>Continents</legend><div class="geography-checkboxes">
      ${(geographyOptions?.continents || []).map((continent) => `<label><input type="checkbox" name="detail-continent" value="${escapeHtml(continent)}" ${selectedContinents.has(continent) ? "checked" : ""}> ${escapeHtml(displayTerm(continent))}</label>`).join("")}
    </div></fieldset>
    <label class="geography-primary">Primary continent / swimlane
      <select name="detail-primary-continent"><option value="">Automatic</option>${(geographyOptions?.continents || []).map((continent) => `<option value="${escapeHtml(continent)}" ${polity.geography?.primary_continent === continent ? "selected" : ""}>${escapeHtml(displayTerm(continent))}</option>`).join("")}</select>
    </label>
    <fieldset><legend>Present countries</legend>
      <input class="country-filter" type="search" placeholder="Filter countries…" aria-label="Filter country list">
      <div class="country-checklist">${countries.map((country) => `<label data-country-search="${escapeHtml(`${country.label} ${country.code}`.toLowerCase())}"><input type="checkbox" name="detail-country" value="${escapeHtml(country.code)}" ${selectedCountries.has(country.code) ? "checked" : ""}> ${escapeHtml(country.label)} <small>${escapeHtml(country.code)}</small></label>`).join("")}</div>
      <small>Choosing countries automatically updates the continents above.</small>
    </fieldset>
    <div class="detail-edit-row"><button type="button" class="detail-save-geography">Save geography</button></div>
  </details>`;
}

function wireGeographyEditor(polity, ctx, onSaved, setStatus) {
  const editor = explorePanel.querySelector(".detail-geography-edit");
  if (!editor) return;
  const syncContinentsFromCountries = () => {
    const selectedCountries = new Set(
      [...editor.querySelectorAll('input[name="detail-country"]:checked')].map((input) => input.value),
    );
    const inferred = new Set(
      (ctx.geographyOptions?.countries || [])
        .filter((country) => selectedCountries.has(country.code))
        .flatMap((country) => country.continents || []),
    );
    editor.querySelectorAll('input[name="detail-continent"]').forEach((input) => {
      input.checked = inferred.has(input.value);
    });
    const primary = editor.querySelector('[name="detail-primary-continent"]');
    if (primary.value && !inferred.has(primary.value)) primary.value = "";
  };
  editor.querySelectorAll('input[name="detail-country"]').forEach((input) => {
    input.addEventListener("change", syncContinentsFromCountries);
  });
  const filterInput = editor.querySelector(".country-filter");
  filterInput.addEventListener("input", () => {
    const query = filterInput.value.trim().toLowerCase();
    editor.querySelectorAll(".country-checklist label").forEach((label) => {
      label.hidden = query.length > 0 && !label.dataset.countrySearch.includes(query);
    });
  });
  editor.querySelector(".detail-save-geography").addEventListener("click", async () => {
    const continents = [...editor.querySelectorAll('input[name="detail-continent"]:checked')].map((input) => input.value);
    const countries = [...editor.querySelectorAll('input[name="detail-country"]:checked')].map((input) => input.value);
    const primary = editor.querySelector('[name="detail-primary-continent"]').value || null;
    if (primary && !continents.includes(primary)) {
      setStatus("Primary continent must also be checked.", true);
      return;
    }
    try {
      const payload = await postJson(`/api/polities/${encodeURIComponent(polity.id)}/geography`, "PATCH", {
        continents, primary_continent: primary, present_countries: countries,
      });
      const updated = { ...polity, geography: payload.geography, manual_overrides: payload.manual_overrides };
      ctx.politiesById.set(polity.id, updated);
      onSaved(updated);
      ctx.onEdit?.();
      setStatus(REBUILD_NOTE, false);
    } catch (error) {
      setStatus(error.message, true);
    }
  });
}

function detailOfCandidateButton(candidate) {
  const id = candidate.polity_id || candidate.period_id;
  return `<button type="button" class="type-choice detail-of-choice" data-detail-of-id="${escapeHtml(id)}">
    <strong>${escapeHtml(candidate.canonical_name)}</strong>
    <span>${escapeHtml(candidate.kind === "period" ? "Period" : "Polity")} · Histomap ID: ${escapeHtml(id)} · ${formatYear(candidate.canonical_start)}–${formatYear(candidate.canonical_end)}</span>
  </button>`;
}

// Search-and-pick-a-parent pattern (the /subdivision-review workflow this
// once mirrored was removed -- see ROADMAP.md), PATCHing `detail_of` via
// the same generic /fields endpoint the raw editor above already uses (it
// merges rather than replaces, so a bare `{ detail_of: ... }` body is
// enough). Only rendered (see detailOfEditorHtml) when the record has no
// `detail_of` yet -- once set, the panel shows a plain "Clear" button
// instead, no search box. `kind` is "polity" or "period" -- a polity's
// target search stays polity-only (the reverse direction is never
// allowed, see build.py's validate_entity_relationships), but a period's
// target can be either a period or a polity (build.py's
// validate_period_detail_of), so its search merges both endpoints.
function wireDetailOfEditor(record, kind, ctx, onSaved, setStatus) {
  const editor = explorePanel.querySelector(".detail-of-edit");
  if (!editor) return;
  const fieldsUrl = kind === "polity"
    ? `/api/polities/${encodeURIComponent(record.id)}/fields`
    : `/api/periods/${encodeURIComponent(record.id)}/fields`;
  const byIdMap = kind === "polity" ? ctx.politiesById : ctx.periodsById;
  const saveDetailOf = async (targetId) => {
    try {
      const result = await postJson(fieldsUrl, "PATCH", { detail_of: targetId });
      byIdMap.set(record.id, result.document);
      onSaved(result.document);
      ctx.onEdit?.();
      setStatus(REBUILD_NOTE, false);
    } catch (error) {
      setStatus(error.message, true);
    }
  };
  const clearButton = editor.querySelector(".detail-of-clear");
  if (clearButton) {
    clearButton.addEventListener("click", () => saveDetailOf(null));
    return;
  }
  const input = editor.querySelector("#detail-of-search");
  const resultsEl = editor.querySelector(".detail-of-search-results");
  const searchOneKind = async (url, resultKind) => {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    return payload.items.map((item) => ({ ...item, kind: resultKind }));
  };
  const runSearch = async () => {
    const query = input.value.trim();
    if (query.length < 2) {
      resultsEl.innerHTML = "<p>Enter at least two characters.</p>";
      return;
    }
    const q = encodeURIComponent(query);
    const searches = kind === "polity"
      ? [searchOneKind(`/api/polities/search?q=${q}&limit=10`, "polity")]
      : [searchOneKind(`/api/polities/search?q=${q}&limit=10`, "polity"), searchOneKind(`/api/periods/search?q=${q}&limit=10`, "period")];
    const resultSets = await Promise.all(searches);
    const candidates = resultSets.flat()
      .filter((item) => (item.polity_id || item.period_id) !== record.id)
      .sort((a, b) => b.search_score - a.search_score)
      .slice(0, 10);
    resultsEl.innerHTML = candidates.length
      ? candidates.map(detailOfCandidateButton).join("")
      : "<p>No matches found.</p>";
    resultsEl.querySelectorAll(".detail-of-choice").forEach((button) => {
      button.addEventListener("click", () => saveDetailOf(button.dataset.detailOfId));
    });
  };
  editor.querySelector(".detail-of-search-btn").addEventListener("click", () => runSearch().catch((error) => setStatus(error.message, true)));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runSearch().catch((error) => setStatus(error.message, true));
    }
  });
}

// Shared by both renderPolityDetails and renderPeriodDetails: the
// "Convert to..." + "Edit fields" block, and the wiring for both. `kind`
// is "polity" or "period"; `record` is the current cached document;
// `onSaved(updatedRecord)` re-renders the panel with fresh data after any
// successful save, so the displayed details never go stale.
// ROADMAP.md "0 bis" -- the /consolidation-review "detail_of" decision and
// the raw edit-fields textarea were previously the only ways to set this
// field; this gives it a friendly search-and-pick control right in
// /explore's own side panel, mirroring subdivision_review.js's identical
// "find another polity" parent-picker (same /api/polities/search endpoint,
// same .parent-search/.type-choice/.type-choice-list markup and CSS).
function detailOfEditorHtml(record, ctx) {
  const current = record.detail_of ? entityRefButton(ctx, record.detail_of) : null;
  return `<details class="detail-of-edit">
    <summary>Set as detail of</summary>
    ${current
      ? `<p>Currently a detail of ${current}. <button class="detail-of-clear" type="button">Clear</button></p>`
      : `<p>Not currently marked as a detail of another entity.</p>
         <div class="parent-search">
           <label for="detail-of-search">Find the container entity</label>
           <div><input id="detail-of-search" type="search" placeholder="Name or Histomap ID"><button class="detail-of-search-btn" type="button">Search</button></div>
           <div class="detail-of-search-results type-choice-list"></div>
         </div>`}
  </details>`;
}

// ROADMAP.md item: "Allow simple edit of the parent era for periods in
// /explore (dropdown)." Only rendered for tier: "period" records (the
// default tier, named periods) -- a regional_era's own parent is a
// macro_chapter, not another era, and a macro_chapter has no parent at
// all (see ONTOLOGY.md's "chronological hierarchy" table), so this
// control wouldn't mean the same thing there. Sets broader_periods to
// exactly one era id, matching ONTOLOGY.md's "single parent by
// convention" rule -- the same generic /fields PATCH endpoint every
// other simple editor here already uses.
function parentEraEditorHtml(period, ctx) {
  const eras = [...ctx.periodsById.values()]
    .filter((candidate) => candidate.tier === "regional_era")
    .sort((a, b) => a.canonical_name.localeCompare(b.canonical_name));
  const currentParent = (period.broader_periods || [])[0] || "";
  return `<div class="detail-edit-row">
    <select class="detail-parent-era-select" aria-label="Parent era">
      <option value="">No parent era</option>
      ${eras.map((era) => `<option value="${escapeHtml(era.id)}" ${era.id === currentParent ? "selected" : ""}>${escapeHtml(era.canonical_name)}</option>`).join("")}
    </select>
    <button class="detail-save-parent-era" type="button">Set parent era</button>
  </div>`;
}

function wireParentEraEditor(period, ctx, onSaved, setStatus) {
  const button = explorePanel.querySelector(".detail-save-parent-era");
  if (!button) return;
  button.addEventListener("click", async () => {
    const eraId = explorePanel.querySelector(".detail-parent-era-select").value;
    try {
      const result = await postJson(`/api/periods/${encodeURIComponent(period.id)}/fields`, "PATCH", {
        broader_periods: eraId ? [eraId] : [],
      });
      ctx.periodsById.set(period.id, result.document);
      onSaved(result.document);
      ctx.onEdit?.();
      setStatus(REBUILD_NOTE, false);
    } catch (error) {
      setStatus(error.message, true);
    }
  });
}

function editControlsHtml(kind, record, geographyOptions, ctx) {
  const convertBlock = kind === "polity"
    ? `<div class="detail-edit-row">
         <select class="detail-entity-type-select" name="entity-type" aria-label="Entity type">${optionsHtml(ENTITY_TYPE_OPTIONS, record.entity_type || "polity")}</select>
         <button class="detail-convert-entity-type" type="button">Set entity type</button>
       </div>
       <div class="detail-edit-row">
         <button class="detail-convert-to-period" type="button">Convert to period</button>
       </div>
       ${detailOfEditorHtml(record, ctx)}
       ${geographyEditorHtml(record, geographyOptions)}`
    : `<div class="detail-edit-row">
         <select class="detail-entity-type-select" name="entity-type" aria-label="Entity type">${optionsHtml(ENTITY_TYPE_OPTIONS, "polity")}</select>
         <button class="detail-convert-to-entity" type="button">Convert to entity</button>
       </div>
       ${(record.tier || "period") === "period" ? parentEraEditorHtml(record, ctx) : ""}
       ${detailOfEditorHtml(record, ctx)}`;
  return `<details class="detail-edit">
      <summary>Edit</summary>
      ${convertBlock}
      <details class="detail-raw-edit">
        <summary>Edit fields</summary>
        <textarea class="detail-raw-textarea" name="raw-fields" aria-label="Raw record fields (JSON)" rows="14" spellcheck="false">${escapeHtml(JSON.stringify(record, null, 2))}</textarea>
        <div class="detail-edit-row">
          <button class="detail-raw-save" type="button">Save fields</button>
        </div>
      </details>
      <p class="detail-edit-status" role="status"></p>
      <div class="detail-edit-row">
        <button class="detail-delete danger" type="button">Delete permanently</button>
      </div>
    </details>`;
}

function wireEditControls(kind, record, ctx, onSaved) {
  // Re-queries the live element every call rather than capturing it once --
  // onSaved(updated) fully re-renders the panel (so displayed dates/entity
  // type/etc. reflect the save), which replaces this element; setting the
  // message before that re-render would just get wiped by it, so every
  // handler below calls onSaved() first, then setStatus() against the fresh
  // element that re-render just created.
  const setStatus = (message, isError) => {
    const status = explorePanel.querySelector(".detail-edit-status");
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("is-error", Boolean(isError));
  };
  const idPath = kind === "polity" ? `/api/polities/${encodeURIComponent(record.id)}` : `/api/periods/${encodeURIComponent(record.id)}`;
  wireDetailOfEditor(record, kind, ctx, onSaved, setStatus);
  if (kind === "polity") wireGeographyEditor(record, ctx, onSaved, setStatus);
  if (kind !== "polity") wireParentEraEditor(record, ctx, onSaved, setStatus);

  if (kind === "polity") {
    explorePanel.querySelector(".detail-convert-entity-type").addEventListener("click", async () => {
      const entityType = explorePanel.querySelector(".detail-entity-type-select").value;
      try {
        await postJson(`${idPath}/entity-type`, "PATCH", { entity_type: entityType });
        const updated = { ...record, entity_type: entityType };
        ctx.politiesById.set(record.id, updated);
        onSaved(updated);
        ctx.onEdit?.();
        setStatus(REBUILD_NOTE, false);
      } catch (error) {
        setStatus(error.message, true);
      }
    });
    explorePanel.querySelector(".detail-convert-to-period").addEventListener("click", async () => {
      if (!confirm(`Convert "${record.canonical_name}" to a period? It will stop appearing in the Polities row after the next build.`)) return;
      try {
        const result = await postJson(`${idPath}/convert-to-period`, "POST");
        ctx.onEdit?.();
        setStatus(`${REBUILD_NOTE} New period id: ${result.period_id}.`, false);
      } catch (error) {
        setStatus(error.message, true);
      }
    });
  } else {
    explorePanel.querySelector(".detail-convert-to-entity").addEventListener("click", async () => {
      const entityType = explorePanel.querySelector(".detail-entity-type-select").value;
      if (!confirm(`Convert "${record.canonical_name}" to a polity (entity type: ${entityType})? The period record will be deleted after the next build.`)) return;
      try {
        const result = await postJson(`${idPath}/promote-to-entity`, "POST", { entity_type: entityType });
        ctx.onEdit?.();
        setStatus(`${REBUILD_NOTE} New polity id: ${result.entity_id}.`, false);
      } catch (error) {
        setStatus(error.message, true);
      }
    });
  }

  explorePanel.querySelector(".detail-raw-save").addEventListener("click", async () => {
    const textarea = explorePanel.querySelector(".detail-raw-textarea");
    let fields;
    try {
      fields = JSON.parse(textarea.value);
    } catch (error) {
      setStatus(`Invalid JSON: ${error.message}`, true);
      return;
    }
    try {
      const result = await postJson(`${idPath}/fields`, "PATCH", fields);
      if (kind === "polity") ctx.politiesById.set(record.id, result.document);
      else ctx.periodsById.set(record.id, result.document);
      onSaved(result.document);
      ctx.onEdit?.();
      setStatus(REBUILD_NOTE, false);
    } catch (error) {
      setStatus(error.message, true);
    }
  });

  // Hard delete -- unlike every other button here (which patches the
  // record), this removes it entirely. Refused (409) with a list of
  // remaining references if anything else still points to it (see
  // find_delete_blockers in server/app.py) -- that message surfaces here
  // rather than closing the panel, so the reviewer can go fix the
  // reference first.
  explorePanel.querySelector(".detail-delete").addEventListener("click", async () => {
    if (!confirm(`Permanently delete "${record.canonical_name}"? This cannot be undone from here -- only from git history.`)) return;
    try {
      await postJson(idPath, "DELETE");
      if (kind === "polity") ctx.politiesById.delete(record.id);
      else ctx.periodsById.delete(record.id);
      ctx.onEdit?.();
      closeExploreDetails();
    } catch (error) {
      setStatus(error.message, true);
    }
  });
}

// escapeHtml, displayTerm live in common.js, loaded first on /explore.

const exploreCountryNames = new Intl.DisplayNames(["en"], { type: "region" });

const TIER_KICKER = {
  macro_chapter: "Macro chapter",
  regional_era: "Regional era",
  period: "Period",
};

// A record's own id may not resolve (e.g. a broader_periods/successor
// pointing at something outside the currently-loaded set) -- fall back to
// a displayable version of the raw id rather than showing nothing.
// Look up id in map, fall back to a displayable version of the raw id
// (a stale/mistyped reference pointing outside the currently-loaded set)
// rather than showing nothing; wrap in a clickable ref button only when
// the target actually resolves. periodRefButton/polityRefButton/
// eventRefButton below are the same shape, one per lookup map + data
// attribute the click-wiring in wireEntityRefButtons listens for.
function refButton(map, id, dataAttr) {
  const label = map.get(id)?.canonical_name || displayTerm(id);
  return map.has(id)
    ? `<button class="entity-link" type="button" data-${dataAttr}="${escapeHtml(id)}">${escapeHtml(label)}</button>`
    : escapeHtml(label);
}

function periodRefButton(periodsById, id) {
  return refButton(periodsById, id, "explore-period-id");
}

function polityRefButton(politiesById, id) {
  return refButton(politiesById, id, "explore-polity-id");
}

function eventRefButton(eventsById, id) {
  return refButton(eventsById, id, "explore-event-id");
}

// A period's detail_of target -- and, in reverse, whatever's listed as a
// period's own "detail of" child -- can be either a period or a polity
// (the reverse is never true: a polity's own detail_of/children stay
// polity-only, see build.py's validate_entity_relationships/
// validate_period_detail_of). Dispatches to whichever of the two ref-button
// helpers actually has the id, since ids are unique across both.
function entityRefButton(ctx, id) {
  if (ctx.periodsById.has(id)) return periodRefButton(ctx.periodsById, id);
  if (ctx.politiesById.has(id)) return polityRefButton(ctx.politiesById, id);
  return eventRefButton(ctx.eventsById, id);
}

function externalLinksForPeriod(period) {
  const links = Object.entries(period.external_ids || {}).map(([source, value]) => {
    const url = String(value).startsWith("http") ? value
      : source === "wikidata" ? `https://www.wikidata.org/wiki/${encodeURIComponent(value)}` : "";
    return url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(displayTerm(source))} ↗</a>` : "";
  }).filter(Boolean);
  links.push(...(period.source_urls || []).map((url, index) =>
    `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Source ${index + 1} ↗</a>`));
  return links;
}

function externalLinksForPolity(polity) {
  const wikidata = polity.external_ids?.wikidata;
  const wikipedia = polity.external_ids?.wikipedia_en
    || (wikidata ? `https://www.wikidata.org/wiki/Special:GoToLinkedPage/enwiki/${encodeURIComponent(wikidata)}` : "");
  const seshat = polity.external_ids?.seshat || [];
  const centroid = polity.geography?.centroid;
  return [
    wikidata ? `<a href="https://www.wikidata.org/wiki/${encodeURIComponent(wikidata)}" target="_blank" rel="noopener noreferrer">Wikidata (${escapeHtml(wikidata)}) ↗</a>` : "",
    wikipedia ? `<a href="${escapeHtml(wikipedia)}" target="_blank" rel="noopener noreferrer">Wikipedia (English) ↗</a>` : "",
    seshat.length ? `<a href="https://www.seshat-db.com/api/core/polities/?search=${encodeURIComponent(polity.canonical_name)}" target="_blank" rel="noopener noreferrer">Seshat (${escapeHtml(seshat.join(", "))}) ↗</a>` : "",
    centroid ? `<a href="https://www.openstreetmap.org/?mlat=${centroid.lat}&mlon=${centroid.lon}#map=5/${centroid.lat}/${centroid.lon}" target="_blank" rel="noopener noreferrer">View location ↗</a>` : "",
    ...(polity.source_urls || []).map((url, index) =>
      `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Source ${index + 1} ↗</a>`),
  ].filter(Boolean);
}

// ROADMAP.md item 6 -- "Display more pictures and information from
// wikipedia on the side panel". Client-side only: resolves a Wikipedia
// article title for a record (direct URL if present, else a live
// Wikidata sitelink lookup by QID -- see resolveWikipediaTitle) and calls
// Wikipedia's public, CORS-enabled REST summary endpoint straight from the
// browser. Cached in memory per title so navigating back and forth in one
// session doesn't refetch; silently renders nothing if no title can be
// resolved or a fetch fails (redirect oddities, offline, 404 -- never
// shown as an error to the user).
const wikiSummaryCache = new Map();
const wikidataTitleCache = new Map();

function extractWikipediaTitle(record) {
  const candidates = [
    ...Object.values(record.external_ids || {}),
    ...(record.source_urls || []),
  ];
  for (const candidate of candidates) {
    const value = Array.isArray(candidate) ? candidate.join(" ") : String(candidate ?? "");
    const match = value.match(/en\.wikipedia\.org\/wiki\/([^\s#?]+)/);
    if (match) return decodeURIComponent(match[1]);
  }
  return null;
}

// Fallback for the common case (most polities): only a bare Wikidata QID
// on file, no direct Wikipedia URL. Wikidata's action API supports CORS
// via origin=* (the standard trick for calling it from an arbitrary
// browser origin, no key needed).
async function resolveWikipediaTitleFromWikidata(qid) {
  if (!qid) return null;
  if (wikidataTitleCache.has(qid)) return wikidataTitleCache.get(qid);
  let title = null;
  try {
    const url = `https://www.wikidata.org/w/api.php?action=wbgetentities&ids=${encodeURIComponent(qid)}&props=sitelinks&sitefilter=enwiki&format=json&origin=*`;
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (response.ok) {
      const data = await response.json();
      title = data?.entities?.[qid]?.sitelinks?.enwiki?.title || null;
    }
  } catch {
    title = null;
  }
  wikidataTitleCache.set(qid, title);
  return title;
}

async function resolveWikipediaTitle(record) {
  return extractWikipediaTitle(record) || resolveWikipediaTitleFromWikidata(record.external_ids?.wikidata);
}

// slots = { subtitle: <p data-wiki-subtitle>, body: <div data-wiki> } --
// both always rendered together from the same API response.
function renderWikipediaSummary(slots, data) {
  if (!slots.body.isConnected) return; // panel moved on to a different record while the fetch was in flight
  const displayImage = data?.thumbnail?.source || data?.originalimage?.source;
  const fullImage = data?.originalimage?.source || displayImage;
  // extract_html (not the plain-text extract) so inline links/formatting
  // survive -- inserted as-is, not escapeHtml'd: it's Wikipedia's own
  // sanitized markup from a trusted API response, not user input.
  const extractHtml = data?.extract_html || (data?.extract ? `<p>${escapeHtml(data.extract)}</p>` : "");
  if (slots.subtitle) slots.subtitle.textContent = data?.description || "";
  if (!data || (!extractHtml && !displayImage)) {
    slots.body.innerHTML = "";
    return;
  }
  slots.body.innerHTML = `
    ${displayImage ? `<a class="wiki-summary-image" href="${escapeHtml(fullImage)}" target="_blank" rel="noopener noreferrer"><img src="${escapeHtml(displayImage)}" alt=""></a>` : ""}
    ${extractHtml}
  `;
}

async function loadWikipediaSummary(record, slots) {
  const title = await resolveWikipediaTitle(record);
  if (!title) {
    slots.body.innerHTML = "";
    if (slots.subtitle) slots.subtitle.textContent = "";
    return;
  }
  if (!slots.body.isConnected) return; // panel moved on while the QID lookup above was in flight
  if (wikiSummaryCache.has(title)) {
    renderWikipediaSummary(slots, wikiSummaryCache.get(title));
    return;
  }
  try {
    const response = await fetch(`https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title)}`, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    wikiSummaryCache.set(title, data);
    renderWikipediaSummary(slots, data);
  } catch {
    wikiSummaryCache.set(title, null);
    slots.body.innerHTML = "";
    if (slots.subtitle) slots.subtitle.textContent = "";
  }
}

function wikiSummarySlots(panel) {
  return { subtitle: panel.querySelector("[data-wiki-subtitle]"), body: panel.querySelector("[data-wiki]") };
}

function renderPeriodDetails(period, ctx) {
  const { periodsById, politiesById, periodLinks } = ctx;
  const countries = (period.geography?.present_countries || []).map((code) => exploreCountryNames.of(code) || code);
  const contained = [...periodsById.values()].filter((candidate) => (candidate.broader_periods || []).includes(period.id));
  const predecessors = [...periodsById.values()].filter((candidate) => (candidate.successors || []).includes(period.id));
  const linked = periodLinks.filter((link) => link.period_id === period.id);
  const externalLinks = externalLinksForPeriod(period);
  // A period's own detail_of children are always other periods -- a polity
  // can never be a detail of a period (see build.py's validate_entity_
  // relationships). Distinct from `contained` above (broader_periods, the
  // structural era-nesting relationship) -- "Details"/"Detail of" label
  // the detail_of relationship specifically, to avoid colliding with the
  // existing "Part of"/"Contains" labels already used for broader_periods.
  const detailChildren = [...periodsById.values()].filter((candidate) => candidate.detail_of === period.id);
  // ROADMAP.md item 0 (8 September 2026): an event bound to this period
  // (edge=start or edge=end) used to only ever show up via its own
  // Events-lane marker on the chart -- clicking the period itself showed
  // nothing, unlike every other detail_of relationship. Same "Details"
  // row as detailChildren above, not a separate one.
  const boundEvents = [...ctx.eventsById.values()].filter((event) => (event.bounds || []).some((bound) => bound.target === period.id));
  const detailRefs = [
    ...detailChildren.map((item) => periodRefButton(periodsById, item.id)),
    ...boundEvents.map((item) => eventRefButton(ctx.eventsById, item.id)),
  ];

  explorePanel.innerHTML = `<button class="detail-close" type="button" aria-label="Close details">×</button>
    <p class="detail-kicker">${escapeHtml(TIER_KICKER[period.tier] || "Period")}</p>
    <h2>${escapeHtml(period.canonical_name)}</h2>
    <p class="wiki-subtitle" data-wiki-subtitle></p>
    <div class="detail-actions"><button class="zoom-explore" type="button">Zoom to this</button><button class="reset-explore" type="button">Full timeline</button></div>
    <div class="wiki-summary" data-wiki></div>
    <p>${escapeHtml(period.notes || "Sourced chronological context; this record is not a polity.")}</p>
    <dl>
      <dt>Dates</dt><dd>${formatYear(period.start)}–${formatYear(period.end)}</dd>
      <dt>Authority</dt><dd>${escapeHtml(period.authority || "unknown")}</dd>
      <dt>Continents</dt><dd>${escapeHtml((period.geography?.continents || []).map(displayTerm).join(", ") || "unknown")}</dd>
      <dt>Present countries</dt><dd>${escapeHtml(countries.join(", ") || "unknown")}</dd>
      ${(period.geography?.historical_regions || []).length ? `<dt>Historical regions</dt><dd>${escapeHtml(period.geography.historical_regions.map(displayTerm).join(", "))}</dd>` : ""}
      ${(period.broader_periods || []).length ? `<dt>Part of</dt><dd>${period.broader_periods.map((id) => periodRefButton(periodsById, id)).join(", ")}</dd>` : ""}
      ${period.detail_of ? `<dt>Detail of</dt><dd>${entityRefButton(ctx, period.detail_of)}</dd>` : ""}
      ${contained.length ? `<dt>Contains</dt><dd>${contained.map((item) => periodRefButton(periodsById, item.id)).join(", ")}</dd>` : ""}
      ${detailRefs.length ? `<dt>Details</dt><dd>${detailRefs.join(", ")}</dd>` : ""}
      ${predecessors.length ? `<dt>Preceded by</dt><dd>${predecessors.map((item) => periodRefButton(periodsById, item.id)).join(", ")}</dd>` : ""}
      ${(period.successors || []).length ? `<dt>Followed by</dt><dd>${period.successors.map((id) => periodRefButton(periodsById, id)).join(", ")}</dd>` : ""}
      ${linked.length ? `<dt>Linked entities</dt><dd class="detail-links">${linked.map((link) => `${polityRefButton(politiesById, link.entity_id)} <small>${escapeHtml(link.evidence)}, ${escapeHtml(link.confidence)}</small>`).join("<br>")}</dd>` : ""}
      ${externalLinks.length ? `<dt>External pages</dt><dd class="detail-links">${externalLinks.join("<br>")}</dd>` : ""}
    </dl>
    ${editControlsHtml("period", period, null, ctx)}`;

  wireExplorePanel(ctx, period.start, period.end, period.detail_of || period.id);
  loadWikipediaSummary(period, wikiSummarySlots(explorePanel));
  wireEditControls("period", period, ctx, (updated) => renderPeriodDetails(updated, ctx));
  wireEntityRefButtons(ctx);
}

// ROADMAP.md item 5 / docs/plans/2026-09-07-events-lane-design.md. An
// event has no detail_of/bounds editor of its own yet (unlike polities/
// periods) -- editing those goes through the raw-fields editor for now,
// same minimal-first-pass scope as event creation itself.
function renderEventDetails(event, ctx) {
  const detailOfTargets = event.detail_of || [];
  const boundsTargets = event.bounds || [];
  const externalLinks = (event.source_urls || []).map((url, index) =>
    `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Source ${index + 1} ↗</a>`);

  explorePanel.innerHTML = `<button class="detail-close" type="button" aria-label="Close details">×</button>
    <p class="detail-kicker">Event</p>
    <h2>${escapeHtml(event.canonical_name)}</h2>
    <p class="wiki-subtitle" data-wiki-subtitle></p>
    <div class="detail-actions"><button class="zoom-explore" type="button">Zoom to this</button><button class="reset-explore" type="button">Full timeline</button></div>
    <div class="wiki-summary" data-wiki></div>
    <p>${escapeHtml(event.notes || "A dated historical event.")}</p>
    <dl>
      <dt>Year</dt><dd>${formatYear(event.year)}</dd>
      <dt>Authority</dt><dd>${escapeHtml(event.authority || "unknown")}</dd>
      ${detailOfTargets.length ? `<dt>Detail of</dt><dd>${detailOfTargets.map((id) => entityRefButton(ctx, id)).join(", ")}</dd>` : ""}
      ${boundsTargets.length ? `<dt>Bounds</dt><dd>${boundsTargets.map((bound) => `${entityRefButton(ctx, bound.target)} (${escapeHtml(bound.edge)})`).join(", ")}</dd>` : ""}
      ${externalLinks.length ? `<dt>External pages</dt><dd class="detail-links">${externalLinks.join("<br>")}</dd>` : ""}
    </dl>`;

  wireExplorePanel(ctx, event.year, event.year, detailOfTargets[0] || event.id);
  loadWikipediaSummary(event, wikiSummarySlots(explorePanel));
  wireEntityRefButtons(ctx);
}

// Population lane (ROADMAP.md item, 10 September 2026): no Wikipedia
// summary call, unlike every other kind here -- a population estimate
// isn't a Wikidata-backed entity with its own article, just a sourced
// figure from population_estimates.js. `formatPopulation`/`formatYear`
// come from explore_timeline.js (loaded first, see explore.html), same
// classic-script global-scope sharing common.js's own docstring already
// explains.
// `entry.segments` is [{continent, population}] -- one segment (continent:
// null) in the hand-curated fallback, six real continents in HYDE mode
// (see explore.js's buildPopulationSeries). Sorted largest-first so the
// breakdown reads like a ranked list, not the fixed stack-draw order
// POPULATION_CONTINENT_ORDER uses (that order is about visual stability
// across years, not about which continent is biggest in any one year).
function renderPopulationDetails(entry, ctx) {
  const total = entry.segments.reduce((sum, segment) => sum + segment.population, 0);
  const breakdown = entry.segments.length > 1
    ? [...entry.segments].sort((a, b) => b.population - a.population)
        .map((segment) => `<dt>${escapeHtml(displayTerm(segment.continent))}</dt><dd>~${escapeHtml(formatPopulation(segment.population))} (${segment.population.toLocaleString()})</dd>`)
        .join("")
    : "";

  explorePanel.innerHTML = `<button class="detail-close" type="button" aria-label="Close details">×</button>
    <p class="detail-kicker">Population estimate</p>
    <h2>${escapeHtml(formatYear(entry.year))}</h2>
    <div class="detail-actions"><button class="zoom-explore" type="button">Zoom to this</button><button class="reset-explore" type="button">Full timeline</button></div>
    <p>Estimated ${breakdown ? "world" : ""} population: <strong>~${escapeHtml(formatPopulation(total))}</strong> people.</p>
    <dl>
      <dt>Year</dt><dd>${escapeHtml(formatYear(entry.year))}</dd>
      <dt>Total</dt><dd>~${escapeHtml(formatPopulation(total))} (${total.toLocaleString()})</dd>
      ${breakdown}
      <dt>Source</dt><dd class="detail-links"><a href="${escapeHtml(entry.source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(entry.source.name)} ↗</a></dd>
    </dl>`;

  wireExplorePanel(ctx, entry.year, entry.year, entry.id);
}

function renderPolityDetails(polity, ctx) {
  const { periodsById, politiesById, periodLinks } = ctx;
  const description = polity.text?.long_en || polity.notes;
  const descriptionText = description || "Draft record; description pending review.";
  const aliases = [polity.names?.aliases_en?.replaceAll(" | ", ", "), polity.names?.fr].filter(Boolean).join("; ");
  const countries = (polity.geography?.present_countries || []).map((code) => exploreCountryNames.of(code) || code);
  const centroid = polity.geography?.centroid;
  const duration = polity.end == null ? null : polity.end - polity.start;
  // A polity's "Contains" (its detail_of children) can now include periods
  // too, not just other polities -- e.g. a short-lived named period that's
  // a detail of this polity. ROADMAP.md item 0 (8 September 2026): an
  // event detail_of this polity belongs here too -- same gap as the
  // period side (see renderPeriodDetails' boundEvents), just via detail_of
  // instead of bounds, since an event's detail_of is polity-only.
  const children = [
    ...[...politiesById.values()].filter((candidate) => candidate.detail_of === polity.id),
    ...[...periodsById.values()].filter((candidate) => candidate.detail_of === polity.id),
    ...[...ctx.eventsById.values()].filter((candidate) => (candidate.detail_of || []).includes(polity.id)),
  ];
  const predecessors = [...politiesById.values()].filter((candidate) => (candidate.successors || []).includes(polity.id));
  const relevantPeriods = periodLinks.filter((link) => link.entity_id === polity.id);
  const relevantTransitions = (ctx.transitions || []).filter((transition) => [...transition.from, ...transition.to].includes(polity.id));
  const externalLinks = externalLinksForPolity(polity);

  explorePanel.innerHTML = `<button class="detail-close" type="button" aria-label="Close details">×</button>
    <h2>${escapeHtml(polity.canonical_name)}</h2>
    <p class="wiki-subtitle" data-wiki-subtitle></p>
    <div class="detail-actions"><button class="zoom-explore" type="button">Zoom to this</button><button class="reset-explore" type="button">Full timeline</button></div>
    <div class="wiki-summary" data-wiki></div>
    <p>${escapeHtml(descriptionText)}</p>
    <dl>
      <dt>Dates</dt><dd>${formatYear(polity.start)}–${polity.end == null ? "present" : formatYear(polity.end)}${duration ? ` (${duration.toLocaleString()} years)` : ""}</dd>
      <dt>Entity type</dt><dd>${escapeHtml(displayTerm(polity.entity_type || "polity"))}</dd>
      ${aliases ? `<dt>Other names</dt><dd>${escapeHtml(aliases)}</dd>` : ""}
      ${polity.detail_of ? `<dt>Part of</dt><dd>${polityRefButton(politiesById, polity.detail_of)}</dd>` : ""}
      ${children.length ? `<dt>Contains</dt><dd>${children.map((item) => entityRefButton(ctx, item.id)).join(", ")}</dd>` : ""}
      ${predecessors.length ? `<dt>Preceded by</dt><dd>${predecessors.map((item) => polityRefButton(politiesById, item.id)).join(", ")}</dd>` : ""}
      ${(polity.successors || []).length ? `<dt>Followed by</dt><dd>${polity.successors.map((id) => polityRefButton(politiesById, id)).join(", ")}</dd>` : ""}
      <dt>Continents</dt><dd>${escapeHtml((polity.geography?.continents || []).map(displayTerm).join(", ") || "unknown")}</dd>
      <dt>Present countries</dt><dd>${escapeHtml(countries.join(", ") || "unknown")}</dd>
      ${centroid ? `<dt>Approx. location</dt><dd>${centroid.lat.toFixed(2)}°, ${centroid.lon.toFixed(2)}°</dd>` : ""}
      <dt>Prominence</dt><dd>${Number(polity.prominence_score || 0).toFixed(2)} / 100</dd>
      <dt>Historical weight</dt><dd>${polity.weight_imputed ? "estimated" : "source-based"}</dd>
      ${(polity.sources || []).length ? `<dt>Data sources</dt><dd>${escapeHtml(polity.sources.map(displayTerm).join(", "))}</dd>` : ""}
      ${relevantTransitions.length ? `<dt>Transitions</dt><dd class="detail-links">${relevantTransitions.map((transition) => {
        const label = `${formatYear(transition.year)}: ${escapeHtml(transition.label)}`;
        return transition.source_urls?.[0] ? `<a href="${escapeHtml(transition.source_urls[0])}" target="_blank" rel="noopener noreferrer">${label} ↗</a>` : label;
      }).join("<br>")}</dd>` : ""}
      ${relevantPeriods.length ? `<dt>Historical periods</dt><dd class="detail-links">${relevantPeriods.map((link) => `${periodRefButton(periodsById, link.period_id)} <small>${escapeHtml(link.evidence)}, ${escapeHtml(link.confidence)}</small>`).join("<br>")}</dd>` : ""}
      ${externalLinks.length ? `<dt>External pages</dt><dd class="detail-links">${externalLinks.join("<br>")}</dd>` : ""}
    </dl>
    ${editControlsHtml("polity", polity, ctx.geographyOptions, ctx)}`;

  wireExplorePanel(ctx, polity.start, polity.end ?? ctx.domainEnd, polity.detail_of || polity.id);
  loadWikipediaSummary(polity, wikiSummarySlots(explorePanel));
  wireEditControls("polity", polity, ctx, (updated) => renderPolityDetails(updated, ctx));
  wireEntityRefButtons(ctx);
}

// Every ref button rendered anywhere in the currently-open panel (periodRefButton/
// polityRefButton/eventRefButton, direct or via entityRefButton) shares this one
// click-wiring pass -- called once per render*Details, regardless of which of
// the three kinds actually appear; a selector with no matches is a no-op.
function wireEntityRefButtons(ctx) {
  explorePanel.querySelectorAll("[data-explore-period-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = ctx.periodsById.get(button.dataset.explorePeriodId);
      if (target) renderPeriodDetails(target, ctx);
    });
  });
  explorePanel.querySelectorAll("[data-explore-polity-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = ctx.politiesById.get(button.dataset.explorePolityId);
      if (target) renderPolityDetails(target, ctx);
    });
  });
  explorePanel.querySelectorAll("[data-explore-event-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = ctx.eventsById.get(button.dataset.exploreEventId);
      if (target) renderEventDetails(target, ctx);
    });
  });
}

function wireExplorePanel(ctx, start, end, expandId) {
  explorePanel.querySelector(".detail-close").addEventListener("click", closeExploreDetails);
  explorePanel.querySelector(".zoom-explore").addEventListener("click", () => {
    closeExploreDetails();
    // expandId auto-opens the enclosing panel for a detail_of entity's
    // container (see explore.js's zoomToRange) so "Zoom to this" on a
    // hidden detail reveals it, not just its neighbourhood.
    ctx.onZoomToRange(start, end, expandId);
  });
  explorePanel.querySelector(".reset-explore").addEventListener("click", () => {
    closeExploreDetails();
    ctx.onResetZoom();
  });
  explorePanel.classList.add("is-open");
  explorePanelBackdrop.classList.add("is-open");
  explorePanel.setAttribute("aria-hidden", "false");
  explorePanel.querySelector(".detail-close").focus();
}

function closeExploreDetails() {
  explorePanel.classList.remove("is-open");
  explorePanelBackdrop.classList.remove("is-open");
  explorePanel.setAttribute("aria-hidden", "true");
}

explorePanelBackdrop.addEventListener("click", closeExploreDetails);
// ROADMAP.md item: ESC closes the side panel when it's open. Ignored while
// a text input/textarea/select inside the panel has focus (e.g. the raw
// JSON editor, a country filter) -- ESC there is a natural "cancel this
// edit" keystroke a browser may already handle, not "close the whole panel".
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!explorePanel.classList.contains("is-open")) return;
  const target = event.target;
  if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT")) return;
  closeExploreDetails();
});

// kind: "chapter" | "era" | "period" -> periodsById; "polity" -> politiesById;
// "event" -> eventsById (ROADMAP.md item 5). Silently no-ops if the id isn't
// found (e.g. data not loaded yet) rather than throwing and breaking the
// click handler for every other band.
function showExploreDetails(kind, id, ctx) {
  if (kind === "polity") {
    const polity = ctx.politiesById.get(id);
    if (polity) renderPolityDetails(polity, ctx);
    return;
  }
  if (kind === "event") {
    const event = ctx.eventsById.get(id);
    if (event) renderEventDetails(event, ctx);
    return;
  }
  if (kind === "population") {
    const point = ctx.populationById.get(id);
    if (point) renderPopulationDetails(point, ctx);
    return;
  }
  const period = ctx.periodsById.get(id);
  if (period) renderPeriodDetails(period, ctx);
}
