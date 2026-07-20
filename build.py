import json
import sys
from pathlib import Path

import yaml

from schema import Polity

ROOT = Path(__file__).parent
POLITIES_DIR = ROOT / "polities"
OUT_PATH = ROOT / "data.json"


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


def main() -> None:
    polities = load_all()
    OUT_PATH.write_text(
        json.dumps(
            [p.model_dump(mode="json") for p in polities],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"OK  validated and wrote {len(polities)} polities to {OUT_PATH.name}")


if __name__ == "__main__":
    main()
