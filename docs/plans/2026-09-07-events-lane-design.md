# Events lane -- design

ROADMAP.md item 5: "Add a lane for main events." Brainstormed live, 7 September 2026;
implemented same day. This doc is a record of the agreed design, not a separate planning
artifact -- the user approved "implement" directly from the in-chat design, so there's no
companion implementation-plan document.

## Why a new `Event` model, not a generalized `Transition`

ONTOLOGY.md's architecture table already lists "Events" against the existing `Transition`
model (split/merge/succession). But `Transition` is narrowly scoped: always polity-to-polity,
one `year`, no way to attach to a civilization/culture or to be *the* boundary event of an
era/chapter/period. Stretching it to cover general historical events (a battle, an eruption,
"Bronze Age Collapse") would overload a model that's cleanly "a dated polity handover" today.
`Transition` is untouched by this feature.

## Schema (`schema.py`)

```python
class EventBound(BaseModel):
    target: str                       # a Period id, any tier
    edge: Literal["start", "end"]

class Event(BaseModel):
    id: str
    canonical_name: str
    year: int                         # single year, not a range -- matches Transition's
                                       # own shape; a multi-year event picks its
                                       # conventionally-cited year
    detail_of: list[str] = []         # Polity ids (civilization/culture are entity_type
                                       # values on Polity, not a separate model)
    bounds: list[EventBound] = []     # periods this event starts/ends
    eligibility: Eligibility = Eligibility.review
    external_ids: ExternalIds = ExternalIds()
    authority: str
    notes: str = ""
    source_urls: list[str] = []
```

`detail_of` and `bounds` are both lists and both independent/optional -- the same real
event (e.g. Bronze Age Collapse) can be a detail of several affected civilizations AND the
shared boundary ending one era and starting the next, at once. Neither, either, or both can
be set.

New `events/*.yaml` directory, mirroring `polities/`/`periods/`.

## Visibility policy -- a deliberate exception to existing convention

Every other record type in this dataset publishes regardless of `eligibility`
("publish everything, check later" -- see build.py). Events are the one exception:
`eligibility: review` (the default) is **excluded** from `events.json`, because an event's
whole point is confirming its `detail_of`/`bounds` attachment is actually correct before it
renders anywhere. There's nothing analogous to "an unclassified polity still has a
start/end, still worth seeing" here -- a wrongly-attached event is actively misleading, not
just incomplete.

## Validation (`build.py`)

- `detail_of` targets must resolve to a known, active `Polity`.
- `bounds[].target` targets must resolve to a known `Period` (any tier).
- `year` must fall within a tolerance of the bounded period's own start/end -- same ±25-year
  tolerance `validate_transitions` already applies to polity dates, reused rather than
  inventing a new threshold.

## API (`server/app.py`)

- `POST /api/events` -- creation, same slugify-id/validate-then-write pattern as
  `create_polity`/`create_period`. Defaults to `eligibility: review`.
- `GET /api/events-review` -- lists every `review` event with its resolved attachment
  targets (names + dates) inlined. No scoring/candidate-matching (unlike
  consolidation-review) -- a hand-authored event already has its attachment chosen by
  whoever created it; the queue's only job is confirm-or-reject.
- `POST /api/events-review/{event_id}` -- `{"decision": "accepted" | "excluded"}`.
  Rejected events keep their file (`eligibility: excluded`), same audit-trail convention as
  every other "discarded" mechanism in this app.
- `PATCH /api/events/{event_id}/fields` -- generic raw-field editor, same as
  `update_polity_fields`/`update_period_fields`.
- `DELETE /api/events/{event_id}` -- hard delete, same as `delete_polity`/`delete_period`.
  No blocker scan needed: nothing else in the dataset ever references an event id (events
  only ever point outward via `detail_of`/`bounds`), so deleting one is always safe.

## `/explore` rendering

**Shared Events lane:** one new thin row, placed once (after Period, before
Civilizations), regardless of which Period.tier a given event bounds -- Epoch/Chapter/
Era/Period are all just `Period` at different `tier` values (ONTOLOGY.md), so one lane
naturally covers all of them rather than needing four separate per-tier lanes. Each event
renders as a circle marker at `scale.x(event.year)` plus its title beside it. Overlap
handling reuses the existing `lane_packing.js` (`packIntoLanes`, already used for eras/
periods/polities) with a pixel-space range accessor -- events whose labels would collide
get pushed into a stacked sub-lane with a short connector line back to their marker,
rather than a new packing algorithm.

**Detail-of events:** an event attached via `detail_of` appears in that entity's existing
expandable "details" list (the same recursive `_attach_nested_details`/`details_by_target`
mechanism detail_of polities/periods already use), tagged `kind: "event"` so it renders as
a circle + label instead of a band.

Clicking any event marker (either lane) opens the standard detail panel: name, year, notes,
sources, and which periods/entities it's attached to.

## Sourcing -- hand-authored, not a Wikidata pipeline (for now)

The first Event records are hand-authored (via the `+ New entity` UI, extended with an
"Event" type, or directly as YAML) -- no Wikidata extraction pipeline in this pass. A
pipeline is a legitimate later project once the schema/UI have proven out on a real
starter set; out of scope here. This implementation ships the schema/build/API/UI plumbing
with `events/` empty -- authoring real starter events (Bronze Age Collapse and similar) is
deliberately left to the user/curator through the now-built tooling, not invented
unsupervised by whoever implements this.
