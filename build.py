import json
import sys
from pathlib import Path

import yaml

from schema import Polity, Transition

ROOT = Path(__file__).parent
POLITIES_DIR = ROOT / "polities"
OUT_PATH = ROOT / "data.json"
TRANSITIONS_PATH = ROOT / "transitions.yaml"
TRANSITIONS_OUT_PATH = ROOT / "transitions.json"


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


def load_all() -> list[Polity]:
    polities: list[Polity] = []
    seen_ids: set[str] = set()
    errors: list[str] = []
    for path in sorted(POLITIES_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
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
    known_ids = {polity.id for polity in polities}
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


def main() -> None:
    polities = load_all()
    transitions = load_transitions(polities)
    OUT_PATH.write_text(
        json.dumps(
            [p.model_dump(mode="json") for p in polities],
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
    print(f"OK  validated and wrote {len(polities)} polities and {len(transitions)} transitions")


if __name__ == "__main__":
    main()
