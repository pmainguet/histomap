"""Apply saved Seshat review decisions without rerunning candidate reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from pipeline.reconcile import DECISIONS_PATH, REVIEW_PATH, load_review_decisions, normalize_name

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
SEPARATE_DRAFTS_PATH = ROOT / "reports" / "seshat_separate_entity_drafts.yaml"


def apply_review_decisions(
    review_path: Path = REVIEW_PATH,
    decisions_path: Path = DECISIONS_PATH,
    polities_dir: Path = POLITIES_DIR,
    separate_drafts_path: Path = SEPARATE_DRAFTS_PATH,
) -> dict[str, int]:
    records = {
        record["seshat_id"]: record
        for line in review_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
        for record in [json.loads(line)]
    }
    decisions = load_review_decisions(decisions_path)
    accepted = 0
    rejected = 0
    unchanged = 0
    separate_drafts = []

    for seshat_id, decision in decisions.items():
        record = records.get(seshat_id)
        if record is None:
            raise ValueError(f"review decision references unknown Seshat record {seshat_id}")
        if decision["decision"] == "reject":
            separate_drafts.append(
                {
                    "id": f"seshat_{normalize_name(record['seshat_name']).replace(' ', '_')}_{seshat_id.lower()}",
                    "canonical_name": record["seshat_name"],
                    "external_ids": {"seshat": [seshat_id]},
                    "start": int(record["start_year"]),
                    "end": int(record["end_year"]),
                    "eligibility": "review",
                    "notes": "Kept as a separate entity during Seshat reconciliation; requires canonical review.",
                    "sources": ["seshat"],
                }
            )
            rejected += 1
            continue
        if decision["decision"] != "accept":
            continue

        polity_id = decision.get("polity_id")
        path = polities_dir / f"{polity_id}.yaml"
        if not path.exists():
            raise ValueError(f"review decision references unknown Histomap entity {polity_id}")
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        external_ids = document.setdefault("external_ids", {})
        existing = external_ids.get("seshat", [])
        if isinstance(existing, str):
            existing = [existing]
        updated_ids = sorted(set(existing) | {seshat_id})
        updated_sources = sorted(set(document.get("sources", [])) | {"seshat"})
        if updated_ids == existing and updated_sources == document.get("sources", []):
            unchanged += 1
            continue
        external_ids["seshat"] = updated_ids
        document["sources"] = updated_sources
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        accepted += 1

    separate_drafts_path.parent.mkdir(parents=True, exist_ok=True)
    separate_drafts_path.write_text(
        yaml.safe_dump_all(separate_drafts, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return {"accepted": accepted, "rejected": rejected, "unchanged": unchanged}


def main() -> None:
    counts = apply_review_decisions()
    print(
        "Review decisions applied: "
        + ", ".join(f"{key}={value}" for key, value in counts.items())
    )


if __name__ == "__main__":
    main()
