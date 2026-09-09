"""Shared YAML load/write helpers for one-shot pipeline/ scripts that operate
on a directory of canonical records (polities/, periods/, events/) via raw
dicts rather than validated Pydantic models -- build.py's own load_all()
covers the validated case; this module is for scripts that intentionally
skip validation (see each caller's own docstring for why)."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_yaml_dir(directory: Path) -> list[dict]:
    return [load_yaml(path) for path in sorted(directory.glob("*.yaml"))]


def write_yaml(path: Path, document: dict) -> None:
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
