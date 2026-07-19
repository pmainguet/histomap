import json
import sys
from pathlib import Path

import yaml

from schema import Polity

ROOT = Path(__file__).parent
POLITIES_DIR = ROOT / "polities"
OUT_PATH = ROOT / "data.json"


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
