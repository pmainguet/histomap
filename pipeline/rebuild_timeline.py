"""Recompute cached prominence and rebuild timeline JSON without network access."""

from __future__ import annotations

import build

from pipeline.compute_prominence import compute


def main() -> None:
    counts = compute(offline=True)
    print(f"Scored {counts['scored']} records")
    build.main()


if __name__ == "__main__":
    main()
