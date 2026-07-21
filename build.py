import json
import sys
from pathlib import Path

import yaml

from schema import Period, PeriodLink, Polity, Transition

ROOT = Path(__file__).parent
POLITIES_DIR = ROOT / "polities"
OUT_PATH = ROOT / "data.json"
TRANSITIONS_PATH = ROOT / "transitions.yaml"
TRANSITIONS_OUT_PATH = ROOT / "transitions.json"
PERIODS_DIR = ROOT / "periods"
PERIODS_OUT_PATH = ROOT / "periods.json"
PERIOD_LINKS_PATH = ROOT / "period_links.yaml"
PERIOD_LINKS_OUT_PATH = ROOT / "period_links.json"


def find_parent_cycles(polities: list[Polity]) -> list[list[str]]:
    parents = {polity.id: polity.parent for polity in polities}
    cycles: set[tuple[str, ...]] = set()
    for start in parents:
        path: list[str] = []
        positions: dict[str, int] = {}
        current: str | None = start
        while current in parents and current is not None:
            if current in positions:
                cycle = path[positions[current] :]
                rotations = [tuple(cycle[index:] + cycle[:index]) for index in range(len(cycle))]
                cycles.add(min(rotations))
                break
            positions[current] = len(path)
            path.append(current)
            current = parents[current]
    return [list(cycle) for cycle in sorted(cycles)]


def validate_entity_relationships(polities: list[Polity]) -> list[str]:
    known = {polity.id: polity for polity in polities}
    errors: list[str] = []
    for entity in polities:
        if entity.parent:
            target = known.get(entity.parent)
            if target is None:
                errors.append(f"{entity.id}: unknown parent {entity.parent}")
            elif not (
                target.entity_type.value == "polity"
                and entity.entity_type.value in {"polity", "subdivision"}
            ):
                errors.append(f"{entity.id}: parent requires polity or subdivision → polity")
        elif (
            entity.entity_type.value == "subdivision"
            and entity.subdivision_parent_status == "confirmed"
        ):
            errors.append(f"{entity.id}: confirmed subdivision requires a parent polity")
        for successor_id in entity.successors:
            target = known.get(successor_id)
            if target is None:
                errors.append(f"{entity.id}: unknown successor {successor_id}")
            elif entity.entity_type.value != "polity" or target.entity_type.value != "polity":
                errors.append(f"{entity.id}: political successor requires polity → polity")
        seen: set[tuple[str, str]] = set()
        for relationship in entity.relationships:
            key = (relationship.kind, relationship.target)
            if key in seen:
                errors.append(f"{entity.id}: duplicate {relationship.kind} relationship to {relationship.target}")
                continue
            seen.add(key)
            target = known.get(relationship.target)
            if target is None:
                errors.append(f"{entity.id}: relationship references unknown entity {relationship.target}")
                continue
            source_type = entity.entity_type.value
            target_type = target.entity_type.value
            if relationship.kind.startswith("political_") and (source_type != "polity" or target_type != "polity"):
                errors.append(f"{entity.id}: {relationship.kind} requires polity → polity")
            elif relationship.kind == "administrative_part_of" and (
                source_type != "subdivision" or target_type != "polity"
            ):
                errors.append(f"{entity.id}: administrative_part_of requires subdivision → polity")
            elif relationship.kind == "associated_people" and target_type not in {"people", "tribe"}:
                errors.append(f"{entity.id}: associated_people target must be people or tribe")
            elif relationship.kind == "part_of_civilization" and target_type != "civilization":
                errors.append(f"{entity.id}: part_of_civilization target must be civilization")
            elif relationship.kind == "archaeological_sequence" and (
                source_type not in {"culture", "archaeological_horizon"}
                or target_type not in {"culture", "archaeological_horizon"}
            ):
                errors.append(f"{entity.id}: archaeological_sequence requires culture/horizon endpoints")
            elif relationship.kind == "cultural_sequence" and source_type == "polity" and target_type == "polity":
                errors.append(f"{entity.id}: polity succession must use political_successor")
    return errors


def load_all() -> list[Polity]:
    polities: list[Polity] = []
    seen_ids: set[str] = set()
    errors: list[str] = []
    for path in sorted(POLITIES_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if data.get("timeline_role") == "period":
                continue
            polity = Polity.model_validate(data)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if polity.id in seen_ids:
            errors.append(f"{path.name}: duplicate id {polity.id!r}")
            continue
        seen_ids.add(polity.id)
        polities.append(polity)
    for cycle in find_parent_cycles(polities):
        errors.append(f"parent relationship cycle: {' -> '.join(cycle + [cycle[0]])}")
    errors.extend(validate_entity_relationships(polities))
    if errors:
        for e in errors:
            print(f"ERROR  {e}", file=sys.stderr)
        sys.exit(1)
    return polities


def load_transitions(polities: list[Polity]) -> list[Transition]:
    if not TRANSITIONS_PATH.exists():
        return []
    transitions = [
        Transition.model_validate(item)
        for item in (yaml.safe_load(TRANSITIONS_PATH.read_text(encoding="utf-8")) or [])
    ]
    validate_transitions(transitions, polities)
    return transitions


def validate_transitions(transitions: list[Transition], polities: list[Polity]) -> None:
    known = {polity.id: polity for polity in polities}
    known_ids = set(known)
    transition_ids = [transition.id for transition in transitions]
    if len(transition_ids) != len(set(transition_ids)):
        raise ValueError("transition IDs must be unique")
    unknown = sorted(
        {
            item
            for transition in transitions
            for item in transition.from_ids + transition.to_ids
            if item not in known_ids
        }
    )
    if unknown:
        raise ValueError(f"transitions reference unknown polity IDs: {', '.join(unknown)}")
    non_polities = sorted(
        {
            item
            for transition in transitions
            for item in transition.from_ids + transition.to_ids
            if known[item].entity_type.value != "polity"
        }
    )
    if non_polities:
        raise ValueError(
            "political transitions require polity endpoints: " + ", ".join(non_polities)
        )
    for transition in transitions:
        for source_id in transition.from_ids:
            source = known[source_id]
            if transition.year < source.start or (
                source.end is not None and transition.year > source.end + 25
            ):
                raise ValueError(f"transition {transition.id} falls outside source {source_id} dates")
        for target_id in transition.to_ids:
            target = known[target_id]
            if transition.year < target.start - 25 or (
                target.end is not None and transition.year > target.end
            ):
                raise ValueError(f"transition {transition.id} falls outside target {target_id} dates")


def load_periods() -> list[Period]:
    periods = [
        Period.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(PERIODS_DIR.glob("*.yaml"))
    ] if PERIODS_DIR.exists() else []
    ids = [period.id for period in periods]
    if len(ids) != len(set(ids)):
        raise ValueError("period IDs must be unique")
    known = set(ids)
    for period in periods:
        unknown = (set(period.broader_periods) | set(period.successors)) - known
        if unknown:
            raise ValueError(f"period {period.id} references unknown periods: {', '.join(sorted(unknown))}")
    return periods


def load_period_links(periods: list[Period], polities: list[Polity]) -> list[PeriodLink]:
    if not PERIOD_LINKS_PATH.exists():
        return []
    links = [
        PeriodLink.model_validate(item)
        for item in (yaml.safe_load(PERIOD_LINKS_PATH.read_text(encoding="utf-8")) or [])
    ]
    period_ids = {period.id for period in periods}
    polity_ids = {polity.id for polity in polities}
    for link in links:
        if link.period_id not in period_ids:
            raise ValueError(f"period link references unknown period {link.period_id}")
        if link.entity_id not in polity_ids:
            raise ValueError(f"period link references unknown entity {link.entity_id}")
    return links


def main() -> None:
    polities = load_all()
    transitions = load_transitions(polities)
    periods = load_periods()
    period_links = load_period_links(periods, polities)
    published_polities = [
        polity
        for polity in polities
        if not (
            polity.entity_type.value == "subdivision"
            and polity.subdivision_parent_status == "pending"
        )
    ]
    OUT_PATH.write_text(
        json.dumps(
            [p.model_dump(mode="json") for p in published_polities],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    TRANSITIONS_OUT_PATH.write_text(
        json.dumps(
            [item.model_dump(mode="json", by_alias=True) for item in transitions],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    PERIODS_OUT_PATH.write_text(
        json.dumps([item.model_dump(mode="json") for item in periods], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    PERIOD_LINKS_OUT_PATH.write_text(
        json.dumps([item.model_dump(mode="json") for item in period_links], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        f"OK  validated {len(polities)} and wrote {len(published_polities)} entities, "
        f"{len(transitions)} transitions, "
        f"{len(periods)} periods, and {len(period_links)} period links"
    )


if __name__ == "__main__":
    main()
